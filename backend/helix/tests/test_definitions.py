"""Validate all instrument JSON definitions conform to the schema contract."""

import json

import pytest

# Required top-level keys per the contract (Section 5 of implementation state)
REQUIRED_KEYS = {
    "instrument_id", "version", "name", "abbreviation", "planet", "tier",
    "time_window", "time_window_text", "time_window_days",
    "cultural_validity", "licence_status",
    "sensitive_content", "sensitive_content_warning",
    "calibration_signal", "min_trials_for_partial_scoring",
    "composite_contributions", "consistency_pairs",
    "response_option_sets", "items", "scoring", "routing",
}

VALID_TIERS = {"quick_scan", "deep_dive", "core_flow", "core_exploration"}
VALID_SCORING_METHODS = {"sum", "mean", "custom"}
VALID_CULTURAL_TIERS = {
    "broadly_cross_cultural", "moderate_bias_risk",
    "high_bias_risk", "insufficient_evidence",
}


class TestDefinitionSchema:
    """Every JSON definition must conform to the contract."""

    def test_all_definitions_load(self, all_definitions):
        assert len(all_definitions) > 0, "No definitions found"

    def test_required_keys_present(self, all_definitions):
        for inst_id, defn in all_definitions.items():
            missing = REQUIRED_KEYS - set(defn.keys())
            assert not missing, f"{inst_id}: missing keys {missing}"

    def test_instrument_id_matches_filename(self, definitions_dir):
        for path in sorted(definitions_dir.glob("*.json")):
            if path.name in ("composites.json", "norms.json"):
                continue
            with open(path) as f:
                defn = json.load(f)
            expected_id = path.stem
            assert defn["instrument_id"] == expected_id, (
                f"Filename {path.name} does not match instrument_id '{defn['instrument_id']}'"
            )

    def test_valid_tier(self, all_definitions):
        for inst_id, defn in all_definitions.items():
            assert defn["tier"] in VALID_TIERS, (
                f"{inst_id}: invalid tier '{defn['tier']}'"
            )

    def test_valid_scoring_method(self, all_definitions):
        for inst_id, defn in all_definitions.items():
            assert defn["scoring"]["method"] in VALID_SCORING_METHODS, (
                f"{inst_id}: invalid scoring method '{defn['scoring']['method']}'"
            )

    def test_valid_cultural_validity_tier(self, all_definitions):
        for inst_id, defn in all_definitions.items():
            assert defn["cultural_validity"]["tier"] in VALID_CULTURAL_TIERS, (
                f"{inst_id}: invalid cultural_validity tier"
            )

    def test_items_not_empty(self, all_definitions):
        for inst_id, defn in all_definitions.items():
            assert len(defn["items"]) > 0, f"{inst_id}: no items defined"

    def test_item_ids_unique(self, all_definitions):
        for inst_id, defn in all_definitions.items():
            ids = [item["item_id"] for item in defn["items"]]
            assert len(ids) == len(set(ids)), (
                f"{inst_id}: duplicate item_ids found"
            )

    def test_response_options_key_exists(self, all_definitions):
        """Every item references a response_options_key that exists in response_option_sets."""
        for inst_id, defn in all_definitions.items():
            sets = defn["response_option_sets"]
            for item in defn["items"]:
                key = item["response_options_key"]
                assert key in sets, (
                    f"{inst_id}/{item['item_id']}: response_options_key "
                    f"'{key}' not found in response_option_sets"
                )

    def test_score_range_consistent(self, all_definitions):
        """Score range [min, max] should be achievable given items and response options."""
        for inst_id, defn in all_definitions.items():
            if defn["scoring"]["method"] == "custom":
                continue  # custom scorers validate their own ranges
            score_min, score_max = defn["scoring"]["range"]
            items = defn["items"]
            scoreable = [i for i in items if not i.get("exclude_from_score", False)]

            option_mins = []
            option_maxs = []
            for item in scoreable:
                key = item["response_options_key"]
                options = defn["response_option_sets"][key]
                values = [o["value"] for o in options]
                option_mins.append(min(values))
                option_maxs.append(max(values))

            if defn["scoring"]["method"] == "sum":
                expected_min = sum(option_mins)
                expected_max = sum(option_maxs)
                assert score_min == expected_min, (
                    f"{inst_id}: range min {score_min} != sum of item mins {expected_min}"
                )
                assert score_max == expected_max, (
                    f"{inst_id}: range max {score_max} != sum of item maxes {expected_max}"
                )

    def test_bands_cover_full_range(self, all_definitions):
        """Severity bands should cover the entire score range without gaps or overlaps."""
        for inst_id, defn in all_definitions.items():
            bands = defn["scoring"].get("bands")
            if not bands:
                continue
            score_min, score_max = defn["scoring"]["range"]
            assert bands[0]["min"] == score_min, (
                f"{inst_id}: first band min {bands[0]['min']} != score range min {score_min}"
            )
            assert bands[-1]["max"] == score_max, (
                f"{inst_id}: last band max {bands[-1]['max']} != score range max {score_max}"
            )
            for i in range(1, len(bands)):
                diff = round(bands[i]["min"] - bands[i - 1]["max"], 2)
                assert diff in (1.0, 0.01), (
                    f"{inst_id}: gap or overlap between bands "
                    f"'{bands[i-1]['label']}' and '{bands[i]['label']}'. Gap is {diff}"
                )

    def test_safety_flag_items_have_trigger(self, all_definitions):
        """Items with safety_flag=true must have a safety_trigger defined."""
        for inst_id, defn in all_definitions.items():
            for item in defn["items"]:
                if item.get("safety_flag"):
                    assert item.get("safety_trigger") is not None, (
                        f"{inst_id}/{item['item_id']}: safety_flag=true but no safety_trigger"
                    )

    def test_carry_forward_maps_valid_items(self, all_definitions):
        """If carry_forward_items is defined, all target item_ids must exist in this definition."""
        for inst_id, defn in all_definitions.items():
            cf = defn["routing"].get("carry_forward_items")
            if not cf:
                continue
            item_ids = {item["item_id"] for item in defn["items"]}
            for parent_item, child_item in cf.items():
                assert child_item in item_ids, (
                    f"{inst_id}: carry_forward target '{child_item}' "
                    f"not found in items"
                )

    def test_parent_instrument_exists(self, all_definitions):
        """If parent_instrument is set, that instrument must also have a definition."""
        for inst_id, defn in all_definitions.items():
            parent = defn["routing"].get("parent_instrument")
            if parent:
                assert parent in all_definitions, (
                    f"{inst_id}: parent_instrument '{parent}' has no definition"
                )

    def test_subscale_items_exist(self, all_definitions):
        """All items referenced in subscales must exist in the items array."""
        for inst_id, defn in all_definitions.items():
            subscales = defn["scoring"].get("subscales")
            if not subscales:
                continue
            item_ids = {item["item_id"] for item in defn["items"]}
            for scale_name, scale_def in subscales.items():
                for item_id in scale_def["items"]:
                    assert item_id in item_ids, (
                        f"{inst_id}: subscale '{scale_name}' references "
                        f"non-existent item '{item_id}'"
                    )

    def test_subscale_items_cover_all(self, all_definitions):
        """For custom scorers with subscales, every item should belong to at least one subscale."""
        for inst_id, defn in all_definitions.items():
            subscales = defn["scoring"].get("subscales")
            if not subscales:
                continue
            item_ids = {item["item_id"] for item in defn["items"]
                        if not item.get("exclude_from_score", False)}
            subscale_items = set()
            for scale_def in subscales.values():
                subscale_items.update(scale_def["items"])
            uncovered = item_ids - subscale_items
            assert not uncovered, (
                f"{inst_id}: items not in any subscale: {uncovered}"
            )
