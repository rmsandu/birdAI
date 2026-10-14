"""Compute a RankM-style dataset granularity score for CUB-200-2011.

Implements the "RankM" measure from Cui et al., "Measuring Dataset Granularity"
(2019, https://arxiv.org/html/1912.10154v1): the paper evaluates five candidate
measures and finds RankM best-correlated with actual classification difficulty.
The intuition: a dataset/class is "fine-grained" (hard) when its classes are
close together relative to their own spread in feature space, and "coarse"
(easy) when well separated.

This is a diagnostic tool, not a research reproduction: only RankM is
implemented (not Fisher/RS/RSM/Rank), and it is never imported by the live app
or the serving path — run it manually to characterize the training data.

Usage:
    python -m classifier_service.granularity.compute_granularity \
        --manifest classifier_service/data/CUB_200_2011/manifest.csv \
        --report-dir classifier_service/reports/ \
        [--checkpoint classifier_service/checkpoints/best.pt]
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from torch.utils.data import DataLoader

from classifier_service.training.dataset import CUB200Dataset
from classifier_service.training.model import build_model, get_transforms
from classifier_service.training.train import _device


def extract_embeddings(checkpoint_path: str | None, manifest_csv: str, backbone_name: str):
    device = _device()

    if checkpoint_path:
        checkpoint = torch.load(checkpoint_path, map_location="cpu")
        backbone_name = checkpoint["backbone_name"]
        model = build_model(backbone_name, checkpoint["num_classes"], pretrained=False)
        model.load_state_dict(checkpoint["model_state_dict"])
        label_map = checkpoint["label_map"]
    else:
        model = build_model(backbone_name, num_classes=200, pretrained=True)
        label_map_path = Path(manifest_csv).parent / "label_map.json"
        label_map = json.loads(label_map_path.read_text())

    model.reset_classifier(0)  # drop the head, expose the penultimate embedding
    model.to(device).eval()

    _, eval_transform = get_transforms(backbone_name, pretrained=checkpoint_path is None)
    dataset = CUB200Dataset(manifest_csv, "train", eval_transform)
    loader = DataLoader(dataset, batch_size=32, shuffle=False)

    embeddings = []
    labels = []
    with torch.no_grad():
        for images, batch_labels in loader:
            features = model(images.to(device))
            embeddings.append(features.cpu().numpy())
            labels.append(np.array(batch_labels))

    return np.concatenate(embeddings), np.concatenate(labels), label_map


def compute_rankm(embeddings: np.ndarray, labels: np.ndarray) -> dict:
    """Per-class and dataset-level RankM-style granularity scores.

    For each class: intra-class spread (mean distance to the class centroid)
    vs. inter-class separation (distance to the nearest other class centroid).
    A high ratio of intra-spread to inter-separation means the class is hard
    to tell apart from its nearest neighbor relative to its own variability —
    i.e. more "fine-grained".
    """
    class_ids = sorted(set(labels.tolist()))
    centroids = {}
    intra_spread = {}

    for class_id in class_ids:
        class_embeddings = embeddings[labels == class_id]
        centroid = class_embeddings.mean(axis=0)
        centroids[class_id] = centroid
        intra_spread[class_id] = float(
            np.linalg.norm(class_embeddings - centroid, axis=1).mean()
        )

    centroid_matrix = np.stack([centroids[c] for c in class_ids])
    per_class_scores = {}

    for i, class_id in enumerate(class_ids):
        distances = np.linalg.norm(centroid_matrix - centroid_matrix[i], axis=1)
        distances[i] = np.inf
        nearest_distance = float(distances.min())
        per_class_scores[class_id] = intra_spread[class_id] / max(nearest_distance, 1e-8)

    dataset_score = float(np.mean(list(per_class_scores.values())))
    return {"per_class": per_class_scores, "dataset_score": dataset_score}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--backbone", default="convnext_tiny")
    parser.add_argument("--report-dir", default="classifier_service/reports")
    parser.add_argument("--bottom-n", type=int, default=20, help="'Bitter' (hardest) species count")
    parser.add_argument("--top-n", type=int, default=20, help="'Sweet' (easiest) species count")
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    embeddings, labels, label_map = extract_embeddings(
        args.checkpoint, args.manifest, args.backbone
    )
    scores = compute_rankm(embeddings, labels)

    ranked = sorted(scores["per_class"].items(), key=lambda item: item[1], reverse=True)
    bitter = [
        {"species_name": label_map.get(str(class_id), str(class_id)), "score": score}
        for class_id, score in ranked[: args.bottom_n]
    ]
    sweet = [
        {"species_name": label_map.get(str(class_id), str(class_id)), "score": score}
        for class_id, score in ranked[-args.top_n :]
    ]

    report = {
        "dataset_score": scores["dataset_score"],
        "per_class_scores": {
            label_map.get(str(class_id), str(class_id)): score
            for class_id, score in scores["per_class"].items()
        },
        "bitter_species": bitter,
        "sweet_species": sweet,
    }
    report_path = report_dir / "granularity_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(list(scores["per_class"].values()), bins=30)
    ax.set_xlabel("Per-class RankM-style granularity score")
    ax.set_ylabel("Number of species")
    ax.set_title("CUB-200-2011 granularity distribution")
    plot_path = report_dir / "granularity_plot.png"
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")

    print(f"Dataset-level granularity score: {scores['dataset_score']:.4f}")
    print(f"Wrote {report_path}")
    print(f"Wrote {plot_path}")


if __name__ == "__main__":
    main()
