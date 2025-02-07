 # Dockerfile
FROM python:3.9-slim

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Flask app
COPY src/web_bootanimation.py .

# Expose port 5000 (Flask's default)
EXPOSE 5000

CMD ["python", "web_bootanimation.py"]
