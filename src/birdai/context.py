from datetime import datetime

import httpx

from birdai.config import (
    BIRDAI_DEFAULT_LATITUDE,
    BIRDAI_DEFAULT_LONGITUDE,
    BIRDAI_LOCATION,
    GEOCODING_URL,
    GEOCODING_USER_AGENT,
    HTTP_TIMEOUT_SECONDS,
)
from birdai.file_utils import DetectedFileType, detect_file_type
from birdai.photo_metadata import extract_photo_coordinates
from birdai.schemas import ObservationContext


def get_local_now() -> datetime:
    return datetime.now().astimezone()


def get_default_observation_context() -> ObservationContext:
    now = get_local_now()
    source = "config_default" if BIRDAI_LOCATION else "user_input"
    latitude = BIRDAI_DEFAULT_LATITUDE
    longitude = BIRDAI_DEFAULT_LONGITUDE

    coordinates_are_placeholder = latitude == 0.0 and longitude == 0.0
    should_geocode_default_location = (
        bool(BIRDAI_LOCATION)
        and (
            latitude is None
            or longitude is None
            or coordinates_are_placeholder
        )
    )

    if should_geocode_default_location:
        try:
            coordinates = geocode_location(BIRDAI_LOCATION)
        except httpx.HTTPError:
            coordinates = None

        if coordinates is not None:
            latitude, longitude = coordinates
            source = "geocoded_location"

    return ObservationContext(
        observation_date=now.date(),
        observation_time=now.time().replace(microsecond=0),
        location_text=BIRDAI_LOCATION,
        latitude=latitude,
        longitude=longitude,
        location_source=source,
        timezone_name=str(now.tzinfo) if now.tzinfo else None,
    )


def build_observation_context(
    observation_date: str,
    observation_time: str,
    location_text: str,
    latitude: float | None,
    longitude: float | None,
) -> ObservationContext:
    default_context = get_default_observation_context()

    return ObservationContext.model_validate(
        {
            "observation_date": observation_date or default_context.observation_date.isoformat(),
            "observation_time": observation_time or default_context.observation_time.isoformat(),
            "location_text": location_text or default_context.location_text,
            "latitude": latitude,
            "longitude": longitude,
            "location_source": "user_input",
            "timezone_name": default_context.timezone_name,
        }
    )


def describe_season(observation_context: ObservationContext) -> str:
    month = observation_context.observation_date.month

    if month in (12, 1, 2):
        return "Winter"
    if month in (3, 4, 5):
        return "Spring"
    if month in (6, 7, 8):
        return "Summer"
    return "Autumn"


def geocode_location(
    location_text: str,
    *,
    http_client: httpx.Client | None = None,
) -> tuple[float, float] | None:
    client = http_client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    should_close = http_client is None

    try:
        response = client.get(
            GEOCODING_URL,
            params={
                "q": location_text,
                "format": "jsonv2",
                "limit": 1,
            },
            headers={"User-Agent": GEOCODING_USER_AGENT},
        )
        response.raise_for_status()
        payload = response.json()

        if not payload:
            return None

        first_match = payload[0]
        return float(first_match["lat"]), float(first_match["lon"])
    finally:
        if should_close:
            client.close()


def reverse_geocode_coordinates(
    latitude: float,
    longitude: float,
    *,
    http_client: httpx.Client | None = None,
) -> str | None:
    client = http_client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    should_close = http_client is None

    try:
        response = client.get(
            GEOCODING_URL.replace("/search", "/reverse"),
            params={
                "lat": latitude,
                "lon": longitude,
                "format": "jsonv2",
                "zoom": 14,
            },
            headers={"User-Agent": GEOCODING_USER_AGENT},
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("display_name")
    finally:
        if should_close:
            client.close()


def resolve_observation_context(
    observation_context: ObservationContext,
    *,
    file_path: str | None = None,
    detected_file: DetectedFileType | None = None,
    http_client: httpx.Client | None = None,
) -> tuple[ObservationContext, list[str]]:
    warnings: list[str] = []
    if file_path is not None:
        media_type = detected_file or detect_file_type(file_path)
        if media_type.modality == "image":
            photo_coordinates = extract_photo_coordinates(file_path)
            if photo_coordinates is not None:
                latitude, longitude = photo_coordinates
                resolved_location_text = observation_context.location_text
                try:
                    reverse_geocoded_location = reverse_geocode_coordinates(
                        latitude,
                        longitude,
                        http_client=http_client,
                    )
                except httpx.HTTPError as exc:
                    warnings.append(
                        "Photo GPS metadata was found, but reverse geocoding failed. "
                        f"Keeping the existing location text. {exc}"
                    )
                else:
                    if reverse_geocoded_location:
                        resolved_location_text = reverse_geocoded_location
                return observation_context.model_copy(
                    update={
                        "location_text": resolved_location_text,
                        "latitude": latitude,
                        "longitude": longitude,
                        "location_source": "photo_exif",
                    }
                ), warnings
            warnings.append(
                "No GPS metadata was found in the uploaded photo. Using the location fields instead."
            )

    coordinates_are_placeholder = (
        observation_context.latitude == 0.0
        and observation_context.longitude == 0.0
    )

    if (
        observation_context.latitude is not None
        and observation_context.longitude is not None
        and not coordinates_are_placeholder
    ):
        return observation_context.model_copy(
            update={"location_source": "manual_coordinates"}
        ), []

    if coordinates_are_placeholder:
        warnings.append(
            "Coordinates 0.0, 0.0 look like a placeholder. Geocoding the location text instead."
        )

    if not observation_context.location_text.strip():
        return observation_context, [
            "No coordinates or location text were provided. Skipping eBird enrichment."
        ]

    try:
        coordinates = geocode_location(
            observation_context.location_text,
            http_client=http_client,
        )
    except httpx.HTTPError as exc:
        return observation_context, [
            f"Could not geocode location '{observation_context.location_text}': {exc}. "
            "Skipping eBird enrichment."
        ]

    if coordinates is None:
        return observation_context, [
            f"Could not geocode location '{observation_context.location_text}'. "
            "Skipping eBird enrichment."
        ]

    latitude, longitude = coordinates
    return observation_context.model_copy(
        update={
            "latitude": latitude,
            "longitude": longitude,
            "location_source": "geocoded_location",
        }
    ), warnings
