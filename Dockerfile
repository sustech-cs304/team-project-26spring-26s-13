FROM python:3.10-slim

LABEL maintainer="Team 26s-13"

WORKDIR /app

# Install system dependencies for PyMuPDF
RUN apt-get update && \
    apt-get -y -q --no-install-recommends install gcc g++ libgl1 libglib2.0-0t64 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ backend/
COPY alembic/ alembic/
COPY alembic.ini alembic.ini

# Create data directories
RUN mkdir -p /app/data/workspace /app/data/chromadb /app/data/uploads

# Configure environment
ENV PYTHONUNBUFFERED=1
ENV PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
