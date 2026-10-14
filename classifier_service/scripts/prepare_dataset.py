"""Build a manifest.csv and label_map.json from a downloaded CUB-200-2011 tree.

CUB-200-2011 ships one official train/test split (train_test_split.txt) but no
validation split. This script carves a stratified validation split out of the
official training portion (default 15%, fixed seed) so training/evaluation code
never needs to touch the official held-out test split.

label_map.json is the artifact that couples training/ and serving/: it maps the
0-indexed class id used by the model to a human-friendly species name (CUB class
names look like "001.Black_footed_Albatross" and need cleanup for display).
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import pandas as pd

VAL_FRACTION = 0.15
SEED = 42


def clean_species_name(raw_class_name: str) -> str:
    # e.g. "001.Black_footed_Albatross" -> "Black footed Albatross"
    _, _, name = raw_class_name.partition(".")
    return name.replace("_", " ").strip()


def load_cub_tables(cub_dir: Path) -> pd.DataFrame:
    images = pd.read_csv(
        cub_dir / "images.txt", sep=" ", names=["image_id", "image_path"]
    )
    labels = pd.read_csv(
        cub_dir / "image_class_labels.txt", sep=" ", names=["image_id", "class_id"]
    )
    split = pd.read_csv(
        cub_dir / "train_test_split.txt", sep=" ", names=["image_id", "is_training_image"]
    )
    classes = pd.read_csv(
        cub_dir / "classes.txt", sep=" ", names=["class_id", "class_name"]
    )

    df = images.merge(labels, on="image_id").merge(split, on="image_id")
    df = df.merge(classes, on="class_id")
    return df


def assign_val_split(df: pd.DataFrame, val_fraction: float, seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    by_class_train_ids: dict[int, list[int]] = defaultdict(list)

    for row in df.itertuples():
        if row.is_training_image == 1:
            by_class_train_ids[row.class_id].append(row.image_id)

    val_image_ids: set[int] = set()
    for class_id, image_ids in by_class_train_ids.items():
        image_ids = sorted(image_ids)
        rng.shuffle(image_ids)
        n_val = max(1, round(len(image_ids) * val_fraction))
        val_image_ids.update(image_ids[:n_val])

    def split_for(row) -> str:
        if row.is_training_image == 0:
            return "test"
        if row.image_id in val_image_ids:
            return "val"
        return "train"

    df = df.copy()
    df["split"] = df.apply(split_for, axis=1)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        default=Path(__file__).resolve().parent.parent / "data",
        type=Path,
    )
    parser.add_argument("--val-fraction", type=float, default=VAL_FRACTION)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    cub_dir = args.data_dir / "CUB_200_2011"
    if not cub_dir.exists():
        raise SystemExit(
            f"{cub_dir} not found. Run download_cub200.py first."
        )

    df = load_cub_tables(cub_dir)
    df = assign_val_split(df, args.val_fraction, args.seed)

    df["class_id_0based"] = df["class_id"] - 1
    df["species_name"] = df["class_name"].map(clean_species_name)
    df["image_path"] = df["image_path"].apply(lambda p: str(cub_dir / "images" / p))

    manifest = df[["image_path", "class_id_0based", "species_name", "split"]].rename(
        columns={"class_id_0based": "class_id"}
    )
    manifest_path = cub_dir / "manifest.csv"
    manifest.to_csv(manifest_path, index=False)

    label_map = (
        df[["class_id_0based", "species_name"]]
        .drop_duplicates()
        .sort_values("class_id_0based")
        .set_index("class_id_0based")["species_name"]
        .to_dict()
    )
    label_map_path = cub_dir / "label_map.json"
    label_map_path.write_text(
        json.dumps({str(k): v for k, v in label_map.items()}, indent=2, ensure_ascii=False)
    )

    print(f"Wrote {len(manifest)} rows to {manifest_path}")
    print(f"Wrote {len(label_map)} classes to {label_map_path}")
    print(manifest["split"].value_counts().to_string())


if __name__ == "__main__":
    main()
