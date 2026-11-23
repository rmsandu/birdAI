import logging
from typing import Optional

from birdai.config import (
    BIRDAI_DEFAULT_LATITUDE,
    BIRDAI_DEFAULT_LONGITUDE,
    BIRDAI_LOCATION,
)
from birdai.context import geocode_location
from birdai.ebird_client import EBirdClient, sort_sightings
from birdai.ornitho_client import OrnithoClient, resolve_hotspot_coordinates
from birdai.schemas import SightingItem

logger = logging.getLogger(__name__)

SOURCE_LABELS = {"ebird": "eBird", "ornitho.ch": "ornitho.ch"}


def _unavailable_reason(exc: Exception) -> str:
    if "not configured" in str(exc).lower():
        return "not configured"
    return "could not be reached"


def describe_unavailable_sources(unavailable: dict[str, str]) -> Optional[str]:
    """User-facing notice explaining which sources failed, or None if all worked."""
    if not unavailable:
        return None
    if set(unavailable) >= set(SOURCE_LABELS):
        return (
            "**Note:** I couldn't check for sightings right now — "
            + "; ".join(f"{SOURCE_LABELS[src]} {reason}" for src, reason in unavailable.items())
            + ". This doesn't mean there are no birds; please try again later."
        )
    working = [label for src, label in SOURCE_LABELS.items() if src not in unavailable]
    failed = "; ".join(f"{SOURCE_LABELS[src]} {reason}" for src, reason in unavailable.items())
    return (
        f"**Note:** results are incomplete — {failed}, "
        f"so these sightings come from {' and '.join(working)} only."
    )


class SightingsAggregator:
    def __init__(
        self,
        *,
        ebird_client: Optional[EBirdClient] = None,
        ornitho_client: Optional[OrnithoClient] = None,
    ):
        self.ebird_client = ebird_client or EBirdClient()
        self.ornitho_client = ornitho_client or OrnithoClient()

    def resolve_center_coordinates(
        self,
        location_name: Optional[str] = None,
        user_lat: Optional[float] = None,
        user_lng: Optional[float] = None,
    ) -> tuple[float, float, str]:
        # 1. Use direct coordinates if provided
        if user_lat is not None and user_lng is not None:
            return user_lat, user_lng, location_name or f"GPS ({user_lat:.4f}, {user_lng:.4f})"

        # 2. Check known Swiss hotspots (zero network required)
        if location_name and location_name.strip():
            known = resolve_hotspot_coordinates(location_name.strip())
            if known is not None:
                return known[0], known[1], location_name.strip()

            # 3. Geocode custom location string if provided
            try:
                coords = geocode_location(location_name.strip())
                if coords is not None:
                    return coords[0], coords[1], location_name.strip()
            except Exception as exc:
                logger.warning("Geocoding failed for '%s': %s", location_name, exc)

        # 4. Fallback to default configured location
        default_loc = BIRDAI_LOCATION or "Zurich, Switzerland"
        default_lat = BIRDAI_DEFAULT_LATITUDE or 47.3769
        default_lng = BIRDAI_DEFAULT_LONGITUDE or 8.5417
        return default_lat, default_lng, default_loc

    def search_sightings(
        self,
        location_name: Optional[str] = None,
        radius_km: int = 15,
        species_name: Optional[str] = None,
        back_days: int = 7,
        user_lat: Optional[float] = None,
        user_lng: Optional[float] = None,
    ) -> tuple[list[SightingItem], dict]:
        # Clamp radius to sensible bounds
        radius_km = min(max(int(radius_km), 1), 50)
        back_days = min(max(int(back_days), 1), 30)

        lat, lng, resolved_loc = self.resolve_center_coordinates(
            location_name=location_name,
            user_lat=user_lat,
            user_lng=user_lng,
        )

        all_sightings: list[SightingItem] = []
        unavailable: dict[str, str] = {}

        # --- 1. Query eBird ---
        try:
            if species_name and species_name.strip():
                clean_species = species_name.strip()
                code_res = self.ebird_client.resolve_species_code(clean_species)
                if code_res:
                    sp_code = code_res[0]
                    ebird_results = self.ebird_client.recent_species_sightings_in_radius(
                        species_code=sp_code,
                        lat=lat,
                        lng=lng,
                        dist_km=radius_km,
                        back_days=back_days,
                    )
                else:
                    ebird_results = self.ebird_client.recent_sightings_in_radius(
                        lat=lat,
                        lng=lng,
                        dist_km=radius_km,
                        back_days=back_days,
                    )
                    ebird_results = [
                        s for s in ebird_results
                        if clean_species.lower() in s.species_common_name.lower()
                        or (s.species_scientific_name and clean_species.lower() in s.species_scientific_name.lower())
                    ]
            else:
                ebird_results = self.ebird_client.recent_sightings_in_radius(
                    lat=lat,
                    lng=lng,
                    dist_km=radius_km,
                    back_days=back_days,
                )
            all_sightings.extend(ebird_results)
        except Exception as exc:
            logger.warning("eBird query encountered an error (%s); continuing with ornitho.", exc)
            unavailable["ebird"] = _unavailable_reason(exc)

        # --- 2. Query ornitho.ch ---
        try:
            ornitho_results = self.ornitho_client.get_recent_sightings(
                lat=lat,
                lng=lng,
                dist_km=radius_km,
                species_name=species_name,
            )
            all_sightings.extend(ornitho_results)
        except Exception as exc:
            logger.warning("ornitho.ch query encountered an error (%s); continuing.", exc)
            unavailable["ornitho.ch"] = _unavailable_reason(exc)

        # Strict radius clamping
        filtered = [s for s in all_sightings if s.distance_km <= radius_km]

        # Closest first; most recent first among equal distances
        filtered = sort_sightings(filtered)

        metadata = {
            "location_name": resolved_loc,
            "latitude": round(lat, 5),
            "longitude": round(lng, 5),
            "radius_km": radius_km,
            "back_days": back_days,
            "species_name": species_name,
            "total_count": len(filtered),
            "sources": list({s.source for s in filtered}),
            "unavailable_sources": unavailable,
        }

        return filtered, metadata
