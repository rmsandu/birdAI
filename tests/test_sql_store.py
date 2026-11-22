from datetime import date, datetime, time
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from birdai.db.models import Base, UserModel
from birdai.db.sql_store import SQLObservationStore
from birdai.schemas import (
    ObservationContext,
    ObservationCorrection,
    ObservationRecord,
)


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/test_store.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_sql_store_privacy_isolation(db_session, tmp_path):
    # 1. Setup two users: User A and User B
    user_a = UserModel(
        id=str(uuid.uuid4()),
        email="usera@example.com",
        hashed_password="hasha",
        full_name="User A",
    )
    user_b = UserModel(
        id=str(uuid.uuid4()),
        email="userb@example.com",
        hashed_password="hashb",
        full_name="User B",
    )
    db_session.add_all([user_a, user_b])
    db_session.commit()

    store = SQLObservationStore(db=db_session, base_dir=str(tmp_path))

    # 2. User A creates an observation
    context = ObservationContext(
        observation_date=date(2026, 5, 20),
        observation_time=time(14, 0, 0),
        location_text="Zurich, Switzerland",
        latitude=47.3769,
        longitude=8.5417,
    )
    record_a = ObservationRecord(
        id="obs-user-a-1",
        created_at=datetime(2026, 5, 20, 14, 0, 0),
        modality="image",
        observation_context=context,
        candidates=[],
    )

    saved_a = store.save(
        record_a,
        user_id=user_a.id,
        files={"robin.jpg": b"fake_robin_pixels"},
    )
    assert saved_a.id == "obs-user-a-1"

    # 3. User A can retrieve it
    retrieved_a = store.get("obs-user-a-1", user_id=user_a.id)
    assert retrieved_a is not None
    assert retrieved_a.id == "obs-user-a-1"

    # 4. PRIVACY CHECK: User B CANNOT retrieve User A's observation
    retrieved_by_b = store.get("obs-user-a-1", user_id=user_b.id)
    assert retrieved_by_b is None, "User B should not be able to get User A's observation"

    # 5. PRIVACY CHECK: Listing isolation
    list_a = store.list(user_id=user_a.id)
    assert len(list_a) == 1
    assert list_a[0].id == "obs-user-a-1"

    list_b = store.list(user_id=user_b.id)
    assert len(list_b) == 0, "User B should see 0 observations"

    # 6. PRIVACY CHECK: User B CANNOT update correction on User A's observation
    corr = ObservationCorrection(
        confirmed_species="Eurasian Blue Tit",
        is_correct_prediction=True,
    )
    updated_by_b = store.update_correction("obs-user-a-1", corr, user_id=user_b.id)
    assert updated_by_b is None, "User B should not be able to update User A's observation"

    # 7. User A updates correction
    updated_by_a = store.update_correction("obs-user-a-1", corr, user_id=user_a.id)
    assert updated_by_a is not None
    assert updated_by_a.user_correction.confirmed_species == "Eurasian Blue Tit"

    # 8. PRIVACY CHECK: Media file ownership isolation
    # User B cannot access User A's media path
    media_b = store.get_media_path("obs-user-a-1", "robin.jpg", user_id=user_b.id)
    assert media_b is None, "User B should not have access to User A's media file"

    # User A can access their media path
    media_a = store.get_media_path("obs-user-a-1", "robin.jpg", user_id=user_a.id)
    assert media_a is not None
    assert media_a.read_bytes() == b"fake_robin_pixels"
