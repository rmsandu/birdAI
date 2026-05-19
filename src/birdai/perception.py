from birdai.file_utils import infer_modality
from birdai.gemini_client import analyze_file as analyze_file_with_gemini
from birdai.mock_analyzer import mock_analyze_file
from birdai.schemas import BirdAIResult


def analyze_observation(file_path: str, use_mock: bool = True) -> BirdAIResult:
    modality = infer_modality(file_path)

    if modality == "unknown":
        raise ValueError(
            "Unsupported file type. Please upload an image, audio recording, or short video."
        )

    if use_mock:
        return mock_analyze_file(file_path=file_path, modality=modality)

    gemini_result = analyze_file_with_gemini(file_path=file_path, modality=modality)
    if "modality" not in gemini_result:
        gemini_result["modality"] = modality

    return BirdAIResult.model_validate(gemini_result)