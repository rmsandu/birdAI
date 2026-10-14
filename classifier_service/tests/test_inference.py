import io

import torch
from PIL import Image

from classifier_service.serving.inference import ClassifierModel
from classifier_service.training.model import build_model


def _write_fake_checkpoint(tmp_path, backbone_name="convnext_tiny", num_classes=5):
    model = build_model(backbone_name, num_classes, pretrained=False)
    label_map = {str(i): f"Species {i}" for i in range(num_classes)}
    checkpoint_path = tmp_path / "fake.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "backbone_name": backbone_name,
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


def test_predict_returns_top_k_predictions_summing_to_one(tmp_path):
    checkpoint_path = _write_fake_checkpoint(tmp_path, num_classes=5)
    model = ClassifierModel(str(checkpoint_path))

    predictions = model.predict(_sample_image_bytes(), top_k=3)

    assert len(predictions) == 3
    assert all(0.0 <= p.confidence <= 1.0 for p in predictions)
    assert predictions[0].species_name in {"Species 0", "Species 1", "Species 2", "Species 3", "Species 4"}


def test_predict_caps_top_k_at_num_classes(tmp_path):
    checkpoint_path = _write_fake_checkpoint(tmp_path, num_classes=3)
    model = ClassifierModel(str(checkpoint_path))

    predictions = model.predict(_sample_image_bytes(), top_k=10)

    assert len(predictions) == 3
