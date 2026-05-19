import os

from dotenv import load_dotenv

load_dotenv()


def _get_optional_float(name: str) -> float | None:
    value = os.getenv(name)
    if value in (None, ""):
        return None
    return float(value)


def _get_optional_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return int(value)


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

EBIRD_API_KEY = os.getenv("EBIRD_API_KEY")
EBIRD_API_URL = os.getenv("EBIRD_API_URL", "https://api.ebird.org")
EBIRD_LOOKBACK_DAYS = _get_optional_int("EBIRD_LOOKBACK_DAYS", 30)
EBIRD_RADIUS_KM = _get_optional_int("EBIRD_RADIUS_KM", 25)
EBIRD_MAX_RESULTS = _get_optional_int("EBIRD_MAX_RESULTS", 10)

BIRDAI_LOCATION = os.getenv("BIRDAI_LOCATION", "Zurich, Switzerland")
BIRDAI_DEFAULT_LATITUDE = _get_optional_float("BIRDAI_DEFAULT_LATITUDE")
BIRDAI_DEFAULT_LONGITUDE = _get_optional_float("BIRDAI_DEFAULT_LONGITUDE")

GEOCODING_URL = os.getenv(
    "BIRDAI_GEOCODING_URL",
    "https://nominatim.openstreetmap.org/search",
)
GEOCODING_USER_AGENT = os.getenv(
    "BIRDAI_GEOCODING_USER_AGENT",
    "BirdAI/0.1",
)
HTTP_TIMEOUT_SECONDS = _get_optional_int("BIRDAI_HTTP_TIMEOUT_SECONDS", 20)
