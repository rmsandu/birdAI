from birdai.file_utils import infer_modality


def test_infer_image_modality():
    assert infer_modality("robin.jpg") == "image"
    assert infer_modality("bird.PNG") == "image"


def test_infer_audio_modality():
    assert infer_modality("merlin_recording.wav") == "audio"
    assert infer_modality("blackbird.m4a") == "audio"


def test_infer_video_modality():
    assert infer_modality("birdfy_clip.mp4") == "video"


def test_unknown_modality():
    assert infer_modality("notes.txt") == "unknown"