from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship

from birdai.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserModel(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    observations = relationship(
        "ObservationModel",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(ObservationModel.created_at)",
    )


class ObservationModel(Base):
    __tablename__ = "observations"

    id = Column(String(64), primary_key=True, index=True)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
        nullable=False,
    )
    modality = Column(String(32), nullable=False)
    image_path = Column(String(512), nullable=True)
    audio_path = Column(String(512), nullable=True)

    # Structured metadata payloads (compatible with SQLite JSON & Postgres JSON/JSONB)
    context_json = Column(JSON, nullable=False)
    merlin_suggestion_json = Column(JSON, nullable=True)
    candidates_json = Column(JSON, nullable=False)
    overall_uncertainty = Column(String(32), nullable=False)
    overall_uncertainty_reasons_json = Column(JSON, nullable=False)
    suggested_next_action = Column(Text, nullable=True)
    user_correction_json = Column(JSON, nullable=True)
    warnings_json = Column(JSON, nullable=True)
    local_classifier_json = Column(JSON, nullable=True)

    user = relationship("UserModel", back_populates="observations")
