from pathlib import Path
from datetime import datetime
import pandas as pd

from birdai.schemas import BirdAIResult


def log_observation(
    file_path: str,
    result: BirdAIResult,
    log_path: str = "data/observations.csv",
) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    top_species = result.likely_species[0] if result.likely_species else None

    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "file_path": file_path,
        "modality": result.modality,
        "top_common_name": top_species.common_name if top_species else None,
        "top_scientific_name": top_species.scientific_name if top_species else None,
        "top_likelihood": top_species.likelihood if top_species else None,
        "uncertainty": result.uncertainty,
        "suggested_next_action": result.suggested_next_action,
    }

    new_df = pd.DataFrame([row])

    if path.exists():
        old_df = pd.read_csv(path)
        df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        df = new_df

    df.to_csv(path, index=False)