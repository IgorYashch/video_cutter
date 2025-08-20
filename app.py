#!/usr/bin/env python3
import os
import shutil
import sys
import tempfile
import uuid
import webbrowser
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

from flask import Flask, render_template, request, send_file, flash, session


APP_NAME = "VideoCutApp"


def resource_path(*relative: str) -> Path:
    """Resolve a resource path whether running from source or a frozen bundle.

    When packaged with PyInstaller, resources are unpacked under sys._MEIPASS.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*relative)


def user_data_dir() -> Path:
    """Return a writable per-user data directory suitable for temp/work files."""
    # Prefer standard macOS location; fall back to tempdir elsewhere
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(tempfile.gettempdir()) / APP_NAME


BASE_DIR = Path(__file__).resolve().parent
WORK_DIR = user_data_dir() / "web_tmp"
WORK_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder=str(resource_path("templates")))
app.config.update(
    # No explicit file size limit to avoid blocking large uploads in MVP
    SECRET_KEY=os.environ.get("VIDEO_CUT_APP_SECRET", "dev-secret"),
)


def clean_dir(path: Path):
    try:
        shutil.rmtree(path)
    except Exception:
        pass


@app.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        ranges="",
        accurate=False,
        out_name="output.mp4",
        last_file_name=session.get("last_input_name"),
    )


@app.route("/process", methods=["POST"])
def process():
    file = request.files.get("video")

    # Accept ranges from hidden 'ranges' textarea or from multiple start[]/end[] inputs
    ranges_text = (request.form.get("ranges", "") or "").strip()
    if not ranges_text:
        starts = request.form.getlist("start[]")
        ends = request.form.getlist("end[]")
        pairs = []
        for s, e in zip(starts, ends):
            s = (s or "").strip()
            e = (e or "").strip()
            if s == "" and e == "":
                continue
            # Build line as per CLI format: "<start> - <end>" with empties allowed
            left = s
            right = e
            pairs.append(f"{left} - {right}")
        ranges_text = "\n".join(pairs).strip()

    accurate = request.form.get("accurate") == "on"
    out_name = request.form.get("out_name", "output.mp4").strip() or "output.mp4"

    if not ranges_text:
        flash("Please provide at least one time range.")
        return render_template("index.html", ranges=ranges_text, accurate=accurate, out_name=out_name, last_file_name=session.get("last_input_name")), 400

    # Workspace for this job
    job_dir = WORK_DIR / f"job_{uuid.uuid4().hex}"
    job_dir.mkdir(parents=True, exist_ok=True)
    input_path: Path
    ranges_path = job_dir / "ranges.txt"
    output_path = job_dir / out_name

    try:
        if file and file.filename:
            # Save new upload and remember for reuse
            input_path = job_dir / (Path(file.filename).name or "input.mp4")
            file.save(str(input_path))
            session["last_input_path"] = str(input_path)
            session["last_input_name"] = Path(file.filename).name
        else:
            # Reuse last uploaded file to avoid unnecessary re-uploads
            last = session.get("last_input_path")
            if not last or not os.path.exists(last):
                flash("Please choose a video file (no previous upload found).")
                return render_template("index.html", ranges=ranges_text, accurate=accurate, out_name=out_name, last_file_name=session.get("last_input_name")), 400
            input_path = Path(last)

        ranges_path.write_text(ranges_text + ("\n" if not ranges_text.endswith("\n") else ""), encoding="utf-8")

        # Invoke the core logic in-process for bundle compatibility
        import videocut  # local module

        args = [
            "-i",
            str(input_path),
            "-r",
            str(ranges_path),
            "-o",
            str(output_path),
            "--force",
        ]
        if accurate:
            args.append("--accurate")

        out_buf, err_buf = StringIO(), StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = videocut.main(args)

        if rc != 0 or not output_path.exists():
            stderr_text = err_buf.getvalue().strip()
            app.logger.error("videocut failed: %s", stderr_text)
            flash("Processing failed. Please check your time ranges and try again.")
            if stderr_text:
                flash(stderr_text)
            clean_dir(job_dir)
            return render_template("index.html", ranges=ranges_text, accurate=accurate, out_name=out_name, last_file_name=session.get("last_input_name")), 400

        return send_file(
            str(output_path),
            as_attachment=True,
            download_name=out_name,
            mimetype="video/mp4",
        )
    finally:
        # Best-effort cleanup of large inputs; keep only when send_file holds a handle
        pass


def main():
    # Auto-open browser when running as a frozen app (i.e., .app)
    if getattr(sys, "frozen", False):
        try:
            webbrowser.open_new("http://127.0.0.1:5000")
        except Exception:
            pass
    # Bind to localhost only for safety
    app.run(host="127.0.0.1", port=5000, debug=False)


 


if __name__ == "__main__":
    main()
