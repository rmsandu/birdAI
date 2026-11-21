from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from birdai.api.routes import router as api_router

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app = FastAPI(
    title="BirdAI Perception API",
    description="Multimodal bird perception, evidence exposure, and observation review service.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", include_in_schema=False)
def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "BirdAI API running. Visit /docs for Swagger API documentation."}


@app.get("/favicon.ico", include_in_schema=False)
def serve_favicon():
    fav_file = FRONTEND_DIR / "favicon.ico"
    if fav_file.exists():
        return FileResponse(fav_file, media_type="image/x-icon")
    icon_file = FRONTEND_DIR / "icon.png"
    if icon_file.exists():
        return FileResponse(icon_file, media_type="image/png")
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/manifest.json", include_in_schema=False)
def serve_manifest():
    manifest_file = FRONTEND_DIR / "manifest.json"
    if manifest_file.exists():
        return FileResponse(manifest_file, media_type="application/manifest+json")
    return {"name": "BirdAI", "short_name": "BirdAI", "start_url": "/"}


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "birdai"}
