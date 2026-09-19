# BirdAI Phase 1: Fine-tuned Species Classifier + FastAPI/Docker Service + Granularity Diagnostic

## Context

BirdAI ([app.py](../../app.py), [src/birdai](../../src/birdai)) is currently a Gradio app that orchestrates calls to Gemini (for species ID), eBird (for recent-sighting evidence), and geocoding — it has no CV/ML of its own. The owner wants to (a) learn PyTorch fine-tuning, FastAPI, Docker, and agent-orchestration hands-on, and (b) turn BirdAI into something with a real technical hook worth a GitHub-stars push and a blog post, rather than "a wrapper around the Gemini API."

This phase adds a locally fine-tuned, fine-grained bird-species classifier as a second, independent signal alongside the existing Gemini analysis — served as its own FastAPI/Docker microservice so it's a genuine standalone deliverable (and a template for later phases: BirdNET audio confidence, SmolVLM fine-tuning, Birdfy camera-stream ingestion, none of which are designed here but the architecture should not block them). It also includes a small offline diagnostic, implementing the RankM granularity measure from ["Measuring Dataset Granularity"](https://arxiv.org/html/1912.10154v1) (Cui et al., 2019) over the CUB-200-2011 dataset, to characterize which species are hardest to tell apart and cross-check that against the classifier's actual per-class accuracy — a nice, low-effort research angle for the writeup. This diagnostic is explicitly scoped small and kept out of the app's/service's critical path.

## Goals recap
- Learn: PyTorch fine-tuning, FastAPI, Docker, agent-orchestration patterns.
- Ship: a genuinely useful second signal in the existing Gradio app (classifier confidence alongside Gemini), demo-worthy for a GitHub-stars/blog push.
- Side quest: a small, standalone "dataset granularity" diagnostic (RankM-style) over CUB-200, kept out of the critical path.
- Do not block later phases (BirdNET audio, SmolVLM fine-tuning, Birdfy ingestion) — keep interfaces generic (`*_client.py` + HTTP service pattern) so those phases can add sibling services later.

---

## 1. Directory / module layout

Recommendation: **new top-level `classifier_service/` directory**, separate from `src/birdai/`. Rationale:
- Different deploy lifecycle: training + Docker image build + (optionally) GPU host, versus the Gradio app which is a single lightweight process today with no Dockerfile at all.
- Different dependency footprint: torch/torchvision/timm are heavy; keeping them out of `requirements.txt` (the Gradio app's deps) avoids bloating the app's install and keeps `src/birdai/` free of ML training deps. The main app only needs `httpx` to talk to the service.
- Mirrors the eventual shape of phase 2/3 (BirdNET, SmolVLM) — each is plausibly its own service with its own Dockerfile, so establishing `*_service/` as the convention now avoids a rename later. A `services/` parent directory is an alternative if the user wants to group them, but a flat top-level `classifier_service/` is fine for phase 1 and easy to rename into `services/classifier/` later without churn to `src/birdai/`.
- The **client-side glue** (`classifier_client.py`, schema fields, perception.py enrichment step, Gradio wiring) stays inside `src/birdai/`, following the existing `ebird_client.py`/`gemini_client.py` convention exactly — this is the only piece of the new work that touches the existing app's request path.

Proposed tree:
```
classifier_service/
  README.md                      # how to train, run, and hit the API; troubleshooting
  requirements.txt                # torch, torchvision or timm, fastapi, uvicorn, pillow, pydantic
  Dockerfile
  .dockerignore
  data/
    .gitkeep                      # CUB_200_2011/ downloaded here, gitignored
  scripts/
    download_cub200.py            # fetches + extracts CUB-200-2011, writes train/val/test split manifest
    prepare_dataset.py            # builds a torchvision-style ImageFolder or a CSV manifest + Dataset class
  training/
    dataset.py                    # CUB200Dataset (torch Dataset), transforms, label map (id <-> species name)
    model.py                      # build_model(num_classes) using timm/torchvision backbone + classifier head
    train.py                      # CLI entrypoint: training loop, checkpointing, logging (argparse or simple config)
    evaluate.py                   # top-1/top-3 accuracy, confusion on val/test split, saves metrics.json
    config.py                     # dataclass/dict of hyperparams (epochs, lr, batch size, backbone name)
  checkpoints/
    .gitkeep                      # trained .pt files land here, gitignored (large binaries)
  serving/
    app.py                        # FastAPI app: POST /predict, GET /health, GET /labels
    inference.py                  # loads checkpoint once at startup, preprocess + forward + topk
    schemas.py                    # PredictionResponse / SpeciesPrediction pydantic models (service-local, independent of birdai.schemas)
  tests/
    test_inference.py             # unit test with a tiny stub checkpoint / mocked model forward
    test_api.py                   # FastAPI TestClient hitting /predict with a fixture image
  granularity/
    compute_granularity.py        # standalone diagnostic script (see section 6)
    README.md                     # what it does, how to run it, how to read the report
  reports/
    .gitkeep                      # granularity_report.json / .png land here (gitignored or committed selectively)
```

Root-level changes:
- `requirements.txt` (existing, app-level): add `httpx` (already present), no torch needed here — the app only calls the service over HTTP.
- `.env.example` / `.env`: add `CLASSIFIER_SERVICE_URL`.
- `src/birdai/config.py`: add classifier config constants.
- `src/birdai/classifier_client.py`: new file.
- `src/birdai/schemas.py`, `src/birdai/perception.py`, `app.py`: modified as described below.
- `.gitignore`: add `classifier_service/data/`, `classifier_service/checkpoints/*.pt` (or the whole `checkpoints/` dir), `classifier_service/reports/`.
- Top-level `docker-compose.yml` (optional but recommended for demo-friendliness): one service `classifier`, exposing port e.g. 8000, so `docker compose up` boots the classifier next to `python app.py`. Greenfield — no existing compose file to conflict with.

---

## 2. Dataset download / prep (CUB-200-2011)

`classifier_service/scripts/download_cub200.py`:
- Downloads `CUB_200_2011.tgz` from Caltech's official mirror (the classic Caltech Vision URL redirects; document the current working URL in the script's docstring since these links rot — fall back to instructing the user to download manually if the request fails, with a clear error message).
- Extracts into `classifier_service/data/CUB_200_2011/` (contains `images/`, `images.txt`, `train_test_split.txt`, `classes.txt`, `image_class_labels.txt`, `bounding_boxes.txt`).
- Verify integrity: check expected file/dir count or a checksum if available; fail loudly with a clear message rather than silently proceeding on a partial download.
- CLI flags: `--data-dir` (default `classifier_service/data`), `--skip-if-exists`.

`classifier_service/scripts/prepare_dataset.py`:
- Reads `images.txt`, `image_class_labels.txt`, `train_test_split.txt`, `classes.txt`.
- CUB-200-2011 ships one official train/test split (`is_training_image` flag) but no val split — carve a stratified val split out of the training portion (e.g. 85/15 by class) with a fixed seed so training is reproducible.
- Emits a `manifest.csv` (columns: `image_path`, `class_id`, `class_name`, `split`) plus a `label_map.json` (int id -> canonical species common name, since CUB class names are like `001.Black_footed_Albatross` and need cleanup to display nicely in the UI). `label_map.json` is the same artifact the FastAPI service loads at inference time to turn predicted indices back into species names — this is the file that couples `training/` and `serving/`.
- Idempotent: re-running just rewrites the manifest.

---

## 3. Model choice and training script structure

**Recommendation: ConvNeXt-Tiny (timm `convnext_tiny`, ImageNet-pretrained) as the primary backbone**, with ViT-B/16 noted as an easy swap-in for a follow-up blog comparison. Rationale:
- ~28M params — fine-tunes comfortably on CUB's ~11,788 images (5,994 train) without heavy overfitting risk, and trains in reasonable time on a single consumer GPU or even CPU for a "quick verification" run with a tiny subset.
- CNN inductive bias historically does well on fine-grained bounded-object classification like CUB without needing heavy data augmentation tuning that ViTs often require at this data scale.
- `timm` gives a one-line `timm.create_model('convnext_tiny', pretrained=True, num_classes=200)` and consistent preprocessing (`timm.data.resolve_data_config` + `create_transform`), which is a clean teaching example for the fine-tuning blog post.
- Document ViT-B/16 (`timm` `vit_base_patch16_224`) as the "try this next" alternative in the README, since it's the more fashionable comparison point for a granularity-diagnostic narrative (does a ViT need more/less fine-grained signal than a ConvNeXt?) — but don't implement both in phase 1, just make `model.py`'s backbone name a config parameter so swapping is trivial later.

`classifier_service/training/model.py`:
- `build_model(backbone_name: str, num_classes: int, pretrained: bool = True) -> nn.Module` via `timm.create_model`.
- `get_transforms(backbone_name)` returning train (with augmentation: random crop/resize, horizontal flip, color jitter) and eval (deterministic resize/center-crop) transform pipelines, ideally derived from `timm.data.resolve_data_config` for correctness with the pretrained normalization stats.

`classifier_service/training/dataset.py`:
- `CUB200Dataset(manifest_csv, split, transform)` — a `torch.utils.data.Dataset` reading the manifest produced above, loading images with PIL, applying transform, returning `(tensor, label_id)`.

`classifier_service/training/train.py` (CLI, e.g. `python -m classifier_service.training.train --epochs 15 --backbone convnext_tiny --batch-size 32`):
- Standard loop: load manifest, build datasets/dataloaders for train/val, build model, optimizer (AdamW), LR scheduler (cosine or step), loss (CrossEntropyLoss, optionally label smoothing given CUB's fine granularity), mixed precision if CUDA available.
- Freeze/unfreeze strategy: start with backbone frozen + head-only for 1-2 epochs (fast, teaches transfer-learning concept clearly), then unfreeze full network for remaining epochs at a lower LR — a good "here's what fine-tuning means" narrative beat for the blog post.
- Per-epoch: train loss/acc, val loss/acc, top-3 val acc; save best checkpoint by val accuracy to `classifier_service/checkpoints/best.pt` (state_dict + metadata: backbone name, num_classes, label_map reference, training args) and periodically save `last.pt`.
- `--quick` / `--max-samples` flag for a fast sanity-check run (e.g. 200 images, 1 epoch) — this is what the verification section below uses so the whole pipeline can be smoke-tested in minutes without a full ~1-2 hour training run.
- Log to stdout (simple) — no need for W&B/tensorboard in phase 1 scope, but structure the loop so adding a logger later is a small diff.

`classifier_service/training/evaluate.py`:
- Loads a checkpoint + the held-out test split (`is_training_image == 0` from the official split, kept separate from the train/val carve-out), computes top-1/top-3 accuracy, per-class accuracy, writes `classifier_service/checkpoints/metrics.json` and optionally a confusion-heavy report for the worst-performing classes (nice tie-in with the granularity "bitter" subset — worst classes should correlate).

Checkpoint format: a single `.pt` containing `{"model_state_dict": ..., "backbone_name": ..., "num_classes": 200, "label_map": {...}}` so `serving/inference.py` is self-contained and doesn't need the training manifest at serve time.

---

## 4. FastAPI service

`classifier_service/serving/schemas.py`:
- `SpeciesPrediction(species_name: str, scientific_name: str | None, confidence: float)` (0-1 float, service-local — keep this decoupled from `birdai.schemas.SpeciesCandidate`, which uses an int 0-100; the `birdai` side's `normalize_*` function does the conversion, same pattern as `gemini_client.normalize_birdai_result` doing its own shaping).
- `PredictResponse(predictions: list[SpeciesPrediction], model_version: str, backbone: str)`.
- `HealthResponse(status: str, model_loaded: bool)`.

`classifier_service/serving/inference.py`:
- `ClassifierModel` class wrapping the loaded checkpoint: `__init__(checkpoint_path)` loads once; `predict(image: PIL.Image, top_k: int = 3) -> list[SpeciesPrediction]` runs preprocessing + forward + softmax + topk.
- Loaded as a singleton at FastAPI startup (via `lifespan` context manager, the modern FastAPI pattern, rather than deprecated `@app.on_event("startup")`), so the model is in memory once and reused across requests.

`classifier_service/serving/app.py`:
- `POST /predict` — accepts `multipart/form-data` file upload (`UploadFile`), reads bytes into PIL Image, calls the singleton classifier, returns `PredictResponse`. Reject non-image content types with 415, reject decode failures with 400.
- `GET /health` — returns whether the model is loaded, for container healthchecks and for `classifier_client.py`'s own graceful-degradation check.
- `GET /labels` — returns the full label map (handy for debugging/demo, and lets the Gradio app or docs list all 200 species without duplicating the label map file).
- CORS: not needed since `app.py` (Gradio) calls this server-side over HTTP, not from the browser.
- Config via env vars: `CLASSIFIER_CHECKPOINT_PATH` (default `checkpoints/best.pt`), `CLASSIFIER_TOP_K` (default 3), read directly with `os.getenv` in a small `serving/settings.py` or inline — keep it minimal, this service doesn't need the full `birdai.config` machinery.

Dockerfile design (`classifier_service/Dockerfile`):
- Base image: `python:3.11-slim` — CPU-only inference is the right default for a demo/blog-post service (small image, runs anywhere, no CUDA driver dependency on the host); document a GPU variant (`nvidia/cuda:...-runtime` base + `torch` CUDA wheel) as a commented-out alternative in the Dockerfile or a separate `Dockerfile.gpu`, since training happens outside Docker (locally, wherever the user has a GPU) and only *inference* needs to run in the container for phase 1.
- Install `torch`/`torchvision` CPU wheels explicitly via the PyTorch CPU index URL (`--index-url https://download.pytorch.org/whl/cpu`) to avoid pulling multi-GB CUDA wheels into a CPU-serving image — this is the single biggest image-size lever (CPU torch wheel is a few hundred MB vs several GB for CUDA builds).
- Multi-stage not strictly necessary at this size but worth it for teaching value: builder stage installs deps into a venv, final stage copies venv + app code, keeping the runtime image lean and pip cache out of the final layer.
- `COPY checkpoints/best.pt` into the image (fine for a demo-scale single ~100-300MB checkpoint) — or optionally support mounting the checkpoint as a volume so the image itself stays small and checkpoints can be swapped without a rebuild; document the volume-mount approach as the recommended path for iterating, and "bake it in" as the recommended path for a shareable demo image people can `docker run` with zero setup (better for the GitHub-stars use case — a one-line `docker run` that just works is the whole point).
- `EXPOSE 8000`, `CMD ["uvicorn", "serving.app:app", "--host", "0.0.0.0", "--port", "8000"]`.
- `.dockerignore`: exclude `data/`, `.git`, `__pycache__`, `tests/`, `granularity/`, `reports/`.

---

## 5. Integration into the existing app

`src/birdai/config.py` additions (same flat `os.getenv` style):
```
CLASSIFIER_SERVICE_URL = os.getenv("CLASSIFIER_SERVICE_URL", "http://localhost:8000")
CLASSIFIER_TOP_K = _get_optional_int("CLASSIFIER_TOP_K", 3)
CLASSIFIER_TIMEOUT_SECONDS = _get_optional_int("CLASSIFIER_TIMEOUT_SECONDS", 10)
CLASSIFIER_ENABLED = os.getenv("CLASSIFIER_ENABLED", "true").lower() == "true"
```

`.env.example` additions:
```
# Optional local classifier microservice (see classifier_service/):
# CLASSIFIER_SERVICE_URL=http://localhost:8000
# CLASSIFIER_TOP_K=3
# CLASSIFIER_TIMEOUT_SECONDS=10
# CLASSIFIER_ENABLED=true
```

`src/birdai/schemas.py` — add a new sibling model rather than overloading `SpeciesCandidate`/`ObservationEvidence` (per the exploration notes, `evidence` doesn't fit a classifier signal):
```python
class LocalClassifierPrediction(BaseModel):
    species_name: str
    scientific_name: Optional[str] = None
    confidence_probability: int = Field(ge=0, le=100)

class LocalClassifierResult(BaseModel):
    source: str = "none"              # "local_classifier" | "unavailable" | "error"
    model_version: Optional[str] = None
    predictions: List[LocalClassifierPrediction] = Field(default_factory=list)
    summary: str = ""
```
Add `local_classifier: LocalClassifierResult = Field(default_factory=LocalClassifierResult)` to `BirdAIResult` (top-level, since the classifier scores the whole image independently rather than annotating one Gemini candidate — a top-level field is truer to what it is than nesting it under each `SpeciesCandidate`). Note this is an additive, backward-compatible schema change (new field with a default), so `mock_analyzer.py` and existing tests that build `BirdAIResult` without it keep working.

`src/birdai/classifier_client.py` (new, mirrors `ebird_client.py`/`gemini_client.py` conventions):
- `class ClassifierServiceError(RuntimeError): pass`
- `get_client(http_client: httpx.Client | None = None) -> httpx.Client` — thin wrapper, or just take `http_client` as a parameter into the call function directly, matching how `EBirdClient` takes an optional `http_client`.
- `def classify_image(file_path: str, *, http_client: httpx.Client | None = None) -> dict` — POSTs the image bytes to `f"{CLASSIFIER_SERVICE_URL}/predict"`, raises `ClassifierServiceError` on network failure, non-2xx, or timeout (wrapping `httpx.HTTPError`), same as `EBirdClient._request`.
- `def normalize_classifier_result(payload: dict) -> LocalClassifierResult` — converts the service's float 0-1 confidences to the app's int 0-100 scale, maps `predictions` -> `LocalClassifierPrediction` list, sets `source="local_classifier"`.
- Only called for **image** modality (the classifier is vision-only) — audio files skip this step entirely, which is also the natural seam where a later BirdNET audio-confidence phase would plug in its own client/enrichment step without touching this one.

`src/birdai/perception.py` — add a sibling enrichment step next to `_enrich_candidate_with_recent_observations`, but note it operates at the *result* level, not per-candidate (it's a whole-image classification, not enrichment of one Gemini-proposed species):
```python
def _add_local_classifier_signal(
    file_path: str,
    *,
    detected_file: DetectedFileType,
    classifier_client_fn=classify_image,
) -> tuple[LocalClassifierResult, list[str]]:
    warnings = []
    if not CLASSIFIER_ENABLED or detected_file.modality != "image":
        return LocalClassifierResult(source="unavailable"), warnings
    try:
        payload = classifier_client_fn(file_path)
        return normalize_classifier_result(payload), warnings
    except ClassifierServiceError as exc:
        warnings.append(f"Local classifier unavailable: {exc}")
        return LocalClassifierResult(source="error", summary=str(exc)), warnings
```
Call this inside `analyze_observation`, after the existing eBird enrichment loop, and fold its warnings into `all_warnings`; pass `local_classifier=...` into the final `result.model_copy(update={...})`. Keep it decoupled from the eBird loop (independent try/except, independent optional dependency) so a classifier-service outage degrades gracefully — Gemini output and eBird evidence are unaffected, matching the existing fallback philosophy already used for eBird -> web-search fallback.

`app.py` changes:
- Add a new Gradio output component, e.g. `classifier_output = gr.Code(label="Local classifier signal", language="json")` (or a simpler `gr.Textbox` summarizing "Local model: European Stonechat (82%)" — recommend `gr.Textbox` for demo readability, since the full JSON is already visible in `result_output`; the point of a dedicated output is a quick visual gut-check, not raw JSON duplication).
- In `run_birdai`, after getting `result`, format a one-line summary from `result.local_classifier` (e.g. top prediction + confidence, or "Classifier unavailable" if `source != "local_classifier"`), return it as an additional tuple element.
- Update `outputs=[warnings_output, location_status_output, result_output]` (line ~289) to include the new output, and update the early-return tuples (lines ~157-161, ~186) and the `reset_button.click` lambda (lines ~291-311) to match the new arity — these are the three places that must stay in sync whenever `run_birdai`'s return signature changes.

`src/birdai/logging_utils.py` — optional small addition: add a `local_classifier_top_name` / `local_classifier_confidence` column to the CSV row for easy spreadsheet-level comparison against Gemini's `top_confidence_probability`, alongside keeping the full blob in `result_json` (which will automatically include it once the schema changes, since `result.model_dump(mode="json")` is generic). This directly enables a "does the fine-tuned classifier agree with Gemini" analysis for the blog post.

---

## 6. Granularity diagnostic (small, standalone, offline)

Lives at `classifier_service/granularity/compute_granularity.py` — deliberately placed under `classifier_service/` (not `src/birdai/`) since it depends on the trained/pretrained vision backbone and torch, and is a training-data characterization tool, not part of either the app or the serving path. It is a manual/offline script, never imported by `app.py`, `perception.py`, or the FastAPI service.

Scope (kept small per requirements):
1. **Feature extraction**: load the CUB-200 manifest (reuses `classifier_service/scripts/prepare_dataset.py` output), run each image through the trained checkpoint's backbone (or a plain ImageNet-pretrained backbone if no checkpoint yet — should work standalone before/independent of training completing) with the classification head removed, producing a penultimate-layer embedding per image. Cache embeddings to disk (`.npy` or `.pt`) since this is the expensive step and the script will be re-run while iterating on the statistic.
2. **RankM-style granularity statistic**: for each class, compute intra-class distance statistics (e.g. mean pairwise distance or spread of embeddings within a class) and inter-class distance statistics (distance between class centroids), then combine into a per-class and dataset-level granularity score, following the "rank margin" intuition from the paper (how separable/close classes are in feature space — the closer clusters are relative to their spread, the more fine-grained/harder the discrimination task). This does not need to reproduce every candidate measure from the paper (Fisher/RS/RSM/Rank) — implement RankM only, since the paper identifies it as the best-performing measure, and this is a diagnostic, not a research reproduction.
3. **Bitter/sweet subset extraction**: rank the 200 species by their per-class granularity contribution (or simply by nearest-neighbor confusability of their centroid with other centroids); output the bottom-N "bitter" (hardest, most fine-grained-relative-to-others) and top-N "sweet" (easiest, most separable) species lists.
4. **Report output**: write `classifier_service/reports/granularity_report.json` (dataset-level score, per-class scores, bitter/sweet lists) and a simple matplotlib bar chart or 2D projection (e.g. UMAP/PCA of embeddings colored by class, or a histogram of per-class scores) saved as `classifier_service/reports/granularity_plot.png`. A notebook is optional/nice-to-have, not required — a plain script with a `--report-dir` flag producing JSON + PNG is enough to satisfy "keep this small."
5. CLI: `python -m classifier_service.granularity.compute_granularity --checkpoint checkpoints/best.pt --manifest data/CUB_200_2011/manifest.csv --report-dir reports/ [--bottom-n 20] [--top-n 20]`.

Cross-reference value for the blog post: compare the granularity script's "bitter" species list against `evaluate.py`'s per-class worst-accuracy list from section 3 — if they correlate, that's a nice validating result to write up (the paper's thesis borne out on this exact dataset/model).

No changes to `src/birdai/` are needed for this piece, and it must not import anything from `perception.py`/`app.py`/`classifier_client.py` — keep the dependency direction one-way (diagnostic tool depends on training/serving code being available locally, never the reverse).

---

## 7. Tests (pytest, following existing conventions: plain functions, stubbed HTTP/model, no live network or heavy model calls)

New/modified test files:
- `tests/test_classifier_client.py` (new, mirrors `tests/test_ebird_client.py`): stub the HTTP call with `httpx.MockTransport`, assert `classify_image` posts to `/predict` with the right file, assert `normalize_classifier_result` correctly maps a sample payload (float confidences -> int 0-100, predictions list -> `LocalClassifierPrediction`), assert `ClassifierServiceError` is raised on a 500 response and on a connection error.
- `tests/test_perception.py` (existing, extend): add a case where `_add_local_classifier_signal` (or the full `analyze_observation` call) is exercised with a stubbed classifier client function for an image file, asserting `result.local_classifier.source == "local_classifier"` and the confidence maps through; add a case for an audio file asserting the classifier step is skipped (`source == "unavailable"`); add a case where the classifier client raises, asserting a warning is appended and `source == "error"` while the rest of the result (Gemini candidates) is untouched.
- `tests/test_schemas.py` (existing, extend): validate `LocalClassifierResult`/`LocalClassifierPrediction` construction and that `BirdAIResult` defaults `local_classifier` when omitted (backward compatibility check).
- `tests/test_app.py` (existing, extend): update any test asserting `run_birdai`'s return arity/outputs to account for the new classifier output element.
- `tests/test_logging.py` (existing, extend, if the CSV column is added): assert the new column appears and round-trips.
- `classifier_service/tests/test_inference.py` (new, service-local pytest): construct `ClassifierModel` against a tiny fake checkpoint (e.g. a randomly-initialized small model saved with 3-5 fake classes) so the test doesn't depend on the real trained weights; assert `predict()` returns the right shape/types (top_k predictions, confidence in [0,1], sums to ~1 after softmax).
- `classifier_service/tests/test_api.py` (new): use FastAPI's `TestClient` against `serving/app.py` with the app's model dependency overridden/mocked (don't load real weights in CI), assert `/health` reports `model_loaded`, `/predict` with a fixture image returns a well-formed `PredictResponse`, and a non-image upload returns 415/400.

No test should require the real CUB-200 download, a trained checkpoint, or a running Docker container — everything is stubbed/mocked, consistent with the existing test suite's "no live network or model calls" rule.

---

## 8. Dependency additions

`requirements.txt` (root, app-level) — no changes needed beyond what's already there; `httpx` is already present for the new `classifier_client.py`. (Optionally pin `fastapi`/`uvicorn` here too only if the plan later wants to run the classifier service in-process instead of via Docker for local dev, but recommend keeping it fully separate — install classifier deps only inside `classifier_service/`.)

`classifier_service/requirements.txt` (new file):
```
torch
torchvision
timm
fastapi
uvicorn[standard]
pillow
pydantic
pandas          # for manifest handling in scripts/
httpx            # for tests using TestClient's underlying transport, and any service-side calls
pytest
matplotlib       # granularity report plot
scikit-learn     # optional: PCA/clustering helpers for granularity script
```
Document in `classifier_service/README.md` that CPU-only torch install should use `--index-url https://download.pytorch.org/whl/cpu` locally too (not just in Docker) if the user doesn't have a CUDA GPU, to avoid an accidental multi-GB CUDA download during `pip install`.

No root `pyproject.toml` exists today (project uses `requirements.txt` only) — keep that convention; don't introduce a `pyproject.toml`/Poetry/uv setup unless the user asks, to avoid an unplanned tooling migration.

---

## 9. Verification plan (how to confirm each piece works end-to-end)

1. **Dataset prep**: `python classifier_service/scripts/download_cub200.py` then `python classifier_service/scripts/prepare_dataset.py` — check `classifier_service/data/CUB_200_2011/manifest.csv` has ~11,788 rows and `label_map.json` has 200 entries.
2. **Quick training smoke test**: `python -m classifier_service.training.train --quick --max-samples 200 --epochs 1` — confirms the full data-loading -> model -> loss -> checkpoint-save pipeline runs without needing a full multi-hour training run; check `classifier_service/checkpoints/best.pt` is written and `evaluate.py --checkpoint checkpoints/best.pt` produces a `metrics.json` with plausible (even if poor, since it's undertrained) accuracy numbers.
3. **Full training run** (separate, longer): run without `--quick`, confirm val accuracy climbs epoch over epoch and final top-1/top-3 test accuracy is reported (CUB-200 fine-tuned ConvNeXt-Tiny should reasonably reach somewhere in the 70-80%+ top-1 range with a proper run, per typical published fine-tuning results on this dataset — treat this as a sanity ballpark, not a hard target).
4. **FastAPI service standalone**: `uvicorn classifier_service.serving.app:app --reload`, then `curl -X POST http://localhost:8000/predict -F "file=@classifier_service/tests/fixtures/<sample_bird>.jpg"` — confirm a JSON response with ranked predictions; `curl http://localhost:8000/health` confirms `model_loaded: true`.
5. **Docker build/run**: `docker build -t birdai-classifier classifier_service/`, `docker run -p 8000:8000 birdai-classifier`, re-run the curl checks above against the containerized service; check image size is reasonable (spot-check `docker images` — CPU-torch-based image should land well under 2GB, ideally under 1GB with a slim multi-stage build).
6. **App integration**: with the classifier service running (`CLASSIFIER_SERVICE_URL` pointing at it) and `CLASSIFIER_ENABLED=true`, run `python app.py`, upload a bird image, click Analyze, confirm the new classifier output element shows a species + confidence, and confirm `result_output`'s JSON includes a populated `local_classifier` block. Then stop the classifier service and re-run to confirm graceful degradation (a warning appears, Gemini result still returns normally, `local_classifier.source == "error"`).
7. **Automated tests**: `pytest` at repo root (existing app tests + new classifier_client/perception/schema/app tests) and `pytest classifier_service/tests` (service-local tests) both green, with no network/model dependency per the "no live calls" rule.
8. **Granularity script**: `python -m classifier_service.granularity.compute_granularity --checkpoint classifier_service/checkpoints/best.pt --manifest classifier_service/data/CUB_200_2011/manifest.csv --report-dir classifier_service/reports/` — confirm `granularity_report.json` and `granularity_plot.png` are produced, spot-check that the "bitter" species list is non-degenerate (not all identical scores) and, as a soft validation, eyeball whether it overlaps with `evaluate.py`'s worst-accuracy class list from step 3.

---

## Critical Files for Implementation
- src/birdai/schemas.py — add `LocalClassifierResult`/`LocalClassifierPrediction`, extend `BirdAIResult`
- src/birdai/perception.py — add the classifier enrichment step inside `analyze_observation`
- src/birdai/classifier_client.py (new) — HTTP client + `normalize_classifier_result`, mirrors `ebird_client.py`
- app.py — new Gradio output component and `run_birdai` wiring (lines ~148-186, ~278-311)
- classifier_service/serving/app.py (new) — FastAPI `/predict`, `/health`, `/labels` endpoints
- classifier_service/training/train.py (new) — fine-tuning entrypoint producing the checkpoint consumed by serving
- classifier_service/Dockerfile (new) — CPU-first containerization of the serving app
