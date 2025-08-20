VideoCutApp — ultra-fast local video cutter/gluer

Overview
- Adds an MP4 file, takes a list of time ranges, cuts those parts, and glues them together.
- Uses ffmpeg stream copy for near-instant processing (no re-encode). Optional accurate mode re-encodes video.

Web UI (MVP)
- Minimal Flask app with HTML form to upload a video, paste ranges, choose fast/accurate, and download the result.
- Run locally:
  - `pip install -r requirements.txt`
  - `python3 app.py`
  - Open `http://127.0.0.1:5000`

macOS launcher (no terminal for users)
- A double-clickable script `Start VideoCutApp.command` starts the server and opens the browser.
- First launch steps:
  - Ensure Python 3 and ffmpeg are installed (developer should prepare the machine; otherwise Homebrew: `brew install python ffmpeg`).
  - Make it executable once: `chmod +x Start VideoCutApp.command`.
  - Double-click it in Finder. Leave the Terminal window open while using the app; close it to stop the server.

Requirements
- macOS/Linux/Windows with `ffmpeg` and `ffprobe` available on PATH.
  - On macOS: `brew install ffmpeg`

Install / Run
- No install needed. Run the script directly:
  - `python3 videocut.py -i input.mp4 -r ranges.txt -o output.mp4 --force`

Testing
- Requires `pytest`, `ffmpeg`, and `ffprobe` on PATH.
- Run all tests:
  - `pytest -q`

Ranges file format
- Plain text; one range per line.
- Use a dash to separate start and end; leave empty for start-of-file or end-of-file.
- Examples:
  - `- 00:15:40`        (from start to 00:15:40)
  - `00:32:00 - 01:10:00`
  - `1:12:00 -`         (from 1:12:00 to end)
- Accepted time formats: `SS`, `MM:SS`, `HH:MM:SS` (optionally with decimals, e.g., `01:02:03.500`).

Fast vs accurate cuts
- Default (fast): copies both video and audio (`-map 0:v? -map 0:a? -c:v copy -c:a copy`) with `-ss`+`-t` for keyframe-accurate, lossless speed.
- Accurate: add `--accurate` to re-encode video for frame-accurate cuts (slower), while audio stays copied (`-c:a copy`).

Examples
- Keep beginning to 15:40, keep 32:00–1:10:00, keep 1:12:00 to end:

```
cat > ranges.txt <<'EOF'
- 00:15:40
00:32:00 - 01:10:00
1:12:00 -
EOF

python3 videocut.py -i input.mp4 -r ranges.txt -o output.mp4 --force
```

Notes
- All segments are cut from the same input and concatenated using ffmpeg’s concat demuxer.
- The output preserves original codecs and quality.
- Add `--accurate` if you need exact frame boundaries (slower).

Roadmap (for future iPhone/mac app)
- Wrap this core ffmpeg flow in a minimal SwiftUI/macOS app.
- Export/import ranges, show timeline UI, and call the same CLI under-the-hood.
- Consider `ffmpeg` static builds bundled or Homebrew detection.
