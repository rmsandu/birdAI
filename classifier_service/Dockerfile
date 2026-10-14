# CPU-only inference image for the BirdAI classifier service.
# Training happens outside Docker; this image only serves a trained checkpoint.

FROM python:3.11-slim AS builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
# CPU-only torch/torchvision wheels: a few hundred MB instead of several GB
# for CUDA builds, which matters a lot for a demo-scale serving image.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch torchvision \
    && pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY serving/ classifier_service/serving/
COPY training/ classifier_service/training/
COPY __init__.py classifier_service/__init__.py
# Bake in the checkpoint so `docker run` works with zero extra setup, the
# priority for a shareable demo image. For local iteration, mount a fresher
# checkpoint over this path instead: -v $(pwd)/checkpoints:/app/checkpoints
COPY checkpoints/best.pt classifier_service/checkpoints/best.pt

ENV CLASSIFIER_CHECKPOINT_PATH=/app/classifier_service/checkpoints/best.pt
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "classifier_service.serving.app:app", "--host", "0.0.0.0", "--port", "8000"]
