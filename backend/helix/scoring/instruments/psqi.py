from __future__ import annotations
from typing import Dict, Any, Tuple, Optional
import re

from helix.scoring.base import BaseScorer, ScoreResult

class PSQIScorer(BaseScorer):
    """
    Custom scorer for the Pittsburgh Sleep Quality Index (PSQI).
    Calculates the 7 component scores and the global score.
    """

    def __init__(self, definition: Dict[str, Any]) -> None:
        self._def = definition
        self.instrument_id = definition["instrument_id"]
        self.items = definition["items"]
        self.scoring = definition["scoring"]
        self._item_order = [item["item_id"] for item in self.items]
        self._bands = self.scoring.get("bands")

    def _parse_time(self, time_str: str) -> Tuple[int, int]:
        """Parse time string like '10:30 PM' or '22:30' into 24h hours and minutes."""
        if not time_str or not isinstance(time_str, str):
            raise ValueError(f"Invalid time string: {time_str}")
            
        time_str = time_str.strip().lower()
        
        match = re.search(r'(\d{1,2})[:.]?(\d{2})?\s*(am|pm)?', time_str)
        if not match:
            raise ValueError(f"Could not parse time from: {time_str}")
            
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        ampm = match.group(3)
        
        if ampm == 'pm' and hour < 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
            
        return hour, minute

    def _calculate_hours_in_bed(self, bed_time_str: str, wake_time_str: str) -> float:
        try:
            b_hr, b_min = self._parse_time(bed_time_str)
            w_hr, w_min = self._parse_time(wake_time_str)
            
            if w_hr < b_hr:
                w_hr += 24
                
            hours = (w_hr - b_hr) + (w_min - b_min) / 60.0
            
            if hours < 0:
                hours += 24
            
            return max(0.1, min(hours, 24.0))
        except Exception:
            return 8.0

    def score(
        self,
        responses: dict[str, int | float | str],
        timestamps: Optional[list[float]] = None,
        carried_responses: Optional[dict[str, int | float | str]] = None,
    ) -> ScoreResult:
        all_responses = dict(responses)
        if carried_responses:
            all_responses.update(carried_responses)

        def get_val(item_id: str, default: int = 0) -> int:
            try:
                return int(all_responses.get(item_id, default))
            except ValueError:
                return default
                
        def get_float(item_id: str, default: float = 0.0) -> float:
            try:
                return float(all_responses.get(item_id, default))
            except ValueError:
                return default

        # Component 1
        comp_1 = get_val("psqi_06", 0)
        
        # Component 2
        q2_mins = get_val("psqi_02", 0)
        if q2_mins <= 15:
            q2_score = 0
        elif 16 <= q2_mins <= 30:
            q2_score = 1
        elif 31 <= q2_mins <= 60:
            q2_score = 2
        else:
            q2_score = 3
            
        q5a = get_val("psqi_05a", 0)
        comp_2_sum = q2_score + q5a
        if comp_2_sum == 0:
            comp_2 = 0
        elif 1 <= comp_2_sum <= 2:
            comp_2 = 1
        elif 3 <= comp_2_sum <= 4:
            comp_2 = 2
        else:
            comp_2 = 3
            
        # Component 3
        q4_hours = get_float("psqi_04", 0.0)
        if q4_hours > 7:
            comp_3 = 0
        elif 6 <= q4_hours <= 7:
            comp_3 = 1
        elif 5 <= q4_hours < 6:
            comp_3 = 2
        else:
            comp_3 = 3
            
        # Component 4
        bed_time = all_responses.get("psqi_01", "10:00 PM")
        wake_time = all_responses.get("psqi_03", "6:00 AM")
        
        hours_in_bed = self._calculate_hours_in_bed(str(bed_time), str(wake_time))
        efficiency = (q4_hours / hours_in_bed) * 100 if hours_in_bed > 0 else 0
        
        if efficiency > 85:
            comp_4 = 0
        elif 75 <= efficiency <= 85:
            comp_4 = 1
        elif 65 <= efficiency < 75:
            comp_4 = 2
        else:
            comp_4 = 3
            
        # Component 5
        dist_items = [
            "psqi_05b", "psqi_05c", "psqi_05d", "psqi_05e", 
            "psqi_05f", "psqi_05g", "psqi_05h", "psqi_05i", "psqi_05j"
        ]
        comp_5_sum = sum(get_val(k, 0) for k in dist_items)
        if comp_5_sum == 0:
            comp_5 = 0
        elif 1 <= comp_5_sum <= 9:
            comp_5 = 1
        elif 10 <= comp_5_sum <= 18:
            comp_5 = 2
        else:
            comp_5 = 3
            
        # Component 6
        comp_6 = get_val("psqi_07", 0)
        
        # Component 7
        comp_7_sum = get_val("psqi_08", 0) + get_val("psqi_09", 0)
        if comp_7_sum == 0:
            comp_7 = 0
        elif 1 <= comp_7_sum <= 2:
            comp_7 = 1
        elif 3 <= comp_7_sum <= 4:
            comp_7 = 2
        else:
            comp_7 = 3
            
        global_score = comp_1 + comp_2 + comp_3 + comp_4 + comp_5 + comp_6 + comp_7
        band = self._assign_band(float(global_score), self._bands)

        validity_warnings = []
        # Filter out text fields for longstring
        likert_items = [iid for iid in self._item_order if "psqi_01" not in iid and "psqi_03" not in iid]
        if self._detect_longstring(all_responses, likert_items):
            validity_warnings.append("longstring: 8+ identical consecutive responses detected")
        if self._detect_rapid_response(timestamps):
            validity_warnings.append("rapid_response: median inter-item time below 1.0s threshold")

        return ScoreResult(
            instrument_id=self.instrument_id,
            total_score=float(global_score),
            band=band,
            subscale_scores={
                "subjective_sleep_quality": float(comp_1),
                "sleep_latency": float(comp_2),
                "sleep_duration": float(comp_3),
                "habitual_sleep_efficiency": float(comp_4),
                "sleep_disturbances": float(comp_5),
                "use_of_sleeping_medication": float(comp_6),
                "daytime_dysfunction": float(comp_7),
            },
            safety_flags=[],
            validity_warnings=validity_warnings,
            metadata={
                "calculated_sleep_efficiency_percent": round(efficiency, 1),
                "calculated_hours_in_bed": round(hours_in_bed, 2)
            }
        )

def create_scorer(definition: Dict[str, Any]) -> PSQIScorer:
    return PSQIScorer(definition)
