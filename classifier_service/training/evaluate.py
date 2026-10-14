"""Evaluate a trained checkpoint on the held-out CUB-200-2011 test split.

Usage:
    python -m classifier_service.training.evaluate --checkpoint classifier_service/checkpoints/best.pt --manifest classifier_service/data/CUB_200_2011/manifest.csv
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from classifier_service.training.dataset import CUB200Dataset
from classifier_service.training.model import build_model, get_transforms
from classifier_service.training.train import _device


def load_checkpoint(checkpoint_path: str):
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model = build_model(
        checkpoint["backbone_name"], checkpoint["num_classes"], pretrained=False
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    return model, checkpoint


def evaluate(checkpoint_path: str, manifest_csv: str, batch_size: int = 32, top_k: int = 3) -> dict:
    device = _device()
    model, checkpoint = load_checkpoint(checkpoint_path)
    model.to(device).eval()

    _, eval_transform = get_transforms(checkpoint["backbone_name"])
    test_dataset = CUB200Dataset(manifest_csv, "test", eval_transform)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

    correct_top1 = 0
    correct_topk = 0
    total = 0
    per_class_correct: dict[int, int] = defaultdict(int)
    per_class_total: dict[int, int] = defaultdict(int)

    with torch.no_grad():
        for images, labels in test_loader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            topk_preds = outputs.topk(top_k, dim=1).indices

            correct_top1 += (topk_preds[:, 0] == labels).sum().item()
            correct_topk += (topk_preds == labels.unsqueeze(1)).any(dim=1).sum().item()
            total += images.size(0)

            for label, top1 in zip(labels.tolist(), topk_preds[:, 0].tolist()):
                per_class_total[label] += 1
                if label == top1:
                    per_class_correct[label] += 1

    label_map = checkpoint["label_map"]
    per_class_accuracy = {
        label_map.get(str(class_id), str(class_id)): per_class_correct[class_id] / per_class_total[class_id]
        for class_id in per_class_total
    }
    worst_classes = sorted(per_class_accuracy.items(), key=lambda item: item[1])[:20]

    metrics = {
        "top1_accuracy": correct_top1 / max(total, 1),
        f"top{top_k}_accuracy": correct_topk / max(total, 1),
        "num_test_samples": total,
        "worst_20_classes": worst_classes,
    }
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    metrics = evaluate(args.checkpoint, args.manifest, top_k=args.top_k)

    metrics_path = Path(args.checkpoint).parent / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))

    print(f"top1_accuracy={metrics['top1_accuracy']:.4f}")
    print(f"top{args.top_k}_accuracy={metrics[f'top{args.top_k}_accuracy']:.4f}")
    print(f"Wrote {metrics_path}")


if __name__ == "__main__":
    main()
