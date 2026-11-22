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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


def _get_model_fallbacks() -> list[str]:
    env_val = os.getenv("GEMINI_FALLBACK_MODELS")
    if env_val:
        return [m.strip() for m in env_val.split(",") if m.strip()]
    candidates = [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ]
    return [m for m in candidates if m != GEMINI_MODEL]


# Fallback chain tried in order when the primary model returns 404 (deprecated/unavailable)
GEMINI_MODEL_FALLBACKS = _get_model_fallbacks()

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

CLASSIFIER_SERVICE_URL = os.getenv("CLASSIFIER_SERVICE_URL", "http://localhost:8000")
CLASSIFIER_TOP_K = _get_optional_int("CLASSIFIER_TOP_K", 3)
CLASSIFIER_TIMEOUT_SECONDS = _get_optional_int("CLASSIFIER_TIMEOUT_SECONDS", 10)
CLASSIFIER_ENABLED = os.getenv("CLASSIFIER_ENABLED", "true").lower() == "true"

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/birdai.db")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "birdai-dev-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = _get_optional_int(
    "JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7
)
