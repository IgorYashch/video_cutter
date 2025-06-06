import argparse
import tempfile
from typing import List, Tuple

from .utils import cut_segments, join_segments


def parse_segments(segment_strs: List[str]) -> List[Tuple[float, float]]:
    segments: List[Tuple[float, float]] = []
    for item in segment_strs:
        parts = item.split('-')
        if len(parts) != 2:
            raise ValueError(f"Invalid segment '{item}'. Use start-end")
        start, end = map(float, parts)
        segments.append((start, end))
    return segments


def main() -> None:
    parser = argparse.ArgumentParser(description="Cut and join video segments without re-encoding")
    parser.add_argument("input", help="Input video file")
    parser.add_argument("output", help="Output file")
    parser.add_argument(
        "segments",
        nargs='+',
        help="Segments to cut in format start-end (seconds)",
    )
    args = parser.parse_args()

    segments = parse_segments(args.segments)
    with tempfile.TemporaryDirectory() as tmp:
        seg_files = cut_segments(args.input, segments, tmp)
        join_segments(seg_files, args.output)


if __name__ == "__main__":
    main()
