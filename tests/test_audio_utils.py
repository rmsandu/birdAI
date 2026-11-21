from pathlib import Path

from birdai.audio_utils import inspect_audio_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_inspect_audio_file_wav():
    wav_path = str(FIXTURES / "sample.wav")
    info = inspect_audio_file(wav_path)

    assert info["format"] == "wav"
    assert info["file_size_bytes"] > 0
