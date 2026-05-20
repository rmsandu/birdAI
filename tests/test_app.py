import json
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

from birdai import context as context_module
from birdai.file_utils import DetectedFileType
from birdai.mock_analyzer import mock_analyze_file


FIXTURES = Path(__file__).parent / "fixtures"


def test_run_birdai_returns_result_json(monkeypatch):
    monkeypatch.setattr(
        context_module,
        "geocode_location",
        lambda location_text, http_client=None: (47.3769, 8.5417),
    )

    sys.modules.pop("app", None)
    app_module = importlib.import_module("app")

    context = context_module.get_default_observation_context()
    file_obj = SimpleNamespace(name=str(FIXTURES / "sample.jpg"))

    monkeypatch.setattr(
        app_module,
        "analyze_observation",
        lambda file_path, observation_context, use_mock=False: mock_analyze_file(
            file_path,
            modality="image",
            observation_context=observation_context,
        ),
    )
    monkeypatch.setattr(app_module, "log_observation", lambda *args, **kwargs: None)

    warnings_text, location_status, result_json = app_module.run_birdai(
        file_obj,
        context.observation_date.isoformat(),
        context.observation_time.isoformat(timespec="seconds"),
        context.location_text,
        context.latitude,
        context.longitude,
    )

    payload = json.loads(result_json)

    assert warnings_text == "No warnings."
    assert location_status == "Using the current location fields."
    assert payload["likely_species"][0]["common_name"] == "European Robin"


def test_update_coordinates_from_photo_uses_embedded_gps(monkeypatch):
    monkeypatch.setattr(
        context_module,
        "geocode_location",
        lambda location_text, http_client=None: (47.3769, 8.5417),
    )

    sys.modules.pop("app", None)
    app_module = importlib.import_module("app")
    monkeypatch.setattr(
        app_module,
        "detect_file_type",
        lambda file_path: DetectedFileType(
            modality="image",
            mime_type="image/heic",
        ),
    )
    monkeypatch.setattr(
        app_module,
        "extract_photo_coordinates",
        lambda file_path: (47.3769, 8.5417),
    )
    monkeypatch.setattr(
        app_module,
        "reverse_geocode_coordinates",
        lambda latitude, longitude: "Zurich, District 1, Zurich, Switzerland",
    )
    file_obj = SimpleNamespace(name=str(Path(__file__).parent / "IMG_3219.HEIC"))

    location_text, latitude, longitude, status, preview_image = app_module.update_coordinates_from_photo(
        file_obj,
        "Zurich, Switzerland",
        None,
        None,
    )

    assert location_text == "Zurich, District 1, Zurich, Switzerland"
    assert latitude == 47.3769
    assert longitude == 8.5417
    assert "photo metadata" in status
    assert preview_image is not None
    assert Path(preview_image).exists()


def test_build_photo_preview_returns_rescaled_image(monkeypatch):
    monkeypatch.setattr(
        context_module,
        "geocode_location",
        lambda location_text, http_client=None: (47.3769, 8.5417),
    )
    sys.modules.pop("app", None)
    app_module = importlib.import_module("app")
    file_obj = SimpleNamespace(name=str(FIXTURES / "sample.jpg"))

    preview_image = app_module.build_photo_preview(file_obj)

    assert preview_image is not None
    assert Path(preview_image).exists()


def test_use_location_search_geocodes_location_text(monkeypatch):
    monkeypatch.setattr(
        context_module,
        "geocode_location",
        lambda location_text, http_client=None: (47.3769, 8.5417),
    )
    sys.modules.pop("app", None)
    app_module = importlib.import_module("app")
    monkeypatch.setattr(
        app_module,
        "geocode_location",
        lambda location_text: (47.3769, 8.5417),
    )

    latitude, longitude, status = app_module.use_location_search(
        "Zurich, Switzerland",
        None,
        None,
    )

    assert latitude == 47.3769
    assert longitude == 8.5417
    assert "geocoded" in status.lower()
