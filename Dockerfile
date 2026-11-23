FROM python:3.14-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/src/

# Runtime data (SQLite DB, uploads) is NOT baked into the image: it contains user
# accounts and private media. docker-compose mounts ./data at /app/data instead.
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8080

CMD ["uvicorn", "birdai.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
