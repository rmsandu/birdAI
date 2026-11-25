from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from birdai.config import DATABASE_URL

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    # Ensure parent directory of sqlite file exists
    if "///" in DATABASE_URL:
        db_path = DATABASE_URL.split("///", 1)[1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Enable foreign keys for SQLite
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(target_engine=None):
    from birdai.db import models  # noqa: F401
    bind_engine = target_engine or engine
    Base.metadata.create_all(bind=bind_engine)
    # Lightweight additive column migration for existing SQLite/SQL databases
    inspector = inspect(bind_engine)
    if "observations" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("observations")}
        if "video_path" not in cols:
            with bind_engine.begin() as conn:
                conn.execute(text("ALTER TABLE observations ADD COLUMN video_path VARCHAR(512)"))
