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


def test_detect_video_from_file_content():
    detected = detect_file_type(str(FIXTURES / "sample.mp4"))

    assert detected.modality == "video"
    assert detected.mime_type == "video/mp4"


def test_detect_quicktime_and_webm_video(tmp_path):
    mov_file = tmp_path / "clip.mov"
    mov_file.write_bytes(b"\x00\x00\x00\x14ftypqt  \x00\x00\x02\x00qt  ")
    assert detect_file_type(str(mov_file)).mime_type == "video/quicktime"
    assert detect_file_type(str(mov_file)).modality == "video"

    webm_file = tmp_path / "clip.webm"
    webm_file.write_bytes(b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01")
    assert detect_file_type(str(webm_file)).mime_type == "video/webm"
    assert detect_file_type(str(webm_file)).modality == "video"


def test_detect_heic_image_from_file_content():
    detected = detect_file_type(str(Path(__file__).parent / "IMG_3219.HEIC"))

    assert detected.modality == "image"
    assert detected.mime_type == "image/heic"


def test_reject_renamed_non_media_file():
    assert infer_modality(str(FIXTURES / "not-really-jpg.jpg")) == "unknown"
