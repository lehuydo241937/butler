FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Set default environment variables (can be overridden in docker-compose or .env)
ENV REDIS_HOST=redis
ENV QDRANT_HOST=qdrant
ENV API_PORT=8000

EXPOSE 8000

# Default command runs the API
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
