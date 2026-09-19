import timm
from timm.data import create_transform, resolve_data_config
from torch import nn


def build_model(backbone_name: str, num_classes: int, pretrained: bool = True) -> nn.Module:
    return timm.create_model(backbone_name, pretrained=pretrained, num_classes=num_classes)


def get_transforms(backbone_name: str, pretrained: bool = True):
    """Returns (train_transform, eval_transform) matching the backbone's pretrained stats."""
    reference_model = timm.create_model(backbone_name, pretrained=pretrained)
    data_config = resolve_data_config({}, model=reference_model)

    train_transform = create_transform(**data_config, is_training=True)
    eval_transform = create_transform(**data_config, is_training=False)
    return train_transform, eval_transform


def set_backbone_trainable(model: nn.Module, backbone_name: str, trainable: bool) -> None:
    """Freezes/unfreezes everything except the final classifier head.

    timm models expose their head via `get_classifier()`; we freeze every other
    parameter and always keep the head trainable.
    """
    head = model.get_classifier()
    head_param_ids = {id(p) for p in head.parameters()}

    for param in model.parameters():
        if id(param) in head_param_ids:
            param.requires_grad = True
        else:
            param.requires_grad = trainable
