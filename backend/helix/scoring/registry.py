"""Scorer registry — dynamic registration and auto-discovery from JSON definitions."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Optional

from helix.scoring.base import BaseScorer
from helix.scoring.generic import GenericScorer

DEFINITIONS_DIR = (
    Path(__file__).resolve().parent / "instruments" / "definitions"
)

# instrument_id → module path for custom scorers.
# Add entries here as custom scorers are implemented.
CUSTOM_SCORER_MODULES: dict[str, str] = {
    "paq": "helix.scoring.instruments.paq",
    "pbat": "helix.scoring.instruments.pbat",
    "meq": "helix.scoring.instruments.meq",
    "psqi": "helix.scoring.instruments.psqi",
}

_registry: dict[str, BaseScorer] = {}


def register(instrument_id: str, scorer: BaseScorer) -> None:
    """Register a scorer under the given instrument_id."""
    _registry[instrument_id] = scorer


def get_scorer(instrument_id: str) -> BaseScorer:
    """Return the scorer for instrument_id.

    Raises KeyError if not registered. Call auto_discover() first or
    register scorers explicitly.
    """
    if instrument_id not in _registry:
        raise KeyError(
            f"No scorer registered for '{instrument_id}'. "
            "Has auto_discover() been called?"
        )
    return _registry[instrument_id]


def all_registered() -> list[str]:
    """Return sorted list of all registered instrument IDs."""
    return sorted(_registry.keys())


def auto_discover(definitions_dir: Optional[Path] = None) -> None:
    """Scan definitions directory and register scorers.

    - sum/mean instruments → GenericScorer
    - custom instruments → load from CUSTOM_SCORER_MODULES, call register()
    - composites.json → skipped (handled by composite engine)
    """
    defs_dir = definitions_dir or DEFINITIONS_DIR
    for path in sorted(defs_dir.glob("*.json")):
        if path.name in ("composites.json", "norms.json"):
            continue
        with open(path) as f:
            definition = json.load(f)

        instrument_id: str = definition["instrument_id"]
        method: str = definition["scoring"]["method"]

        if method in ("sum", "mean"):
            register(instrument_id, GenericScorer(definition))
        elif method == "custom":
            module_path = CUSTOM_SCORER_MODULES.get(instrument_id)
            if module_path is None:
                # Custom scorer not yet implemented — skip silently for now.
                # This allows partial discovery during incremental development.
                continue
            module = importlib.import_module(module_path)
            # Convention: module exposes a factory function `create_scorer(definition)`
            scorer: BaseScorer = module.create_scorer(definition)
            register(instrument_id, scorer)
