import os
import subprocess
from typing import List, Tuple


def run_ffmpeg(args: List[str]) -> None:
    """Run ffmpeg command and raise RuntimeError on failure."""
    result = subprocess.run(
        ["ffmpeg", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout)


def cut_segments(input_file: str, segments: List[Tuple[float, float]], temp_dir: str) -> List[str]:
    """Cut segments from input_file and return list of paths to segment files."""
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file {input_file} not found")

    os.makedirs(temp_dir, exist_ok=True)
    segment_files = []
    for idx, (start, end) in enumerate(segments):
        if start >= end:
            raise ValueError(f"Segment {idx} start >= end")
        output = os.path.join(temp_dir, f"segment_{idx}.mp4")
        args = [
            "-y",
            "-ss",
            str(start),
            "-to",
            str(end),
            "-i",
            input_file,
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            output,
        ]
        run_ffmpeg(args)
        segment_files.append(output)
    return segment_files


def join_segments(segment_files: List[str], output_file: str) -> None:
    """Join segments using ffmpeg concat demuxer."""
    concat_list = os.path.join(os.path.dirname(output_file), "concat.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for path in segment_files:
            f.write(f"file '{path}'\n")

    args = [
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_list,
        "-c",
        "copy",
        output_file,
    ]
    run_ffmpeg(args)

