"""Clinical organization rules for the case sheet."""
from __future__ import annotations

from typing import List
from .schemas import SummaryResult


SECTION_ORDER = [
    "chief_complaints",
    "history_of_present_illness",
    "relevant_symptoms",
    "medical_history",
    "medication_history",
    "allergies",
    "investigations",
    "document_derived_findings",
    "timeline",
    "red_flags",
    "relevant_negatives",
    "other",
]


def clinical_section_order() -> List[str]:
    return list(SECTION_ORDER)


def render_template(summary: SummaryResult) -> dict:
    """Return a stable, structured clinical template.

    Empty sections are retained so physician UI clients have a stable shape.
    """
    data = summary.sections.model_dump()
    return {name: data[name] for name in SECTION_ORDER}
