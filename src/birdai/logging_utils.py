import json
from datetime import datetime
from pathlib import Path

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
    serialized_result = result.model_dump(mode="json")

    row = {
        "logged_at": datetime.now().isoformat(timespec="seconds"),
        "file_path": file_path,
        "observation_date": serialized_result["observation_context"]["observation_date"],
        "observation_time": serialized_result["observation_context"]["observation_time"],
        "location_text": serialized_result["observation_context"]["location_text"],
        "latitude": serialized_result["observation_context"]["latitude"],
        "longitude": serialized_result["observation_context"]["longitude"],
        "location_source": serialized_result["observation_context"]["location_source"],
        "modality": result.modality,
        "top_common_name": top_species.common_name if top_species else None,
        "top_scientific_name": top_species.scientific_name if top_species else None,
        "top_confidence_probability": (
            top_species.confidence_probability if top_species else None
        ),
        "uncertainty": result.uncertainty,
        "suggested_next_action": result.suggested_next_action,
        "evidence_source": top_species.evidence.source if top_species else None,
        "result_json": json.dumps(serialized_result, ensure_ascii=False),
    }

    new_df = pd.DataFrame([row])

    if path.exists():
        old_df = pd.read_csv(path)
        df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        df = new_df

    df.to_csv(path, index=False)
