import wave
from pathlib import Path


def inspect_audio_file(file_path: str) -> dict:
    """Extract standard audio properties (duration, sample rate, channels, format).

    Safe fallback logic ensures it works without failing if ffmpeg is missing for
    compressed files.
    """
    path = Path(file_path)
    file_size = path.stat().st_size if path.exists() else 0
    info = {
        "format": path.suffix.lower().lstrip("."),
        "file_size_bytes": file_size,
        "duration_seconds": None,
        "sample_rate": None,
        "channels": None,
    }

    # 1. Try native wave module first for standard WAV files
    try:
        with wave.open(str(path), "rb") as wf:
            channels = wf.getnchannels()
            sample_rate = wf.getframerate()
            frames = wf.getnframes()
            duration = frames / float(sample_rate) if sample_rate > 0 else 0.0
            info.update({
                "duration_seconds": round(duration, 2),
                "sample_rate": sample_rate,
                "channels": channels,
            })
            return info
    except Exception:
        pass

    # 2. Try pydub for non-WAV formats if available
    try:
        from pydub import AudioSegment

        segment = AudioSegment.from_file(str(path))
        info.update({
            "duration_seconds": round(len(segment) / 1000.0, 2),
            "sample_rate": segment.frame_rate,
            "channels": segment.channels,
        })
    except Exception:
        # Graceful fallback: return format and file size
        pass

    return info
