#!/usr/bin/env python3
"""Migrate existing JSON observation records from data/observations into the SQLite/PostgreSQL database."""

import json
import sys
import uuid
from pathlib import Path

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from birdai.auth.security import hash_password
from birdai.db.models import UserModel
from birdai.db.session import SessionLocal, init_db
from birdai.db.sql_store import SQLObservationStore
from birdai.schemas import ObservationRecord


def migrate(data_dir: str = "data", db_session=None) -> int:
    init_db()
    db = db_session if db_session is not None else SessionLocal()
    store = SQLObservationStore(db=db, base_dir=data_dir)

    try:
        # Check if an admin/seed user exists, create if missing
        admin_user = (
            db.query(UserModel).filter(UserModel.email == "admin@birdai.local").first()
        )
        if not admin_user:
            admin_user = (
                db.query(UserModel).order_by(UserModel.created_at.asc()).first()
            )
        if not admin_user:
            print("Creating default seed user 'admin@birdai.local'...")
            admin_user = UserModel(
                id=str(uuid.uuid4()),
                email="admin@birdai.local",
                hashed_password=hash_password("birdai12345"),
                full_name="BirdAI Administrator",
                is_active=True,
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            print(f"Created user: {admin_user.email} (ID: {admin_user.id})")

        obs_dir = Path(data_dir) / "observations"
        if not obs_dir.exists():
            print(f"No observations directory found at {obs_dir}")
            return 0

        migrated_count = 0
        json_files = sorted(obs_dir.glob("*.json"))
        print(f"Found {len(json_files)} JSON observation file(s) to migrate.")

        for fpath in json_files:
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
                record = ObservationRecord.model_validate(data)

                # Check if already in DB
                existing = store.get(record.id, user_id=admin_user.id)
                if existing:
                    print(f"Skipping already imported record: {record.id}")
                    continue

                store.save(record, user_id=admin_user.id)
                migrated_count += 1
                print(f"Migrated observation {record.id} -> user {admin_user.email}")
            except Exception as exc:
                print(f"Failed to migrate {fpath.name}: {exc}")

        print(f"Migration complete: {migrated_count} observation(s) imported.")
        return migrated_count
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
