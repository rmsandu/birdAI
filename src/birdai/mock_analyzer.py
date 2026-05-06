from birdai.schemas import BirdAIResult


def mock_analyze_file(file_path: str, modality: str) -> BirdAIResult:
    return BirdAIResult.model_validate(
        {
            "likely_species": [
                {
                    "common_name": "European Robin",
                    "scientific_name": "Erithacus rubecula",
                    "likelihood": "medium",
                    "reason": "Mock result for MVP testing."
                }
            ],
            "uncertainty": "medium",
            "uncertainty_reasons": [
                "mock analyzer does not inspect real image/audio content"
            ],
            "ecological_plausibility": {
                "location": "Zurich, Switzerland",
                "season": "May",
                "plausibility": "high",
                "reason": "European Robin is common in Switzerland."
            },
            "suggested_next_action": "Capture another image or add audio confirmation.",
            "modality": modality
        }
    )