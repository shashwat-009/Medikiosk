"""Deterministic source merger with provenance and conflict preservation."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple
from .schemas import (
    ConflictValue, NormalizedItem, SummaryInput, SummaryResult,
    SummarySections, Provenance, VerificationStatus,
)


def _key(value: Any) -> str:
    if isinstance(value, dict):
        return repr(sorted((str(k), repr(v)) for k, v in value.items())).lower()
    if isinstance(value, list):
        return repr(value).lower()
    return str(value).strip().casefold()


def _merge_lists(*groups: List[NormalizedItem]) -> Tuple[List[Any], List[Provenance]]:
    """Stable union. Equal values are deduplicated; unequal values remain."""
    result, provenance = [], []
    seen = set()
    for group in groups:
        for item in group:
            k = _key(item.value)
            if k not in seen:
                seen.add(k)
                result.append(item.value)
                provenance.append(item.provenance)
    return result, provenance


def _merge_field(
    field: str,
    groups: List[List[NormalizedItem]],
    conflicts: Dict[str, ConflictValue],
    provenance: Dict[str, List[Provenance]],
) -> List[Any]:
    values, prov = _merge_lists(*groups)
    provenance[field] = prov
    if len(values) > 1:
        conflicts[field] = ConflictValue(values=values, provenances=prov)
    return values


def merge_sources(data: SummaryInput) -> SummaryResult:
    c = data.conversation
    o = data.ocr

    sections = SummarySections()
    conflicts: Dict[str, ConflictValue] = {}
    provenance: Dict[str, List[Provenance]] = {}

    sections.chief_complaints = _merge_field(
        "chief_complaints", [c.chief_complaints if c else []], conflicts, provenance
    )
    sections.history_of_present_illness = _merge_field(
        "history_of_present_illness", [c.history if c else []], conflicts, provenance
    )
    sections.relevant_symptoms = _merge_field(
        "relevant_symptoms",
        [c.symptoms if c else [], o.clinical_entities if o else []],
        conflicts, provenance,
    )
    sections.medical_history = _merge_field(
        "medical_history", [c.medical_history if c else []], conflicts, provenance
    )
    sections.medication_history = _merge_field(
        "medication_history",
        [c.medications if c else [], o.medications if o else []],
        conflicts, provenance,
    )
    sections.allergies = _merge_field(
        "allergies", [c.allergies if c else [], o.allergies if o else []],
        conflicts, provenance,
    )
    sections.investigations = _merge_field(
        "investigations", [c.investigations if c else [], o.labs if o else []],
        conflicts, provenance,
    )
    sections.document_derived_findings = _merge_field(
        "document_derived_findings",
        [o.discharge_findings if o else [], o.clinical_entities if o else []],
        conflicts, provenance,
    )
    sections.red_flags = _merge_field(
        "red_flags", [c.red_flags if c else []], conflicts, provenance
    )
    sections.relevant_negatives = _merge_field(
        "relevant_negatives", [c.relevant_negatives if c else []],
        conflicts, provenance,
    )

    timeline = list(data.timeline)
    if o:
        for item in o.timeline:
            timeline.append({
                "event": item.value,
                "provenance": item.provenance.model_dump(),
            })
    sections.timeline = timeline
    provenance["timeline"] = [e.provenance for e in data.timeline] + (
        [x.provenance for x in o.timeline] if o else []
    )

    other: Dict[str, List[Any]] = {}
    other_groups = []
    if c:
        other_groups.append(c.other)
    if o:
        other_groups.append(o.other)
    keys = sorted({k for group in other_groups for k in group})
    for key in keys:
        groups = [group.get(key, []) for group in other_groups]
        vals, prov = _merge_lists(*groups)
        if vals:
            other[key] = vals
            provenance[f"other.{key}"] = prov
    sections.other = other

    return SummaryResult(
        sections=sections,
        conflicts=conflicts,
        provenance=provenance,
        verification_status=(
            VerificationStatus.NEEDS_REVIEW if conflicts
            else VerificationStatus.UNVERIFIED
        ),
    )
