"""Deterministic source merger for the physician review screen.

The physician view has two canonical sources:
1. Patient interview -> clinical history sections.
2. Uploaded medical documents -> one dedicated document-extraction section.

OCR data is intentionally NOT copied into interview sections. This prevents the
same medication/lab/diagnosis from appearing in multiple places.
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


# OCR bookkeeping fields are never clinical findings.
_NON_CLINICAL_DOCUMENT_FIELDS = {
    "document_id",
    "documentid",
    "filename",
    "file_name",
    "document_type",
    "documenttype",
    "patient",
    "patient_name",
    "patient_id",
    "patientid",
    "hospital_id",
    "hospitalid",
    "age",
    "sex",
    "gender",
    "id",
    "raw_text",
    "ocr_text",
    "text",
    "confidence",
    "processing_status",
    "source",
    "provenance",
}


def _canonical(value: Any) -> Any:
    """Create a stable, metadata-free representation for deduplication."""
    if isinstance(value, dict):
        return tuple(
            sorted(
                (
                    str(key).strip().casefold(),
                    _canonical(child),
                )
                for key, child in value.items()
                if str(key).strip().casefold()
                not in _NON_CLINICAL_DOCUMENT_FIELDS
            )
        )

    if isinstance(value, list):
        return tuple(_canonical(item) for item in value)

    if isinstance(value, str):
        return " ".join(value.split()).casefold()

    return value


def _merge_lists(
    *groups: List[NormalizedItem],
) -> Tuple[List[Any], List[Provenance]]:
    """Stable union of values while removing true duplicates."""
    result: List[Any] = []
    provenance: List[Provenance] = []
    seen = set()

    for group in groups:
        for item in group:
            key = _canonical(item.value)

            if key in seen:
                continue

            seen.add(key)
            result.append(item.value)
            provenance.append(item.provenance)

    return result, provenance


def _merge_field(
    field: str,
    groups: List[List[NormalizedItem]],
    conflicts: Dict[str, ConflictValue],
    provenance: Dict[str, List[Provenance]],
    *,
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
    """Keep only clinical OCR entities and remove document metadata."""
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

        final_component = path.rsplit(".", 1)[-1]

        if final_component in _NON_CLINICAL_DOCUMENT_FIELDS:
            continue

        # Some OCR extractors store many entity types under the generic
        # ``clinical_entities`` path and put the actual field name inside the
        # value, e.g. {"field": "patient", "value": {...}}.
        if isinstance(item.value, dict):
            inner_field = str(
                item.value.get("field") or item.value.get("type") or ""
            ).strip().casefold().replace("-", "_").replace(" ", "_")

            if inner_field in _NON_CLINICAL_DOCUMENT_FIELDS:
                continue

        result.append(item)

    return result


def _document_groups(ocr) -> List[List[NormalizedItem]]:
    """Return every clinically useful OCR stream exactly once."""
    if not ocr:
        return []

    return [
        ocr.medications,
        ocr.labs,
        ocr.allergies,
        ocr.discharge_findings,
        _clinical_document_entities(ocr.clinical_entities),
    ]


def merge_sources(data: SummaryInput) -> SummaryResult:
    """Build a clean physician-facing case sheet.

    Canonical placement:
    - Interview symptoms/history -> normal clinical summary.
    - OCR medications/labs/diagnoses/procedures/findings -> document extraction.
    - OCR metadata -> nowhere in the physician clinical summary.
    """

    c = data.conversation
    o = data.ocr

    sections = SummarySections()
    conflicts: Dict[str, ConflictValue] = {}
    provenance: Dict[str, List[Provenance]] = {}

    # ------------------------------------------------------------------
    # INTERVIEW ONLY
    # ------------------------------------------------------------------

    sections.chief_complaints = _merge_field(
        "chief_complaints",
        [c.chief_complaints if c else []],
        conflicts,
        provenance,
    )

    # Multiple HPI question/answer pairs are expected, not conflicts.
    sections.history_of_present_illness = _merge_field(
        "history_of_present_illness",
        [c.history_of_present_illness if c else []],
        conflicts,
        provenance,
        detect_conflict=False,
    )

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

    # OCR medication/lab data used to be copied here AND rendered again
    # inside Medical Documents. Keep these sections interview-only.
    sections.medication_history = _merge_field(
        "medication_history",
        [c.medications if c else []],
        conflicts,
        provenance,
    )

    sections.allergies = _merge_field(
        "allergies",
        [c.allergies if c else []],
        conflicts,
        provenance,
    )

    sections.investigations = _merge_field(
        "investigations",
        [c.investigations if c else []],
        conflicts,
        provenance,
    )

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

    # ------------------------------------------------------------------
    # ONE CANONICAL OCR LOCATION
    # ------------------------------------------------------------------

    document_values: List[Any] = []
    document_provenance: List[Provenance] = []
    seen_document_values = set()

    for group in _document_groups(o):
        for item in group:
            key = _canonical(item.value)

            if key in seen_document_values:
                continue

            seen_document_values.add(key)
            document_values.append(item.value)
            document_provenance.append(item.provenance)

    sections.document_derived_findings = document_values
    provenance["document_derived_findings"] = document_provenance

    # Multiple labs/medications/diagnoses in a document are normal. They are
    # not source conflicts and should not force the whole summary into a
    # conflict state.
    #
    # If the same clinical fact is extracted twice, _canonical() removes it.

    # ------------------------------------------------------------------
    # TIMELINE
    # ------------------------------------------------------------------

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
        + ([item.provenance for item in o.timeline] if o else [])
    )

    # ------------------------------------------------------------------
    # OTHER EXPLICITLY NORMALIZED FIELDS
    # ------------------------------------------------------------------

    other: Dict[str, List[Any]] = {}
    other_groups = []

    if c:
        other_groups.append(c.other)

    if o:
        other_groups.append(o.other)

    for key in sorted({key for group in other_groups for key in group}):
        values, prov = _merge_lists(
            *[group.get(key, []) for group in other_groups]
        )

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
