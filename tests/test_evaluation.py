import json
from pathlib import Path

from birdai.evaluation import evaluate_observations
from birdai.schemas import ObservationRecord

BENCHMARK_PATH = Path(__file__).parent.parent / "data" / "evaluation_samples" / "seed_benchmark.json"


def test_evaluate_seed_benchmark():
    assert BENCHMARK_PATH.exists()
    data = json.loads(BENCHMARK_PATH.read_text())
    records = [ObservationRecord.model_validate(item) for item in data]

    results = evaluate_observations(records, top_k=2)

    assert results["total_records"] == 5
    assert results["total_evaluated"] == 5
    # 4 out of 5 were top-1 correct (Robin, Stonechat, Buzzard, Blue Tit)
    assert results["top_1_accuracy"] == 0.8
    # 5 out of 5 were in top-2 (House Sparrow was candidate #2 in bench-004)
    assert results["top_2_accuracy"] == 1.0
    assert results["mean_reciprocal_rank"] > 0.8

    # Check Merlin performance (2 suggestions: Chaffinch [wrong], Great Tit [wrong])
    assert results["merlin_performance"]["total_suggestions"] == 2
    assert results["merlin_performance"]["accuracy"] == 0.0

    # Calibration note is present
    assert "calibration_note" in results
