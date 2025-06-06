import os
import tempfile
from typing import List, Tuple

import streamlit as st

from video_cutter.utils import cut_segments, join_segments

st.title("Video Cutter")

uploaded_file = st.file_uploader("Choose a video or audio file", type=["mp4", "mov", "mkv", "mp3", "wav"])

if uploaded_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as input_tmp:
        input_tmp.write(uploaded_file.read())
        input_path = input_tmp.name

    segments: List[Tuple[float, float]] = []
    st.write("Enter segments as start and end times in seconds")
    count = st.number_input("Number of segments", min_value=1, step=1, value=1)
    for i in range(int(count)):
        start = st.number_input(f"Segment {i+1} start", min_value=0.0, step=0.1)
        end = st.number_input(f"Segment {i+1} end", min_value=0.0, step=0.1)
        segments.append((start, end))

    output = st.text_input("Output filename", "output.mp4")

    if st.button("Cut and Join"):
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                seg_files = cut_segments(input_path, segments, tmpdir)
                output_path = os.path.join(tmpdir, output)
                join_segments(seg_files, output_path)
                with open(output_path, "rb") as f:
                    st.download_button("Download", f, file_name=output)
        except Exception as exc:
            st.error(str(exc))
