#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Segment:
    start: Optional[float]  # seconds, None means start of file
    end: Optional[float]    # seconds, None means end of file

    def duration(self, total: float) -> Optional[float]:
        s = 0.0 if self.start is None else self.start
        e = total if self.end is None else self.end
        if e <= s:
            return None
        return e - s


TIME_RE = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})(?:\.(\d+))?\s*$|^\s*(\d+)(?:\.(\d+))?\s*$")


def parse_time(t: str) -> float:
    """
    Parse time strings like:
      - SS
      - MM:SS
      - HH:MM:SS
      - with optional fractional seconds like 01:02:03.500 or 95.25
    Returns seconds as float.
    """
    m = TIME_RE.match(t)
    if not m:
        raise ValueError(f"Invalid time format: '{t}'")

    if m.group(5) is not None:
        # Plain seconds (with optional fraction)
        sec = float(m.group(5))
        if m.group(6):
            sec += float(f"0.{m.group(6)}")
        return sec

    hours = int(m.group(1) or 0)
    minutes = int(m.group(2))
    seconds = int(m.group(3))
    frac = float(f"0.{m.group(4)}") if m.group(4) else 0.0
    return hours * 3600 + minutes * 60 + seconds + frac


def parse_ranges_file(path: str) -> List[Segment]:
    segments: List[Segment] = []
    with open(path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            # Accept forms like: "- 00:15:40", "00:32:00 - 01:10:00", "1:12:00 -"
            if "-" not in raw:
                raise ValueError(f"Line {idx}: Expected a '-' between start and end: '{raw}'")
            left, right = raw.split("-", 1)
            left = left.strip()
            right = right.strip()

            start = None if left == "" else parse_time(left)
            end = None if right == "" else parse_time(right)
            segments.append(Segment(start=start, end=end))
    if not segments:
        raise ValueError("No segments parsed from ranges file")
    return segments


def which_or_exit(cmd: str):
    path = shutil.which(cmd)
    if not path:
        print(f"Error: '{cmd}' not found. Please install ffmpeg first.", file=sys.stderr)
        sys.exit(2)
    return path


def probe_duration(input_path: str) -> float:
    which_or_exit("ffprobe")
    # Use ffprobe to get duration in seconds
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        input_path,
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed: {e.output.decode('utf-8', 'ignore')}")

    s = out.decode("utf-8", "ignore").strip()
    try:
        return float(s)
    except ValueError as e:
        raise RuntimeError(f"Unable to parse duration from ffprobe output: '{s}'")


def fmt_time(seconds: float) -> str:
    # HH:MM:SS.mmm (ffmpeg-friendly)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    if secs.is_integer():
        return f"{hours:02d}:{minutes:02d}:{int(secs):02d}"
    else:
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def cut_segment(input_path: str, seg: Segment, total: float, out_path: str, accurate: bool = False) -> None:
    which_or_exit("ffmpeg")
    start = 0.0 if seg.start is None else seg.start
    end = total if seg.end is None else seg.end
    if end <= start:
        raise ValueError(f"Invalid segment: end ({end}) <= start ({start})")
    duration = end - start

    # Fast path: stream copy (keyframe-accurate). Accurate path re-encodes video.
    if not accurate:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            fmt_time(start),
            "-i",
            input_path,
            "-t",
            fmt_time(duration),
            # map only video and audio; copy both for speed and quality
            "-map",
            "0:v?",
            "-map",
            "0:a?",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            out_path,
        ]
    else:
        # Accurate trimming using re-encode for video, copy audio
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            input_path,
            "-ss",
            fmt_time(start),
            "-t",
            fmt_time(duration),
            # map only video and audio to keep concat-friendly streams
            "-map",
            "0:v?",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "copy",
            out_path,
        ]

    subprocess.run(cmd, check=True)


def concat_segments(files: List[str], out_path: str) -> None:
    which_or_exit("ffmpeg")
    # Prepare concat list file
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tf:
        list_path = tf.name
        for f in files:
            tf.write(f"file '{os.path.abspath(f)}'\n")

    try:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_path,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            out_path,
        ]
        subprocess.run(cmd, check=True)
    finally:
        try:
            os.remove(list_path)
        except OSError:
            pass


def ensure_outdir(path: str):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Cut and glue parts of a video quickly using ffmpeg (stream copy).")
    p.add_argument("-i", "--input", required=True, help="Input video file (e.g. input.mp4)")
    p.add_argument("-r", "--ranges", required=True, help="Path to ranges.txt describing segments to keep")
    p.add_argument("-o", "--output", default="output.mp4", help="Output video path (default: output.mp4)")
    p.add_argument("--accurate", action="store_true", help="Enable frame-accurate cuts (re-encode video; slower)")
    p.add_argument("--keep-temp", action="store_true", help="Keep temporary segment files")
    p.add_argument("--force", action="store_true", help="Overwrite output if it exists")
    args = p.parse_args(argv)

    if not os.path.isfile(args.ranges):
        print(f"Ranges file not found: {args.ranges}", file=sys.stderr)
        return 2
    if not os.path.isfile(args.input):
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 2
    if os.path.exists(args.output) and not args.force:
        print(f"Output exists: {args.output}. Use --force to overwrite.", file=sys.stderr)
        return 2

    # Check tools
    which_or_exit("ffmpeg")
    which_or_exit("ffprobe")

    # Parse and validate segments
    try:
        segments = parse_ranges_file(args.ranges)
    except Exception as e:
        print(f"Failed to parse ranges: {e}", file=sys.stderr)
        return 2

    try:
        total = probe_duration(args.input)
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 2

    # Validate and normalize segments
    norm_segments: List[Segment] = []
    for s in segments:
        start = 0.0 if s.start is None else s.start
        end = total if s.end is None else s.end
        if start < 0 or end < 0:
            print("Negative times are not allowed", file=sys.stderr)
            return 2
        if start >= total:
            print(f"Segment start {start:.3f}s beyond duration {total:.3f}s", file=sys.stderr)
            return 2
        if end > total:
            end = total
        if end <= start:
            print(f"Skipping empty/invalid segment: start={start:.3f}s end={end:.3f}s", file=sys.stderr)
            continue
        norm_segments.append(Segment(start=start, end=end))

    if not norm_segments:
        print("No valid segments after validation", file=sys.stderr)
        return 2

    # Create temp dir for segments
    tmpdir = tempfile.mkdtemp(prefix="videocut_")
    seg_files: List[str] = []
    try:
        # Cut each segment
        for idx, seg in enumerate(norm_segments, start=1):
            seg_path = os.path.join(tmpdir, f"segment_{idx:03d}.mp4")
            try:
                cut_segment(args.input, seg, total, seg_path, accurate=args.accurate)
            except subprocess.CalledProcessError as e:
                print(f"ffmpeg failed cutting segment {idx}: {e}", file=sys.stderr)
                return 2
            seg_files.append(seg_path)

        # Concat
        ensure_outdir(args.output)
        if os.path.exists(args.output) and args.force:
            os.remove(args.output)
        concat_segments(seg_files, args.output)

        print(f"Done. Wrote: {args.output}")
        return 0
    finally:
        if not args.keep_temp:
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
