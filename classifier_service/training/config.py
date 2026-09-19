from dataclasses import dataclass


@dataclass
class TrainConfig:
    manifest_csv: str
    backbone_name: str = "convnext_tiny"
    num_classes: int = 200
    epochs: int = 15
    frozen_epochs: int = 2
    batch_size: int = 32
    lr_head: float = 1e-3
    lr_full: float = 1e-4
    weight_decay: float = 0.05
    label_smoothing: float = 0.1
    num_workers: int = 4
    checkpoint_dir: str = "classifier_service/checkpoints"
    max_samples: int | None = None
    seed: int = 42
