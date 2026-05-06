// dictionary.js

const FRIENDLY_NAMES = {
    // Core Flow
    'intake': 'About You',
    'pbat': 'How You\'ve Been',
    'anchors': 'Right Now',
    'wsas': 'Daily Life Impact',
    'pcptsd5': 'Recent Experiences',

    // Mercury — Sleep, Function & Body
    'isi': 'Sleep Patterns',
    'wemwbs': 'Mental Wellbeing',
    'maia2_brief': 'Body Awareness',
    'meq': 'Sleep-Wake Rhythm',
    'psqi': 'Sleep Quality',
    'ffmq15': 'Mindful Awareness',

    // Venus — Mood, Emotion & Awareness
    'phq2': 'Mood Screen',
    'phq9': 'Mood & Depression',
    'gad2': 'Anxiety Screen',
    'gad7': 'Anxiety & Worry',
    'paq_s': 'Emotional Awareness Screen',
    'paq': 'Emotional Awareness',
    'ders16': 'Emotion Regulation',
    'pss10': 'Perceived Stress',
    'dts': 'Distress Tolerance',
    'erq': 'Emotion Strategies',

    // Earth — Core Self
    'bfi_s': 'Personality Snapshot',
    'ipip50': 'Personality in Depth',
    'scs_sf': 'Self-Compassion',
    'brs': 'Resilience',
    'rses': 'Self-Esteem',
    'aces': 'Childhood Experiences',
    'via_is_p': 'Character Strengths',

    // Mars — Attention & Drive
    'asrs_a': 'Attention & Focus Screen',
    'asrs_full': 'Attention & Focus in Depth',
    'bdefs_sf': 'Executive Functioning',
    'cfq25': 'Everyday Cognitive Slips',

    // Jupiter — Values, Motivation & Meaning
    'vlq': 'Values & Priorities',
    'aaq2': 'Psychological Flexibility',
    'compact': 'Openness & Valued Action',
    'mlq': 'Meaning in Life',
    'swls': 'Life Satisfaction',

    // Saturn — Social & Relational
    'lsas_sr_short': 'Social Comfort Screen',
    'lsas_sr_full': 'Social Comfort in Depth',
    'ecr_s': 'Attachment Style',
    'ecr_rs': 'Relationship Patterns',
    'dejong': 'Connection & Loneliness',

    // Neptune — Deep Patterns
    'ius12': 'Uncertainty Tolerance',
    'mss_ysq': 'Core Beliefs & Schemas',
    'ptq10': 'Repetitive Thinking',
    'cpq': 'Perfectionism',
    'des_b': 'Dissociative Experiences',
    'pswq': 'Worry Patterns',
    'oci_r': 'Intrusive Thoughts & Habits',

    // Uranus — Neurodivergence
    'aq10': 'Autism Traits Screen',
    'catq': 'Social Camouflaging',
    'raads_r': 'Autism Traits in Depth',

    // Asteroid Belt — Trauma
    'pcl5': 'Trauma Response',
};

function getFriendlyName(id) {
    if (!id) return '';
    const key = id.toLowerCase();
    
    // Add the acronym to the end if we have a friendly name
    if (FRIENDLY_NAMES[key]) {
        return `${FRIENDLY_NAMES[key]} (${id.toUpperCase()})`;
    }
    return id.toUpperCase();
}
