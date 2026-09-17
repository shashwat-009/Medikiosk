"""
MediKiosk Conversation Orchestrator.

Coordinates:
    DialogueState
    Ontology
    Question Bank
    AdaptiveQuestioning
    RedFlagDetector
    Optional AYUSH history domain

This module does not:
    - perform diagnosis
    - call an LLM
    - call Sarvam/ASR
    - access the database
    - make network requests
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai.conversation.adaptive_questioning import (
    AdaptiveQuestioning,
    NextQuestionResult,
    answer_establishes_persistent_duration,
)
from ai.conversation.ayush_mode import AyushMode
from ai.conversation.dialogue_state import (
    DialogueState,
    DialogueStateSnapshot,
    DialogueTurn,
    PatientAnswer,
)
from ai.conversation.ontology import OntologyRegistry
from ai.conversation.question_bank import (
    Question,
    QuestionLanguage,
    get_questions_for_field,
)
from ai.conversation.red_flags import (
    DetectedRedFlag,
    RedFlagDetector,
)


class _QuestionBankAdapter:
    """Adapter exposing the standard question-bank API."""

    @staticmethod
    def get_questions_for_field(
        complaint: Any,
        field: Any,
    ) -> tuple[Question, ...]:
        field_id = getattr(field, "identifier", field)

        return get_questions_for_field(
            complaint,
            str(field_id),
        )


class _AyushQuestionBankAdapter:
    """
    Adapter exposing AYUSH questions through the interface expected by
    AdaptiveQuestioning.

    AYUSH questions are currently deterministic and English-only.
    """

    def __init__(self, ayush_mode: AyushMode) -> None:
        self.ayush_mode = ayush_mode

    def get_questions_for_field(
        self,
        complaint: Any,
        field: Any,
    ) -> tuple[Any, ...]:
        field_id = (
            getattr(field, "identifier", None)
            or getattr(field, "field_id", None)
            or str(field)
        )

        return tuple(
            question
            for question in self.ayush_mode.questions()
            if question.field_id == str(field_id)
        )


@dataclass(frozen=True)
class ConversationResult:
    """Result after processing one patient answer."""

    next_question: Any | None
    red_flag: DetectedRedFlag | None
    completed: bool


class DialogueManager:
    """
    Orchestrates one deterministic clinical interview.

    Standard mode uses:
        DialogueState
        OntologyRegistry
        QuestionBank

    AYUSH mode can additionally provide:
        AyushMode

    DialogueManager remains responsible for runtime conversation flow,
    while AdaptiveQuestioning remains responsible for deterministic
    next-question selection.
    """

    def __init__(
        self,
        state: DialogueState,
        *,
        language: QuestionLanguage | str = QuestionLanguage.ENGLISH,
        red_flag_detector: RedFlagDetector | None = None,
        ayush_mode: AyushMode | None = None,
    ) -> None:
        if not isinstance(state, DialogueState):
            raise TypeError(
                "state must be a DialogueState instance."
            )

        if ayush_mode is not None and not isinstance(
            ayush_mode,
            AyushMode,
        ):
            raise TypeError(
                "ayush_mode must be an AyushMode instance."
            )

        self.state = state
        self.ayush_mode = ayush_mode

        if self.ayush_mode is not None:
            self.state.allowed_fields = tuple(
                self.ayush_mode.fields
            )

        self.language = (
            language
            if isinstance(language, QuestionLanguage)
            else QuestionLanguage(language)
        )

        self.red_flag_detector = (
            red_flag_detector
            if red_flag_detector is not None
            else RedFlagDetector()
        )

        if self.ayush_mode is not None:
            question_bank = _AyushQuestionBankAdapter(
                self.ayush_mode
            )
            field_provider = self.ayush_mode
        else:
            question_bank = _QuestionBankAdapter()
            field_provider = None

        self._questioning = AdaptiveQuestioning(
            ontology=OntologyRegistry,
            question_bank=question_bank,
            dialogue_state=self.state,
            field_provider=field_provider,
        )

    @classmethod
    def create(
        cls,
        complaint: str,
        *,
        language: QuestionLanguage | str = QuestionLanguage.ENGLISH,
        red_flag_detector: RedFlagDetector | None = None,
        ayush_mode: AyushMode | None = None,
    ) -> "DialogueManager":
        """Create a new conversation for a supported complaint."""

        state = DialogueState.create(complaint)

        return cls(
            state,
            language=language,
            red_flag_detector=red_flag_detector,
            ayush_mode=ayush_mode,
        )

    # ------------------------------------------------------------------
    # Question flow
    # ------------------------------------------------------------------

    def start(self) -> Any | None:
        """Start the interview and return the first question."""

        return self.get_next_question()

    def get_next_question(self) -> Any | None:
        """Get the next question in the configured language."""

        result: NextQuestionResult = (
            self._questioning.get_next_question(
                language=self.language,
            )
        )

        if result.question is None:
            return None

        question = result.question

        # Standard QuestionBank objects.
        if isinstance(question, Question):
            if question.language == self.language:
                self.state.set_current_question(
                    question.question_id
                )
                return question

            localized_questions = get_questions_for_field(
                self.state.complaint,
                question.field_id,
                language=self.language,
            )

            if not localized_questions:
                return None

            localized_question = localized_questions[0]

            self.state.set_current_question(
                localized_question.question_id
            )

            return localized_question

        # AYUSH questions currently do not have QuestionLanguage.
        question_id = getattr(
            question,
            "id",
            None,
        )

        if question_id is not None:
            self.state.set_current_question(
                str(question_id)
            )

        return question

    def get_next_question_result(self) -> NextQuestionResult:
        """Return the complete AdaptiveQuestioning result."""

        return self._questioning.get_next_question(
            language=self.language,
        )

    # ------------------------------------------------------------------
    # Answer flow
    # ------------------------------------------------------------------

    def record_answer(
        self,
        field_id: str,
        value: Any,
        *,
        question_id: str | None = None,
        source: str | None = None,
        text_for_red_flags: str | None = None,
    ) -> ConversationResult:
        """
        Record one patient answer.

        The answer is stored by DialogueState.
        RedFlagDetector receives only the patient's text.
        """

        resolved_question_id = (
            question_id
            if question_id is not None
            else self.state.current_question_id
        )

        answer = PatientAnswer(
            field_id=field_id,
            value=value,
            question_id=resolved_question_id,
            source=source,
        )

        self.state.record_answer(answer)

        # If onset already contains a usable duration, store the same answer
        # in the structured duration field. AdaptiveQuestioning will therefore
        # skip the redundant duration question safely.
        self._capture_explicit_duration_from_onset(
            field_id=field_id,
            value=value,
        )

        if self.ayush_mode is not None:
            self.ayush_mode.update_field(
                field_id,
                value,
            )

        if text_for_red_flags is None and isinstance(value, str):
            text_for_red_flags = value

        red_flag = None

        if text_for_red_flags:
            detected = self.red_flag_detector.detect(
                text_for_red_flags
            )

            if detected.detected:
                red_flag = detected

        self._record_patient_turn(
            field_id=field_id,
            value=value,
            question_id=resolved_question_id,
        )

        next_question = self.get_next_question()

        return ConversationResult(
            next_question=next_question,
            red_flag=red_flag,
            completed=next_question is None,
        )

    def process_voice_answer(
        self,
        field_id: str,
        transcript: str,
        *,
        question_id: str | None = None,
    ) -> ConversationResult:
        """Process an already-transcribed ASR response."""

        if not isinstance(transcript, str):
            raise TypeError(
                "transcript must be a string."
            )

        transcript = transcript.strip()

        if not transcript:
            raise ValueError(
                "transcript cannot be empty."
            )

        return self.record_answer(
            field_id=field_id,
            value=transcript,
            question_id=question_id,
            source="voice",
            text_for_red_flags=transcript,
        )

    def process_text_answer(
        self,
        field_id: str,
        text: str,
        *,
        question_id: str | None = None,
    ) -> ConversationResult:
        """Process a typed patient response."""

        if not isinstance(text, str):
            raise TypeError(
                "text must be a string."
            )

        text = text.strip()

        if not text:
            raise ValueError(
                "text cannot be empty."
            )

        return self.record_answer(
            field_id=field_id,
            value=text,
            question_id=question_id,
            source="text",
            text_for_red_flags=text,
        )

    # ------------------------------------------------------------------
    # Interview state
    # ------------------------------------------------------------------

    def is_complete(self) -> bool:
        """Return True when there is no remaining question."""

        return self.get_next_question() is None

    def get_snapshot(self) -> DialogueStateSnapshot:
        """Return an immutable snapshot of the interview state."""

        return self.state.snapshot()

    @property
    def complaint(self) -> str:
        """Current chief complaint."""

        return self.state.complaint

    @property
    def progress(self) -> float:
        """Ontology-field completion ratio."""

        return self.state.completion_ratio

    @property
    def collected_fields(self) -> tuple[str, ...]:
        """Fields already collected."""

        return self.state.collected_fields()

    @property
    def missing_fields(self) -> tuple[str, ...]:
        """Fields not yet collected."""

        return self.state.missing_fields()

    @property
    def is_ayush(self) -> bool:
        """Return True when AYUSH mode is attached."""

        return self.ayush_mode is not None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _capture_explicit_duration_from_onset(
        self,
        *,
        field_id: str,
        value: Any,
    ) -> None:
        """
        Store a duration derived from an onset answer only when the shared
        duration parser confirms that the answer explicitly states a duration.
        """

        field_key = (
            field_id.strip().lower()
            if isinstance(field_id, str)
            else ""
        )

        complaint = str(
            getattr(self.state, "complaint", "")
        ).strip().lower()

        persistent_duration_complaints = {
            "fever",
            "cough",
            "abdominal_pain",
        }

        if (
            field_key != "onset"
            or complaint not in persistent_duration_complaints
        ):
            return

        # Uses the exact parser that decides whether the question is skipped.
        if not answer_establishes_persistent_duration(value):
            return

        if self.state.is_field_missing("duration"):
            self.state.update_field(
                "duration",
                value,
                source="derived_from_explicit_onset_duration",
            )

    def _record_patient_turn(
        self,
        *,
        field_id: str,
        value: Any,
        question_id: str | None,
    ) -> None:
        """Record the patient's response in conversation history."""

        text = (
            value
            if isinstance(value, str)
            else str(value)
        )

        turn_number = len(self.state.turns) + 1

        self.state.record_turn(
            DialogueTurn(
                turn_id=f"patient-{turn_number}",
                role="patient",
                text=text,
                question_id=question_id,
                field_id=field_id,
            )
        )


__all__ = [
    "ConversationResult",
    "DialogueManager",
]