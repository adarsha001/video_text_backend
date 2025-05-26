FROM python:3.10-slim

# Install system build tools and curl (required for building wheels and downloading rustup)
RUN apt-get update && apt-get install -y build-essential curl

# Install Rust (required by maturin and some Python packages like pywinpty)
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Copy your requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

# Copy the rest of your application code
COPY . .

# Default command
CMD ["python", "your_app.py"]
