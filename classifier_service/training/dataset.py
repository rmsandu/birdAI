from pathlib import Path

import pandas as pd
from PIL import Image
from torch.utils.data import Dataset


class CUB200Dataset(Dataset):
    def __init__(self, manifest_csv: str, split: str, transform=None, max_samples: int | None = None):
        df = pd.read_csv(manifest_csv)
        df = df[df["split"] == split].reset_index(drop=True)
        if max_samples is not None:
            df = df.iloc[:max_samples].reset_index(drop=True)

        self.image_paths = df["image_path"].tolist()
        self.class_ids = df["class_id"].tolist()
        self.transform = transform

    def __len__(self) -> int:
        return len(self.image_paths)

    def __getitem__(self, index: int):
        image_path = self.image_paths[index]
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            if self.transform is not None:
                image = self.transform(image)
        return image, self.class_ids[index]
