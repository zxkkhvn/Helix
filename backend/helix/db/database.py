"""Database engine, session factory, and FastAPI dependency."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# DB path configurable via env var. Defaults to helix.db next to this file.
_default_db = str(Path(__file__).resolve().parent.parent.parent / "helix.db")
DB_URL = os.environ.get("HELIX_DB_URL", f"sqlite:///{_default_db}")

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a database session."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_tables(target_engine=None) -> None:
    """Create all tables. Accepts an optional engine for test overrides."""
    resolved_engine = target_engine or engine
    Base.metadata.create_all(bind=resolved_engine)
    _apply_sqlite_compatibility_migrations(resolved_engine)


def _apply_sqlite_compatibility_migrations(target_engine) -> None:
    """Add missing columns for older local SQLite databases.

    This keeps existing developer databases usable after lightweight schema
    changes without introducing a full migration framework yet.
    """
    if target_engine.dialect.name != "sqlite":
        return

    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())

    with target_engine.begin() as conn:
        if "sessions" in existing_tables:
            session_columns = {
                column["name"] for column in inspector.get_columns("sessions")
            }
            missing_session_columns = {
                "fatigue_nudge_shown": "BOOLEAN DEFAULT 0",
                "fatigue_nudge_dismissed": "BOOLEAN DEFAULT 0",
                "narratives_stale": "BOOLEAN DEFAULT 0",
            }
            for column_name, column_sql in missing_session_columns.items():
                if column_name not in session_columns:
                    conn.execute(
                        text(
                            f"ALTER TABLE sessions ADD COLUMN {column_name} {column_sql}"
                        )
                    )
            conn.execute(
                text(
                    "UPDATE sessions "
                    "SET fatigue_nudge_shown = COALESCE(fatigue_nudge_shown, 0), "
                    "fatigue_nudge_dismissed = COALESCE(fatigue_nudge_dismissed, 0), "
                    "narratives_stale = COALESCE(narratives_stale, 0)"
                )
            )

        if "narratives" in existing_tables:
            narrative_columns = {
                column["name"] for column in inspector.get_columns("narratives")
            }
            if "context_hash" not in narrative_columns:
                conn.execute(
                    text("ALTER TABLE narratives ADD COLUMN context_hash VARCHAR(64)")
                )
