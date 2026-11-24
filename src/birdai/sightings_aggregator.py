import logging
from typing import Optional

from birdai.config import (
    BIRDAI_DEFAULT_LATITUDE,
    BIRDAI_DEFAULT_LONGITUDE,
    BIRDAI_LOCATION,
    ORNITHO_ENABLED,
)
from birdai.context import geocode_location
from birdai.ebird_client import EBirdClient, sort_sightings
from birdai.ornitho_client import OrnithoClient, resolve_hotspot_coordinates
from birdai.schemas import SightingItem
from birdai.species_search import SpeciesNames, match_species, match_species_in_text

logger = logging.getLogger(__name__)

SOURCE_LABELS = {"ebird": "eBird", "ornitho.ch": "ornitho.ch"}

# When a group search ("owl", "duck") matches many species, fetch full sightings for
# at most this many (nearest first) to bound eBird calls; the rest are still listed.
MAX_SPECIES_PER_SEARCH = 10
DEFAULT_LISTING_LIMIT = 40


def _unavailable_reason(exc: Exception) -> str:
    if "not configured" in str(exc).lower():
        return "not configured"
    return "could not be reached"


def describe_unavailable_sources(
    unavailable: dict[str, str],
    queried: Optional[list[str]] = None,
) -> Optional[str]:
    """User-facing notice explaining which queried sources failed, or None if all worked."""
    if not unavailable:
        return None
    queried = queried if queried is not None else list(SOURCE_LABELS)
    if set(unavailable) >= set(queried):
        return (
            "**Note:** I couldn't check for sightings right now — "
            + "; ".join(f"{SOURCE_LABELS[src]} {reason}" for src, reason in unavailable.items())
            + ". This doesn't mean there are no birds; please try again later."
        )
    working = [SOURCE_LABELS[src] for src in queried if src not in unavailable]
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
        # ornitho.ch is parked unless enabled in config (or a client is passed explicitly)
        if ornitho_client is not None:
            self.ornitho_client: Optional[OrnithoClient] = ornitho_client
        else:
            self.ornitho_client = OrnithoClient() if ORNITHO_ENABLED else None

    @property
    def sources(self) -> list[str]:
        """Sources this aggregator queries."""
        return ["ebird"] + (["ornitho.ch"] if self.ornitho_client is not None else [])

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
        species_in_free_text: bool = False,
    ) -> tuple[list[SightingItem], dict]:
        """Recent sightings around a location, optionally for a species or bird group.

        ``species_name`` may be a species or a group ("owl", "Eulen", "chouette") in
        English, German, French, Italian or Latin. With ``species_in_free_text=True`` it is
        a whole user message and the species is detected inside it (rule-based mode);
        if no bird is recognised, all species are returned.
        """
        radius_km = min(max(int(radius_km), 1), 50)
        back_days = min(max(int(back_days), 1), 30)
        species_query = (species_name or "").strip() or None

        lat, lng, resolved_loc = self.resolve_center_coordinates(
            location_name=location_name,
            user_lat=user_lat,
            user_lng=user_lng,
        )

        all_sightings: list[SightingItem] = []
        unavailable: dict[str, str] = {}
        species_info: dict = {"matched_species": [], "species_filter_applied": False}

        # --- 1. eBird ---
        try:
            if species_query:
                ebird_results, species_info = self._ebird_species_search(
                    species_query, lat, lng, radius_km, back_days, species_in_free_text
                )
            else:
                ebird_results = self.ebird_client.recent_sightings_in_radius(
                    lat=lat, lng=lng, dist_km=radius_km, back_days=back_days,
                    max_results=DEFAULT_LISTING_LIMIT,
                )
            all_sightings.extend(ebird_results)
        except Exception as exc:
            logger.warning("eBird query encountered an error (%s).", exc)
            unavailable["ebird"] = _unavailable_reason(exc)

        # --- 2. ornitho.ch (parked unless enabled) ---
        if self.ornitho_client is not None:
            try:
                all_sightings.extend(
                    self.ornitho_client.get_recent_sightings(
                        lat=lat,
                        lng=lng,
                        dist_km=radius_km,
                        species_name=None if species_in_free_text else species_query,
                    )
                )
            except Exception as exc:
                logger.warning("ornitho.ch query encountered an error (%s); continuing.", exc)
                unavailable["ornitho.ch"] = _unavailable_reason(exc)

        filtered = sort_sightings([s for s in all_sightings if s.distance_km <= radius_km])

        metadata = {
            "location_name": resolved_loc,
            "latitude": round(lat, 5),
            "longitude": round(lng, 5),
            "radius_km": radius_km,
            "back_days": back_days,
            "species_name": None if species_in_free_text else species_query,
            **species_info,
            "total_count": len(filtered),
            "sources": list({s.source for s in filtered}),
            "sources_queried": self.sources,
            "unavailable_sources": unavailable,
        }
        return filtered, metadata

    def _ebird_species_search(
        self,
        query: str,
        lat: float,
        lng: float,
        radius_km: int,
        back_days: int,
        free_text: bool,
    ) -> tuple[list[SightingItem], dict]:
        # Everything seen in the area (one record per species), uncapped
        area = sort_sightings(
            self.ebird_client.recent_sightings_in_radius(
                lat=lat, lng=lng, dist_km=radius_km, back_days=back_days, max_results=None
            )
        )
        names = self.ebird_client.species_names({s.species_code for s in area if s.species_code})
        match = match_species_in_text(query, names) if free_text else match_species(query, names)

        if free_text and not match.codes:
            # No bird recognised in the message: list everything nearby
            return area[:DEFAULT_LISTING_LIMIT], {
                "matched_species": [],
                "species_filter_applied": False,
                "species_note": "No bird name recognised in the message; showing all species.",
            }

        names_by_code = {n.code: n for n in names}
        # Nearest species first (area is sorted by distance)
        wanted = set(match.codes)
        ordered = list(dict.fromkeys(s.species_code for s in area if s.species_code in wanted))
        selected = ordered[:MAX_SPECIES_PER_SEARCH]

        sightings: list[SightingItem] = []
        counts: dict[str, int] = {}
        for code in selected:
            found = self.ebird_client.recent_species_sightings_in_radius(
                species_code=code, lat=lat, lng=lng, dist_km=radius_km, back_days=back_days
            )
            counts[code] = len(found)
            sightings.extend(found)

        return sightings, {
            "species_filter_applied": True,
            "species_match_type": "group" if match.is_group else ("species" if ordered else "none"),
            "matched_terms": match.matched_terms,
            "matched_species": [
                _species_summary(names_by_code[code], counts.get(code)) for code in ordered
            ],
            "species_not_fetched": len(ordered) - len(selected),
        }


def _species_summary(names: SpeciesNames, sightings_count: Optional[int]) -> dict:
    return {
        "species_code": names.code,
        "common_names": names.names,
        "scientific_name": names.scientific_name,
        "family": names.family,
        # None = not fetched (beyond MAX_SPECIES_PER_SEARCH)
        "sightings_count": sightings_count,
    }
