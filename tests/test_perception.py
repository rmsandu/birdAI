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


def test_analyze_observation_skips_ebird_without_coordinates():
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

    assert result.likely_species[0].evidence.source == "none"
    assert any("No coordinates were provided" in warning for warning in result.warnings)
    assert any("Skipping eBird enrichment" in warning for warning in result.warnings)
