"""Protocol citation registry.

Single source of truth for the formal references used in clinical advice
text shown to operators and base-station commanders. Citations are short,
human-readable strings (NOT URLs) so that they survive an offline /
no-internet environment intact.

Used by:
    - risk_engine.py (every HIDDEN_RISK_RULES entry has a `source` value
      that must appear in this registry)
    - sitrep_generator.py (when commander asks "why is this RED?",
      we attach the citation lineage)
    - gradio_app.py (info-tooltip text)
"""
from typing import Dict, List

PROTOCOL_REGISTRY: Dict[str, Dict[str, str]] = {
    "ATLS_11": {
        "name": "ATLS 11th Edition",
        "full_name": "Advanced Trauma Life Support (ACS)",
        "publisher": "American College of Surgeons Committee on Trauma",
        "year": "2018",
    },
    "PHTLS_10": {
        "name": "PHTLS 10th Edition",
        "full_name": "Pre-Hospital Trauma Life Support",
        "publisher": "NAEMT / American College of Surgeons",
        "year": "2023",
    },
    "AHA_2024": {
        "name": "AHA 2024 First Aid",
        "full_name": "AHA / Red Cross First Aid Guidelines 2024",
        "publisher": "American Heart Association",
        "year": "2024",
    },
    "WHO_EMT_2021": {
        "name": "WHO EMT Standards 2021",
        "full_name": "Classification and Minimum Standards for Emergency Medical Teams",
        "publisher": "World Health Organization",
        "year": "2021",
    },
    "CDC_BLAST": {
        "name": "CDC Blast Injury Guidelines",
        "full_name": "Emergency Department Blast Injury Resources",
        "publisher": "Centers for Disease Control and Prevention",
        "year": "2020",
    },
    "ALSO": {
        "name": "ALSO",
        "full_name": "Advanced Life Support in Obstetrics",
        "publisher": "American Academy of Family Physicians",
        "year": "2017",
    },
    "JUMPSTART": {
        "name": "JumpSTART Pediatric Triage",
        "full_name": "Pediatric Multiple Casualty Incident Triage Tool",
        "publisher": "Lou Romig MD (originator)",
        "year": "1995, revised",
    },
    "GERIATRIC_TRAUMA": {
        "name": "Geriatric Trauma Guidelines",
        "full_name": "Eastern Association for the Surgery of Trauma — Geriatric Trauma PMG",
        "publisher": "EAST",
        "year": "2012, revised",
    },
    "ERG_2024": {
        "name": "ERG 2024",
        "full_name": "Emergency Response Guidebook",
        "publisher": "PHMSA / US DOT",
        "year": "2024",
    },
    "NIMS": {
        "name": "NIMS / FEMA IS-100/200/700",
        "full_name": "National Incident Management System Independent Study",
        "publisher": "FEMA Emergency Management Institute",
        "year": "2018, revised",
    },
}


# Token aliases for sloppy citation strings (e.g. "PHTLS 10th Ed" vs full name).
_ALIASES = {
    "ATLS_11": ("atls",),
    "PHTLS_10": ("phtls",),
    "AHA_2024": ("aha", "red cross"),
    "WHO_EMT_2021": ("who emt",),
    "CDC_BLAST": ("cdc blast",),
    "ALSO": ("also",),
    "JUMPSTART": ("jumpstart",),
    "GERIATRIC_TRAUMA": ("geriatric",),
    "ERG_2024": ("erg",),
    "NIMS": ("nims", "fema"),
}


def lookup(citation_str: str) -> List[Dict[str, str]]:
    """Resolve a free-text citation like 'PHTLS 10th Ed; WHO EMT Standards 2021'
    into a list of registry entries, preserving order. Unknown sources are
    silently dropped — the caller can fall back to the raw string."""
    if not citation_str:
        return []
    raw_parts = [p.strip() for p in citation_str.replace(",", ";").split(";")]
    matches: List[Dict[str, str]] = []
    for part in raw_parts:
        low = part.lower()
        hit_key: str | None = None
        for key, aliases in _ALIASES.items():
            if any(a in low for a in aliases):
                hit_key = key
                break
        if hit_key and hit_key in PROTOCOL_REGISTRY:
            entry = PROTOCOL_REGISTRY[hit_key]
            if entry not in matches:
                matches.append(entry)
    return matches


def all_protocol_names() -> List[str]:
    """For sitrep/footer rendering."""
    return [v["name"] for v in PROTOCOL_REGISTRY.values()]
