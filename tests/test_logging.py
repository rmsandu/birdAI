import json

import pandas as pd

from birdai.context import get_default_observation_context
from birdai.logging_utils import log_observation
from birdai.mock_analyzer import mock_analyze_file
from birdai.schemas import LocalClassifierPrediction, LocalClassifierResult


def test_log_observation(tmp_path):
    log_path = tmp_path / "observations.csv"
    context = get_default_observation_context()

    result = mock_analyze_file(
        "sample.jpg",
        modality="image",
        observation_context=context,
    )
    log_observation("sample.jpg", result, log_path=str(log_path))

    df = pd.read_csv(log_path)

    assert len(df) == 1
    assert df.iloc[0]["top_common_name"] == "European Robin"
    assert df.iloc[0]["modality"] == "image"
    assert df.iloc[0]["top_confidence_probability"] == 76

    stored_result = json.loads(df.iloc[0]["result_json"])
    assert stored_result["observation_context"]["location_text"] == context.location_text


def test_log_observation_includes_local_classifier_columns(tmp_path):
    log_path = tmp_path / "observations.csv"
    context = get_default_observation_context()

    result = mock_analyze_file(
        "sample.jpg",
        modality="image",
        observation_context=context,
    ).model_copy(
        update={
            "local_classifier": LocalClassifierResult(
                source="local_classifier",
                model_version="convnext_tiny-v1",
                predictions=[
                    LocalClassifierPrediction(
                        species_name="European Robin",
                        scientific_name="Erithacus rubecula",
                        confidence_probability=90,
                    )
                ],
                summary="European Robin at 90%.",
            )
        }
    )
    log_observation("sample.jpg", result, log_path=str(log_path))

    df = pd.read_csv(log_path)

    assert df.iloc[0]["local_classifier_top_name"] == "European Robin"
    assert df.iloc[0]["local_classifier_confidence"] == 90
