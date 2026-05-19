import json
from pathlib import Path
from types import SimpleNamespace

from app import run_birdai
from birdai.context import get_default_observation_context
from birdai.mock_analyzer import mock_analyze_file


FIXTURES = Path(__file__).parent / "fixtures"


def test_run_birdai_returns_result_json(monkeypatch):
    context = get_default_observation_context()
    file_obj = SimpleNamespace(name=str(FIXTURES / "sample.jpg"))

    monkeypatch.setattr(
        "app.analyze_observation",
        lambda file_path, observation_context, use_mock=False: mock_analyze_file(
            file_path,
            modality="image",
            observation_context=observation_context,
        ),
    )
    monkeypatch.setattr("app.log_observation", lambda *args, **kwargs: None)

    warnings_text, result_json = run_birdai(
        file_obj,
        context.observation_date.isoformat(),
        context.observation_time.isoformat(timespec="seconds"),
        context.location_text,
        context.latitude,
        context.longitude,
    )

    payload = json.loads(result_json)

    assert warnings_text == "No warnings."
    assert payload["likely_species"][0]["common_name"] == "European Robin"
