import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from birdai.db.models import ObservationModel, UserModel
from birdai.db.session import init_db
from scripts.migrate_json_to_db import migrate


def test_migrate_json_to_db_imports_files_and_creates_user(tmp_path):
    test_db_path = tmp_path / "migration_test.db"
    test_engine = create_engine(
        f"sqlite:///{test_db_path}",
        connect_args={"check_same_thread": False},
    )
    init_db(target_engine=test_engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = Session()

    # Create dummy observation json file
    obs_dir = tmp_path / "observations"
    obs_dir.mkdir(parents=True, exist_ok=True)
    sample_obs = {
        "id": "obs-migrated-001",
        "created_at": "2026-05-20T10:00:00Z",
        "modality": "image",
        "observation_context": {
            "observation_date": "2026-05-20",
            "observation_time": "10:00:00",
            "location_text": "Bern, Switzerland",
            "latitude": 46.948,
            "longitude": 7.4474,
            "location_source": "manual",
            "timezone_name": "Europe/Zurich",
        },
        "candidates": [
            {
                "common_name": "Common Chaffinch",
                "scientific_name": "Fringilla coelebs",
                "confidence_probability": 85,
                "reason": "Clear wing bars.",
            }
        ],
        "overall_uncertainty": "low",
        "overall_uncertainty_reasons": [],
        "suggested_next_action": "None",
    }
    (obs_dir / "obs-migrated-001.json").write_text(json.dumps(sample_obs))

    try:
        count = migrate(data_dir=str(tmp_path), db_session=session)
        assert count == 1

        user = session.query(UserModel).filter(UserModel.email == "admin@birdai.local").first()
        assert user is not None
        obs = session.query(ObservationModel).filter(ObservationModel.id == "obs-migrated-001").first()
        assert obs is not None
        assert obs.user_id == user.id
        assert obs.candidates_json[0]["common_name"] == "Common Chaffinch"
    finally:
        session.close()
