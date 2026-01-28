FROM python:3.11-slim

# Install system dependencies for AxiDraw (USB access)
RUN apt-get update && apt-get install -y \
    libusb-1.0-0 \
    udev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Create data directory
RUN mkdir -p /data/uploads

# Non-root user for security (while maintaining USB access)
RUN groupadd -r axidraw && useradd -r -g axidraw axidraw
RUN chown -R axidraw:axidraw /app /data

ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data

EXPOSE 8080

USER axidraw

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
