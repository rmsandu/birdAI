from functools import lru_cache

import httpx

from birdai.config import (
    EBIRD_API_KEY,
    EBIRD_API_URL,
    EBIRD_LOOKBACK_DAYS,
    EBIRD_MAX_RESULTS,
    EBIRD_RADIUS_KM,
    HTTP_TIMEOUT_SECONDS,
)
from birdai.schemas import ObservationContext, ObservationEvidence


class EBirdServiceError(RuntimeError):
    pass


class EBirdClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = EBIRD_API_URL,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or EBIRD_API_KEY
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client

    def _client(self) -> tuple[httpx.Client, bool]:
        if self.http_client is not None:
            return self.http_client, False
        return httpx.Client(timeout=HTTP_TIMEOUT_SECONDS), True

    def _request(self, path: str, *, params: dict | None = None):
        if not self.api_key:
            raise EBirdServiceError("EBIRD_API_KEY is not configured.")

        client, should_close = self._client()

        try:
            response = client.get(
                f"{self.base_url}{path}",
                params=params,
                headers={"X-eBirdApiToken": self.api_key},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise EBirdServiceError(f"eBird request failed: {exc}") from exc
        finally:
            if should_close:
                client.close()

    @lru_cache(maxsize=1)
    def taxonomy(self) -> list[dict]:
        return self._request(
            "/v2/ref/taxonomy/ebird",
            params={"fmt": "json", "locale": "en", "cat": "species"},
        )

    def resolve_species_code(
        self,
        common_name: str,
        scientific_name: str | None = None,
    ) -> tuple[str, str, str] | None:
        common_name_normalized = common_name.strip().lower()
        scientific_name_normalized = (scientific_name or "").strip().lower()
        taxonomy = self.taxonomy()

        if scientific_name_normalized:
            for item in taxonomy:
                if (
                    item.get("sciName", "").strip().lower()
                    == scientific_name_normalized
                ):
                    return item["speciesCode"], item["comName"], item.get("sciName", "")

        for item in taxonomy:
            if (
                item.get("comName", "").strip().lower() == common_name_normalized
            ):
                return item["speciesCode"], item["comName"], item.get("sciName", "")

        return None

    def recent_observations_for_species(
        self,
        species_code: str,
        observation_context: ObservationContext,
    ) -> ObservationEvidence:
        if (
            observation_context.latitude is None
            or observation_context.longitude is None
        ):
            raise EBirdServiceError("Coordinates are required for eBird geo queries.")

        payload = self._request(
            f"/v2/data/obs/geo/recent/{species_code}",
            params={
                "lat": observation_context.latitude,
                "lng": observation_context.longitude,
                "back": EBIRD_LOOKBACK_DAYS,
                "dist": EBIRD_RADIUS_KM,
                "maxResults": EBIRD_MAX_RESULTS,
            },
        )

        if not payload:
            return ObservationEvidence(
                source="ebird",
                recent_observation_count=0,
                lookback_days=EBIRD_LOOKBACK_DAYS,
                species_code=species_code,
                summary=(
                    "No recent eBird observations were found within the configured "
                    "distance and lookback window."
                ),
            )

        last_observation = payload[0]
        count = len(payload)
        last_date = last_observation.get("obsDt")

        return ObservationEvidence(
            source="ebird",
            recent_observation_count=count,
            lookback_days=EBIRD_LOOKBACK_DAYS,
            species_code=species_code,
            last_observation_date=last_date,
            summary=(
                f"eBird reported {count} recent observations in the last "
                f"{EBIRD_LOOKBACK_DAYS} days near this location."
            ),
        )
