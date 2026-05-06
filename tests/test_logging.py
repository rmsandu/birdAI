import pandas as pd

from birdai.mock_analyzer import mock_analyze_file
from birdai.logging_utils import log_observation


def test_log_observation(tmp_path):
    log_path = tmp_path / "observations.csv"

    result = mock_analyze_file("sample.jpg", modality="image")
    log_observation("sample.jpg", result, log_path=str(log_path))

    df = pd.read_csv(log_path)

    assert len(df) == 1
    assert df.iloc[0]["top_common_name"] == "European Robin"
    assert df.iloc[0]["modality"] == "image"