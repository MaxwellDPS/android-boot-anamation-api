#!/usr/bin/env python3

import os
import zipfile
import shutil
import uuid
import tempfile
import ffmpeg  # <-- Using ffmpeg-python
from flask import (
    Flask,
    request,
    send_file,
    render_template_string,
    jsonify,
    redirect,
    url_for
)
from pathlib import Path

app = Flask(__name__)

# ---------------------------------------------------------------------------
# 1) Utility function to create bootanimation.zip
#    (Now uses ffmpeg-python for frame extraction)
# ---------------------------------------------------------------------------
def create_bootanimation_zip(
    video_path,
    output_zip,
    width,
    height,
    fps,
    extract_folder,
    part_name="part0",
    loop_count=0,
    pause=0,
):
    """
    Converts an MP4 video to an Android bootanimation.zip:
      1. Extract frames using ffmpeg-python
      2. Create desc.txt
      3. Zip everything up
    """
    # Clean up the extract folder if it exists
    if os.path.exists(extract_folder):
        shutil.rmtree(extract_folder)
    os.makedirs(extract_folder)

    part_folder = os.path.join(extract_folder, part_name)
    os.makedirs(part_folder)

    # 1) Extract frames using ffmpeg-python
    #    Equivalent to: ffmpeg -i video_path -vf scale=width:height -r fps part_folder/frame_%04d.png
    (
        ffmpeg
        .input(video_path)
        .filter('scale', width, height)
        .filter('fps', fps=fps)
        .output(os.path.join(part_folder, 'frame_%04d.png'))
        .run()  # run ffmpeg
    )

    # 2) Create desc.txt
    desc_file_path = os.path.join(extract_folder, "desc.txt")
    with open(desc_file_path, "w") as desc_file:
        desc_file.write(f"{width} {height} {fps}\n")
        desc_file.write(f"p {loop_count} {pause} {part_name}\n")

    # 3) Create the ZIP file
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        # Add desc.txt
        rel_desc_path = os.path.relpath(desc_file_path, extract_folder)
        zipf.write(desc_file_path, rel_desc_path)
        # Add frames
        for root, dirs, files in os.walk(part_folder):
            for f in sorted(files):
                file_path = os.path.join(root, f)
                rel_path = os.path.relpath(file_path, extract_folder)
                zipf.write(file_path, rel_path)

    return output_zip

# ---------------------------------------------------------------------------
# 2) Web UI (HTML) – simple inline template
# ---------------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Boot Animation Creator</title>
    <style>
        body { font-family: sans-serif; max-width: 600px; margin: 30px auto; }
        label { display: inline-block; width: 120px; }
        input[type="number"] { width: 80px; }
    </style>
</head>
<body>
    <h1>Android Boot Animation Creator</h1>
    <form method="POST" action="{{ url_for('convert_form') }}" enctype="multipart/form-data">
        <div>
            <label>Video (MP4):</label>
            <input type="file" name="video" accept=".mp4" required />
        </div>
        <div>
            <label>Width:</label>
            <input type="number" name="width" value="1080" required />
        </div>
        <div>
            <label>Height:</label>
            <input type="number" name="height" value="1920" required />
        </div>
        <div>
            <label>FPS:</label>
            <input type="number" name="fps" value="30" required />
        </div>
        <div>
            <label>Loop Count:</label>
            <input type="number" name="loop_count" value="0" required />
            <small>(0 = infinite)</small>
        </div>
        <div>
            <label>Pause:</label>
            <input type="number" name="pause" value="0" required />
            <small>(Frames to pause after part)</small>
        </div>
        <div>
            <label>Part Name:</label>
            <input type="text" name="part_name" value="part0" required />
        </div>
        <br />
        <button type="submit">Create Boot Animation</button>
    </form>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# 3) Routes
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    """Serve a simple HTML form for uploading the MP4 and parameters."""
    return render_template_string(HTML_TEMPLATE)

@app.route("/convert_form", methods=["POST"])
def convert_form():
    """
    Handle the form submission from the Web UI.
    Creates the bootanimation.zip and then serves it for download.
    """
    video_file = request.files.get("video")
    if not video_file:
        return "No video provided", 400

    width = int(request.form.get("width"))
    height = int(request.form.get("height"))
    fps = int(request.form.get("fps"))
    loop_count = int(request.form.get("loop_count"))
    pause = int(request.form.get("pause"))
    part_name = request.form.get("part_name", "part0")

    # Create a temp folder for storing input/output
    session_id = str(uuid.uuid4())
    temp_dir = Path(tempfile.gettempdir()) / f"bootanim_{session_id}"
    os.makedirs(temp_dir, exist_ok=True)

    # Save the uploaded MP4
    input_video_path = temp_dir / "input.mp4"
    video_file.save(str(input_video_path))

    # Create the bootanimation.zip
    output_zip_path = temp_dir / "bootanimation.zip"
    extract_folder = temp_dir / "frames"
    create_bootanimation_zip(
        video_path=str(input_video_path),
        output_zip=str(output_zip_path),
        width=width,
        height=height,
        fps=fps,
        extract_folder=str(extract_folder),
        part_name=part_name,
        loop_count=loop_count,
        pause=pause
    )

    # Return the file as an attachment (download)
    return send_file(
        str(output_zip_path),
        as_attachment=True,
        download_name="bootanimation.zip"
    )

@app.route("/api/convert", methods=["POST"])
def api_convert():
    """
    JSON API endpoint for programmatic access.
    Expects JSON with:
      {
        "video_path": "<path or URL>" (optional if you upload as form-data),
        "width": ...,
        "height": ...,
        "fps": ...,
        "loop_count": ...,
        "pause": ...,
        "part_name": ...
      }
    Or you can upload a file as multipart form data under "video".
    """
    if "video" in request.files:
        # File is uploaded directly
        video_file = request.files["video"]
        if video_file.filename == "":
            return jsonify({"error": "No video file provided"}), 400
        
        session_id = str(uuid.uuid4())
        temp_dir = Path(tempfile.gettempdir()) / f"bootanim_{session_id}"
        os.makedirs(temp_dir, exist_ok=True)

        input_video_path = temp_dir / "input.mp4"
        video_file.save(str(input_video_path))
        
        width = int(request.form.get("width", 1080))
        height = int(request.form.get("height", 1920))
        fps = int(request.form.get("fps", 30))
        loop_count = int(request.form.get("loop_count", 0))
        pause = int(request.form.get("pause", 0))
        part_name = request.form.get("part_name", "part0")
    else:
        # Parse JSON from body
        data = request.get_json(force=True)
        if not data or "video_path" not in data:
            return jsonify({"error": "Must provide video_path or upload a file"}), 400
        
        video_path = data["video_path"]
        session_id = str(uuid.uuid4())
        temp_dir = Path(tempfile.gettempdir()) / f"bootanim_{session_id}"
        os.makedirs(temp_dir, exist_ok=True)
        
        input_video_path = Path(video_path)
        width = int(data.get("width", 1080))
        height = int(data.get("height", 1920))
        fps = int(data.get("fps", 30))
        loop_count = int(data.get("loop_count", 0))
        pause = int(data.get("pause", 0))
        part_name = data.get("part_name", "part0")

    # Create the bootanimation.zip
    output_zip_path = temp_dir / "bootanimation.zip"
    extract_folder = temp_dir / "frames"
    try:
        create_bootanimation_zip(
            video_path=str(input_video_path),
            output_zip=str(output_zip_path),
            width=width,
            height=height,
            fps=fps,
            extract_folder=str(extract_folder),
            part_name=part_name,
            loop_count=loop_count,
            pause=pause
        )
    except ffmpeg.Error as e:
        return jsonify({"error": f"ffmpeg-python failed: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Serve the file via /api/download/<session_id>
    download_url = url_for("api_download", session_id=session_id, _external=True)
    return jsonify({"download_url": download_url})

@app.route("/api/download/<session_id>", methods=["GET"])
def api_download(session_id):
    """
    Serve the resulting bootanimation.zip for a given session_id.
    In production, you'd typically want authentication or signed URLs.
    """
    temp_dir = Path(tempfile.gettempdir()) / f"bootanim_{session_id}"
    output_zip_path = temp_dir / "bootanimation.zip"

    if not output_zip_path.exists():
        return jsonify({"error": "File not found"}), 404

    return send_file(
        str(output_zip_path),
        as_attachment=True,
        download_name="bootanimation.zip"
    )

# ---------------------------------------------------------------------------
# 4) Run the Flask app
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # By default, runs on http://127.0.0.1:5000
    app.run(debug=True)
