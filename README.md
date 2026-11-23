# BirdAI

BirdAI is a context-aware embodied bird perception and observation review system. It combines field birdwatching with practical machine perception: comparing uncertain observations from camera and audio sources, exposing transparent confidence and evidence, and helping an observer learn from them.

---

## Core Principles

- **Uncertainty & Evidence Over Labels**: Rather than returning a single overconfident label, BirdAI provides ranked candidate species alongside an explicit evidence breakdown (visual features, audio call patterns, and regional checklist plausibility).
- **Merlin Audio Candidates Are Not Ground Truth**: Audio recordings from Merlin Bird ID are supported, but Merlin's suggested species is modeled as an *unverified external prior*, allowing the user to inspect whether the recording actually supports it.
- **Data Discipline & Uncalibrated Scores**: Model confidence scores are explicitly documented and displayed as uncalibrated heuristic estimates rather than empirical probabilities.
- **Human Verification Loop**: Every observation can be reviewed, confirmed, or corrected by the user. Saved observations form an empirical evaluation and learning set.
- **Mobile-First & Desktop Responsive (Google Stitch)**: Designed using [Google Stitch](https://stitch.google.com/) with a naturalist color scheme, touch-friendly camera/audio capture on mobile, and a side-by-side evidence workbench on desktop.

---

## Color Palette & Design System

The application styling follows a 5-color field guide palette:

| Color | Hex | Role |
| :--- | :--- | :--- |
| **Deep Evergreen** | `#123F2A` | Primary brand, navigation bar, headers, high-contrast text |
| **Olive Leaf** | `#547239` | High-confidence badges, confirmed species checkmarks, nature accents |
| **Crimson Berry** | `#9F2245` | Primary action buttons (*Analyze Observation*), alert flags |
| **Coral Pink** | `#FF868A` | Active tab highlights, audio waveform accents, chips |
| **Warm Sand Tan** | `#C19168` | Card borders, metadata tags (date, time, GPS coordinates), dividers |

Detailed Stitch design prompts and component specifications are documented in [`docs/stitch/prompt_guide.md`](docs/stitch/prompt_guide.md).

---

## Architecture Overview

```
                      ┌────────────────────────────────────────┐
                      │        Responsive Web Client           │
                      │  Mobile (PWA / Touch) & Desktop UI     │
                      └──────────────────┬─────────────────────┘
                                         │  HTTP / JSON
                                         ▼
                      ┌────────────────────────────────────────┐
                      │          FastAPI Service (:8080)       │
                      │    /api/observations, /correct, /docs  │
                      └───────┬────────────────────────┬───────┘
                              │                        │
               ┌──────────────▼──────────┐   ┌─────────▼──────────────┐
               │    Perception Engine    │   │  Local Storage Layer   │
               │  • Gemini 2.5 Flash VLM │   │  • data/uploads/{id}/  │
               │  • Audio Property Insp. │   │  • data/observations/  │
               │  • Merlin Prior Parser  │   │  • Verification State  │
               │  • eBird Context Prior  │   └─────────┬──────────────┘
               │  • Optional Classifier  │             │
               └─────────────────────────┘             │
                                                       ▼
                                             ┌──────────────────┐
                                             │ Evaluation Suite │
                                             │ Top-k, MRR, Brier│
                                             └──────────────────┘
```

---

## Quickstart

### 1. Prerequisites & Environment Setup

Copy `.env.example` to `.env` and add your API keys:

```bash
cp .env.example .env
```

Edit `.env`:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
EBIRD_API_KEY=your_ebird_api_key_here
# Optional Stitch MCP API key:
STITCH_API_KEY=your_stitch_api_key_here
```

### 2. Local Python Development

Install dependencies and start the service:

```bash
pip install -r requirements.txt
PYTHONPATH=src uvicorn birdai.api.app:app --host 0.0.0.0 --port 8080 --reload
```

- **Web App**: Open [http://localhost:8080](http://localhost:8080)
- **Interactive REST Docs (Swagger)**: Open [http://localhost:8080/docs](http://localhost:8080/docs)

---

## Running with OrbStack (macOS) or Docker

On macOS, **[OrbStack](https://orbstack.dev/)** is the recommended container engine, offering near-instant startup, native volume performance, and drop-in compatibility with the standard Docker CLI.

### Container Concepts

- **Building an Image** (`docker compose build`): Packages Python, system dependencies from `requirements.txt`, application code from `src/`, and default assets into a reproducible, isolated image.
- **Running a Container** (`docker compose up`): Launches an isolated execution instance of that image. Port mapping (`8080:8080`) routes localhost traffic directly into the container, while the volume mount (`./data:/app/data`) ensures that saved observations and uploaded images/audio persist on your host machine across container restarts.

### Commands

Build and start the container stack:

```bash
# Build the BirdAI container image
docker compose build

# Start the service in the foreground
docker compose up
```

Once running, navigate to [http://localhost:8080](http://localhost:8080).

---

## Evaluation Workflow

A central contribution of BirdAI is reliable, reproducible evaluation over real-world observations with human-verified labels.

### Running the Evaluator

Evaluate against the included benchmark dataset (`data/evaluation_samples/seed_benchmark.json`) or the observations you've recorded in the app database (`DATABASE_URL`, default `data/birdai.db`). Only observations you've confirmed or corrected in the app are scored.

```bash
# Run against seed benchmark
PYTHONPATH=src python scripts/evaluate.py --benchmark data/evaluation_samples/seed_benchmark.json

# Run against all users' verified observations in the database
PYTHONPATH=src python scripts/evaluate.py

# Only one user's observations, or a different database
PYTHONPATH=src python scripts/evaluate.py --user you@example.com
PYTHONPATH=src python scripts/evaluate.py --database-url sqlite:///path/to/other.db
```

Legacy JSON observations in `data/observations/` must be imported first with `scripts/migrate_json_to_db.py`.

### Reported Metrics

1. **Top-1 & Top-k Accuracy**: Proportion of observations where the verified true species matches the top prediction or appears in the top-k candidates.
2. **Mean Reciprocal Rank (MRR)**: Evaluates ranking quality across candidate lists ($1/\text{rank}$).
3. **Modality Breakdown**: Separate performance tracking for image-only, audio-only, and multimodal submissions.
4. **Merlin Prior Performance**: Evaluates how often Merlin's external suggestion was correct vs. incorrect.
5. **Calibration Analysis**: Groups predictions into confidence bins (`0-49%`, `50-74%`, `75-100%`) and compares average model confidence against actual empirical accuracy.

---

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/observations` | Ingest image, audio, context, and optional Merlin suggestion |
| `GET` | `/api/observations/{id}` | Inspect observation details, candidates, and evidence breakdown |
| `POST` | `/api/observations/{id}/correct` | Submit verified ground truth or species correction |
| `GET` | `/api/observations` | List saved observations with optional `?reviewed_only=true` filter |
| `GET` | `/api/media/{id}/{file}` | Stream uploaded image or audio file |
| `GET` | `/health` | Service health status |

---

## Testing

Run the automated test suite:

```bash
PYTHONPATH=src pytest
```
