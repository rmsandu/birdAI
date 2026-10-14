import io

import torch
from fastapi.testclient import TestClient
from PIL import Image

from classifier_service.serving import app as app_module
from classifier_service.serving.inference import ClassifierModel
from classifier_service.training.model import build_model


def _write_fake_checkpoint(tmp_path, num_classes=5):
    model = build_model("convnext_tiny", num_classes, pretrained=False)
    label_map = {str(i): f"Species {i}" for i in range(num_classes)}
    checkpoint_path = tmp_path / "fake.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "backbone_name": "convnext_tiny",
            "num_classes": num_classes,
            "label_map": label_map,
        },
        checkpoint_path,
    )
    return checkpoint_path


def _sample_image_bytes() -> bytes:
    image = Image.new("RGB", (224, 224), color=(120, 150, 90))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_health_and_predict_with_loaded_model(tmp_path, monkeypatch):
    checkpoint_path = _write_fake_checkpoint(tmp_path)

    # The lifespan startup runs on TestClient context entry and overwrites
    # _state["model"] (no real checkpoint at the default path in tests), so
    # the fake model must be injected after entering the context.
    with TestClient(app_module.app) as client:
        app_module._state["model"] = ClassifierModel(str(checkpoint_path))

        health_response = client.get("/health")
        assert health_response.json() == {"status": "ok", "model_loaded": True}

        predict_response = client.post(
            "/predict",
            files={"file": ("bird.jpg", _sample_image_bytes(), "image/jpeg")},
        )
        assert predict_response.status_code == 200
        payload = predict_response.json()
        assert len(payload["predictions"]) == 3
        assert payload["backbone"] == "convnext_tiny"


def test_predict_rejects_non_image_upload(tmp_path):
    checkpoint_path = _write_fake_checkpoint(tmp_path)

    with TestClient(app_module.app) as client:
        app_module._state["model"] = ClassifierModel(str(checkpoint_path))
        response = client.post(
            "/predict",
            files={"file": ("notes.txt", b"not an image", "text/plain")},
        )
        assert response.status_code == 415


def test_health_reports_model_not_loaded_when_unset():
    app_module._state["model"] = None

    with TestClient(app_module.app) as client:
        response = client.get("/health")
        assert response.json()["model_loaded"] is False
