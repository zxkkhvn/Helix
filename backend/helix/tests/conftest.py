"""Shared test fixtures for Helix scoring tests."""

import json
from pathlib import Path

import pytest

DEFINITIONS_DIR = Path(__file__).resolve().parent.parent / "scoring" / "instruments" / "definitions"


@pytest.fixture
def definitions_dir():
    """Path to instrument JSON definitions directory."""
    return DEFINITIONS_DIR


@pytest.fixture
def all_definitions(definitions_dir):
    """Load and return all instrument definitions as a dict keyed by instrument_id."""
    defs = {}
    for path in sorted(definitions_dir.glob("*.json")):
        if path.name == "composites.json":
            continue
        with open(path) as f:
            defn = json.load(f)
        defs[defn["instrument_id"]] = defn
    return defs


@pytest.fixture
def load_definition(definitions_dir):
    """Factory fixture: load a single instrument definition by instrument_id."""
    def _load(instrument_id: str) -> dict:
        path = definitions_dir / f"{instrument_id}.json"
        if not path.exists():
            pytest.fail(f"Definition file not found: {path}")
        with open(path) as f:
            return json.load(f)
    return _load


def make_responses(definition: dict, value: int) -> dict:
    """Generate a response dict for all items in a definition set to the same value."""
    return {item["item_id"]: value for item in definition["items"]}


def make_max_responses(definition: dict) -> dict:
    """Generate responses at the maximum value for each item."""
    responses = {}
    for item in definition["items"]:
        key = item["response_options_key"]
        options = definition["response_option_sets"][key]
        responses[item["item_id"]] = max(o["value"] for o in options)
    return responses


def make_min_responses(definition: dict) -> dict:
    """Generate responses at the minimum value for each item."""
    responses = {}
    for item in definition["items"]:
        key = item["response_options_key"]
        options = definition["response_option_sets"][key]
        responses[item["item_id"]] = min(o["value"] for o in options)
    return responses
