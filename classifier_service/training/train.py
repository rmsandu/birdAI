"""Fine-tune a pretrained vision backbone for CUB-200-2011 species classification.

Usage:
    python -m classifier_service.training.train --manifest classifier_service/data/CUB_200_2011/manifest.csv
    python -m classifier_service.training.train --manifest ... --quick --max-samples 200 --epochs 1
"""

import argparse
import json
import time
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader

from classifier_service.training.config import TrainConfig
from classifier_service.training.dataset import CUB200Dataset
from classifier_service.training.model import build_model, get_transforms, set_backbone_trainable


def _device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _label_map_for(manifest_csv: str) -> dict:
    label_map_path = Path(manifest_csv).parent / "label_map.json"
    return json.loads(label_map_path.read_text())


def run_epoch(model, loader, optimizer, criterion, device, *, train: bool) -> tuple[float, float]:
    model.train(mode=train)
    total_loss = 0.0
    correct = 0
    total = 0

    context = torch.enable_grad() if train else torch.no_grad()
    with context:
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)

            if train:
                optimizer.zero_grad()

            outputs = model(images)
            loss = criterion(outputs, labels)

            if train:
                loss.backward()
                optimizer.step()

            total_loss += loss.item() * images.size(0)
            correct += (outputs.argmax(dim=1) == labels).sum().item()
            total += images.size(0)

    return total_loss / max(total, 1), correct / max(total, 1)


def train(config: TrainConfig) -> Path:
    device = _device()
    print(f"Training on {device}")

    label_map = _label_map_for(config.manifest_csv)
    train_transform, eval_transform = get_transforms(config.backbone_name)

    train_dataset = CUB200Dataset(
        config.manifest_csv, "train", train_transform, max_samples=config.max_samples
    )
    val_dataset = CUB200Dataset(
        config.manifest_csv, "val", eval_transform, max_samples=config.max_samples
    )

    train_loader = DataLoader(
        train_dataset, batch_size=config.batch_size, shuffle=True, num_workers=config.num_workers
    )
    val_loader = DataLoader(
        val_dataset, batch_size=config.batch_size, shuffle=False, num_workers=config.num_workers
    )

    model = build_model(config.backbone_name, config.num_classes).to(device)
    criterion = nn.CrossEntropyLoss(label_smoothing=config.label_smoothing)

    checkpoint_dir = Path(config.checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    best_val_acc = 0.0

    for epoch in range(config.epochs):
        frozen = epoch < config.frozen_epochs
        set_backbone_trainable(model, config.backbone_name, trainable=not frozen)
        lr = config.lr_head if frozen else config.lr_full
        optimizer = torch.optim.AdamW(
            (p for p in model.parameters() if p.requires_grad),
            lr=lr,
            weight_decay=config.weight_decay,
        )

        start = time.time()
        train_loss, train_acc = run_epoch(
            model, train_loader, optimizer, criterion, device, train=True
        )
        val_loss, val_acc = run_epoch(
            model, val_loader, None, criterion, device, train=False
        )
        elapsed = time.time() - start

        print(
            f"epoch {epoch + 1}/{config.epochs} "
            f"[{'frozen' if frozen else 'unfrozen'}, {elapsed:.1f}s] "
            f"train_loss={train_loss:.4f} train_acc={train_acc:.4f} "
            f"val_loss={val_loss:.4f} val_acc={val_acc:.4f}"
        )

        checkpoint = {
            "model_state_dict": model.state_dict(),
            "backbone_name": config.backbone_name,
            "num_classes": config.num_classes,
            "label_map": label_map,
        }
        torch.save(checkpoint, checkpoint_dir / "last.pt")

        if val_acc >= best_val_acc:
            best_val_acc = val_acc
            torch.save(checkpoint, checkpoint_dir / "best.pt")

    print(f"Best val accuracy: {best_val_acc:.4f}")
    return checkpoint_dir / "best.pt"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--backbone", default="convnext_tiny")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--frozen-epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--checkpoint-dir", default="classifier_service/checkpoints")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Shorthand for a fast smoke test: --max-samples 200 --epochs 1 if not overridden.",
    )
    parser.add_argument("--max-samples", type=int, default=None)
    args = parser.parse_args()

    max_samples = args.max_samples
    epochs = args.epochs
    if args.quick:
        max_samples = max_samples or 200
        if args.epochs == 15:
            epochs = 1

    config = TrainConfig(
        manifest_csv=args.manifest,
        backbone_name=args.backbone,
        epochs=epochs,
        frozen_epochs=min(args.frozen_epochs, epochs),
        batch_size=args.batch_size,
        checkpoint_dir=args.checkpoint_dir,
        max_samples=max_samples,
    )
    train(config)


if __name__ == "__main__":
    main()
