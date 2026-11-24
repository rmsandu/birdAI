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


def _species_names():
    from birdai.species_search import SpeciesNames

    return [
        SpeciesNames("comkin1", "Alcedo atthis", "Kingfishers",
                     {"en": "Common Kingfisher", "de": "Eisvogel", "fr": "Martin-pêcheur d'Europe", "it": "Martin pescatore"}),
        SpeciesNames("barowl2", "Tyto alba", "Barn-Owls",
                     {"en": "Western Barn Owl", "de": "Schleiereule", "fr": "Effraie des clochers", "it": "Barbagianni"}),
        SpeciesNames("tawowl1", "Strix aluco", "Owls",
                     {"en": "Tawny Owl", "de": "Waldkauz", "fr": "Chouette hulotte", "it": "Allocco"}),
        SpeciesNames("mallar3", "Anas platyrhynchos", "Ducks, Geese, and Waterfowl",
                     {"en": "Mallard", "de": "Stockente", "fr": "Canard colvert", "it": "Germano reale"}),
    ]


def _area_sighting(code, name, distance):
    return SightingItem(species_common_name=name, species_code=code, observed_at="2026-11-22 08:00",
                        location_name="Somewhere", latitude=47.4, longitude=8.5,
                        distance_km=distance, source="ebird")


def _mock_ebird_for_species_search():
    ebird = MagicMock()
    # One record per species in the area, like eBird's geo/recent endpoint
    ebird.recent_sightings_in_radius.return_value = [
        _area_sighting("mallar3", "Mallard", 1.0),
        _area_sighting("tawowl1", "Tawny Owl", 3.0),
        _area_sighting("comkin1", "Common Kingfisher", 2.0),
        _area_sighting("barowl2", "Western Barn Owl", 8.0),
    ]
    ebird.species_names.return_value = _species_names()
    # Full sightings for one species
    ebird.recent_species_sightings_in_radius.side_effect = lambda species_code, **kw: [
        _area_sighting(species_code, species_code, d) for d in (2.0, 5.0)
    ]
    return ebird


def test_species_search_is_multilingual_and_uncapped():
    ebird = _mock_ebird_for_species_search()
    agg = SightingsAggregator(ebird_client=ebird)

    results, meta = agg.search_sightings(location_name="Zurich", radius_km=25, species_name="Eisvogel")

    # The area listing is fetched without the 40-result cap
    assert ebird.recent_sightings_in_radius.call_args.kwargs["max_results"] is None
    ebird.recent_species_sightings_in_radius.assert_called_once()
    assert ebird.recent_species_sightings_in_radius.call_args.kwargs["species_code"] == "comkin1"
    assert len(results) == 2
    assert meta["species_match_type"] == "species"
    assert [m["species_code"] for m in meta["matched_species"]] == ["comkin1"]
    assert meta["matched_species"][0]["common_names"]["de"] == "Eisvogel"


def test_group_search_returns_all_owls_nearest_first():
    ebird = _mock_ebird_for_species_search()
    agg = SightingsAggregator(ebird_client=ebird)

    results, meta = agg.search_sightings(location_name="Zurich", radius_km=25, species_name="Eulen")

    assert meta["species_match_type"] == "group"
    assert [m["species_code"] for m in meta["matched_species"]] == ["tawowl1", "barowl2"]
    assert {s.species_code for s in results} == {"tawowl1", "barowl2"}
    assert meta["species_not_fetched"] == 0


def test_group_search_caps_detailed_lookups(monkeypatch):
    import birdai.sightings_aggregator as agg_module

    monkeypatch.setattr(agg_module, "MAX_SPECIES_PER_SEARCH", 1)
    ebird = _mock_ebird_for_species_search()
    results, meta = SightingsAggregator(ebird_client=ebird).search_sightings(
        location_name="Zurich", species_name="owl"
    )

    assert ebird.recent_species_sightings_in_radius.call_count == 1
    assert meta["species_not_fetched"] == 1
    assert meta["matched_species"][1]["sightings_count"] is None  # listed, not fetched


def test_free_text_without_bird_lists_all_species():
    ebird = _mock_ebird_for_species_search()
    results, meta = SightingsAggregator(ebird_client=ebird).search_sightings(
        location_name="Zurich", species_name="What birds are near Zurich?", species_in_free_text=True
    )

    assert meta["species_filter_applied"] is False
    assert len(results) == 4
    ebird.recent_species_sightings_in_radius.assert_not_called()


def test_ornitho_is_parked_by_default():
    agg = SightingsAggregator(ebird_client=MagicMock())
    assert agg.ornitho_client is None
    assert agg.sources == ["ebird"]

    _, meta = agg.search_sightings(location_name="Zurich")
    assert meta["sources_queried"] == ["ebird"]
    assert "ornitho.ch" not in meta["unavailable_sources"]
