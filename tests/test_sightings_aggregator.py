from unittest.mock import MagicMock

from birdai.schemas import SightingItem
from birdai.sightings_aggregator import SightingsAggregator


def test_resolve_center_coordinates():
    agg = SightingsAggregator()

    # Direct coordinates take priority
    lat, lng, name = agg.resolve_center_coordinates(user_lat=47.1, user_lng=8.2)
    assert lat == 47.1
    assert lng == 8.2

    # Geocoded location
    lat, lng, name = agg.resolve_center_coordinates(location_name="Zurich")
    assert round(lat, 1) == 47.4
    assert round(lng, 1) == 8.5
    assert name == "Zurich"


def test_search_sightings_merges_and_clamps_radius():
    mock_ebird = MagicMock()
    mock_ornitho = MagicMock()

    mock_ebird.resolve_species_code.return_value = None
    mock_ebird.recent_sightings_in_radius.return_value = [
        SightingItem(
            species_common_name="European Robin",
            species_scientific_name="Erithacus rubecula",
            count=1,
            observed_at="2026-11-20 10:00",
            location_name="Zürichberg",
            latitude=47.38,
            longitude=8.56,
            distance_km=2.5,
            source="ebird",
        ),
        SightingItem(
            species_common_name="Mallard",
            species_scientific_name="Anas platyrhynchos",
            count=6,
            observed_at="2026-11-20 10:30",
            location_name="Lake Constance",
            latitude=47.6,
            longitude=9.2,
            distance_km=60.0,  # Far outside radius!
            source="ebird",
        ),
    ]

    mock_ornitho.get_recent_sightings.return_value = [
        SightingItem(
            species_common_name="Common Kingfisher",
            species_scientific_name="Alcedo atthis",
            count=1,
            observed_at="2026-11-20 09:00",
            location_name="Neeracherried",
            latitude=47.50,
            longitude=8.49,
            distance_km=14.2,
            source="ornitho.ch",
        )
    ]

    aggregator = SightingsAggregator(
        ebird_client=mock_ebird,
        ornitho_client=mock_ornitho,
    )

    # Search with 15 km radius
    results, meta = aggregator.search_sightings(
        location_name="Zurich",
        radius_km=15,
        species_name=None,
    )

    # Mallard (60 km) must be excluded; Robin (2.5 km) and Kingfisher (14.2 km) must be included
    assert len(results) == 2
    names = [s.species_common_name for s in results]
    assert "European Robin" in names
    assert "Common Kingfisher" in names
    assert "Mallard" not in names
    assert all(s.distance_km <= 15 for s in results)
    assert meta["radius_km"] == 15
    assert set(meta["sources"]) == {"ebird", "ornitho.ch"}


def test_search_sightings_reports_failed_sources():
    from birdai.ebird_client import EBirdServiceError
    from birdai.ornitho_client import OrnithoServiceError

    mock_ebird = MagicMock()
    mock_ebird.recent_sightings_in_radius.side_effect = EBirdServiceError("EBIRD_API_KEY is not configured.")
    mock_ornitho = MagicMock()
    mock_ornitho.get_recent_sightings.side_effect = OrnithoServiceError("timeout")

    aggregator = SightingsAggregator(ebird_client=mock_ebird, ornitho_client=mock_ornitho)
    results, meta = aggregator.search_sightings(location_name="Zurich")

    assert results == []
    assert meta["unavailable_sources"] == {
        "ebird": "not configured",
        "ornitho.ch": "could not be reached",
    }


def test_describe_unavailable_sources():
    from birdai.sightings_aggregator import describe_unavailable_sources

    assert describe_unavailable_sources({}) is None

    partial = describe_unavailable_sources({"ebird": "could not be reached"})
    assert "incomplete" in partial and "from ornitho.ch only" in partial

    total = describe_unavailable_sources(
        {"ebird": "could not be reached", "ornitho.ch": "could not be reached"}
    )
    assert "couldn't check" in total and "doesn't mean there are no birds" in total
