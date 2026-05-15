from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

import helix.models.models  # noqa: F401
from helix.db.database import create_tables


def test_create_tables_backfills_sqlite_compat_columns():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE sessions (
                    id VARCHAR(36) PRIMARY KEY,
                    state VARCHAR(32),
                    safety_flags JSON,
                    intake_data JSON,
                    anchors JSON,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE narratives (
                    id VARCHAR(36) PRIMARY KEY,
                    session_id VARCHAR(36),
                    task_type VARCHAR(64),
                    parameters_hash VARCHAR(64),
                    output_json JSON,
                    model_used VARCHAR(64),
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    created_at DATETIME
                )
                """
            )
        )

    create_tables(engine)

    inspector = inspect(engine)
    session_columns = {column["name"] for column in inspector.get_columns("sessions")}
    narrative_columns = {
        column["name"] for column in inspector.get_columns("narratives")
    }

    assert "fatigue_nudge_shown" in session_columns
    assert "fatigue_nudge_dismissed" in session_columns
    assert "narratives_stale" in session_columns
    assert "context_hash" in narrative_columns
