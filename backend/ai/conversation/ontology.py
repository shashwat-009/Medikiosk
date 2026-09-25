"""
Clinical History Ontology for MediSetu.

This module defines the clinical information that is relevant to
different chief complaints.

The ontology is intentionally independent from the dialogue runtime.
It does not perform:
- question selection
- diagnosis
- red-flag detection
- medical inference
- LLM/API calls

It provides structured metadata that future conversation components
can use to determine which clinical fields are relevant and important.
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel, ConfigDict, Field


class ComplaintType(str, Enum):
    """Supported chief complaint categories."""

    FEVER = "fever"
    CHEST_PAIN = "chest_pain"
    COUGH = "cough"
    HEADACHE = "headache"
    ABDOMINAL_PAIN = "abdominal_pain"


class ClinicalDataType(str, Enum):
    """Supported data types for clinical history fields."""

    TEXT = "text"
    YES_NO = "yes_no"
    NUMERIC = "numeric"
    DURATION = "duration"
    DATETIME = "datetime"
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"


class ClinicalField(BaseModel):
    """
    Definition of one clinical-history field.

    A ClinicalField describes what information can be collected.
    It contains no patient-specific value and no dialogue logic.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    data_type: ClinicalDataType
    core: bool = False
    triage_relevant: bool = False
    complaints: tuple[ComplaintType, ...] = ()
    priority: int = Field(default=0, ge=0)


class ComplaintOntology(BaseModel):
    """
    Complete clinical-history ontology for one chief complaint.

    `fields` preserves the recommended deterministic collection order.
    This order is metadata only; it is not an adaptive questioning
    algorithm.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    complaint: ComplaintType
    fields: tuple[ClinicalField, ...]
    description: str = ""

    def get_field(self, identifier: str) -> ClinicalField | None:
        """Return a field by identifier, or None when it is absent."""
        for field in self.fields:
            if field.identifier == identifier:
                return field
        return None

    @property
    def core_fields(self) -> tuple[ClinicalField, ...]:
        """Return fields marked as core/important."""
        return tuple(field for field in self.fields if field.core)

    @property
    def additional_fields(self) -> tuple[ClinicalField, ...]:
        """Return fields that are not marked as core."""
        return tuple(field for field in self.fields if not field.core)


def _field(
    identifier: str,
    name: str,
    description: str,
    data_type: ClinicalDataType,
    complaint: ComplaintType,
    *,
    core: bool = False,
    triage_relevant: bool = False,
    priority: int,
) -> ClinicalField:
    """Create a complaint-specific clinical field definition."""
    return ClinicalField(
        identifier=identifier,
        name=name,
        description=description,
        data_type=data_type,
        core=core,
        triage_relevant=triage_relevant,
        complaints=(complaint,),
        priority=priority,
    )


# ---------------------------------------------------------------------------
# Shared general clinical history
# ---------------------------------------------------------------------------


GENERAL_HISTORY_FIELDS: tuple[ClinicalField, ...] = (
    ClinicalField(
        identifier="past_medical_history",
        name="Past Medical History",
        description="Previous medical conditions, diagnoses, or significant illnesses.",
        data_type=ClinicalDataType.TEXT,
        priority=1,
    ),
    ClinicalField(
        identifier="past_surgical_history",
        name="Past Surgical History",
        description="Previous surgeries, procedures, or significant hospitalisations.",
        data_type=ClinicalDataType.TEXT,
        priority=2,
    ),
    ClinicalField(
        identifier="current_medications",
        name="Medication History",
        description="Current medicines, regular treatments, or supplements being taken.",
        data_type=ClinicalDataType.TEXT,
        priority=3,
    ),
    ClinicalField(
        identifier="allergies",
        name="Allergies / Hypersensitivities",
        description="Known medicine, food, or other allergies or hypersensitivities.",
        data_type=ClinicalDataType.TEXT,
        priority=4,
    ),
    ClinicalField(
        identifier="family_history",
        name="Family History",
        description="Important illnesses or health conditions in close family members.",
        data_type=ClinicalDataType.TEXT,
        priority=5,
    ),
    ClinicalField(
        identifier="personal_history",
        name="Personal History",
        description="Relevant lifestyle, occupation, tobacco, alcohol, diet, sleep, or other personal factors.",
        data_type=ClinicalDataType.TEXT,
        priority=6,
    ),
    ClinicalField(
        identifier="review_of_systems",
        name="Review of Systems",
        description="Other symptoms not already covered in the current complaint history.",
        data_type=ClinicalDataType.TEXT,
        priority=7,
    ),
)

GENERAL_HISTORY_FIELD_IDS: tuple[str, ...] = tuple(
    field.identifier for field in GENERAL_HISTORY_FIELDS
)



def _build_ontologies() -> dict[ComplaintType, ComplaintOntology]:
    """Build the static ontology definitions."""

    fever = ComplaintOntology(
        complaint=ComplaintType.FEVER,
        description="Structured history fields relevant to fever.",
        fields=(
            _field(
                "onset",
                "Onset",
                "When the symptom started.",
                ClinicalDataType.DATETIME,
                ComplaintType.FEVER,
                core=True,
                priority=1,
            ),
            _field(
                "duration",
                "Duration",
                "How long the fever has been present.",
                ClinicalDataType.DURATION,
                ComplaintType.FEVER,
                core=True,
                priority=2,
            ),
            _field(
                "severity",
                "Severity",
                "Reported severity of the fever.",
                ClinicalDataType.NUMERIC,
                ComplaintType.FEVER,
                core=True,
                priority=3,
            ),
            _field(
                "temperature",
                "Temperature",
                "Measured or reported body temperature.",
                ClinicalDataType.NUMERIC,
                ComplaintType.FEVER,
                core=True,
                priority=4,
            ),
            _field(
                "chills",
                "Chills",
                "Presence of chills.",
                ClinicalDataType.YES_NO,
                ComplaintType.FEVER,
                priority=5,
            ),
            _field(
                "sweating",
                "Sweating",
                "Presence or pattern of sweating.",
                ClinicalDataType.YES_NO,
                ComplaintType.FEVER,
                priority=6,
            ),
            _field(
                "headache",
                "Headache",
                "Presence of headache with the fever.",
                ClinicalDataType.YES_NO,
                ComplaintType.FEVER,
                priority=7,
            ),
            _field(
                "cough",
                "Cough",
                "Presence of cough with the fever.",
                ClinicalDataType.YES_NO,
                ComplaintType.FEVER,
                priority=8,
            ),
            _field(
                "associated_symptoms",
                "Associated Symptoms",
                "Other symptoms occurring with the fever.",
                ClinicalDataType.MULTIPLE_CHOICE,
                ComplaintType.FEVER,
                priority=9,
            ),
        ),
    )

    chest_pain = ComplaintOntology(
        complaint=ComplaintType.CHEST_PAIN,
        description="Structured history fields relevant to chest pain.",
        fields=(
            _field(
                "onset",
                "Onset",
                "When the chest pain started.",
                ClinicalDataType.DATETIME,
                ComplaintType.CHEST_PAIN,
                core=True,
                priority=1,
            ),
            _field(
                "location",
                "Location",
                "Location of the chest pain.",
                ClinicalDataType.TEXT,
                ComplaintType.CHEST_PAIN,
                core=True,
                priority=2,
            ),
            _field(
                "character",
                "Character",
                "Description of the character of the pain.",
                ClinicalDataType.TEXT,
                ComplaintType.CHEST_PAIN,
                core=True,
                priority=3,
            ),
            _field(
                "duration",
                "Duration",
                "How long the pain lasts or has been present.",
                ClinicalDataType.DURATION,
                ComplaintType.CHEST_PAIN,
                core=True,
                priority=4,
            ),
            _field(
                "radiation",
                "Radiation",
                "Whether the pain spreads to another area.",
                ClinicalDataType.TEXT,
                ComplaintType.CHEST_PAIN,
                priority=5,
            ),
            _field(
                "aggravating_factors",
                "Aggravating Factors",
                "Factors that make the pain worse.",
                ClinicalDataType.MULTIPLE_CHOICE,
                ComplaintType.CHEST_PAIN,
                priority=6,
            ),
            _field(
                "relieving_factors",
                "Relieving Factors",
                "Factors that reduce the pain.",
                ClinicalDataType.MULTIPLE_CHOICE,
                ComplaintType.CHEST_PAIN,
                priority=7,
            ),
            _field(
                "severity",
                "Severity",
                "Reported severity of the pain.",
                ClinicalDataType.NUMERIC,
                ComplaintType.CHEST_PAIN,
                core=True,
                priority=8,
            ),
            _field(
                "associated_symptoms",
                "Associated Symptoms",
                "Other symptoms occurring with the chest pain.",
                ClinicalDataType.MULTIPLE_CHOICE,
                ComplaintType.CHEST_PAIN,
                triage_relevant=True,
                priority=9,
            ),
        ),
    )

    cough = ComplaintOntology(
        complaint=ComplaintType.COUGH,
        description="Structured history fields relevant to cough.",
        fields=(
            _field(
                "onset",
                "Onset",
                "When the cough started.",
                ClinicalDataType.DATETIME,
                ComplaintType.COUGH,
                core=True,
                priority=1,
            ),
            _field(
                "duration",
                "Duration",
                "How long the cough has been present.",
                ClinicalDataType.DURATION,
                ComplaintType.COUGH,
                core=True,
                priority=2,
            ),
            _field(
                "severity",
                "Severity",
                "Reported severity of the cough.",
                ClinicalDataType.NUMERIC,
                ComplaintType.COUGH,
                core=True,
                priority=3,
            ),
            _field(
                "nature",
                "Dry or Productive",
                "Whether the cough is dry or produces sputum.",
                ClinicalDataType.SINGLE_CHOICE,
                ComplaintType.COUGH,
                core=True,
                priority=4,
            ),
            _field(
                "sputum",
                "Sputum",
                "Presence of sputum with the cough.",
                ClinicalDataType.YES_NO,
                ComplaintType.COUGH,
                priority=5,
            ),
            _field(
                "sputum_characteristics",
                "Sputum Characteristics",
                "Relevant characteristics of the sputum.",
                ClinicalDataType.TEXT,
                ComplaintType.COUGH,
                priority=6,
            ),
            _field(
                "blood_presence",
                "Blood Presence",
                "Whether blood is reported with the cough.",
                ClinicalDataType.YES_NO,
                ComplaintType.COUGH,
                triage_relevant=True,
                priority=7,
            ),
            _field(
                "fever",
                "Fever",
                "Whether fever is present with the cough.",
                ClinicalDataType.YES_NO,
                ComplaintType.COUGH,
                priority=8,
            ),
            _field(
                "nocturnal_sweating",
                "Nocturnal Sweating",
                "Whether there is unusual sweating during the night.",
                ClinicalDataType.YES_NO,
                ComplaintType.COUGH,
                priority=9,
            ),
            _field(
                "dyspnea_grade",
                "Breathing Difficulty",
                "Reported grade of breathing difficulty associated with the cough.",
                ClinicalDataType.SINGLE_CHOICE,
                ComplaintType.COUGH,
                priority=10,
            ),
            _field(
                "associated_symptoms",
                "Associated Symptoms",
                "Other symptoms occurring with the cough.",
                ClinicalDataType.MULTIPLE_CHOICE,
                ComplaintType.COUGH,
                priority=11,
            ),
            _field(
                "aggravating_factors",
                "Aggravating Factors",
                "Factors that make the cough worse.",
                ClinicalDataType.MULTIPLE_CHOICE,
                ComplaintType.COUGH,
                priority=12,
            ),
        ),
    )

    headache = ComplaintOntology(
        complaint=ComplaintType.HEADACHE,
        description="Structured history fields relevant to headache.",
        fields=(
            _field(
                "onset",
                "Onset",
                "When the headache started.",
                ClinicalDataType.DATETIME,
                ComplaintType.HEADACHE,
                core=True,
                priority=1,
            ),
            _field(
                "duration",
                "Duration",
                "How long the headache lasts or has been present.",
                ClinicalDataType.DURATION,
                ComplaintType.HEADACHE,
                core=True,
                priority=2,
            ),
            _field(
                "location",
                "Location",
                "Location of the headache.",
                ClinicalDataType.TEXT,
                ComplaintType.HEADACHE,
                core=True,
                priority=3,
            ),
            _field(
                "character",
                "Character",
                "Description of the character of the headache.",
                ClinicalDataType.TEXT,
                ComplaintType.HEADACHE,
                core=True,
                priority=4,
            ),
            _field(
                "severity",
                "Severity",
                "Reported severity of the headache.",
                ClinicalDataType.NUMERIC,
                ComplaintType.HEADACHE,
                core=True,
                priority=5,
            ),
            _field(
                "frequency_pattern",
                "Frequency and Pattern",
                "Frequency and temporal pattern of headaches.",
                ClinicalDataType.TEXT,
                ComplaintType.HEADACHE,
                priority=6,
            ),
            _field(
                "aggravating_factors",
                "Aggravating Factors",
                "Factors that make the headache worse.",
                ClinicalDataType.MULTIPLE_CHOICE,
                ComplaintType.HEADACHE,
                priority=7,
            ),
            _field(
                "relieving_factors",
                "Relieving Factors",
                "Factors that reduce the headache.",
                ClinicalDataType.MULTIPLE_CHOICE,
                ComplaintType.HEADACHE,
                priority=8,
            ),
            _field(
                "associated_symptoms",
                "Associated Symptoms",
                "Other symptoms occurring with the headache.",
                ClinicalDataType.MULTIPLE_CHOICE,
                ComplaintType.HEADACHE,
                triage_relevant=True,
                priority=9,
            ),
        ),
    )

    abdominal_pain = ComplaintOntology(
        complaint=ComplaintType.ABDOMINAL_PAIN,
        description="Structured history fields relevant to abdominal pain.",
        fields=(
            _field(
                "onset",
                "Onset",
                "When the abdominal pain started.",
                ClinicalDataType.DATETIME,
                ComplaintType.ABDOMINAL_PAIN,
                core=True,
                priority=1,
            ),
            _field(
                "location",
                "Location",
                "Location of the abdominal pain.",
                ClinicalDataType.TEXT,
                ComplaintType.ABDOMINAL_PAIN,
                core=True,
                priority=2,
            ),
            _field(
                "character",
                "Character",
                "Description of the character of the pain.",
                ClinicalDataType.TEXT,
                ComplaintType.ABDOMINAL_PAIN,
                core=True,
                priority=3,
            ),
            _field(
                "duration",
                "Duration",
                "How long the pain lasts or has been present.",
                ClinicalDataType.DURATION,
                ComplaintType.ABDOMINAL_PAIN,
                core=True,
                priority=4,
            ),
            _field(
                "severity",
                "Severity",
                "Reported severity of the pain.",
                ClinicalDataType.NUMERIC,
                ComplaintType.ABDOMINAL_PAIN,
                core=True,
                priority=5,
            ),
            _field(
                "radiation",
                "Radiation",
                "Whether the pain spreads to another area.",
                ClinicalDataType.TEXT,
                ComplaintType.ABDOMINAL_PAIN,
                priority=6,
            ),
            _field(
                "aggravating_factors",
                "Aggravating Factors",
                "Factors that make the pain worse.",
                ClinicalDataType.MULTIPLE_CHOICE,
                ComplaintType.ABDOMINAL_PAIN,
                priority=7,
            ),
            _field(
                "relieving_factors",
                "Relieving Factors",
                "Factors that reduce the pain.",
                ClinicalDataType.MULTIPLE_CHOICE,
                ComplaintType.ABDOMINAL_PAIN,
                priority=8,
            ),
            _field(
                "associated_symptoms",
                "Associated Symptoms",
                "Other symptoms occurring with the abdominal pain.",
                ClinicalDataType.MULTIPLE_CHOICE,
                ComplaintType.ABDOMINAL_PAIN,
                priority=9,
            ),
            _field(
                "bowel_related_symptoms",
                "Bowel-related Symptoms",
                "Relevant changes or symptoms related to bowel habits.",
                ClinicalDataType.MULTIPLE_CHOICE,
                ComplaintType.ABDOMINAL_PAIN,
                priority=10,
            ),
            _field(
                "vomiting_nausea",
                "Vomiting or Nausea",
                "Presence of nausea or vomiting.",
                ClinicalDataType.MULTIPLE_CHOICE,
                ComplaintType.ABDOMINAL_PAIN,
                priority=11,
            ),
        ),
    )

    return {
        ontology.complaint: ontology
        for ontology in (
            fever,
            chest_pain,
            cough,
            headache,
            abdominal_pain,
        )
    }


_ONTOLOGIES: Final = MappingProxyType(_build_ontologies())


class OntologyRegistry:
    """
    Deterministic registry for clinical complaint ontologies.

    The registry contains only static in-process knowledge. It performs
    no network access and has no dependency on the dialogue runtime.
    """

    @classmethod
    def get(cls, complaint: ComplaintType | str) -> ComplaintOntology:
        """
        Retrieve the ontology for a complaint.

        Raises:
            ValueError: If the complaint is not a supported complaint.
            TypeError: If the input cannot be interpreted as a complaint.
        """
        try:
            complaint_type = (
                complaint
                if isinstance(complaint, ComplaintType)
                else ComplaintType(complaint)
            )
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Unknown clinical complaint: {complaint!r}"
            ) from exc

        try:
            return _ONTOLOGIES[complaint_type]
        except KeyError as exc:
            raise ValueError(
                f"No ontology registered for complaint: {complaint_type.value}"
            ) from exc

    @classmethod
    def get_general_history_fields(cls) -> tuple[ClinicalField, ...]:
        """Return shared general-history fields in deterministic order."""

        return GENERAL_HISTORY_FIELDS

    @classmethod
    def all(cls) -> tuple[ComplaintOntology, ...]:
        """Return all registered ontologies in deterministic order."""
        return tuple(_ONTOLOGIES.values())


def get_ontology(
    complaint: ComplaintType | str,
) -> ComplaintOntology:
    """Convenience function for retrieving a complaint ontology."""
    return OntologyRegistry.get(complaint)


__all__ = [
    "ClinicalDataType",
    "ClinicalField",
    "ComplaintOntology",
    "ComplaintType",
    "GENERAL_HISTORY_FIELDS",
    "GENERAL_HISTORY_FIELD_IDS",
    "OntologyRegistry",
    "get_ontology",
]