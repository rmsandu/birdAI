import httpx
import pytest

from birdai.ornitho_client import (
    OrnithoClient,
    OrnithoServiceError,
    resolve_hotspot_coordinates,
)

ZURICH = (47.3769, 8.5417)

SAMPLE_RSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>ornitho.ch - Bemerkenswerte Beobachtungen</title>
    <item>
      <title>Eisvogel (Alcedo atthis) - Neeracherried ZH</title>
      <link>https://www.ornitho.ch/index.php?m_id=54&amp;mid=123</link>
      <description>1 Ind., jagend am Schilfrand</description>
      <pubDate>Sun, 22 Nov 2026 10:00:00 +0100</pubDate>
    </item>
    <item>
      <title>Rotmilan (Milvus milvus) - Fanel BE</title>
      <link>https://www.ornitho.ch/index.php?m_id=54&amp;mid=124</link>
      <description>3 Ind. kreisend</description>
      <pubDate>Sat, 21 Nov 2026 14:30:00 +0100</pubDate>
    </item>
    <item>
      <title>Wasseramsel (Cinclus cinclus) - Irgendwo unbekannt</title>
      <link>https://www.ornitho.ch/index.php?m_id=54&amp;mid=125</link>
      <description>am Bach</description>
      <pubDate>Sat, 21 Nov 2026 09:00:00 +0100</pubDate>
    </item>
  </channel>
</rss>"""


class MockResponse:
    text = SAMPLE_RSS_XML

    def raise_for_status(self):
        pass


class MockClient:
    def get(self, *args, **kwargs):
        return MockResponse()


class FailingClient:
    def get(self, *args, **kwargs):
        raise httpx.ConnectError("network down")


def test_resolve_hotspot_coordinates():
    assert resolve_hotspot_coordinates("Observation at Neeracherried ZH") == (47.5098, 8.4988)
    assert resolve_hotspot_coordinates("Klingnauer Stausee AG") == (47.5856, 8.2324)
    assert resolve_hotspot_coordinates("Somewhere completely unknown") is None


def test_rss_parsing_extracts_species_and_location():
    items = OrnithoClient(http_client=MockClient()).fetch_rss_sightings()
    assert len(items) == 3
    assert items[0]["species_common_name"] == "Eisvogel"
    assert items[0]["species_scientific_name"] == "Alcedo atthis"
    assert items[0]["location"] == "Neeracherried ZH"


def test_unreachable_feed_raises_instead_of_returning_empty():
    client = OrnithoClient(http_client=FailingClient())
    with pytest.raises(OrnithoServiceError):
        client.get_recent_sightings(lat=ZURICH[0], lng=ZURICH[1], dist_km=50)


def test_sightings_filtered_by_radius_and_unknown_locations_skipped():
    client = OrnithoClient(http_client=MockClient())
    sightings = client.get_recent_sightings(lat=ZURICH[0], lng=ZURICH[1], dist_km=25)

    # Neeracherried (~15 km) is in; Fanel (~110 km) is out; the unknown location is never guessed
    assert [s.species_common_name for s in sightings] == ["Eisvogel"]
    s = sightings[0]
    assert s.source == "ornitho.ch"
    assert s.location_name == "Neeracherried ZH"
    assert s.distance_km <= 25
    assert s.observed_at == "2026-11-22 10:00"


def test_species_filter_matches_scientific_name():
    client = OrnithoClient(http_client=MockClient())
    sightings = client.get_recent_sightings(
        lat=ZURICH[0], lng=ZURICH[1], dist_km=50, species_name="alcedo"
    )
    assert len(sightings) == 1
    assert sightings[0].species_scientific_name == "Alcedo atthis"
