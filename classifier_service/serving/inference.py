import io

import torch
import torch.nn.functional as F
from PIL import Image

from classifier_service.serving.schemas import SpeciesPrediction
from classifier_service.training.model import build_model, get_transforms

MODEL_VERSION = "convnext_tiny-v1"


class ClassifierModel:
    def __init__(self, checkpoint_path: str):
        checkpoint = torch.load(checkpoint_path, map_location="cpu")

        self.backbone_name: str = checkpoint["backbone_name"]
        self.label_map: dict[str, str] = checkpoint["label_map"]
        self.model = build_model(
            self.backbone_name, checkpoint["num_classes"], pretrained=False
        )
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()

        _, self.transform = get_transforms(self.backbone_name, pretrained=False)

    def predict(self, image_bytes: bytes, top_k: int = 3) -> list[SpeciesPrediction]:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        tensor = self.transform(image).unsqueeze(0)

        with torch.no_grad():
            logits = self.model(tensor)
            probabilities = F.softmax(logits, dim=1).squeeze(0)

        top_k = min(top_k, probabilities.shape[0])
        top_probs, top_indices = probabilities.topk(top_k)

        return [
            SpeciesPrediction(
                species_name=self.label_map.get(str(index.item()), f"class_{index.item()}"),
                scientific_name=None,
                confidence=round(prob.item(), 4),
            )
            for prob, index in zip(top_probs, top_indices)
        ]
