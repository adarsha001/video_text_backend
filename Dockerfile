# Use Python 3.10 base image for compatibility
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install OS dependencies (adjust as needed)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

# Copy application code
COPY . .

# Expose port (adjust based on your app)
EXPOSE 5000

# Set entrypoint (adjust based on how your Flask app is run)
CMD ["python", "app.py"]
