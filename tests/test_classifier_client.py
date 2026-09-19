from pathlib import Path

import httpx
import pytest

from birdai.classifier_client import (
    ClassifierServiceError,
    classify_image,
    normalize_classifier_result,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_classify_image_posts_file_and_returns_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/predict"
        assert request.url.params["top_k"] == "3"
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {
                        "species_name": "European Robin",
                        "scientific_name": "Erithacus rubecula",
                        "confidence": 0.82,
                    }
                ],
                "model_version": "convnext_tiny-v1",
                "backbone": "convnext_tiny",
            },
        )

    payload = classify_image(
        str(FIXTURES / "sample.jpg"),
        base_url="http://classifier.test",
        top_k=3,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert payload["predictions"][0]["species_name"] == "European Robin"


def test_classify_image_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "model not loaded"})

    with pytest.raises(ClassifierServiceError):
        classify_image(
            str(FIXTURES / "sample.jpg"),
            base_url="http://classifier.test",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )


def test_classify_image_raises_on_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ClassifierServiceError):
        classify_image(
            str(FIXTURES / "sample.jpg"),
            base_url="http://classifier.test",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )


def test_normalize_classifier_result_maps_confidence_to_percent():
    payload = {
        "predictions": [
            {
                "species_name": "European Robin",
                "scientific_name": "Erithacus rubecula",
                "confidence": 0.8234,
            },
            {
                "species_name": "European Stonechat",
                "scientific_name": "Saxicola rubicola",
                "confidence": 0.1123,
            },
        ],
        "model_version": "convnext_tiny-v1",
        "backbone": "convnext_tiny",
    }

    result = normalize_classifier_result(payload)

    assert result.source == "local_classifier"
    assert result.model_version == "convnext_tiny-v1"
    assert result.predictions[0].species_name == "European Robin"
    assert result.predictions[0].confidence_probability == 82
    assert "European Robin" in result.summary


def test_normalize_classifier_result_handles_empty_predictions():
    result = normalize_classifier_result({"predictions": [], "backbone": "convnext_tiny"})

    assert result.source == "local_classifier"
    assert result.predictions == []
    assert result.summary == "Local classifier returned no predictions."
