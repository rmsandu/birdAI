#!/usr/bin/env python3
"""BirdAI Evaluation Runner.

Evaluates saved observations or benchmark datasets against human-verified ground
truth labels. Reports top-k accuracy, ranking quality, and calibration diagnostics.

By default, observations are read from the app database (``DATABASE_URL``,
``sqlite:///./data/birdai.db`` unless overridden).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from birdai.config import DATABASE_URL
from birdai.db.models import UserModel
from birdai.db.sql_store import SQLObservationStore
from birdai.evaluation import evaluate_observations
from birdai.schemas import ObservationRecord


class EvaluationInputError(RuntimeError):
    pass


def load_benchmark(path: str) -> list[ObservationRecord]:
    bench_path = Path(path)
    if not bench_path.exists():
        raise EvaluationInputError(f"Benchmark file {bench_path} not found.")
    data = json.loads(bench_path.read_text())
    return [ObservationRecord.model_validate(item) for item in data]


def load_db_observations(db: Session, user_email: Optional[str] = None) -> list[ObservationRecord]:
    user_id = None
    if user_email:
        user = db.query(UserModel).filter(UserModel.email == user_email.strip().lower()).first()
        if user is None:
            raise EvaluationInputError(f"No user with email {user_email} in the database.")
        user_id = user.id
    return SQLObservationStore(db).list_all_for_evaluation(user_id=user_id)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate BirdAI observations.")
    parser.add_argument(
        "--benchmark",
        help="Evaluate a benchmark JSON file instead of the database "
        "(e.g. data/evaluation_samples/seed_benchmark.json)",
    )
    parser.add_argument(
        "--database-url",
        default=DATABASE_URL,
        help=f"SQLAlchemy database URL (default: DATABASE_URL, currently {DATABASE_URL})",
    )
    parser.add_argument(
        "--user",
        metavar="EMAIL",
        help="Only evaluate observations belonging to this user (default: all users)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Value of k for top-k accuracy (default: 3)",
    )
    args = parser.parse_args(argv)

    try:
        if args.benchmark:
            records = load_benchmark(args.benchmark)
            print(f"Loaded {len(records)} observations from benchmark {args.benchmark}")
        else:
            engine = create_engine(args.database_url)
            with sessionmaker(bind=engine)() as db:
                records = load_db_observations(db, user_email=args.user)
            scope = f"user {args.user}" if args.user else "all users"
            print(f"Loaded {len(records)} observations from {args.database_url} ({scope})")
    except EvaluationInputError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    results = evaluate_observations(records, top_k=args.top_k)
    print("\n" + "=" * 50)
    print("           BIRDAI EVALUATION REPORT")
    print("=" * 50)
    print(json.dumps(results, indent=2))
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
