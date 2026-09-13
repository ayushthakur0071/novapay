FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source tree
COPY . .

EXPOSE 5000 8080 80

# Run with Gunicorn WSGI server binding dynamically to cloud-assigned PORT (defaults to 5000)
CMD ["sh", "-c", "gunicorn 'run:app' --bind 0.0.0.0:${PORT:-5000} --workers 2 --threads 4 --timeout 60"]
