import os

CLASSIFIER_CHECKPOINT_PATH = os.getenv(
    "CLASSIFIER_CHECKPOINT_PATH", "checkpoints/best.pt"
)
CLASSIFIER_TOP_K = int(os.getenv("CLASSIFIER_TOP_K", "3"))
