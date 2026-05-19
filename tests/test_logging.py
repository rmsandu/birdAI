import json

import pandas as pd

from birdai.context import get_default_observation_context
from birdai.logging_utils import log_observation
from birdai.mock_analyzer import mock_analyze_file


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
