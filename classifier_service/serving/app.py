from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile

from classifier_service.serving.inference import MODEL_VERSION, ClassifierModel
from classifier_service.serving.schemas import HealthResponse, PredictResponse
from classifier_service.serving.settings import CLASSIFIER_CHECKPOINT_PATH, CLASSIFIER_TOP_K

_state: dict[str, ClassifierModel | None] = {"model": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _state["model"] = ClassifierModel(CLASSIFIER_CHECKPOINT_PATH)
    except FileNotFoundError:
        # Allow the service to start (e.g. for /health checks in CI) even
        # without a trained checkpoint present.
        _state["model"] = None
    yield
    _state["model"] = None


app = FastAPI(title="BirdAI Classifier Service", lifespan=lifespan)


def get_model() -> ClassifierModel:
    model = _state["model"]
    if model is None:
        raise HTTPException(status_code=503, detail="Model is not loaded.")
    return model


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", model_loaded=_state["model"] is not None)


@app.get("/labels")
def labels() -> dict:
    model = get_model()
    return model.label_map


@app.post("/predict", response_model=PredictResponse)
async def predict(file: UploadFile, top_k: int = CLASSIFIER_TOP_K) -> PredictResponse:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Only image uploads are supported.")

    model = get_model()
    image_bytes = await file.read()

    try:
        predictions = model.predict(image_bytes, top_k=top_k)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not decode image: {exc}") from exc

    return PredictResponse(
        predictions=predictions,
        model_version=MODEL_VERSION,
        backbone=model.backbone_name,
    )
