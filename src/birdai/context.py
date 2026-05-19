from datetime import datetime

from birdai.config import (
    BIRDAI_DEFAULT_LATITUDE,
    BIRDAI_DEFAULT_LONGITUDE,
    BIRDAI_LOCATION,
)
from birdai.schemas import ObservationContext


def get_local_now() -> datetime:
    return datetime.now().astimezone()


def get_default_observation_context() -> ObservationContext:
    now = get_local_now()
    source = "config_default" if BIRDAI_LOCATION else "user_input"

    return ObservationContext(
        observation_date=now.date(),
        observation_time=now.time().replace(microsecond=0),
        location_text=BIRDAI_LOCATION,
        latitude=BIRDAI_DEFAULT_LATITUDE,
        longitude=BIRDAI_DEFAULT_LONGITUDE,
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


def resolve_observation_context(
    observation_context: ObservationContext,
) -> tuple[ObservationContext, list[str]]:
    if (
        observation_context.latitude is not None
        and observation_context.longitude is not None
    ):
        return observation_context.model_copy(
            update={"location_source": "manual_coordinates"}
        ), []

    return observation_context, [
        "No coordinates were provided. Skipping eBird enrichment."
    ]
