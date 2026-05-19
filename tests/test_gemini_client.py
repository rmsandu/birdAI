import pytest

from birdai.gemini_client import (
    extract_response_text,
    normalize_birdai_result,
    parse_gemini_json,
)
from birdai.schemas import ObservationContext


def _observation_context() -> ObservationContext:
    return ObservationContext.model_validate(
        {
            "observation_date": "2026-05-19",
            "observation_time": "10:23:51",
            "location_text": "Zurich, Switzerland",
            "latitude": 47.3769,
            "longitude": 8.5417,
            "location_source": "manual_coordinates",
            "timezone_name": "Europe/Zurich",
        }
    )


def test_parse_gemini_json_rejects_malformed_json():
    with pytest.raises(ValueError, match="malformed JSON"):
        parse_gemini_json("{not valid json")


def test_extract_response_text_prefers_interaction_output_text():
    class FakeInteraction:
        output_text = '{"ok": true}'

    assert extract_response_text(FakeInteraction()) == '{"ok": true}'


def test_normalize_birdai_result_keeps_top_candidates_without_forcing_single_result():
    payload = {
        "likely_species": [
            {
                "common_name": "European Robin",
                "scientific_name": "Erithacus rubecula",
                "confidence_probability": 100,
                "reason": "Clear identifying features.",
            },
            {
                "common_name": "Common Redstart",
                "scientific_name": "Phoenicurus phoenicurus",
                "confidence_probability": 41,
                "reason": "Possible but less likely.",
            },
        ],
        "uncertainty": "low",
        "uncertainty_reasons": ["clear image"],
        "ecological_plausibility": {
            "location": "Zurich, Switzerland",
            "season": "Spring",
            "plausibility": "high",
            "reason": "Matches common local species.",
        },
        "suggested_next_action": "No further action needed.",
    }

    result = normalize_birdai_result(
        payload,
        observation_context=_observation_context(),
        modality="image",
    )

    assert len(result.likely_species) == 2
    assert result.likely_species[0].confidence_probability == 100


def test_normalize_birdai_result_sorts_and_limits_to_top_three():
    payload = {
        "likely_species": [
            {
                "common_name": "Species 1",
                "scientific_name": "One one",
                "confidence_probability": 60,
                "reason": "Reason 1",
            },
            {
                "common_name": "Species 2",
                "scientific_name": "Two two",
                "confidence_probability": 85,
                "reason": "Reason 2",
            },
            {
                "common_name": "Species 3",
                "scientific_name": "Three three",
                "confidence_probability": 40,
                "reason": "Reason 3",
            },
            {
                "common_name": "Species 4",
                "scientific_name": "Four four",
                "confidence_probability": 70,
                "reason": "Reason 4",
            },
        ],
        "uncertainty": "medium",
        "uncertainty_reasons": ["partial view"],
        "ecological_plausibility": {
            "location": "Zurich, Switzerland",
            "season": "Spring",
            "plausibility": "medium",
            "reason": "Possible migration overlap.",
        },
        "suggested_next_action": "Capture another angle.",
    }

    result = normalize_birdai_result(
        payload,
        observation_context=_observation_context(),
        modality="image",
    )

    assert [candidate.common_name for candidate in result.likely_species] == [
        "Species 2",
        "Species 4",
        "Species 1",
    ]
