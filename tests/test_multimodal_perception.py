from datetime import date, time
from pathlib import Path

from birdai.perception import analyze_multimodal_observation
from birdai.schemas import MerlinSuggestion, ObservationContext, ObservationEvidence

FIXTURES = Path(__file__).parent / "fixtures"


class StubEBirdClient:
    def resolve_species_code(self, common_name: str, scientific_name: str | None = None):
        return "eurrob1", "European Robin", "Erithacus rubecula"

    def recent_observations_for_species(self, species_code: str, observation_context: ObservationContext):
        return ObservationEvidence(
            source="ebird",
            recent_observation_count=5,
            lookback_days=30,
            summary="5 observations in last 30 days.",
            species_code=species_code,
        )


def test_analyze_multimodal_observation_with_image_and_merlin():
    context = ObservationContext(
        observation_date=date(2026, 5, 20),
        observation_time=time(12, 0, 0),
        location_text="Zurich, Switzerland",
        latitude=47.3769,
        longitude=8.5417,
    )

    merlin = MerlinSuggestion(
        species_name="Eurasian Blue Tit",
        notes="High pitch call heard near feeder",
    )

    record = analyze_multimodal_observation(
        image_path=str(FIXTURES / "sample.jpg"),
        audio_path=str(FIXTURES / "sample.wav"),
        observation_context=context,
        merlin_suggestion=merlin,
        use_mock=True,
        ebird_client=StubEBirdClient(),
    )

    assert record.id.startswith("obs-")
    assert record.modality == "multimodal"
    assert record.merlin_suggestion is not None
    assert record.merlin_suggestion.species_name == "Eurasian Blue Tit"
    assert len(record.candidates) >= 2

    # Check that candidates have evidence attached
    cand_names = [c.common_name for c in record.candidates]
    assert "European Robin" in cand_names
    assert "Eurasian Blue Tit" in cand_names
