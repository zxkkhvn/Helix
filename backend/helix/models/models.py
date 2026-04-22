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
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    assessment_instances: Mapped[list[AssessmentInstance]] = relationship(
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
