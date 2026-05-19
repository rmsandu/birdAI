from birdai.context import describe_season, get_default_observation_context
from birdai.schemas import BirdAIResult


def mock_analyze_file(
    file_path: str,
    modality: str,
    observation_context=None,
) -> BirdAIResult:
    context = observation_context or get_default_observation_context()

    return BirdAIResult.model_validate(
        {
            "observation_context": context.model_dump(mode="json"),
            "likely_species": [
                {
                    "common_name": "European Robin",
                    "scientific_name": "Erithacus rubecula",
                    "confidence_probability": 76,
                    "reason": "Mock result for MVP testing.",
                    "evidence": {
                        "source": "none",
                        "recent_observation_count": 0,
                        "lookback_days": 30,
                        "summary": "No recent-observation enrichment was requested.",
                    },
                }
            ],
            "uncertainty": "medium",
            "uncertainty_reasons": [
                "mock analyzer does not inspect real image or audio content"
            ],
            "ecological_plausibility": {
                "location": context.location_text,
                "season": describe_season(context),
                "plausibility": "high",
                "reason": "European Robin is common in Switzerland.",
            },
            "suggested_next_action": "Capture another image or add audio confirmation.",
            "modality": modality,
            "warnings": [],
        }
    )
