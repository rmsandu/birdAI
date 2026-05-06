from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


def infer_modality(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()

    if suffix in IMAGE_EXTENSIONS:
        return "image"

    if suffix in AUDIO_EXTENSIONS:
        return "audio"

    if suffix in VIDEO_EXTENSIONS:
        return "video"

    return "unknown"