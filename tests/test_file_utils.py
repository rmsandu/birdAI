from pathlib import Path

from birdai.file_utils import detect_file_type, infer_modality


FIXTURES = Path(__file__).parent / "fixtures"


def test_detect_image_from_file_content():
    detected = detect_file_type(str(FIXTURES / "sample.jpg"))

    assert detected.modality == "image"
    assert detected.mime_type == "image/jpeg"


def test_detect_audio_from_file_content():
    detected = detect_file_type(str(FIXTURES / "sample.wav"))

    assert detected.modality == "audio"
    assert detected.mime_type == "audio/wav"


def test_reject_video_from_file_content():
    detected = detect_file_type(str(FIXTURES / "sample.mp4"))

    assert detected.modality == "unknown"
    assert detected.mime_type == "application/octet-stream"


def test_reject_renamed_non_media_file():
    assert infer_modality(str(FIXTURES / "not-really-jpg.jpg")) == "unknown"
