# Video Cutter

This repo contains a small library and interface for cutting pieces of a video or audio file and joining them together without re‑encoding. `ffmpeg` is used under the hood.

## Library Usage

```
from video_cutter.utils import cut_segments, join_segments

segments = [(0, 5), (10, 15)]
seg_files = cut_segments('input.mp4', segments, 'tmp')
join_segments(seg_files, 'output.mp4')
```

## CLI

```
python -m video_cutter.cli input.mp4 output.mp4 0-5 10-15
```

## Web Interface

Run the Streamlit app:

```
streamlit run app.py
```

Upload a file, choose segments, and download the result.
