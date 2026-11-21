import json
from pathlib import Path
from typing import List, Optional, Protocol

from birdai.schemas import ObservationCorrection, ObservationRecord


class ObservationStore(Protocol):
    def save(
        self,
        record: ObservationRecord,
        files: Optional[dict[str, bytes]] = None,
    ) -> ObservationRecord: ...

    def get(self, observation_id: str) -> Optional[ObservationRecord]: ...

    def update_correction(
        self,
        observation_id: str,
        correction: ObservationCorrection,
    ) -> Optional[ObservationRecord]: ...

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        reviewed_only: Optional[bool] = None,
    ) -> List[ObservationRecord]: ...


class LocalObservationStore:
    def __init__(self, base_dir: str = "data"):
        self.base_dir = Path(base_dir)
        self.uploads_dir = self.base_dir / "uploads"
        self.records_dir = self.base_dir / "observations"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.records_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        record: ObservationRecord,
        files: Optional[dict[str, bytes]] = None,
    ) -> ObservationRecord:
        obs_dir = self.uploads_dir / record.id
        obs_dir.mkdir(parents=True, exist_ok=True)

        if files:
            for filename, content in files.items():
                dest = obs_dir / filename
                dest.write_bytes(content)

        record_file = self.records_dir / f"{record.id}.json"
        record_file.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2, ensure_ascii=False)
        )
        return record

    def get(self, observation_id: str) -> Optional[ObservationRecord]:
        record_file = self.records_dir / f"{observation_id}.json"
        if not record_file.exists():
            return None
        try:
            data = json.loads(record_file.read_text())
            return ObservationRecord.model_validate(data)
        except Exception:
            return None

    def update_correction(
        self,
        observation_id: str,
        correction: ObservationCorrection,
    ) -> Optional[ObservationRecord]:
        record = self.get(observation_id)
        if not record:
            return None
        updated = record.model_copy(update={"user_correction": correction})
        record_file = self.records_dir / f"{observation_id}.json"
        record_file.write_text(
            json.dumps(updated.model_dump(mode="json"), indent=2, ensure_ascii=False)
        )
        return updated

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        reviewed_only: Optional[bool] = None,
    ) -> List[ObservationRecord]:
        records: List[ObservationRecord] = []
        for path in sorted(self.records_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text())
                record = ObservationRecord.model_validate(data)
                if reviewed_only is True and record.user_correction is None:
                    continue
                if reviewed_only is False and record.user_correction is not None:
                    continue
                records.append(record)
            except Exception:
                continue
        return records[offset : offset + limit]

    def get_media_path(self, observation_id: str, filename: str) -> Optional[Path]:
        target = self.uploads_dir / observation_id / filename
        if target.exists() and target.is_file():
            return target
        return None
