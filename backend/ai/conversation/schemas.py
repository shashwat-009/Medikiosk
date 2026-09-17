"""
Provider-independent data contracts for the MediKiosk conversation layer
(the adaptive clinical-history-taking engine).

This module defines the *shape* of conversation state, questions, answers,
and decisions. It intentionally contains NO behavior: no clinical
reasoning, no adaptive-questioning logic, no red-flag rule evaluation, no
database or API calls, and no LLM calls. Those all belong to future
sibling modules that will import and use these schemas:

    - ontology.py            (canonical clinical field definitions)
    - question_bank.py       (concrete Question catalog)
    - dialogue_state.py       (state transition logic)
    - adaptive_questioning.py (next-question selection logic)
    - red_flags.py            (red-flag rule evaluation)
    - dialogue_manager.py     (orchestrates all of the above)

Relationship to ai/asr:
    This module consumes the ASR subsystem's standardized
    ``ai.asr.schemas.ASRResponse`` as-is (imported, never redefined or
    duplicated) via composition inside ``PatientAnswer``. The ASR module
    is complete, frozen, and NOT modified by anything here. Only ONE
    import crosses the ai.asr <-> ai.conversation boundary
    (``ASRResponse``), and it flows in a single direction, so no circular
    import is introduced.

Design philosophy (mirrors ai/asr/schemas.py):
    - Finished, atomic pieces of information (a recorded answer, a posed
      question, a single dialogue turn, a red-flag detection, a next-step
      decision) are modeled as immutable, ``frozen=True`` value objects —
      exactly like ``ASRResponse`` itself. Once created, they represent a
      historical fact and should not be mutated in place.
    - Evolving aggregate state (``DialogueState``, ``InterviewSession``)
      is deliberately left mutable, since a future ``dialogue_manager.py``
      needs to update it turn by turn (append turns, advance phase,
      record newly collected fields, etc.).
    - Every model uses ``extra="forbid"`` so that unexpected fields fail
      loudly instead of being silently accepted, matching the strictness
      already established by ``ASRResponse``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai.asr.schemas import ASRResponse

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class InputMode(str, Enum):
    """How the patient supplied a given answer."""

    VOICE = "voice"
    TOUCH = "touch"


class QuestionType(str, Enum):
    """The interaction style a Question expects from the patient."""

    FREE_TEXT = "free_text"
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    YES_NO = "yes_no"
    NUMERIC = "numeric"


class DialogueRole(str, Enum):
    """Who produced a given DialogueTurn."""

    ASSISTANT = "assistant"
    PATIENT = "patient"


class DialoguePhase(str, Enum):
    """Coarse-grained stage of the overall interview."""

    GREETING = "greeting"
    CHIEF_COMPLAINT = "chief_complaint"
    HISTORY_TAKING = "history_taking"
    RED_FLAG_CHECK = "red_flag_check"
    CLOSING = "closing"
    COMPLETE = "complete"


class RedFlagPriority(str, Enum):
    """Urgency level of a detected red flag (triage signal, not diagnosis)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FieldValueSource(str, Enum):
    """Where a ClinicalFieldValue's value ultimately came from."""

    VOICE = "voice"
    TOUCH = "touch"
    DERIVED = "derived"


def _utcnow() -> datetime:
    """Timezone-aware "now", used as a shared default_factory.

    Defined once and reused (rather than inlined lambdas per-field) purely
    to avoid repeating the same small expression; it carries no business
    logic.
    """
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Question catalog shapes
# ---------------------------------------------------------------------------


class QuestionOption(BaseModel):
    """
    A single selectable touchscreen option for a Question.

    Deliberately separates the machine-readable ``value`` from the
    human-readable ``display_text`` — the latter may be translated/
    localized per Question.language, while the former is what actually
    gets recorded as the answer's underlying value.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    option_id: str = Field(
        ..., min_length=1, description="Stable identifier for this option."
    )
    display_text: str = Field(
        ...,
        min_length=1,
        description="Human-readable label shown on the touchscreen button.",
    )
    value: str = Field(
        ...,
        min_length=1,
        description=(
            "Normalized, machine-readable value recorded when this option "
            "is selected (e.g. 'yes', 'fever', '3_to_5_days')."
        ),
    )


class Question(BaseModel):
    """
    A single question the assistant may ask the patient.

    This is a plain data record describing *what* a question is — the
    logic for *which* question to ask next lives in the future
    ``adaptive_questioning.py`` / ``question_bank.py`` modules, not here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(..., min_length=1, description="Stable question identifier.")
    text: str = Field(..., min_length=1, description="The question text as posed to the patient.")
    language: str = Field(
        ...,
        min_length=1,
        description="Language/locale code of `text` (e.g. 'hi', 'en-IN').",
    )
    target_field: str = Field(
        ...,
        min_length=1,
        description=(
            "Name of the clinical field this question is intended to "
            "populate (e.g. 'chief_complaint', 'fever_duration_days'). "
            "Kept as a plain string rather than an enum so this schema "
            "does not need to import a not-yet-built ontology.py — a "
            "future ontology module can define the canonical set of valid "
            "field names without this file needing to change."
        ),
    )
    question_type: QuestionType = Field(
        ..., description="Interaction style expected from the patient."
    )
    required: bool = Field(
        default=True,
        description="Whether the interview cannot proceed without an answer to this question.",
    )
    options: list[QuestionOption] = Field(
        default_factory=list,
        description=(
            "Touchscreen options for select-type questions. Empty for "
            "FREE_TEXT/NUMERIC questions, and optional for YES_NO."
        ),
    )

    @model_validator(mode="after")
    def _validate_options_for_question_type(self) -> "Question":
        """Select-type questions need at least two distinct options to be
        meaningful; this is a structural check, not clinical judgement."""
        if self.question_type in (QuestionType.SINGLE_SELECT, QuestionType.MULTI_SELECT):
            if len(self.options) < 2:
                raise ValueError(
                    f"question_type={self.question_type.value} requires at "
                    "least 2 options"
                )
        return self


# ---------------------------------------------------------------------------
# Patient answers
# ---------------------------------------------------------------------------


class PatientAnswer(BaseModel):
    """
    A single answer supplied by the patient, via voice or touch.

    Integrates with the ASR subsystem by COMPOSITION: when
    ``input_mode == VOICE``, the full ``ASRResponse`` produced by the ASR
    module is nested under ``asr_response`` as-is. Its fields (text,
    language, confidence, provider, request_id, duration_ms) are never
    copied or redeclared here — this model only adds the information the
    conversation layer needs on top of that (which question it answers,
    and how it was captured).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer_id: str = Field(..., min_length=1, description="Stable identifier for this answer.")
    question_id: str = Field(
        ..., min_length=1, description="ID of the Question this answer responds to."
    )
    input_mode: InputMode = Field(..., description="How the patient supplied this answer.")

    asr_response: ASRResponse | None = Field(
        default=None,
        description=(
            "The standardized ASR result for this answer. Populated ONLY "
            "when input_mode == VOICE. This is the existing, unmodified "
            "ai.asr.schemas.ASRResponse — its fields are intentionally "
            "not duplicated on this model."
        ),
    )
    selected_option_id: str | None = Field(
        default=None,
        description=(
            "ID of the QuestionOption the patient tapped. Populated only "
            "when input_mode == TOUCH and a predefined option was chosen."
        ),
    )
    touch_value: str | None = Field(
        default=None,
        description=(
            "Raw value entered via touch input when not selecting a "
            "predefined option (e.g. a typed number). Populated only "
            "when input_mode == TOUCH."
        ),
    )
    answered_at: datetime = Field(
        default_factory=_utcnow, description="When this answer was recorded (UTC)."
    )

    @model_validator(mode="after")
    def _validate_mode_matches_payload(self) -> "PatientAnswer":
        """Ensure the populated fields actually match the declared
        input_mode, so downstream code can trust input_mode without
        re-checking every field."""
        if self.input_mode == InputMode.VOICE:
            if self.asr_response is None:
                raise ValueError("asr_response is required when input_mode is VOICE")
            if self.selected_option_id is not None or self.touch_value is not None:
                raise ValueError(
                    "selected_option_id/touch_value must not be set when input_mode is VOICE"
                )
        elif self.input_mode == InputMode.TOUCH:
            if self.asr_response is not None:
                raise ValueError("asr_response must not be set when input_mode is TOUCH")
            if self.selected_option_id is None and self.touch_value is None:
                raise ValueError(
                    "one of selected_option_id or touch_value is required when "
                    "input_mode is TOUCH"
                )
        return self

    def resolved_text(self) -> str | None:
        """
        Best-effort plain-text view of this answer, regardless of source.

        Returns the ASR transcript text for voice answers, or the raw
        touch value / selected option id for touch answers. Intentionally
        simple — any real normalization belongs to a future extraction
        module, not to this schema.
        """
        if self.asr_response is not None:
            return self.asr_response.text
        return self.touch_value or self.selected_option_id


# ---------------------------------------------------------------------------
# Dialogue turns
# ---------------------------------------------------------------------------


class DialogueTurn(BaseModel):
    """
    One immutable entry in the conversation transcript.

    Stores a full snapshot of the ``Question`` as it was actually posed
    (not just its id), so the conversation can be reconstructed later even
    if the underlying question bank changes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_id: str = Field(..., min_length=1, description="Stable identifier for this turn.")
    turn_number: int = Field(..., ge=0, description="0-based position of this turn in the session.")
    role: DialogueRole = Field(..., description="Who produced this turn.")
    question: Question | None = Field(
        default=None, description="The question posed. Populated only when role == ASSISTANT."
    )
    answer: PatientAnswer | None = Field(
        default=None, description="The answer given. Populated only when role == PATIENT."
    )
    timestamp: datetime = Field(default_factory=_utcnow, description="When this turn occurred (UTC).")

    @model_validator(mode="after")
    def _validate_role_matches_payload(self) -> "DialogueTurn":
        if self.role == DialogueRole.ASSISTANT:
            if self.question is None:
                raise ValueError("question is required when role is ASSISTANT")
            if self.answer is not None:
                raise ValueError("answer must not be set when role is ASSISTANT")
        elif self.role == DialogueRole.PATIENT:
            if self.answer is None:
                raise ValueError("answer is required when role is PATIENT")
            if self.question is not None:
                raise ValueError("question must not be set when role is PATIENT")
        return self


# ---------------------------------------------------------------------------
# Collected clinical information
# ---------------------------------------------------------------------------


class ClinicalFieldValue(BaseModel):
    """
    A single normalized clinical data point collected during the interview.

    NOTE on `confidence`: this is distinct from ``ASRResponse.confidence``.
    ``ASRResponse.confidence`` measures how confident the ASR provider was
    in the raw *transcription*. This field's ``confidence`` (when a future
    extraction module chooses to set it) measures confidence in the
    *normalized clinical value* derived from that transcription — a
    different, downstream concept. The two are never merged.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    field_name: str = Field(
        ...,
        min_length=1,
        description=(
            "Canonical clinical field name (e.g. 'chief_complaint', "
            "'fever_duration_days'). Plain string for the same reason as "
            "Question.target_field — no dependency on a not-yet-built "
            "ontology.py."
        ),
    )
    value: str | int | float | bool | list[str] = Field(
        ..., description="Normalized value for this field."
    )
    source: FieldValueSource = Field(
        ..., description="Where this value came from: voice, touch, or derived."
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Optional confidence in this normalized value (extraction "
            "confidence, not ASR transcription confidence — see class "
            "docstring)."
        ),
    )
    source_turn_id: str | None = Field(
        default=None,
        description="ID of the DialogueTurn this value was extracted from, for traceability.",
    )
    updated_at: datetime = Field(default_factory=_utcnow, description="When this value was recorded (UTC).")


# ---------------------------------------------------------------------------
# Red-flag (triage) signal
# ---------------------------------------------------------------------------


class RedFlagResult(BaseModel):
    """
    The outcome of evaluating one red-flag rule against the interview so
    far.

    IMPORTANT: this is a TRIAGE SIGNAL, not a diagnosis. A detected red
    flag means a rule-based pattern matched the patient's reported
    history and the case may warrant urgent attention or prioritization —
    it is not, and must never be presented as, a medical diagnosis or
    clinical conclusion.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    detected: bool = Field(..., description="Whether this rule matched.")
    flag_id: str | None = Field(
        default=None, description="Identifier of the red-flag rule (e.g. 'chest_pain_acute')."
    )
    priority: RedFlagPriority | None = Field(
        default=None, description="Urgency level if detected=True."
    )
    matched_fields: list[str] = Field(
        default_factory=list,
        description="Clinical field names whose values contributed to this match.",
    )
    matched_text: str | None = Field(
        default=None,
        description="Optional snippet of patient-reported text that triggered the match.",
    )
    explanation: str | None = Field(
        default=None,
        description=(
            "Human-readable, rule-level explanation of why this matched "
            "(e.g. 'duration >= 3 days AND severity == high'). Describes "
            "the triage rule's logic, not a clinical/diagnostic opinion."
        ),
    )
    detected_at: datetime = Field(default_factory=_utcnow, description="When this evaluation ran (UTC).")

    @model_validator(mode="after")
    def _validate_detected_fields(self) -> "RedFlagResult":
        if self.detected and (self.flag_id is None or self.priority is None):
            raise ValueError("flag_id and priority are required when detected is True")
        return self


# ---------------------------------------------------------------------------
# Working dialogue state
# ---------------------------------------------------------------------------


class DialogueState(BaseModel):
    """
    The live, evolving state of a single interview session.

    Unlike the value objects above, this model is intentionally mutable —
    a future ``dialogue_manager.py`` is expected to update it turn by turn
    (advance ``phase``, set ``current_question``, add to
    ``collected_fields``, increment ``turn_count``, etc.).
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, description="ID of the owning InterviewSession.")
    phase: DialoguePhase = Field(
        default=DialoguePhase.GREETING, description="Current coarse-grained stage of the interview."
    )
    chief_complaint: str | None = Field(
        default=None, description="The patient's stated primary complaint, once captured."
    )
    current_question: Question | None = Field(
        default=None, description="The question currently awaiting an answer, if any."
    )
    collected_fields: dict[str, ClinicalFieldValue] = Field(
        default_factory=dict,
        description="Clinical fields collected so far, keyed by field_name.",
    )
    answered_field_names: list[str] = Field(
        default_factory=list, description="Names of clinical fields already answered."
    )
    pending_field_names: list[str] = Field(
        default_factory=list, description="Names of clinical fields still needed."
    )
    turn_count: int = Field(default=0, ge=0, description="Total number of dialogue turns so far.")
    has_red_flag: bool = Field(
        default=False, description="Whether any red flag has been detected so far this session."
    )
    red_flags: list[RedFlagResult] = Field(
        default_factory=list, description="All red-flag evaluation results detected so far."
    )
    is_complete: bool = Field(default=False, description="Whether the interview has finished.")


# ---------------------------------------------------------------------------
# Next-question decision
# ---------------------------------------------------------------------------


class NextQuestionDecision(BaseModel):
    """
    The outcome of deciding what should happen next in the interview.

    This is a plain data record describing a decision that was made — the
    logic that produces it belongs to the future
    ``adaptive_questioning.py`` / ``red_flags.py`` modules, not here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    next_question: Question | None = Field(
        default=None, description="The question to ask next, if the interview continues."
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Short, human-readable explanation for this decision (for logging/debugging).",
    )
    target_field: str | None = Field(
        default=None, description="Clinical field name `next_question` is intended to populate."
    )
    continue_interview: bool = Field(
        default=True, description="Whether the interview should proceed with next_question."
    )
    interview_complete: bool = Field(
        default=False, description="Whether the interview has gathered everything it needs."
    )
    immediate_triage_required: bool = Field(
        default=False,
        description="Whether a red flag requires halting the interview for urgent triage.",
    )

    @model_validator(mode="after")
    def _validate_decision_consistency(self) -> "NextQuestionDecision":
        if self.interview_complete and self.continue_interview:
            raise ValueError("continue_interview must be False when interview_complete is True")
        if self.interview_complete and self.next_question is not None:
            raise ValueError("next_question must not be set when interview_complete is True")
        if self.immediate_triage_required and self.continue_interview:
            raise ValueError(
                "continue_interview must be False when immediate_triage_required is True"
            )
        return self


# ---------------------------------------------------------------------------
# Top-level session
# ---------------------------------------------------------------------------


class InterviewSession(BaseModel):
    """
    The top-level aggregate representing one complete patient interview.

    ``collected_fields``, ``red_flags``, and ``is_complete`` here mirror
    the same-named data inside ``dialogue_state`` and exist as a
    convenient top-level projection for external consumers (e.g. an API
    response) that don't want to reach into ``dialogue_state`` for a
    session-level summary. Keeping the two in sync is the responsibility
    of the future ``dialogue_manager.py`` — this schema only defines the
    shape, not the synchronization logic.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, description="Unique identifier for this interview session.")
    language: str = Field(
        ..., min_length=1, description="Primary language/locale code for this session (e.g. 'hi-IN')."
    )
    dialogue_state: DialogueState = Field(..., description="The current live dialogue state.")
    turns: list[DialogueTurn] = Field(
        default_factory=list, description="Full ordered conversation transcript."
    )
    collected_fields: dict[str, ClinicalFieldValue] = Field(
        default_factory=dict,
        description="Session-level view of collected clinical fields (see class docstring).",
    )
    red_flags: list[RedFlagResult] = Field(
        default_factory=list,
        description="Session-level view of detected red flags (see class docstring).",
    )
    is_complete: bool = Field(
        default=False, description="Session-level completion flag (see class docstring)."
    )
    started_at: datetime = Field(
        default_factory=_utcnow, description="When this session was created (UTC)."
    )