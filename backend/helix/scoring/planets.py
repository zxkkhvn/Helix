"""Planet definitions and instrument mappings."""

PLANET_INSTRUMENTS = {
    "mercury": {
        "display_name": "Mercury — Sleep, Function & Body",
        "quick_scan": ["isi"],
        "deep_dive": ["wemwbs", "maia2_brief", "meq", "psqi", "ffmq15"],
    },
    "venus": {
        "display_name": "Venus — Mood, Emotion & Awareness",
        "quick_scan": ["phq2", "gad2", "paq_s"],
        "deep_dive": ["phq9", "gad7", "paq", "ders16", "pss10", "dts", "erq"],
    },
    "earth": {
        "display_name": "Earth — Core Self",
        "quick_scan": ["bfi_s", "via_is_p"],
        "deep_dive": ["ipip50", "scs_sf", "brs", "rses", "aces"],
    },
    "mars": {
        "display_name": "Mars — Attention & Drive",
        "quick_scan": ["asrs_a"],
        "deep_dive": ["asrs_full", "bdefs_sf", "cfq25"],
    },
    "jupiter": {
        "display_name": "Jupiter — Values, Motivation & Meaning",
        "quick_scan": ["vlq"],
        "deep_dive": ["aaq2", "compact", "mlq", "swls"],
    },
    "saturn": {
        "display_name": "Saturn — Social & Relational",
        "quick_scan": ["lsas_sr_short"],
        "deep_dive": ["lsas_sr_full", "ecr_s", "ecr_rs", "dejong"],
    },
    "neptune": {
        "display_name": "Neptune — Deep Patterns",
        "quick_scan": ["ius12"],
        "deep_dive": ["mss_ysq", "ptq10", "cpq", "des_b", "pswq", "oci_r"],
    },
    "uranus": {
        "display_name": "Uranus — Neurodivergence",
        "quick_scan": ["aq10"],
        "deep_dive": ["catq", "raads_r"],
        "conditional": True,
    },
}

# Flat map for cache scoping and filtering
PLANET_INSTRUMENT_MAP = {
    pid: config.get("quick_scan", []) + config.get("deep_dive", [])
    for pid, config in PLANET_INSTRUMENTS.items()
}
