from typing import Dict, List
from birdai.schemas import ObservationRecord


def evaluate_observations(
    records: List[ObservationRecord],
    top_k: int = 3,
) -> dict:
    """Evaluate candidate species predictions against human-verified corrections."""
    evaluated = [r for r in records if r.user_correction is not None]
    if not evaluated:
        return {
            "total_records": len(records),
            "total_evaluated": 0,
            "error": "No verified or corrected observations found for evaluation.",
            "calibration_note": "Model confidence scores remain uncalibrated. Scores reflect heuristic prompt confidence.",
        }

    total = len(evaluated)
    top1_correct = 0
    topk_correct = 0
    rr_sum = 0.0

    # Modality breakdown
    modality_stats: Dict[str, Dict[str, int]] = {}
    # Merlin breakdown
    merlin_total = 0
    merlin_correct = 0

    # Calibration binning: [0-50), [50-75), [75-100]
    bins = {
        "low (0-49%)": {"count": 0, "correct": 0, "conf_sum": 0.0},
        "medium (50-74%)": {"count": 0, "correct": 0, "conf_sum": 0.0},
        "high (75-100%)": {"count": 0, "correct": 0, "conf_sum": 0.0},
    }

    for record in evaluated:
        correction = record.user_correction
        target = correction.confirmed_species.strip().lower()
        candidate_names = [c.common_name.strip().lower() for c in record.candidates]

        mod = record.modality
        if mod not in modality_stats:
            modality_stats[mod] = {"total": 0, "top1": 0}
        modality_stats[mod]["total"] += 1

        is_top1 = False
        if candidate_names and candidate_names[0] == target:
            top1_correct += 1
            modality_stats[mod]["top1"] += 1
            is_top1 = True

        if target in candidate_names[:top_k]:
            topk_correct += 1

        if target in candidate_names:
            rank = candidate_names.index(target) + 1
            rr_sum += 1.0 / rank

        # Check top prediction confidence calibration
        if record.candidates:
            top_cand = record.candidates[0]
            conf = top_cand.confidence_probability
            bin_key = (
                "high (75-100%)"
                if conf >= 75
                else ("medium (50-74%)" if conf >= 50 else "low (0-49%)")
            )
            bins[bin_key]["count"] += 1
            bins[bin_key]["conf_sum"] += conf
            if is_top1:
                bins[bin_key]["correct"] += 1

        # Check Merlin suggestion
        if record.merlin_suggestion and record.merlin_suggestion.species_name:
            merlin_total += 1
            if record.merlin_suggestion.species_name.strip().lower() == target:
                merlin_correct += 1

    calibration_report = {}
    for k, v in bins.items():
        if v["count"] > 0:
            calibration_report[k] = {
                "count": v["count"],
                "avg_heuristic_confidence": round(v["conf_sum"] / v["count"], 1),
                "actual_empirical_accuracy": round((v["correct"] / v["count"]) * 100, 1),
            }

    modality_breakdown = {}
    for mod, counts in modality_stats.items():
        modality_breakdown[mod] = {
            "total": counts["total"],
            "top1_accuracy": round(counts["top1"] / counts["total"], 4) if counts["total"] > 0 else 0.0,
        }

    return {
        "total_records": len(records),
        "total_evaluated": total,
        "top_1_accuracy": round(top1_correct / total, 4),
        f"top_{top_k}_accuracy": round(topk_correct / total, 4),
        "mean_reciprocal_rank": round(rr_sum / total, 4),
        "modality_breakdown": modality_breakdown,
        "merlin_performance": {
            "total_suggestions": merlin_total,
            "accuracy": round(merlin_correct / merlin_total, 4) if merlin_total > 0 else None,
        },
        "calibration_analysis": calibration_report,
        "calibration_note": (
            "Model confidence scores represent uncalibrated heuristic scores, not empirical probabilities. "
            "Examine calibration_analysis to see gaps between model confidence and observed accuracy."
        ),
    }
