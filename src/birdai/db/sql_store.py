from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session

from birdai.db.models import ObservationModel
from birdai.schemas import ObservationCorrection, ObservationRecord


class SQLObservationStore:
    def __init__(self, db: Session, base_dir: str = "data"):
        self.db = db
        self.base_dir = Path(base_dir)
        self.uploads_dir = self.base_dir / "uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _to_record(model: ObservationModel) -> ObservationRecord:
        data = {
            "id": model.id,
            "created_at": model.created_at.isoformat() if model.created_at else None,
            "modality": model.modality,
            "image_path": model.image_path,
            "audio_path": model.audio_path,
            "observation_context": model.context_json,
            "merlin_suggestion": model.merlin_suggestion_json,
            "candidates": model.candidates_json,
            "overall_uncertainty": model.overall_uncertainty,
            "overall_uncertainty_reasons": model.overall_uncertainty_reasons_json or [],
            "suggested_next_action": model.suggested_next_action,
            "user_correction": model.user_correction_json,
            "warnings": model.warnings_json or [],
            "local_classifier": model.local_classifier_json
            or {
                "source": "empty",
                "model_version": None,
                "predictions": [],
                "summary": "No classifier output recorded.",
            },
        }
        return ObservationRecord.model_validate(data)

    def save(
        self,
        record: ObservationRecord,
        user_id: str,
        files: Optional[dict[str, bytes]] = None,
    ) -> ObservationRecord:
        # Save media files to disk
        obs_dir = self.uploads_dir / record.id
        obs_dir.mkdir(parents=True, exist_ok=True)

        if files:
            for filename, content in files.items():
                dest = obs_dir / filename
                dest.write_bytes(content)

        model = ObservationModel(
            id=record.id,
            user_id=user_id,
            created_at=record.created_at,
            modality=record.modality,
            image_path=record.image_path,
            audio_path=record.audio_path,
            context_json=record.observation_context.model_dump(mode="json"),
            merlin_suggestion_json=(
                record.merlin_suggestion.model_dump(mode="json")
                if record.merlin_suggestion
                else None
            ),
            candidates_json=[c.model_dump(mode="json") for c in record.candidates],
            overall_uncertainty=record.overall_uncertainty,
            overall_uncertainty_reasons_json=record.overall_uncertainty_reasons,
            suggested_next_action=record.suggested_next_action,
            user_correction_json=(
                record.user_correction.model_dump(mode="json")
                if record.user_correction
                else None
            ),
            warnings_json=record.warnings,
            local_classifier_json=(
                record.local_classifier.model_dump(mode="json")
                if record.local_classifier
                else None
            ),
        )

        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_record(model)

    def get(self, observation_id: str, user_id: str) -> Optional[ObservationRecord]:
        model = (
            self.db.query(ObservationModel)
            .filter(
                ObservationModel.id == observation_id,
                ObservationModel.user_id == user_id,
            )
            .first()
        )
        if not model:
            return None
        return self._to_record(model)

    def update_correction(
        self,
        observation_id: str,
        correction: ObservationCorrection,
        user_id: str,
    ) -> Optional[ObservationRecord]:
        model = (
            self.db.query(ObservationModel)
            .filter(
                ObservationModel.id == observation_id,
                ObservationModel.user_id == user_id,
            )
            .first()
        )
        if not model:
            return None

        model.user_correction_json = correction.model_dump(mode="json")
        self.db.commit()
        self.db.refresh(model)
        return self._to_record(model)

    def list(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        reviewed_only: Optional[bool] = None,
    ) -> List[ObservationRecord]:
        query = self.db.query(ObservationModel).filter(
            ObservationModel.user_id == user_id
        )

        if reviewed_only is True:
            query = query.filter(ObservationModel.user_correction_json.is_not(None))
        elif reviewed_only is False:
            query = query.filter(ObservationModel.user_correction_json.is_(None))

        query = query.order_by(ObservationModel.created_at.desc())
        models = query.offset(offset).limit(limit).all()
        return [self._to_record(m) for m in models]

    def get_media_path(
        self,
        observation_id: str,
        filename: str,
        user_id: Optional[str] = None,
    ) -> Optional[Path]:
        # If user_id is provided, verify ownership first
        if user_id:
            exists = (
                self.db.query(ObservationModel)
                .filter(
                    ObservationModel.id == observation_id,
                    ObservationModel.user_id == user_id,
                )
                .first()
            )
            if not exists:
                return None

        target = self.uploads_dir / observation_id / filename
        if target.exists() and target.is_file():
            return target
        return None
