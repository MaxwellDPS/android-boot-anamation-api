FROM python:3.9-slim

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Create working directory
WORKDIR /app

# Copy requirements and install
COPY ./src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your Flask app
COPY ./src/web_bootanimation.py .

# Expose port 5000
EXPOSE 5000

# Use gunicorn to run the Flask app
# We'll reference the app object in web_bootanimation.py: "web_bootanimation:app"
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "web_bootanimation:app"]
