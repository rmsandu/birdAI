from datetime import date, datetime, time

from birdai.schemas import ObservationContext, ObservationCorrection, ObservationRecord
from birdai.storage import LocalObservationStore


def test_local_observation_store_save_get_and_correct(tmp_path):
    store = LocalObservationStore(base_dir=str(tmp_path))

    context = ObservationContext(
        observation_date=date(2026, 5, 20),
        observation_time=time(14, 0, 0),
        location_text="Zurich, Switzerland",
        latitude=47.3769,
        longitude=8.5417,
    )

    record = ObservationRecord(
        id="obs-12345",
        created_at=datetime(2026, 5, 20, 14, 0, 0),
        modality="image",
        observation_context=context,
        candidates=[],
    )

    saved = store.save(record, files={"sample.jpg": b"fake_image_bytes"})
    assert saved.id == "obs-12345"

    loaded = store.get("obs-12345")
    assert loaded is not None
    assert loaded.id == "obs-12345"
    assert loaded.observation_context.location_text == "Zurich, Switzerland"

    # Check media path
    media_path = store.get_media_path("obs-12345", "sample.jpg")
    assert media_path is not None
    assert media_path.read_bytes() == b"fake_image_bytes"

    # Check update correction
    correction = ObservationCorrection(
        confirmed_species="European Robin",
        scientific_name="Erithacus rubecula",
        is_correct_prediction=True,
        correction_notes="Adult robin on a fence",
    )
    updated = store.update_correction("obs-12345", correction)
    assert updated is not None
    assert updated.user_correction is not None
    assert updated.user_correction.confirmed_species == "European Robin"

    # Check listing with filters
    reviewed = store.list(reviewed_only=True)
    assert len(reviewed) == 1
    unreviewed = store.list(reviewed_only=False)
    assert len(unreviewed) == 0
