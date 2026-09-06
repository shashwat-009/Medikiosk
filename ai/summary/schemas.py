"""Pydantic v2 contracts and normalized adapters for the summary layer."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    CONVERSATION = "conversation"
    OCR = "ocr"
    TIMELINE = "timeline"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: SourceType
    path: Optional[str] = None
    note: Optional[str] = None


class ConflictValue(BaseModel):
    """Preserves incompatible source values instead of silently selecting one."""
    model_config = ConfigDict(extra="forbid")

    values: List[Any] = Field(default_factory=list)
    provenances: List[Provenance] = Field(default_factory=list)


Scalar = Union[str, int, float, bool]
ClinicalValue = Union[Scalar, List[Any], Dict[str, Any]]


class NormalizedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any
    provenance: Provenance


class NormalizedConversation(BaseModel):
    """Small canonical representation; adapters can map existing upstream output."""
    model_config = ConfigDict(extra="forbid")

    chief_complaints: List[NormalizedItem] = Field(default_factory=list)
    symptoms: List[NormalizedItem] = Field(default_factory=list)
    history: List[NormalizedItem] = Field(default_factory=list)
    medical_history: List[NormalizedItem] = Field(default_factory=list)
    medications: List[NormalizedItem] = Field(default_factory=list)
    allergies: List[NormalizedItem] = Field(default_factory=list)
    investigations: List[NormalizedItem] = Field(default_factory=list)
    relevant_negatives: List[NormalizedItem] = Field(default_factory=list)
    red_flags: List[NormalizedItem] = Field(default_factory=list)
    other: Dict[str, List[NormalizedItem]] = Field(default_factory=dict)


class NormalizedOCR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ocr_text: Optional[str] = None
    clinical_entities: List[NormalizedItem] = Field(default_factory=list)
    labs: List[NormalizedItem] = Field(default_factory=list)
    discharge_findings: List[NormalizedItem] = Field(default_factory=list)
    medications: List[NormalizedItem] = Field(default_factory=list)
    allergies: List[NormalizedItem] = Field(default_factory=list)
    timeline: List[NormalizedItem] = Field(default_factory=list)
    other: Dict[str, List[NormalizedItem]] = Field(default_factory=dict)


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: Optional[str] = None
    event: str
    provenance: Provenance


class SummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation: Optional[NormalizedConversation] = None
    ocr: Optional[NormalizedOCR] = None
    timeline: List[TimelineEvent] = Field(default_factory=list)


class SummarySections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chief_complaints: List[Any] = Field(default_factory=list)
    history_of_present_illness: List[Any] = Field(default_factory=list)
    relevant_symptoms: List[Any] = Field(default_factory=list)
    medical_history: List[Any] = Field(default_factory=list)
    medication_history: List[Any] = Field(default_factory=list)
    allergies: List[Any] = Field(default_factory=list)
    investigations: List[Any] = Field(default_factory=list)
    document_derived_findings: List[Any] = Field(default_factory=list)
    timeline: List[TimelineEvent] = Field(default_factory=list)
    red_flags: List[Any] = Field(default_factory=list)
    relevant_negatives: List[Any] = Field(default_factory=list)
    other: Dict[str, List[Any]] = Field(default_factory=dict)


class SummaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: SummarySections
    conflicts: Dict[str, ConflictValue] = Field(default_factory=dict)
    provenance: Dict[str, List[Provenance]] = Field(default_factory=dict)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED


class VerificationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    status: VerificationStatus = VerificationStatus.UNVERIFIED
    verified_value: Any = None
    reviewer_note: Optional[str] = None


class ClinicalCaseSheet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: SummaryResult
    verification: List[VerificationItem] = Field(default_factory=list)
    physician_verified: bool = False
    verification_note: Optional[str] = None


def _items(value: Any, source: SourceType, path: str) -> List[NormalizedItem]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    result = []
    for item in values:
        if isinstance(item, NormalizedItem):
            result.append(item)
        elif item not in ("", [], {}):
            result.append(
                NormalizedItem(
                    value=item,
                    provenance=Provenance(source=source, path=path),
                )
            )
    return result


def normalize_conversation(data: Any) -> NormalizedConversation:
    """Adapter for dict-like upstream Conversation Structured Output.

    Unknown fields are retained under ``other`` rather than discarded.
    """
    if isinstance(data, NormalizedConversation):
        return data
    if data is None:
        return NormalizedConversation()
    d = data.model_dump() if isinstance(data, BaseModel) else dict(data)

    known = {
        "chief_complaints": "chief_complaints",
        "chief_complaint": "chief_complaints",
        "symptoms": "symptoms",
        "history": "history",
        "history_of_present_illness": "history",
        "medical_history": "medical_history",
        "medications": "medications",
        "medication_history": "medications",
        "allergies": "allergies",
        "investigations": "investigations",
        "relevant_negatives": "relevant_negatives",
        "red_flags": "red_flags",
    }
    kwargs = {}
    consumed = set()
    for src, dest in known.items():
        if src in d:
            kwargs[dest] = _items(d[src], SourceType.CONVERSATION, src)
            consumed.add(src)

    other = {}
    for key, value in d.items():
        if key not in consumed and value not in (None, "", [], {}):
            other[key] = _items(value, SourceType.CONVERSATION, key)
    kwargs["other"] = other
    return NormalizedConversation(**kwargs)


def normalize_ocr(data: Any) -> NormalizedOCR:
    """Adapter for dict-like OCR export data without performing OCR."""
    if isinstance(data, NormalizedOCR):
        return data
    if data is None:
        return NormalizedOCR()
    d = data.model_dump() if isinstance(data, BaseModel) else dict(data)

    aliases = {
        "clinical_entities": "clinical_entities",
        "entities": "clinical_entities",
        "labs": "labs",
        "lab_results": "labs",
        "discharge_findings": "discharge_findings",
        "discharge_extraction": "discharge_findings",
        "medications": "medications",
        "drug_information": "medications",
        "drugs": "medications",
        "allergies": "allergies",
        "timeline": "timeline",
        "medical_timeline": "timeline",
    }
    kwargs = {}
    consumed = set()
    ocr_text = d.get("ocr_text", d.get("text"))
    if ocr_text not in (None, ""):
        kwargs["ocr_text"] = str(ocr_text)
    consumed.update({"ocr_text", "text"})

    for src, dest in aliases.items():
        if src in d:
            kwargs[dest] = _items(d[src], SourceType.OCR, src)
            consumed.add(src)

    other = {}
    for key, value in d.items():
        if key not in consumed and value not in (None, "", [], {}):
            other[key] = _items(value, SourceType.OCR, key)
    kwargs["other"] = other
    return NormalizedOCR(**kwargs)


def build_summary_input(
    conversation: Any = None,
    ocr: Any = None,
    timeline: Optional[List[Dict[str, Any]]] = None,
) -> SummaryInput:
    events = []
    for raw in timeline or []:
        if isinstance(raw, TimelineEvent):
            events.append(raw)
            continue
        date = raw.get("date") or raw.get("datetime") or raw.get("timestamp")
        event = raw.get("event") or raw.get("description") or raw.get("text")
        if event:
            events.append(
                TimelineEvent(
                    date=str(date) if date is not None else None,
                    event=str(event),
                    provenance=Provenance(
                        source=SourceType.TIMELINE,
                        path="timeline",
                    ),
                )
            )
    return SummaryInput(
        conversation=normalize_conversation(conversation) if conversation is not None else None,
        ocr=normalize_ocr(ocr) if ocr is not None else None,
        timeline=events,
    )
