FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/src/
COPY data/ /app/data/

EXPOSE 8080

CMD ["uvicorn", "birdai.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
