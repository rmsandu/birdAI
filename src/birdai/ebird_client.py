from functools import lru_cache
import math

import httpx

from birdai.config import (
    EBIRD_API_KEY,
    EBIRD_API_URL,
    EBIRD_LOOKBACK_DAYS,
    EBIRD_MAX_RESULTS,
    EBIRD_RADIUS_KM,
    HTTP_TIMEOUT_SECONDS,
)
from birdai.schemas import ObservationContext, ObservationEvidence, SightingItem
from birdai.species_search import SEARCH_LOCALES, SpeciesNames


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance in kilometers between two points."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(r * c, 2)


def sort_sightings(sightings: list[SightingItem]) -> list[SightingItem]:
    """Sort closest first; among equal distances, most recent first.

    Relies on ``observed_at`` being an ISO-like "YYYY-MM-DD HH:MM" string so that
    lexical order matches chronological order.
    """
    by_date_desc = sorted(sightings, key=lambda s: s.observed_at, reverse=True)
    return sorted(by_date_desc, key=lambda s: s.distance_km)  # stable sort keeps date order


class EBirdServiceError(RuntimeError):
    pass


# (species code, locale) -> taxonomy entry; shared across clients, names rarely change
_TAXONOMY_NAME_CACHE: dict[tuple[str, str], dict] = {}


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

    def species_names(
        self,
        species_codes: set[str] | list[str],
        locales: tuple[str, ...] = SEARCH_LOCALES,
    ) -> list[SpeciesNames]:
        """Localized common names (plus scientific and family name) for these species."""
        codes = sorted({c for c in species_codes if c})
        for locale in locales:
            missing = [c for c in codes if (c, locale) not in _TAXONOMY_NAME_CACHE]
            for start in range(0, len(missing), 200):
                chunk = missing[start : start + 200]
                payload = self._request(
                    "/v2/ref/taxonomy/ebird",
                    params={"fmt": "json", "locale": locale, "species": ",".join(chunk)},
                )
                for item in payload or []:
                    _TAXONOMY_NAME_CACHE[(item["speciesCode"], locale)] = item

        result = []
        for code in codes:
            entries = {loc: _TAXONOMY_NAME_CACHE.get((code, loc)) for loc in locales}
            any_entry = next((e for e in entries.values() if e), None)
            if any_entry is None:
                continue
            result.append(
                SpeciesNames(
                    code=code,
                    scientific_name=any_entry.get("sciName", ""),
                    family=any_entry.get("familyComName", ""),
                    names={loc: e["comName"] for loc, e in entries.items() if e and e.get("comName")},
                )
            )
        return result

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

    def _sightings_in_radius(
        self,
        path: str,
        lat: float,
        lng: float,
        dist_km: int,
        back_days: int,
        max_results: int | None,
        notable: bool,
    ) -> list[SightingItem]:
        dist_km = min(max(dist_km, 1), 50)
        back_days = min(max(back_days, 1), 30)

        params = {"lat": lat, "lng": lng, "dist": dist_km, "back": back_days}
        if max_results is not None:  # None = everything eBird has for the area
            params["maxResults"] = max_results
        payload = self._request(path, params=params)

        sightings: list[SightingItem] = []
        for item in payload or []:
            obs_lat = item.get("lat")
            obs_lng = item.get("lng")
            if obs_lat is None or obs_lng is None:
                continue
            distance = haversine_distance_km(lat, lng, obs_lat, obs_lng)
            if distance > dist_km:
                continue

            sub_id = item.get("subId")
            sightings.append(
                SightingItem(
                    species_common_name=item.get("comName", "Unknown"),
                    species_code=item.get("speciesCode"),
                    species_scientific_name=item.get("sciName"),
                    count=item.get("howMany") or 1,
                    observed_at=item.get("obsDt", ""),
                    location_name=item.get("locName", "Nearby Location"),
                    latitude=obs_lat,
                    longitude=obs_lng,
                    distance_km=distance,
                    source="ebird",
                    checklist_url=f"https://ebird.org/checklist/{sub_id}" if sub_id else None,
                    notable=notable,
                )
            )

        return sort_sightings(sightings)

    def recent_sightings_in_radius(
        self,
        lat: float,
        lng: float,
        dist_km: int = 15,
        back_days: int = 7,
        max_results: int | None = 40,
    ) -> list[SightingItem]:
        return self._sightings_in_radius(
            "/v2/data/obs/geo/recent", lat, lng, dist_km, back_days, max_results, notable=False
        )

    def recent_species_sightings_in_radius(
        self,
        species_code: str,
        lat: float,
        lng: float,
        dist_km: int = 15,
        back_days: int = 7,
        max_results: int = 40,
    ) -> list[SightingItem]:
        return self._sightings_in_radius(
            f"/v2/data/obs/geo/recent/{species_code}",
            lat, lng, dist_km, back_days, max_results, notable=False,
        )

    def recent_notable_sightings_in_radius(
        self,
        lat: float,
        lng: float,
        dist_km: int = 15,
        back_days: int = 7,
        max_results: int = 40,
    ) -> list[SightingItem]:
        return self._sightings_in_radius(
            "/v2/data/obs/geo/recent/notable", lat, lng, dist_km, back_days, max_results, notable=True
        )
