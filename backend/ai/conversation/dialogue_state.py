"""
MediKiosk Dialogue State Management.

Responsibilities:
    - Maintain the current structured clinical interview state.
    - Track collected and missing clinical fields.
    - Store patient answers.
    - Track conversation turns.
    - Calculate deterministic interview progress.

This module intentionally does NOT:
    - choose the next question
    - perform adaptive questioning
    - perform diagnosis
    - perform treatment recommendations
    - perform red-flag detection
    - call Sarvam
    - call an LLM
    - access a database
    - make network requests
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ai.conversation.ontology import (
    GENERAL_HISTORY_FIELD_IDS,
    OntologyRegistry,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DialogueStateError(ValueError):
    """Base exception for invalid Dialogue State operations."""


class UnknownComplaintError(DialogueStateError):
    """Raised when an unsupported complaint is supplied."""


class UnknownFieldError(DialogueStateError):
    """Raised when a field does not belong to the current interview."""


class InvalidAnswerError(DialogueStateError):
    """Raised when an answer cannot be stored."""


# ---------------------------------------------------------------------------
# Standard ontology field registry
# ---------------------------------------------------------------------------


COMPLAINT_FIELDS: dict[str, tuple[str, ...]] = {
    ontology.complaint.value: tuple(
        [
            *(clinical_field.identifier for clinical_field in ontology.fields),
            *GENERAL_HISTORY_FIELD_IDS,
        ]
    )
    for ontology in OntologyRegistry.all()
}


SUPPORTED_COMPLAINTS = tuple(COMPLAINT_FIELDS.keys())


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClinicalFieldValue:
    """
    Represents one collected clinical field.

    The value is intentionally generic because the extraction/normalisation
    layer may eventually provide strings, numbers, booleans, lists, etc.
    """

    field_id: str
    value: Any
    source: Optional[str] = None
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(frozen=True)
class PatientAnswer:
    """
    Structured patient answer accepted by Dialogue State.

    This is intentionally independent of ASR. The answer may originate
    from voice, text, touchscreen, or another structured input mechanism.
    """

    field_id: str
    value: Any
    question_id: Optional[str] = None
    source: Optional[str] = None


@dataclass(frozen=True)
class DialogueTurn:
    """Minimal representation of a conversation turn."""

    turn_id: str
    role: str
    text: Optional[str] = None
    question_id: Optional[str] = None
    field_id: Optional[str] = None
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(frozen=True)
class DialogueStateSnapshot:
    """Immutable snapshot of the current interview state."""

    complaint: str
    clinical_fields: Mapping[str, ClinicalFieldValue]
    answers: tuple[PatientAnswer, ...]
    turns: tuple[DialogueTurn, ...]
    current_question_id: Optional[str]
    previous_question_id: Optional[str]
    allowed_fields: Optional[tuple[str, ...]] = None


# ---------------------------------------------------------------------------
# Dialogue State
# ---------------------------------------------------------------------------


@dataclass
class DialogueState:
    """
    Current memory/state of a MediKiosk clinical interview.

    DialogueState stores information; it does not decide what happens next.

    ``allowed_fields`` is optional.

    - Standard mode:
        allowed_fields=None
        -> fields are taken from the standard complaint ontology.

    - Domain-specific mode such as AYUSH:
        allowed_fields=(...)
        -> the supplied domain fields become valid for this state.

    This keeps field validation strict while allowing multiple clinical
    history domains to use the same DialogueState implementation.
    """

    complaint: str

    clinical_fields: dict[str, ClinicalFieldValue] = field(
        default_factory=dict
    )
    answers: list[PatientAnswer] = field(default_factory=list)
    turns: list[DialogueTurn] = field(default_factory=list)

    current_question_id: Optional[str] = None
    previous_question_id: Optional[str] = None

    # Optional domain-specific field registry.
    #
    # None means standard complaint ontology.
    allowed_fields: Optional[tuple[str, ...]] = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        complaint: str,
        *,
        allowed_fields: Optional[tuple[str, ...]] = None,
    ) -> "DialogueState":
        """
        Create an empty state for a supported complaint.

        ``allowed_fields`` can be supplied by a domain-specific history
        provider such as AYUSH.

        Standard behavior is preserved when it is omitted.
        """

        complaint_key = normalize_complaint(complaint)

        validate_complaint(complaint_key)

        normalized_allowed_fields: Optional[tuple[str, ...]] = None

        if allowed_fields is not None:
            normalized_allowed_fields = normalize_allowed_fields(
                allowed_fields
            )

        return cls(
            complaint=complaint_key,
            allowed_fields=normalized_allowed_fields,
        )

    # ------------------------------------------------------------------
    # Field information
    # ------------------------------------------------------------------

    @property
    def relevant_fields(self) -> tuple[str, ...]:
        """
        Return fields relevant to the current interview.

        If a domain-specific field registry was supplied, use it.
        Otherwise use the standard complaint ontology.
        """

        if self.allowed_fields is not None:
            return self.allowed_fields

        return COMPLAINT_FIELDS[self.complaint]

    def collected_fields(self) -> tuple[str, ...]:
        """
        Return fields that currently contain a valid stored value.

        Ordering follows relevant field ordering.
        """

        return tuple(
            field_id
            for field_id in self.relevant_fields
            if field_id in self.clinical_fields
        )

    def missing_fields(self) -> tuple[str, ...]:
        """
        Return relevant fields that have not yet been collected.

        Ordering follows relevant field ordering.
        """

        return tuple(
            field_id
            for field_id in self.relevant_fields
            if field_id not in self.clinical_fields
        )

    def is_field_known(self, field_id: str) -> bool:
        """Return True if the field currently has a stored value."""

        field_key = normalize_field(field_id)
        validate_field_for_state(self, field_key)

        return field_key in self.clinical_fields

    def is_field_missing(self, field_id: str) -> bool:
        """Return True if the field is relevant but has no value."""

        field_key = normalize_field(field_id)
        validate_field_for_state(self, field_key)

        return field_key not in self.clinical_fields

    def get_field_value(self, field_id: str) -> Any:
        """
        Return a field's current value.

        Raises:
            UnknownFieldError: Invalid field.
            DialogueStateError: Field is valid but not collected.
        """

        field_key = normalize_field(field_id)
        validate_field_for_state(self, field_key)

        if field_key not in self.clinical_fields:
            raise DialogueStateError(
                f"Field {field_key!r} has not been collected."
            )

        return self.clinical_fields[field_key].value

    # ------------------------------------------------------------------
    # Updating clinical fields
    # ------------------------------------------------------------------

    def update_field(
        self,
        field_id: str,
        value: Any,
        *,
        source: Optional[str] = None,
    ) -> ClinicalFieldValue:
        """
        Store or replace a clinical field value.

        If a field is updated more than once, the latest valid value becomes
        the current value. Previous answers remain available through
        ``answers`` when record_answer() is used.
        """

        field_key = normalize_field(field_id)
        validate_field_for_state(self, field_key)
        validate_value(value)

        field_value = ClinicalFieldValue(
            field_id=field_key,
            value=value,
            source=source,
        )

        self.clinical_fields[field_key] = field_value

        return field_value

    # ------------------------------------------------------------------
    # Patient answers
    # ------------------------------------------------------------------

    def record_answer(
        self,
        answer: PatientAnswer,
    ) -> ClinicalFieldValue:
        """
        Record a structured patient answer and update the corresponding
        clinical field.

        No inference is performed.
        """

        if not isinstance(answer, PatientAnswer):
            raise InvalidAnswerError(
                "answer must be a PatientAnswer instance."
            )

        field_key = normalize_field(answer.field_id)
        validate_field_for_state(self, field_key)
        validate_value(answer.value)

        self.answers.append(
            PatientAnswer(
                field_id=field_key,
                value=answer.value,
                question_id=answer.question_id,
                source=answer.source,
            )
        )

        return self.update_field(
            field_key,
            answer.value,
            source=answer.source,
        )

    # ------------------------------------------------------------------
    # Conversation turns
    # ------------------------------------------------------------------

    def record_turn(self, turn: DialogueTurn) -> None:
        """
        Record a conversation turn.

        This does not select a next question.
        """

        if not isinstance(turn, DialogueTurn):
            raise DialogueStateError(
                "turn must be a DialogueTurn instance."
            )

        self.turns.append(turn)

        if turn.question_id:
            self.previous_question_id = self.current_question_id
            self.current_question_id = turn.question_id

    def set_current_question(
        self,
        question_id: Optional[str],
    ) -> None:
        """
        Store the current question identifier.

        This method records state only; it does not select the question.
        """

        if question_id is not None:
            if not isinstance(question_id, str):
                raise DialogueStateError(
                    "question_id must be a string or None."
                )

            question_id = question_id.strip()

            if not question_id:
                raise DialogueStateError(
                    "question_id cannot be empty."
                )

        self.previous_question_id = self.current_question_id
        self.current_question_id = question_id

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    @property
    def total_fields(self) -> int:
        """Number of fields relevant to the current interview."""

        return len(self.relevant_fields)

    @property
    def collected_field_count(self) -> int:
        """Number of currently known fields."""

        return len(self.collected_fields())

    @property
    def missing_field_count(self) -> int:
        """Number of currently missing fields."""

        return len(self.missing_fields())

    @property
    def completion_ratio(self) -> float:
        """
        Return deterministic completion ratio.

        Returns:
            0.0 for an empty field set.
            Otherwise collected_fields / total_fields.

        This represents field coverage only. It does NOT indicate
        clinical completeness or diagnostic completeness.
        """

        if self.total_fields == 0:
            return 0.0

        return self.collected_field_count / self.total_fields

    @property
    def completion_percentage(self) -> float:
        """Return completion as a percentage between 0 and 100."""

        return self.completion_ratio * 100.0

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> DialogueStateSnapshot:
        """Return an immutable snapshot of the current state."""

        return DialogueStateSnapshot(
            complaint=self.complaint,
            clinical_fields=dict(self.clinical_fields),
            answers=tuple(self.answers),
            turns=tuple(self.turns),
            current_question_id=self.current_question_id,
            previous_question_id=self.previous_question_id,
            allowed_fields=self.allowed_fields,
        )


# ---------------------------------------------------------------------------
# Public helper functions
# ---------------------------------------------------------------------------


def create_dialogue_state(
    complaint: str,
    *,
    allowed_fields: Optional[tuple[str, ...]] = None,
) -> DialogueState:
    """Create an initial Dialogue State."""

    return DialogueState.create(
        complaint,
        allowed_fields=allowed_fields,
    )


def update_clinical_field(
    state: DialogueState,
    field_id: str,
    value: Any,
    *,
    source: Optional[str] = None,
) -> ClinicalFieldValue:
    """Convenience wrapper for updating one clinical field."""

    if not isinstance(state, DialogueState):
        raise DialogueStateError(
            "state must be a DialogueState instance."
        )

    return state.update_field(
        field_id,
        value,
        source=source,
    )


def record_patient_answer(
    state: DialogueState,
    answer: PatientAnswer,
) -> ClinicalFieldValue:
    """Convenience wrapper for recording a patient answer."""

    if not isinstance(state, DialogueState):
        raise DialogueStateError(
            "state must be a DialogueState instance."
        )

    return state.record_answer(answer)


def get_collected_fields(
    state: DialogueState,
) -> tuple[str, ...]:
    """Return collected fields."""

    if not isinstance(state, DialogueState):
        raise DialogueStateError(
            "state must be a DialogueState instance."
        )

    return state.collected_fields()


def get_missing_fields(
    state: DialogueState,
) -> tuple[str, ...]:
    """Return missing fields."""

    if not isinstance(state, DialogueState):
        raise DialogueStateError(
            "state must be a DialogueState instance."
        )

    return state.missing_fields()


def get_field_value(
    state: DialogueState,
    field_id: str,
) -> Any:
    """Return the current value of a clinical field."""

    if not isinstance(state, DialogueState):
        raise DialogueStateError(
            "state must be a DialogueState instance."
        )

    return state.get_field_value(field_id)


def get_completion_ratio(
    state: DialogueState,
) -> float:
    """Return deterministic completion ratio."""

    if not isinstance(state, DialogueState):
        raise DialogueStateError(
            "state must be a DialogueState instance."
        )

    return state.completion_ratio


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def normalize_complaint(complaint: str) -> str:
    """
    Normalize a complaint identifier.

    No fuzzy matching is performed.
    """

    if not isinstance(complaint, str):
        raise UnknownComplaintError(
            "Complaint must be a string."
        )

    value = complaint.strip().lower().replace(" ", "_")

    if not value:
        raise UnknownComplaintError(
            "Complaint cannot be empty."
        )

    return value


def normalize_field(field_id: str) -> str:
    """Normalize a clinical field identifier."""

    if not isinstance(field_id, str):
        raise UnknownFieldError(
            "Field identifier must be a string."
        )

    value = field_id.strip().lower()

    if not value:
        raise UnknownFieldError(
            "Field identifier cannot be empty."
        )

    return value


def normalize_allowed_fields(
    allowed_fields: tuple[str, ...],
) -> tuple[str, ...]:
    """
    Normalize and validate a domain-specific field collection.

    Duplicate fields are removed while preserving the supplied order.
    """

    if not isinstance(allowed_fields, (tuple, list)):
        raise DialogueStateError(
            "allowed_fields must be a tuple or list of field identifiers."
        )

    normalized: list[str] = []

    for field_id in allowed_fields:
        field_key = normalize_field(field_id)

        if field_key not in normalized:
            normalized.append(field_key)

    return tuple(normalized)


def validate_complaint(complaint: str) -> None:
    """Validate that a complaint is supported."""

    if complaint not in COMPLAINT_FIELDS:
        raise UnknownComplaintError(
            f"Unknown complaint: {complaint!r}"
        )


def validate_field(
    complaint: str,
    field_id: str,
) -> None:
    """
    Validate that a field belongs to the standard complaint ontology.

    Kept as a public helper for backward compatibility.
    """

    validate_complaint(complaint)

    if field_id not in COMPLAINT_FIELDS[complaint]:
        raise UnknownFieldError(
            f"Unknown field {field_id!r} for complaint {complaint!r}"
        )


def validate_field_for_state(
    state: DialogueState,
    field_id: str,
) -> None:
    """
    Validate a field against the current DialogueState's field registry.

    Standard states use the complaint ontology.
    Domain-specific states use allowed_fields.
    """

    validate_complaint(state.complaint)

    if field_id not in state.relevant_fields:
        raise UnknownFieldError(
            f"Unknown field {field_id!r} for complaint "
            f"{state.complaint!r}"
        )


def validate_value(value: Any) -> None:
    """
    Validate a field value.

    None and empty strings are rejected so that missing fields cannot
    accidentally become marked as collected.
    """

    if value is None:
        raise InvalidAnswerError(
            "Clinical field value cannot be None."
        )

    if isinstance(value, str) and not value.strip():
        raise InvalidAnswerError(
            "Clinical field value cannot be empty."
        )


__all__ = [
    "DialogueState",
    "DialogueStateSnapshot",
    "ClinicalFieldValue",
    "PatientAnswer",
    "DialogueTurn",
    "DialogueStateError",
    "UnknownComplaintError",
    "UnknownFieldError",
    "InvalidAnswerError",
    "COMPLAINT_FIELDS",
    "SUPPORTED_COMPLAINTS",
    "create_dialogue_state",
    "update_clinical_field",
    "record_patient_answer",
    "get_collected_fields",
    "get_missing_fields",
    "get_field_value",
    "get_completion_ratio",
    "normalize_complaint",
    "normalize_field",
    "validate_complaint",
    "validate_field",
    "validate_field_for_state",
    "validate_value",
]