"""Composite Index Engine for platform-derived metrics."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np

from helix.scoring.base import ScoreResult

DEFINITIONS_DIR = Path(__file__).resolve().parent / "instruments" / "definitions"

@dataclass
class CompositeResult:
    index_id: str
    version: str
    score: float
    components_present: List[str]
    components_total: List[str]
    label: str
    is_partial: bool

def _load_json(filename: str) -> Union[dict, list]:
    path = DEFINITIONS_DIR / filename
    if not path.exists():
        return {} if filename == "norms.json" else []
    with open(path) as f:
        return json.load(f)

def load_composites() -> list[dict]:
    return _load_json("composites.json")

def load_norms() -> dict:
    return _load_json("norms.json")

def find_score(score_results: List[ScoreResult], component_id: str) -> Optional[float]:
    """Find a score value from a list of ScoreResults.
    
    Checks instrument total_score first. If component_id looks like a subscale
    (e.g. ecr_s_avoidance), checks subscale_scores of the base instrument.
    """
    # 1. Direct match on instrument_id
    for sr in score_results:
        if sr.instrument_id == component_id:
            return sr.total_score
            
    # 2. Subscale match (e.g. ecr_s_avoidance inside ecr_s)
    # The convention is {instrument_id}_{subscale_name}
    for sr in score_results:
        if component_id.startswith(f"{sr.instrument_id}_"):
            subscale_name = component_id[len(sr.instrument_id) + 1:]
            if sr.subscale_scores and subscale_name in sr.subscale_scores:
                return sr.subscale_scores[subscale_name]
                
    return None

def compute_composite(composite_def: dict, score_results: List[ScoreResult], norms: dict) -> Optional[CompositeResult]:
    """Compute a single composite index from available scores."""
    
    # Valued Living Gap is a custom computation based on VLQ gap scores
    if composite_def.get("computation") == "custom":
        if composite_def["index_id"] == "valued_living_gap":
            # VLQ scorer stores mean_gap in metadata and as total_score
            for sr in score_results:
                if sr.instrument_id == "vlq":
                    mean_gap = (
                        sr.metadata.get("mean_gap", sr.total_score)
                        if sr.metadata
                        else sr.total_score
                    )
                    return CompositeResult(
                        index_id=composite_def["index_id"],
                        version=composite_def["version"],
                        score=mean_gap,
                        components_present=["vlq"],
                        components_total=["vlq"],
                        label="1 of 1 components",
                        is_partial=False,
                    )
        return None

    available_z = {}
    for component_id in composite_def["components"]:
        score_val = find_score(score_results, component_id)
        if score_val is not None and component_id in norms:
            z = (score_val - norms[component_id]["mean"]) / norms[component_id]["sd"]
            if component_id in composite_def.get("sign_inversions", []):
                z = -z
            available_z[component_id] = z
    
    # Check required_core
    core_present = all(
        c in available_z for c in composite_def.get("required_core", [])
    )
    
    # Check required_minimum
    if not core_present or len(available_z) < composite_def["required_minimum"]:
        return None
        
    mean_z = float(np.mean(list(available_z.values())))
    
    return CompositeResult(
        index_id=composite_def["index_id"],
        version=composite_def["version"],
        score=mean_z,
        components_present=list(available_z.keys()),
        components_total=composite_def["components"],
        label=f"{len(available_z)} of {len(composite_def['components'])} components",
        is_partial=len(available_z) < len(composite_def["components"]),
    )

def compute_all_composites(score_results: List[ScoreResult], norms: Optional[dict] = None) -> List[dict]:
    """Compute all possible composites from a set of score results."""
    composites_def = load_composites()
    if norms is None:
        norms = load_norms()
        
    results = []
    for c_def in composites_def:
        res = compute_composite(c_def, score_results, norms)
        if res is not None:
            results.append({
                "index_id": res.index_id,
                "version": res.version,
                "score": res.score,
                "components_present": res.components_present,
                "components_total": res.components_total,
                "label": res.label,
                "is_partial": res.is_partial,
            })
    return results
