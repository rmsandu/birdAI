from pathlib import Path

from birdai.ebird_client import EBirdServiceError
from birdai.perception import analyze_observation
from birdai.schemas import ObservationEvidence


FIXTURES = Path(__file__).parent / "fixtures"


class FailingEBirdClient:
    def resolve_species_code(self, common_name: str, scientific_name: str | None = None):
        raise EBirdServiceError("eBird is unavailable.")


def test_analyze_observation_uses_fallback_when_ebird_fails(monkeypatch):
    monkeypatch.setattr(
        "birdai.perception.search_recent_web_evidence",
        lambda **kwargs: ObservationEvidence(
            source="google_search",
            recent_observation_count=0,
            lookback_days=30,
            summary="Fallback web evidence.",
        ),
    )

    from birdai.context import build_observation_context

    context = build_observation_context(
        observation_date="2026-05-19",
        observation_time="10:23:51",
        location_text="Zurich, Switzerland",
        latitude=47.3769,
        longitude=8.5417,
    )

    result = analyze_observation(
        str(FIXTURES / "sample.jpg"),
        context,
        use_mock=True,
        ebird_client=FailingEBirdClient(),
    )

    assert result.likely_species[0].evidence.source == "google_search"
    assert any("eBird enrichment failed" in warning for warning in result.warnings)


def test_analyze_observation_geocodes_location_when_coordinates_missing(monkeypatch):
    monkeypatch.setattr(
        "birdai.perception.search_recent_web_evidence",
        lambda **kwargs: ObservationEvidence(
            source="google_search",
            recent_observation_count=0,
            lookback_days=30,
            summary="Fallback web evidence.",
        ),
    )
    monkeypatch.setattr(
        "birdai.context.geocode_location",
        lambda *args, **kwargs: (47.3769, 8.5417),
    )

    from birdai.context import build_observation_context

    context = build_observation_context(
        observation_date="2026-05-19",
        observation_time="10:23:51",
        location_text="Zurich, Switzerland",
        latitude=None,
        longitude=None,
    )

    result = analyze_observation(
        str(FIXTURES / "sample.jpg"),
        context,
        use_mock=True,
        ebird_client=FailingEBirdClient(),
    )

    assert result.observation_context.latitude == 47.3769
    assert result.observation_context.longitude == 8.5417
    assert result.observation_context.location_source == "geocoded_location"
    assert result.likely_species[0].evidence.source == "google_search"


def test_analyze_observation_prefers_photo_exif_coordinates(monkeypatch):
    monkeypatch.setattr(
        "birdai.context.extract_photo_coordinates",
        lambda file_path: (47.401, 8.601),
    )
    monkeypatch.setattr(
        "birdai.perception.search_recent_web_evidence",
        lambda **kwargs: ObservationEvidence(
            source="google_search",
            recent_observation_count=0,
            lookback_days=30,
            summary="Fallback web evidence.",
        ),
    )

    from birdai.context import build_observation_context

    context = build_observation_context(
        observation_date="2026-05-19",
        observation_time="10:23:51",
        location_text="Zurich, Switzerland",
        latitude=47.3769,
        longitude=8.5417,
    )

    result = analyze_observation(
        str(FIXTURES / "sample.jpg"),
        context,
        use_mock=True,
        ebird_client=FailingEBirdClient(),
    )

    assert result.observation_context.latitude == 47.401
    assert result.observation_context.longitude == 8.601
    assert result.observation_context.location_source == "photo_exif"
