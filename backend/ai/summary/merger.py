"""Deterministic source merger with provenance and conflict preservation.

This module keeps interview information and OCR-derived clinical information
separate so the physician UI receives clean, clinically meaningful sections.

OCR metadata such as document type, patient identifiers, filenames and internal
document IDs is deliberately excluded from the clinical findings section.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .schemas import (
    ConflictValue,
    NormalizedItem,
    SummaryInput,
    SummaryResult,
    SummarySections,
    Provenance,
    VerificationStatus,
)


# These are document/OCR bookkeeping fields, not clinical findings.
# They should never be rendered as part of the physician's clinical summary.
_NON_CLINICAL_DOCUMENT_FIELDS = {
    "document_id",
    "documentid",
    "filename",
    "file_name",
    "document_type",
    "documenttype",
    "patient",
    "patient_id",
    "patientid",
    "hospital_id",
    "hospitalid",
    "id",
    "raw_text",
    "ocr_text",
    "text",
    "confidence",
    "processing_status",
}


def _key(value: Any) -> str:
    if isinstance(value, dict):
        return repr(
            sorted(
                (str(k), repr(v))
                for k, v in value.items()
            )
        ).lower()

    if isinstance(value, list):
        return repr(value).lower()

    return str(value).strip().casefold()


def _merge_lists(
    *groups: List[NormalizedItem],
) -> Tuple[List[Any], List[Provenance]]:
    """Stable union. Equal values are deduplicated; unequal values remain."""
    result: List[Any] = []
    provenance: List[Provenance] = []
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
    detect_conflict: bool = True,
) -> List[Any]:
    values, prov = _merge_lists(*groups)

    provenance[field] = prov

    if detect_conflict and len(values) > 1:
        conflicts[field] = ConflictValue(
            values=values,
            provenances=prov,
        )

    return values


def _clinical_document_entities(
    entities: List[NormalizedItem],
) -> List[NormalizedItem]:
    """Return only clinically useful OCR entities.

    ``clinical_entities`` is intentionally broad at the OCR boundary. It can
    contain diagnoses and findings, but it can also contain document metadata.

    The merger is the final deterministic boundary before physician-facing
    rendering, so metadata is filtered here.

    Structured labs and medications are handled separately and are therefore
    not duplicated here.
    """
    result: List[NormalizedItem] = []

    for item in entities:
        path = (
            str(item.provenance.path or "")
            .strip()
            .casefold()
            .replace("-", "_")
            .replace(" ", "_")
        )

        if path in _NON_CLINICAL_DOCUMENT_FIELDS:
            continue

        # Some extractors use dotted/nested paths, e.g.
        # ``patient.name`` or ``document.filename``.
        final_component = path.rsplit(".", 1)[-1]

        if final_component in _NON_CLINICAL_DOCUMENT_FIELDS:
            continue

        # Some OCR extractors store the actual field inside the value.
        if isinstance(item.value, dict):
            inner_field = (
                str(
                    item.value.get("field")
                    or item.value.get("type")
                    or ""
                )
                .strip()
                .casefold()
                .replace("-", "_")
                .replace(" ", "_")
            )

            if inner_field in _NON_CLINICAL_DOCUMENT_FIELDS:
                continue

        result.append(item)

    return result


def merge_sources(data: SummaryInput) -> SummaryResult:
    """Merge interview, OCR and timeline data into the clinical case sheet.

    Canonical placement:

    - Interview symptoms/history -> normal clinical summary.
    - OCR medications -> medication_history.
    - OCR laboratory results -> investigations.
    - OCR allergies -> allergies.
    - Remaining clinically useful OCR entities/findings ->
      document_derived_findings.
    - OCR metadata -> excluded from the clinical summary.

    This keeps structured document information available to the physician
    without mixing document metadata into patient symptoms.
    """
    c = data.conversation
    o = data.ocr

    sections = SummarySections()
    conflicts: Dict[str, ConflictValue] = {}
    provenance: Dict[str, List[Provenance]] = {}

    ocr_clinical_entities = (
        _clinical_document_entities(o.clinical_entities)
        if o
        else []
    )

    # ------------------------------------------------------------
    # Interview-derived clinical sections
    # ------------------------------------------------------------

    sections.chief_complaints = _merge_field(
        "chief_complaints",
        [c.chief_complaints if c else []],
        conflicts,
        provenance,
    )

    # HPI can legitimately contain multiple question/answer items.
    # Multiple HPI items are not a conflict.
    sections.history_of_present_illness = _merge_field(
        "history_of_present_illness",
        [c.history_of_present_illness if c else []],
        conflicts,
        provenance,
        detect_conflict=False,
    )

    # OCR clinical entities are deliberately NOT placed into symptoms.
    sections.relevant_symptoms = _merge_field(
        "relevant_symptoms",
        [c.symptoms if c else []],
        conflicts,
        provenance,
    )

    sections.medical_history = _merge_field(
        "medical_history",
        [c.medical_history if c else []],
        conflicts,
        provenance,
    )

    # ------------------------------------------------------------
    # Structured OCR clinical information
    # ------------------------------------------------------------

    # OCR medications belong in medication history.
    sections.medication_history = _merge_field(
        "medication_history",
        [
            c.medications if c else [],
            o.medications if o else [],
        ],
        conflicts,
        provenance,
    )

    sections.allergies = _merge_field(
        "allergies",
        [
            c.allergies if c else [],
            o.allergies if o else [],
        ],
        conflicts,
        provenance,
    )

    # OCR laboratory/test results belong in investigations.
    sections.investigations = _merge_field(
        "investigations",
        [
            c.investigations if c else [],
            o.labs if o else [],
        ],
        conflicts,
        provenance,
    )

    # ------------------------------------------------------------
    # Document-derived clinical findings
    # ------------------------------------------------------------

    sections.document_derived_findings = _merge_field(
        "document_derived_findings",
        [
            o.discharge_findings if o else [],
            ocr_clinical_entities,
        ],
        conflicts,
        provenance,
    )

    # ------------------------------------------------------------
    # Red flags
    # ------------------------------------------------------------

    sections.red_flags = _merge_field(
        "red_flags",
        [c.red_flags if c else []],
        conflicts,
        provenance,
    )

    sections.relevant_negatives = _merge_field(
        "relevant_negatives",
        [c.relevant_negatives if c else []],
        conflicts,
        provenance,
    )

    # ------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------

    timeline = list(data.timeline)

    if o:
        for item in o.timeline:
            timeline.append(
                {
                    "event": item.value,
                    "provenance": item.provenance.model_dump(),
                }
            )

    sections.timeline = timeline

    provenance["timeline"] = (
        [event.provenance for event in data.timeline]
        + (
            [item.provenance for item in o.timeline]
            if o
            else []
        )
    )

    # ------------------------------------------------------------
    # Remaining explicitly normalized fields
    # ------------------------------------------------------------

    other: Dict[str, List[Any]] = {}
    other_groups = []

    if c:
        other_groups.append(c.other)

    if o:
        other_groups.append(o.other)

    keys = sorted(
        {
            key
            for group in other_groups
            for key in group
        }
    )

    for key in keys:
        groups = [
            group.get(key, [])
            for group in other_groups
        ]

        values, prov = _merge_lists(*groups)

        if values:
            other[key] = values
            provenance[f"other.{key}"] = prov

    sections.other = other

    return SummaryResult(
        sections=sections,
        conflicts=conflicts,
        provenance=provenance,
        verification_status=(
            VerificationStatus.NEEDS_REVIEW
            if conflicts
            else VerificationStatus.UNVERIFIED
        ),
    )