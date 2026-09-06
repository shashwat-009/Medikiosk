"""Physician-facing case-sheet construction."""
from __future__ import annotations

from .schemas import (
    ClinicalCaseSheet, SummaryResult, VerificationItem, VerificationStatus,
)
from .clinical_template import render_template


def build_case_sheet(summary: SummaryResult) -> ClinicalCaseSheet:
    """Build a structured, explicitly unverified physician-review case sheet."""
    sections = render_template(summary)
    verification = [
        VerificationItem(field=name, status=VerificationStatus.UNVERIFIED)
        for name, value in sections.items()
        if value not in (None, [], {})
    ]
    return ClinicalCaseSheet(
        summary=summary,
        verification=verification,
        physician_verified=False,
        verification_note=None,
    )
