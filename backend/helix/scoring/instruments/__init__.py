"""Exposes the definitions directory path for use by the app factory."""

from pathlib import Path

_DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"
