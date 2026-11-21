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


def test_generate_content_with_fallback_success_first_try():
    from unittest.mock import MagicMock
    from birdai.gemini_client import generate_content_with_fallback

    client = MagicMock()
    expected_response = MagicMock(text="success")
    client.models.generate_content.return_value = expected_response

    res = generate_content_with_fallback(
        client,
        contents=["test"],
        primary_model="gemini-3.5-flash-lite",
        fallback_models=["gemini-2.5-flash"],
    )

    assert res == expected_response
    assert client.models.generate_content.call_count == 1
    assert client.models.generate_content.call_args.kwargs["model"] == "gemini-3.5-flash-lite"


def test_generate_content_with_fallback_switches_on_404():
    from unittest.mock import MagicMock
    from google.genai import errors
    from birdai.gemini_client import generate_content_with_fallback

    client = MagicMock()
    not_found_err = errors.ClientError(
        404,
        {"error": {"code": 404, "message": "This model models/gemini-3.5-flash-lite is no longer available."}}
    )
    fallback_response = MagicMock(text="fallback success")

    client.models.generate_content.side_effect = [not_found_err, fallback_response]

    res = generate_content_with_fallback(
        client,
        contents=["test"],
        primary_model="gemini-3.5-flash-lite",
        fallback_models=["gemini-2.5-flash"],
    )

    assert res == fallback_response
    assert client.models.generate_content.call_count == 2
    # Verify second call used the fallback model
    second_call_model = client.models.generate_content.call_args_list[1].kwargs["model"]
    assert second_call_model == "gemini-2.5-flash"


def test_generate_content_with_fallback_raises_when_all_fail():
    from unittest.mock import MagicMock
    from google.genai import errors
    from birdai.gemini_client import generate_content_with_fallback

    client = MagicMock()
    not_found_err = errors.ClientError(
        404,
        {"error": {"code": 404, "message": "Model not found."}}
    )
    client.models.generate_content.side_effect = not_found_err

    with pytest.raises(errors.ClientError) as exc_info:
        generate_content_with_fallback(
            client,
            contents=["test"],
            primary_model="gemini-3.5-flash-lite",
            fallback_models=["gemini-2.5-flash"],
        )

    assert exc_info.value.code == 404
    assert client.models.generate_content.call_count == 2


def test_generate_content_with_fallback_does_not_catch_unrelated_errors():
    from unittest.mock import MagicMock
    from google.genai import errors
    from birdai.gemini_client import generate_content_with_fallback

    client = MagicMock()
    auth_err = errors.ClientError(
        401,
        {"error": {"code": 401, "message": "API key invalid."}}
    )
    client.models.generate_content.side_effect = auth_err

    with pytest.raises(errors.ClientError) as exc_info:
        generate_content_with_fallback(
            client,
            contents=["test"],
            primary_model="gemini-3.5-flash-lite",
            fallback_models=["gemini-2.5-flash"],
        )

    assert exc_info.value.code == 401
    assert client.models.generate_content.call_count == 1

