FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy package files
COPY pyproject.toml README.md ./
COPY recall ./recall
COPY examples ./examples

# Install the package with server dependencies
RUN pip install --no-cache-dir -e .[server]

# Create data directory
RUN mkdir -p /app/data

# Expose FastAPI port
EXPOSE 8000

# Run the server
CMD ["uvicorn", "recall.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
