import pytest
from pydantic import ValidationError

from birdai.schemas import BirdAIResult


def test_valid_birdai_result():
    data = {
        "likely_species": [
            {
                "common_name": "European Robin",
                "scientific_name": "Erithacus rubecula",
                "likelihood": "medium",
                "reason": "Small bird with orange breast."
            }
        ],
        "uncertainty": "medium",
        "uncertainty_reasons": ["partial occlusion", "single frame"],
        "ecological_plausibility": {
            "location": "Zurich, Switzerland",
            "season": "May",
            "plausibility": "high",
            "reason": "Common species in Switzerland."
        },
        "suggested_next_action": "Capture another frame or confirm with audio.",
        "modality": "image"
    }

    result = BirdAIResult.model_validate(data)

    assert result.likely_species[0].common_name == "European Robin"
    assert result.uncertainty == "medium"


def test_invalid_birdai_result_missing_fields():
    data = {
        "likely_species": [],
        "uncertainty": "medium"
    }

    with pytest.raises(ValidationError):
        BirdAIResult.model_validate(data)