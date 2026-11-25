from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DetectedFileType:
    modality: str
    mime_type: str


def _read_header(file_path: str, size: int = 4096) -> bytes:
    with Path(file_path).open("rb") as file_handle:
        return file_handle.read(size)


def _detect_image(header: bytes) -> DetectedFileType | None:
    if header.startswith(b"\xff\xd8\xff"):
        return DetectedFileType(modality="image", mime_type="image/jpeg")

    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return DetectedFileType(modality="image", mime_type="image/png")

    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return DetectedFileType(modality="image", mime_type="image/webp")

    if len(header) >= 12 and header[4:8] == b"ftyp":
        brand = header[8:12]
        if brand in {
            b"heic",
            b"heix",
            b"hevc",
            b"hevx",
            b"heim",
            b"heis",
        }:
            return DetectedFileType(modality="image", mime_type="image/heic")

    return None


def _detect_audio(header: bytes) -> DetectedFileType | None:
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return DetectedFileType(modality="audio", mime_type="audio/wav")

    if header.startswith(b"ID3") or (
        len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0
    ):
        return DetectedFileType(modality="audio", mime_type="audio/mpeg")

    if header.startswith(b"fLaC"):
        return DetectedFileType(modality="audio", mime_type="audio/flac")

    if header.startswith(b"OggS"):
        return DetectedFileType(modality="audio", mime_type="audio/ogg")

    return None


def _detect_video(header: bytes) -> DetectedFileType | None:
    if len(header) >= 12 and header[4:8] == b"ftyp":
        brand = header[8:12]
        if brand == b"qt  ":
            return DetectedFileType(modality="video", mime_type="video/quicktime")
        if brand in {
            b"isom",
            b"iso2",
            b"mp41",
            b"mp42",
            b"M4V ",
            b"avc1",
            b"3gp4",
            b"3gp5",
            b"dash",
            b"MSNV",
        }:
            return DetectedFileType(modality="video", mime_type="video/mp4")

    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return DetectedFileType(modality="video", mime_type="video/webm")

    return None


def detect_file_type(file_path: str) -> DetectedFileType:
    header = _read_header(file_path)

    for detector in (_detect_image, _detect_audio, _detect_video):
        detected = detector(header)
        if detected is not None:
            return detected

    return DetectedFileType(
        modality="unknown",
        mime_type="application/octet-stream",
    )


def infer_modality(file_path: str) -> str:
    return detect_file_type(file_path).modality
