"""Database engine, session factory, and FastAPI dependency."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
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
    Base.metadata.create_all(bind=target_engine or engine)
