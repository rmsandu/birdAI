import httpx

from birdai.ebird_client import EBirdClient
from birdai.schemas import ObservationContext


def _context() -> ObservationContext:
    return ObservationContext.model_validate(
        {
            "observation_date": "2026-05-19",
            "observation_time": "10:23:51",
            "location_text": "Zurich, Switzerland",
            "latitude": 47.3769,
            "longitude": 8.5417,
            "location_source": "manual_coordinates",
            "timezone_name": "Europe/Zurich",
        }
    )


def test_taxonomy_lookup_and_recent_observations():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/ref/taxonomy/ebird":
            return httpx.Response(
                200,
                json=[
                    {
                        "speciesCode": "eurrob1",
                        "comName": "European Robin",
                        "sciName": "Erithacus rubecula",
                    }
                ],
            )

        if request.url.path == "/v2/data/obs/geo/recent/eurrob1":
            return httpx.Response(
                200,
                json=[
                    {"obsDt": "2026-05-18 07:30", "locName": "Zurich"},
                    {"obsDt": "2026-05-17 08:00", "locName": "Zurich"},
                ],
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    client = EBirdClient(
        api_key="test-key",
        base_url="https://api.ebird.org",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    species_match = client.resolve_species_code("European Robin", "Erithacus rubecula")
    evidence = client.recent_observations_for_species("eurrob1", _context())

    assert species_match == ("eurrob1", "European Robin", "Erithacus rubecula")
    assert evidence.source == "ebird"
    assert evidence.recent_observation_count == 2
    assert evidence.last_observation_date == "2026-05-18 07:30"


def test_taxonomy_lookup_prefers_scientific_name_when_common_name_is_ambiguous():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/ref/taxonomy/ebird":
            return httpx.Response(
                200,
                json=[
                    {
                        "speciesCode": "wrongbird1",
                        "comName": "Robin",
                        "sciName": "Different species",
                    },
                    {
                        "speciesCode": "eurrob1",
                        "comName": "European Robin",
                        "sciName": "Erithacus rubecula",
                    },
                ],
            )

        raise AssertionError(f"Unexpected request: {request.url}")

    client = EBirdClient(
        api_key="test-key",
        base_url="https://api.ebird.org",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    species_match = client.resolve_species_code("Robin", "Erithacus rubecula")

    assert species_match == ("eurrob1", "European Robin", "Erithacus rubecula")


def test_species_names_fetches_each_locale_once_and_caches(monkeypatch):
    import birdai.ebird_client as ebird_module

    monkeypatch.setattr(ebird_module, "_TAXONOMY_NAME_CACHE", {})
    names = {"en": "Common Kingfisher", "de": "Eisvogel", "fr": "Martin-pêcheur d'Europe", "it": "Martin pescatore"}
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        locale = request.url.params["locale"]
        assert request.url.params["species"] == "comkin1"
        return httpx.Response(200, json=[{
            "speciesCode": "comkin1", "comName": names[locale],
            "sciName": "Alcedo atthis", "familyComName": "Kingfishers",
        }])

    client = EBirdClient(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    [species] = client.species_names({"comkin1"})

    assert species.names == names
    assert species.scientific_name == "Alcedo atthis"
    assert species.family == "Kingfishers"
    assert len(requests) == 4  # one per locale

    client.species_names(["comkin1"])
    assert len(requests) == 4  # served from cache


def test_area_listing_without_cap_omits_max_results():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(200, json=[{
            "speciesCode": "comkin1", "comName": "Common Kingfisher", "sciName": "Alcedo atthis",
            "lat": 47.38, "lng": 8.55, "obsDt": "2026-11-22 08:00", "locName": "Limmat", "subId": "S1",
        }])

    client = EBirdClient(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    [sighting] = client.recent_sightings_in_radius(47.3769, 8.5417, dist_km=25, max_results=None)

    assert "maxResults" not in seen
    assert sighting.species_code == "comkin1"
    assert sighting.checklist_url == "https://ebird.org/checklist/S1"
