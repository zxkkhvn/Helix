"""SQLAlchemy ORM models — Venus vertical slice schema.

UUIDs as PKs, JSON columns for flexible payloads.
Designed for Postgres migration (no SQLite-specific types used).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from helix.db.database import Base


class Session(Base):
    """A user assessment session."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    state: Mapped[str] = mapped_column(String(32), default="EXPLORING")
    # JSON list of unacknowledged safety events:
    # [{"instrument_id", "item_id", "reason", "timestamp"}]
    safety_flags: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    intake_data: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    anchors: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    fatigue_nudge_shown: Mapped[bool] = mapped_column(default=False)
    fatigue_nudge_dismissed: Mapped[bool] = mapped_column(default=False)
    # Set True whenever a new score is persisted; cleared when narratives are (re-)generated.
    narratives_stale: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    assessment_instances: Mapped[list[AssessmentInstance]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    narratives: Mapped[list[Narrative]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class AssessmentInstance(Base):
    """One completed administration of an instrument within a session."""

    __tablename__ = "assessment_instances"

    id: Mapped[uuid.UUID] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    instrument_id: Mapped[str] = mapped_column(String(64))
    instrument_version: Mapped[str] = mapped_column(String(16))
    # Self-referencing FK — links expansion instruments to their parent.
    parent_instance_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("assessment_instances.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Complete response set (new items + carried items merged), {item_id: value}
    responses: Mapped[Any] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="COMPLETED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, default=datetime.utcnow
    )

    session: Mapped[Session] = relationship(back_populates="assessment_instances")
    score: Mapped[Optional[Score]] = relationship(
        back_populates="assessment_instance", uselist=False, cascade="all, delete-orphan"
    )
    children: Mapped[list[AssessmentInstance]] = relationship(
        "AssessmentInstance", foreign_keys=[parent_instance_id]
    )


class Score(Base):
    """Persisted ScoreResult from the scoring engine."""

    __tablename__ = "scores"

    id: Mapped[uuid.UUID] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    assessment_instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assessment_instances.id", ondelete="CASCADE")
    )
    instrument_id: Mapped[str] = mapped_column(String(64))
    total_score: Mapped[float] = mapped_column(Float)
    band: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    subscale_scores: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    safety_flags: Mapped[Any] = mapped_column(JSON, default=list)
    validity_warnings: Mapped[Any] = mapped_column(JSON, default=list)
    score_metadata: Mapped[Any] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    assessment_instance: Mapped[AssessmentInstance] = relationship(
        back_populates="score"
    )


class Narrative(Base):
    """Cached AI-generated narrative for a session and task.

    Keyed by (session_id, task_type, parameters_hash) where parameters_hash
    is the sha256 of the sorted task parameters JSON (e.g. {"planet_id": "venus"}).
    """

    __tablename__ = "narratives"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    task_type: Mapped[str] = mapped_column(String(64))
    parameters_hash: Mapped[str] = mapped_column(String(64))
    # sha256 of the ContextSerializer payload used to generate this narrative.
    context_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    output_json: Mapped[Any] = mapped_column(JSON)
    model_used: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped[Session] = relationship(back_populates="narratives")
