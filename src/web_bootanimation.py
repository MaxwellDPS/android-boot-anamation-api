#!/usr/bin/env python3

import os
import zipfile
import shutil
import uuid
import tempfile
import ffmpeg
from flask import (
    Flask,
    request,
    send_file,
    render_template_string,
    jsonify,
    url_for
)
from pathlib import Path

app = Flask(__name__)

def get_video_dimensions(video_path):
    """
    Returns (width, height) of the first video stream in `video_path`
    using ffmpeg.probe(). Raises an exception if no valid video stream
    is found or if probe fails.
    """
    try:
        probe_data = ffmpeg.probe(video_path)
        streams = probe_data.get("streams", [])
        # Find first video stream
        for s in streams:
            if s.get("codec_type") == "video":
                return s["width"], s["height"]
    except ffmpeg.Error as e:
        raise RuntimeError(f"Failed to probe video: {e}")

    raise RuntimeError("No valid video stream found in file.")

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
    Converts an MP4 video to an Android bootanimation.zip using ffmpeg-python:
      1. Extract frames
      2. Create desc.txt
      3. Zip everything
    """
    # Clean up existing
    if os.path.exists(extract_folder):
        shutil.rmtree(extract_folder)
    os.makedirs(extract_folder)

    part_folder = os.path.join(extract_folder, part_name)
    os.makedirs(part_folder)

    # Extract frames
    (
        ffmpeg
        .input(video_path)
        .filter('scale', width, height)  # scale to requested size
        .filter('fps', fps=fps)
        .output(os.path.join(part_folder, 'frame_%04d.png'))
        .run()
    )

    # Create desc.txt
    desc_file_path = os.path.join(extract_folder, "desc.txt")
    with open(desc_file_path, "w") as desc_file:
        desc_file.write(f"{width} {height} {fps}\n")
        desc_file.write(f"p {loop_count} {pause} {part_name}\n")

    # Zip it
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(desc_file_path, os.path.relpath(desc_file_path, extract_folder))
        for root, dirs, files in os.walk(part_folder):
            for f in sorted(files):
                file_path = os.path.join(root, f)
                zipf.write(file_path, os.path.relpath(file_path, extract_folder))

    return output_zip

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
            <input type="number" name="width" value="0" required />
            <small>(Set 0 to auto-detect)</small>
        </div>
        <div>
            <label>Height:</label>
            <input type="number" name="height" value="0" required />
            <small>(Set 0 to auto-detect)</small>
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

@app.route("/", methods=["GET"])
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route("/convert_form", methods=["POST"])
def convert_form():
    # 1) Retrieve file and form data
    video_file = request.files.get("video")
    if not video_file:
        return "No video provided", 400

    width = int(request.form.get("width", 0))
    height = int(request.form.get("height", 0))
    fps = int(request.form.get("fps", 30))
    loop_count = int(request.form.get("loop_count", 0))
    pause = int(request.form.get("pause", 0))
    part_name = request.form.get("part_name", "part0")

    # 2) Save the uploaded video to a temp location
    session_id = str(uuid.uuid4())
    temp_dir = Path(tempfile.gettempdir()) / f"bootanim_{session_id}"
    os.makedirs(temp_dir, exist_ok=True)

    input_video_path = temp_dir / "input.mp4"
    video_file.save(str(input_video_path))

    # 3) Auto-detect width/height if set to 0
    if width == 0 or height == 0:
        try:
            detected_w, detected_h = get_video_dimensions(str(input_video_path))
            if width == 0:
                width = detected_w
            if height == 0:
                height = detected_h
        except Exception as e:
            return f"Error auto-detecting dimensions: {e}", 500

    # 4) Create bootanimation.zip
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
        return f"ffmpeg-python error: {e}", 500
    except Exception as e:
        return f"Error creating boot animation: {e}", 500

    # 5) Return final ZIP
    return send_file(
        str(output_zip_path),
        as_attachment=True,
        download_name="bootanimation.zip"
    )

@app.route("/api/convert", methods=["POST"])
def api_convert():
    # 1) Distinguish between file upload vs JSON
    if "video" in request.files:
        video_file = request.files["video"]
        if video_file.filename == "":
            return jsonify({"error": "No video file provided"}), 400
        
        session_id = str(uuid.uuid4())
        temp_dir = Path(tempfile.gettempdir()) / f"bootanim_{session_id}"
        os.makedirs(temp_dir, exist_ok=True)

        input_video_path = temp_dir / "input.mp4"
        video_file.save(str(input_video_path))
        
        width = int(request.form.get("width", 0))
        height = int(request.form.get("height", 0))
        fps = int(request.form.get("fps", 30))
        loop_count = int(request.form.get("loop_count", 0))
        pause = int(request.form.get("pause", 0))
        part_name = request.form.get("part_name", "part0")
    else:
        # Parse JSON
        data = request.get_json(force=True)
        if not data or "video_path" not in data:
            return jsonify({"error": "Must provide video_path or upload a file"}), 400
        
        video_path = data["video_path"]
        session_id = str(uuid.uuid4())
        temp_dir = Path(tempfile.gettempdir()) / f"bootanim_{session_id}"
        os.makedirs(temp_dir, exist_ok=True)
        
        input_video_path = Path(video_path)
        width = int(data.get("width", 0))
        height = int(data.get("height", 0))
        fps = int(data.get("fps", 30))
        loop_count = int(data.get("loop_count", 0))
        pause = int(data.get("pause", 0))
        part_name = data.get("part_name", "part0")

    # 2) Auto-detect dimensions if 0
    if width == 0 or height == 0:
        try:
            detected_w, detected_h = get_video_dimensions(str(input_video_path))
            if width == 0:
                width = detected_w
            if height == 0:
                height = detected_h
        except Exception as e:
            return jsonify({"error": f"Dimension detection failed: {e}"}), 500

    # 3) Create the bootanimation.zip
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
        return jsonify({"error": f"ffmpeg-python error: {e}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # 4) Provide the file URL for download
    download_url = url_for("api_download", session_id=session_id, _external=True)
    return jsonify({"download_url": download_url})

@app.route("/api/download/<session_id>", methods=["GET"])
def api_download(session_id):
    temp_dir = Path(tempfile.gettempdir()) / f"bootanim_{session_id}"
    output_zip_path = temp_dir / "bootanimation.zip"
    if not output_zip_path.exists():
        return jsonify({"error": "File not found"}), 404

    return send_file(
        str(output_zip_path),
        as_attachment=True,
        download_name="bootanimation.zip"
    )

# Remove or comment out app.run() because we’ll run with gunicorn (or keep for local debug):
# if __name__ == "__main__":
#     app.run(debug=True)
