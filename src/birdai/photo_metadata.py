from fractions import Fraction
from pathlib import Path

from PIL import ExifTags, Image

try:
    from pillow_heif import register_heif_opener
except ImportError:  # pragma: no cover - exercised only when dependency is absent
    register_heif_opener = None


if register_heif_opener is not None:
    register_heif_opener()


GPS_TAG_ID = next(
    tag_id for tag_id, tag_name in ExifTags.TAGS.items() if tag_name == "GPSInfo"
)


def _rational_to_float(value) -> float:
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        return float(value.numerator) / float(value.denominator)
    return float(Fraction(value))


def _dms_to_decimal(values, reference: str) -> float:
    degrees = _rational_to_float(values[0])
    minutes = _rational_to_float(values[1])
    seconds = _rational_to_float(values[2])
    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)

    if reference.upper() in {"S", "W"}:
        decimal *= -1.0

    return decimal


def extract_photo_coordinates(file_path: str) -> tuple[float, float] | None:
    try:
        with Image.open(Path(file_path)) as image:
            exif = image.getexif()
    except Exception:
        return None

    if not exif:
        return None

    gps_info = exif.get_ifd(GPS_TAG_ID)
    if not gps_info:
        return None

    latitude_values = gps_info.get(2)
    latitude_ref = gps_info.get(1)
    longitude_values = gps_info.get(4)
    longitude_ref = gps_info.get(3)

    if not (
        latitude_values
        and latitude_ref
        and longitude_values
        and longitude_ref
    ):
        return None

    latitude = _dms_to_decimal(latitude_values, latitude_ref)
    longitude = _dms_to_decimal(longitude_values, longitude_ref)
    return latitude, longitude
