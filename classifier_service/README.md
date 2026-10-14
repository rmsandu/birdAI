# BirdAI classifier service

A locally fine-tuned fine-grained bird species classifier (CUB-200-2011),
served as a standalone FastAPI/Docker microservice. This is a second,
independent signal alongside the main app's Gemini-based analysis — see
[`../docs/plans/phase1-classifier-service.md`](../docs/plans/phase1-classifier-service.md)
for the full design.

## Setup

This service has heavy dependencies (torch, torchvision, timm) kept out of
the main app's `requirements.txt`. Use a separate virtual environment:

```bash
python -m venv classifier_service/.venv
source classifier_service/.venv/bin/activate
# CPU-only install (skip if you have a CUDA GPU and want the CUDA build instead):
pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision
pip install -r classifier_service/requirements.txt
```

## 1. Prepare the dataset

```bash
python classifier_service/scripts/download_cub200.py
python classifier_service/scripts/prepare_dataset.py
```

This downloads CUB-200-2011 (~1.1GB) to `classifier_service/data/CUB_200_2011/`
and writes `manifest.csv` + `label_map.json` in that directory.

## 2. Train

```bash
# Smoke test first (a few minutes, confirms the pipeline runs end to end):
python -m classifier_service.training.train \
    --manifest classifier_service/data/CUB_200_2011/manifest.csv --quick

# Full run (longer; ~15 epochs by default):
python -m classifier_service.training.train \
    --manifest classifier_service/data/CUB_200_2011/manifest.csv
```

Checkpoints land in `classifier_service/checkpoints/` (`best.pt`, `last.pt`).

```bash
python -m classifier_service.training.evaluate \
    --checkpoint classifier_service/checkpoints/best.pt \
    --manifest classifier_service/data/CUB_200_2011/manifest.csv
```

Backbone is ConvNeXt-Tiny by default (`--backbone convnext_tiny`); swap in
`vit_base_patch16_224` for a ViT comparison.

## 3. Serve

```bash
uvicorn classifier_service.serving.app:app --reload
curl -X POST http://localhost:8000/predict -F "file=@some_bird.jpg"
curl http://localhost:8000/health
```

Or with Docker (from the repo root):

```bash
docker compose up --build
```

## 4. Granularity diagnostic (optional, offline)

Implements the RankM measure from ["Measuring Dataset Granularity"](https://arxiv.org/html/1912.10154v1)
(Cui et al., 2019) to characterize which species are hardest to distinguish:

```bash
python -m classifier_service.granularity.compute_granularity \
    --manifest classifier_service/data/CUB_200_2011/manifest.csv \
    --checkpoint classifier_service/checkpoints/best.pt \
    --report-dir classifier_service/reports/
```

Writes `granularity_report.json` (dataset + per-class scores, bitter/sweet
species lists) and `granularity_plot.png`.

## Configuration

The main app talks to this service over HTTP. See `.env.example` at the repo
root for `CLASSIFIER_SERVICE_URL`, `CLASSIFIER_TOP_K`, `CLASSIFIER_ENABLED`.
