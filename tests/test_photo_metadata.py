from pathlib import Path

from birdai.photo_metadata import extract_photo_coordinates


def test_extract_photo_coordinates_from_heic_fixture():
    coordinates = extract_photo_coordinates(
        str(Path(__file__).parent / "IMG_3219.HEIC")
    )

    assert coordinates is not None
    latitude, longitude = coordinates
    assert abs(latitude - 43.455289) < 0.001
    assert abs(longitude - (-3.731467)) < 0.001


def test_extract_photo_coordinates_returns_none_for_non_geotagged_fixture():
    coordinates = extract_photo_coordinates(
        str(Path(__file__).parent / "fixtures" / "sample.jpg")
    )

    assert coordinates is None
