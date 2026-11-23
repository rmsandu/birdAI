import json
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from birdai.db.models import UserModel
from birdai.db.session import init_db
from birdai.db.sql_store import SQLObservationStore
from birdai.schemas import ObservationRecord
from scripts.evaluate import load_db_observations, main

BENCHMARK = Path(__file__).parent.parent / "data" / "evaluation_samples" / "seed_benchmark.json"


def _seed_db(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'eval.db'}"
    engine = create_engine(db_url)
    init_db(target_engine=engine)
    db = sessionmaker(bind=engine)()

    alice = UserModel(id=str(uuid.uuid4()), email="alice@example.com", hashed_password="x")
    bob = UserModel(id=str(uuid.uuid4()), email="bob@example.com", hashed_password="x")
    db.add_all([alice, bob])
    db.commit()

    records = [ObservationRecord.model_validate(r) for r in json.loads(BENCHMARK.read_text())]
    store = SQLObservationStore(db, base_dir=str(tmp_path))
    for i, record in enumerate(records):
        store.save(record, user_id=alice.id if i < 3 else bob.id)
    return db_url, db, len(records)


def test_load_db_observations_all_users_and_single_user(tmp_path):
    _, db, total = _seed_db(tmp_path)

    assert len(load_db_observations(db)) == total
    assert len(load_db_observations(db, user_email="alice@example.com")) == 3
    assert len(load_db_observations(db, user_email=" Bob@Example.com ")) == total - 3


def test_main_reads_database_and_reports_metrics(tmp_path, capsys):
    db_url, _, total = _seed_db(tmp_path)

    assert main(["--database-url", db_url]) == 0
    out = capsys.readouterr().out
    assert f"Loaded {total} observations" in out
    assert '"top_1_accuracy"' in out


def test_main_unknown_user_fails_cleanly(tmp_path, capsys):
    db_url, _, _ = _seed_db(tmp_path)

    assert main(["--database-url", db_url, "--user", "nobody@example.com"]) == 1
    assert "No user with email nobody@example.com" in capsys.readouterr().err
