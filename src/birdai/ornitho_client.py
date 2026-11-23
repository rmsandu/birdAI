import logging
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Optional

import httpx

from birdai.config import HTTP_TIMEOUT_SECONDS
from birdai.ebird_client import haversine_distance_km, sort_sightings
from birdai.schemas import SightingItem

logger = logging.getLogger(__name__)

ORNITHO_RSS_URL = "https://www.ornitho.ch/index.php?m_id=1202&sp_tg=1&rss=1"

# Well-known Swiss birdwatching hotspot coordinates used for location mapping
SWISS_HOTSPOTS: dict[str, tuple[float, float]] = {
    "klingnauer stausee": (47.5856, 8.2324),
    "neeracherried": (47.5098, 8.4988),
    "greifensee": (47.3512, 8.6789),
    "zürichsee": (47.2800, 8.6500),
    "zurich": (47.3769, 8.5417),
    "flachsee unterlunkhofen": (47.3200, 8.3800),
    "pfäffikersee": (47.3550, 8.7850),
    "fanel": (46.9800, 7.0300),
    "witi grenchen": (47.1850, 7.4000),
    "chablais de cudrefin": (46.9600, 7.0200),
    "lac de morat": (46.9100, 7.1000),
    "lac léman": (46.4500, 6.5500),
    "geneva": (46.2044, 6.1432),
    "bern": (46.9480, 7.4474),
    "basel": (47.5596, 7.5886),
    "lucerne": (47.0502, 8.3093),
    "st. gallen": (47.4245, 9.3767),
    "bolle di magadino": (46.1600, 8.8700),
    "alpnachersee": (46.9700, 8.3000),
    "hallwilersee": (47.2800, 8.2200),
    "sempachersee": (47.1500, 8.1700),
}

class OrnithoServiceError(RuntimeError):
    pass


def resolve_hotspot_coordinates(location_str: str) -> tuple[float, float] | None:
    norm = location_str.lower().strip()
    for spot_name, coords in SWISS_HOTSPOTS.items():
        if spot_name in norm:
            return coords
    return None


def _normalize_pub_date(pub_date: str) -> str:
    """Convert an RFC 822 RSS date to "YYYY-MM-DD HH:MM" (same format as eBird)."""
    if not pub_date:
        return ""
    try:
        return parsedate_to_datetime(pub_date).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return pub_date


class OrnithoClient:
    def __init__(
        self,
        *,
        rss_url: str = ORNITHO_RSS_URL,
        http_client: httpx.Client | None = None,
    ):
        self.rss_url = rss_url
        self.http_client = http_client

    def _client(self) -> tuple[httpx.Client, bool]:
        if self.http_client is not None:
            return self.http_client, False
        return httpx.Client(timeout=HTTP_TIMEOUT_SECONDS), True

    def fetch_rss_sightings(self) -> list[dict]:
        client, should_close = self._client()
        try:
            res = client.get(
                self.rss_url,
                headers={"User-Agent": "BirdAI/0.2 (Naturalist Research)"},
            )
            res.raise_for_status()
            root = ET.fromstring(res.text)
            items = []
            for item in root.findall(".//item"):
                title = item.findtext("title") or ""
                desc = item.findtext("description") or ""
                link = item.findtext("link") or "https://www.ornitho.ch"
                pub_date = item.findtext("pubDate") or ""

                # Example title format: "Eisvogel / Martin-pêcheur d'Europe (Alcedo atthis) - Neeracherried ZH"
                species_name = title
                location = ""
                if " - " in title:
                    species_name, location = (part.strip() for part in title.rsplit(" - ", 1))
                sci_name = None
                m_sci = re.search(r"\(([^)]+)\)", species_name)
                if m_sci:
                    sci_name = m_sci.group(1).strip()
                    species_name = species_name[: m_sci.start()].strip()

                # Clean German/French compound species names
                if " / " in species_name:
                    parts = species_name.split(" / ")
                    species_name = parts[0].strip()

                items.append(
                    {
                        "species_common_name": species_name,
                        "species_scientific_name": sci_name,
                        "location": location,
                        "description": desc,
                        "link": link,
                        "pub_date": pub_date,
                    }
                )
            return items
        except (httpx.HTTPError, ET.ParseError) as exc:
            raise OrnithoServiceError(f"ornitho.ch RSS request failed: {exc}") from exc
        finally:
            if should_close:
                client.close()

    def get_recent_sightings(
        self,
        lat: float,
        lng: float,
        dist_km: int = 15,
        species_name: Optional[str] = None,
    ) -> list[SightingItem]:
        """Return live ornitho.ch sightings within ``dist_km`` of (lat, lng).

        The RSS feed carries no coordinates, so each record is placed by matching its
        location text against known Swiss hotspots. Records whose location cannot be
        resolved are skipped rather than guessed. Raises ``OrnithoServiceError`` if the
        feed is unreachable, so callers can tell "no sightings" apart from "couldn't check".
        """
        dist_km = min(max(dist_km, 1), 50)
        norm_species = (species_name or "").strip().lower()

        sightings: list[SightingItem] = []
        for it in self.fetch_rss_sightings():
            com = it["species_common_name"]
            sci = it["species_scientific_name"]

            if norm_species and norm_species not in com.lower() and (
                not sci or norm_species not in sci.lower()
            ):
                continue

            location_text = " ".join(filter(None, [it.get("location"), it["description"]]))
            coords = resolve_hotspot_coordinates(location_text)
            if coords is None:
                continue

            distance = haversine_distance_km(lat, lng, coords[0], coords[1])
            if distance > dist_km:
                continue

            sightings.append(
                SightingItem(
                    species_common_name=com,
                    species_scientific_name=sci,
                    count=1,
                    observed_at=_normalize_pub_date(it["pub_date"]),
                    location_name=(it.get("location") or it["description"])[:60] or "ornitho.ch record",
                    latitude=coords[0],
                    longitude=coords[1],
                    distance_km=distance,
                    source="ornitho.ch",
                    checklist_url=it["link"],
                    notable=True,
                )
            )

        return sort_sightings(sightings)
