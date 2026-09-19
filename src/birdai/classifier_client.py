from pathlib import Path

import httpx

from birdai.config import (
    CLASSIFIER_SERVICE_URL,
    CLASSIFIER_TIMEOUT_SECONDS,
    CLASSIFIER_TOP_K,
)
from birdai.schemas import LocalClassifierPrediction, LocalClassifierResult


class ClassifierServiceError(RuntimeError):
    pass


def classify_image(
    file_path: str,
    *,
    base_url: str = CLASSIFIER_SERVICE_URL,
    top_k: int = CLASSIFIER_TOP_K,
    http_client: httpx.Client | None = None,
) -> dict:
    client = http_client or httpx.Client(timeout=CLASSIFIER_TIMEOUT_SECONDS)
    should_close = http_client is None

    try:
        with Path(file_path).open("rb") as image_file:
            response = client.post(
                f"{base_url.rstrip('/')}/predict",
                files={"file": (Path(file_path).name, image_file)},
                params={"top_k": top_k},
            )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise ClassifierServiceError(
            f"Local classifier request failed: {exc}"
        ) from exc
    finally:
        if should_close:
            client.close()


def normalize_classifier_result(payload: dict) -> LocalClassifierResult:
    predictions = [
        LocalClassifierPrediction(
            species_name=item["species_name"],
            scientific_name=item.get("scientific_name"),
            confidence_probability=round(item["confidence"] * 100),
        )
        for item in payload.get("predictions", [])
    ]

    top_prediction = predictions[0] if predictions else None
    summary = (
        f"Local classifier ({payload.get('backbone', 'unknown backbone')}) predicts "
        f"{top_prediction.species_name} at {top_prediction.confidence_probability}% confidence."
        if top_prediction
        else "Local classifier returned no predictions."
    )

    return LocalClassifierResult(
        source="local_classifier",
        model_version=payload.get("model_version"),
        predictions=predictions,
        summary=summary,
    )
