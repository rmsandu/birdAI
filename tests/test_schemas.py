import pytest
from pydantic import ValidationError

from birdai.schemas import BirdAIResult


def test_valid_birdai_result():
    data = {
        "observation_context": {
            "observation_date": "2026-05-19",
            "observation_time": "10:23:51",
            "location_text": "Zurich, Switzerland",
            "latitude": 47.3769,
            "longitude": 8.5417,
            "location_source": "manual_coordinates",
            "timezone_name": "Europe/Zurich",
        },
        "likely_species": [
            {
                "common_name": "European Robin",
                "scientific_name": "Erithacus rubecula",
                "confidence_probability": 82,
                "reason": "Small bird with orange breast.",
                "evidence": {
                    "source": "ebird",
                    "recent_observation_count": 3,
                    "lookback_days": 30,
                    "summary": "Recent local sightings were reported.",
                },
            }
        ],
        "uncertainty": "medium",
        "uncertainty_reasons": ["partial occlusion", "single frame"],
        "ecological_plausibility": {
            "location": "Zurich, Switzerland",
            "season": "Spring",
            "plausibility": "high",
            "reason": "Common species in Switzerland.",
        },
        "suggested_next_action": "Capture another frame or confirm with audio.",
        "modality": "image",
        "warnings": [],
    }

    result = BirdAIResult.model_validate(data)

    assert result.likely_species[0].common_name == "European Robin"
    assert result.likely_species[0].confidence_probability == 82


def test_invalid_birdai_result_missing_fields():
    data = {
        "likely_species": [],
        "uncertainty": "medium",
    }

    with pytest.raises(ValidationError):
        BirdAIResult.model_validate(data)
