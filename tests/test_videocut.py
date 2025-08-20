import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "videocut.py"


def has_tool(name: str) -> bool:
    return shutil.which(name) is not None


def ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(path),
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    return float(out.decode("utf-8").strip())


def ffprobe_streams(path: Path):
    # Return list of dicts with codec_type and codec_name
    import json
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    data = json.loads(out.decode("utf-8"))
    return [
        {"codec_type": s.get("codec_type"), "codec_name": s.get("codec_name")}
        for s in data.get("streams", [])
    ]


@pytest.fixture(scope="session")
def ffmpeg_available():
    if not (has_tool("ffmpeg") and has_tool("ffprobe")):
        pytest.skip("ffmpeg/ffprobe not available on PATH")
    return True


@pytest.fixture()
def sample_video(tmp_path: Path, ffmpeg_available):
    # Generate a ~20s test video with audio using lavfi sources
    path = tmp_path / "input.mp4"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=256x144:rate=30",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=1000:sample_rate=48000",
        "-t",
        "20",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-g",
        "30",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(path),
    ]
    subprocess.run(cmd, check=True)
    assert path.exists()
    return path


def run_cli(args, env=None, cwd=None):
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, env=env, cwd=cwd, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def write_ranges(path: Path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_fast_mode_basic(tmp_path: Path, sample_video):
    ranges = tmp_path / "ranges.txt"
    write_ranges(
        ranges,
        [
            "- 00:00:05",
            "00:00:07 - 00:00:12",
            "00:00:15 -",
        ],
    )
    out = tmp_path / "out.mp4"
    code, out_s, err_s = run_cli(["-i", str(sample_video), "-r", str(ranges), "-o", str(out), "--force"])
    assert code == 0, f"stderr: {err_s}"
    assert out.exists()
    # Ensure both video and audio are present
    streams = ffprobe_streams(out)
    v = [s for s in streams if s["codec_type"] == "video"]
    a = [s for s in streams if s["codec_type"] == "audio"]
    assert len(v) == 1 and len(a) == 1
    total = ffprobe_duration(out)
    # Expected ~ (5 + 5 + 5) = 15s, allow some slack for stream copy keyframe rounding
    assert 12.0 <= total <= 18.0


def test_accurate_mode_duration(tmp_path: Path, sample_video):
    ranges = tmp_path / "ranges.txt"
    write_ranges(ranges, ["00:00:02 - 00:00:05", "00:00:10 - 00:00:12.500"])  # 3s + 2.5s = 5.5s
    out = tmp_path / "out_acc.mp4"
    code, out_s, err_s = run_cli(["-i", str(sample_video), "-r", str(ranges), "-o", str(out), "--accurate", "--force"])
    assert code == 0, f"stderr: {err_s}"
    # Ensure both streams exist; audio should be copied
    streams = ffprobe_streams(out)
    v = [s for s in streams if s["codec_type"] == "video"]
    a = [s for s in streams if s["codec_type"] == "audio"]
    assert len(v) == 1 and len(a) == 1
    d = ffprobe_duration(out)
    assert abs(d - 5.5) < 0.35  # small tolerance for container rounding


def test_invalid_time_format(tmp_path: Path, sample_video):
    ranges = tmp_path / "ranges.txt"
    write_ranges(ranges, ["bogus - 00:00:05"])  # invalid
    out = tmp_path / "o.mp4"
    code, _, err_s = run_cli(["-i", str(sample_video), "-r", str(ranges), "-o", str(out), "--force"])
    assert code == 2
    assert "Failed to parse ranges" in err_s or "Invalid time format" in err_s


def test_end_before_start_all_invalid(tmp_path: Path, sample_video):
    ranges = tmp_path / "ranges.txt"
    write_ranges(ranges, ["00:00:10 - 00:00:05"])  # invalid only
    out = tmp_path / "o.mp4"
    code, _, err_s = run_cli(["-i", str(sample_video), "-r", str(ranges), "-o", str(out), "--force"])
    assert code == 2
    assert "No valid segments" in err_s or "Skipping empty/invalid segment" in err_s


def test_trim_beyond_duration(tmp_path: Path, sample_video):
    # Request a segment that extends beyond input; should be trimmed to end
    ranges = tmp_path / "ranges.txt"
    write_ranges(ranges, ["00:00:18 - 00:00:25"])  # input is 20s
    out = tmp_path / "out.mp4"
    code, _, err_s = run_cli(["-i", str(sample_video), "-r", str(ranges), "-o", str(out), "--force"])
    assert code == 0, err_s
    d = ffprobe_duration(out)
    # Expect ~2s (18->20)
    assert 1.6 <= d <= 2.4


def test_output_exists_without_force(tmp_path: Path, sample_video):
    ranges = tmp_path / "ranges.txt"
    write_ranges(ranges, ["- 00:00:01"])  # any small
    out = tmp_path / "out.mp4"
    out.write_bytes(b"x")
    code, _, err_s = run_cli(["-i", str(sample_video), "-r", str(ranges), "-o", str(out)])
    assert code == 2
    assert "Output exists" in err_s


def test_missing_files(tmp_path: Path):
    ranges = tmp_path / "ranges.txt"
    write_ranges(ranges, ["- 00:00:01"])  # any
    out = tmp_path / "out.mp4"
    # Missing input
    code, _, err_s = run_cli(["-i", str(tmp_path / "nope.mp4"), "-r", str(ranges), "-o", str(out)])
    assert code == 2 and "Input not found" in err_s
    # Missing ranges
    code, _, err_s = run_cli(["-i", str(out), "-r", str(tmp_path / "no.txt"), "-o", str(out)])
    assert code == 2 and "Ranges file not found" in err_s


def test_missing_ffmpeg_path_isolated(tmp_path: Path, sample_video):
    # Simulate no ffmpeg by clearing PATH
    ranges = tmp_path / "ranges.txt"
    write_ranges(ranges, ["- 00:00:01"])
    out = tmp_path / "out.mp4"
    env = os.environ.copy()
    env["PATH"] = ""  # hide ffmpeg/ffprobe
    code, _, err_s = run_cli(["-i", str(sample_video), "-r", str(ranges), "-o", str(out), "--force"], env=env)
    assert code == 2
    assert "Please install ffmpeg" in err_s


def test_full_video_segment(tmp_path: Path, sample_video):
    # Using empty start and end to keep full file in one segment
    ranges = tmp_path / "ranges.txt"
    write_ranges(ranges, [" - "])  # start empty, end empty
    out = tmp_path / "out.mp4"
    code, _, err_s = run_cli(["-i", str(sample_video), "-r", str(ranges), "-o", str(out), "--force"])
    assert code == 0, err_s
    d_in = ffprobe_duration(sample_video)
    d_out = ffprobe_duration(out)
    assert abs(d_in - d_out) < 0.5


def test_decimal_times(tmp_path: Path, sample_video):
    ranges = tmp_path / "ranges.txt"
    write_ranges(ranges, ["2.25 - 3.75"])  # 1.5s
    out = tmp_path / "out.mp4"
    code, _, err_s = run_cli(["-i", str(sample_video), "-r", str(ranges), "-o", str(out), "--accurate", "--force"])
    assert code == 0, err_s
    d = ffprobe_duration(out)
    assert abs(d - 1.5) < 0.3
