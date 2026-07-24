FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Ensure only ONE process runs (prevents 409 Conflict on Render web services).
# Render sets WEB_CONCURRENCY=8 by default; we override it here.
ENV WEB_CONCURRENCY=1

# Start the bot
CMD ["python", "main.py"]
