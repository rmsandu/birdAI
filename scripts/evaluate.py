#!/usr/bin/env python3
"""BirdAI Evaluation Runner.

Evaluates saved observations or benchmark datasets against human-verified ground
truth labels. Reports top-k accuracy, ranking quality, and calibration diagnostics.
"""

import argparse
import json
from pathlib import Path

from birdai.evaluation import evaluate_observations
from birdai.schemas import ObservationRecord
from birdai.storage import LocalObservationStore


def main():
    parser = argparse.ArgumentParser(description="Evaluate BirdAI observations.")
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Path to local data directory containing observations/ (default: data)",
    )
    parser.add_argument(
        "--benchmark",
        help="Optional path to a benchmark JSON file (e.g. data/evaluation_samples/seed_benchmark.json)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Value of k for top-k accuracy (default: 3)",
    )
    args = parser.parse_args()

    records = []
    if args.benchmark:
        bench_path = Path(args.benchmark)
        if not bench_path.exists():
            print(f"Error: Benchmark file {bench_path} not found.")
            return
        data = json.loads(bench_path.read_text())
        records = [ObservationRecord.model_validate(item) for item in data]
        print(f"Loaded {len(records)} observations from benchmark {args.benchmark}")
    else:
        store = LocalObservationStore(base_dir=args.data_dir)
        records = store.list(limit=1000)
        print(f"Loaded {len(records)} observations from {args.data_dir}/observations")

    results = evaluate_observations(records, top_k=args.top_k)
    print("\n" + "=" * 50)
    print("           BIRDAI EVALUATION REPORT")
    print("=" * 50)
    print(json.dumps(results, indent=2))
    print("=" * 50)


if __name__ == "__main__":
    main()
