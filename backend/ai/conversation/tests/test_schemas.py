"""
Test suite for the conversation layer's schema/data-contract behavior:

    ai/conversation/schemas.py

Scope: this file tests ONLY schema/data-contract behavior — field
validation, default values, cross-field consistency rules, immutability
vs. mutability, and JSON-compatible construction. It does NOT test or
implement clinical reasoning, adaptive questioning, red-flag rule logic,
database/API behavior, or LLM behavior, since none of that exists in
``schemas.py`` and none of it belongs here.

It also does not duplicate tests that already belong to
``ai/asr/tests/test_asr.py`` — ``ASRResponse``'s own validation rules
(empty text, confidence range, etc.) are not re-tested here. This suite
only checks that the conversation layer *integrates* with the real,
unmodified ``ASRResponse`` correctly.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from ai.asr.schemas import ASRResponse
from ai.conversation.schemas import (
    ClinicalFieldValue,
    DialoguePhase,
    DialogueRole,
    DialogueState,
    DialogueTurn,
    FieldValueSource,
    InputMode,
    InterviewSession,
    NextQuestionDecision,
    PatientAnswer,
    Question,
    QuestionOption,
    QuestionType,
    RedFlagPriority,
    RedFlagResult,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def asr_response() -> ASRResponse:
    """A real, unmodified ASRResponse instance for VOICE-path tests."""
    return ASRResponse(
        text="mujhe do din se bukhar hai",
        language="hi",
        confidence=0.95,
        provider="mock",
        request_id="req-1",
        duration_ms=2500,
    )


@pytest.fixture
def option_yes() -> QuestionOption:
    return QuestionOption(option_id="opt-yes", display_text="Yes", value="yes")


@pytest.fixture
def option_no() -> QuestionOption:
    return QuestionOption(option_id="opt-no", display_text="No", value="no")


@pytest.fixture
def two_options(option_yes: QuestionOption, option_no: QuestionOption) -> list[QuestionOption]:
    return [option_yes, option_no]


@pytest.fixture
def free_text_question() -> Question:
    return Question(
        question_id="q-chief-complaint",
        text="What brings you in today?",
        language="en",
        target_field="chief_complaint",
        question_type=QuestionType.FREE_TEXT,
    )


@pytest.fixture
def single_select_question(two_options: list[QuestionOption]) -> Question:
    return Question(
        question_id="q-fever",
        text="Do you have a fever?",
        language="en",
        target_field="has_fever",
        question_type=QuestionType.SINGLE_SELECT,
        options=two_options,
    )


@pytest.fixture
def voice_answer(asr_response: ASRResponse) -> PatientAnswer:
    return PatientAnswer(
        answer_id="ans-1",
        question_id="q-chief-complaint",
        input_mode=InputMode.VOICE,
        asr_response=asr_response,
    )


@pytest.fixture
def touch_answer(option_yes: QuestionOption) -> PatientAnswer:
    return PatientAnswer(
        answer_id="ans-2",
        question_id="q-fever",
        input_mode=InputMode.TOUCH,
        selected_option_id=option_yes.option_id,
    )


# ---------------------------------------------------------------------------
# 1. QuestionOption
# ---------------------------------------------------------------------------


class TestQuestionOption:
    def test_valid_construction(self) -> None:
        option = QuestionOption(option_id="opt-1", display_text="Yes", value="yes")
        assert option.option_id == "opt-1"
        assert option.display_text == "Yes"
        assert option.value == "yes"

    def test_empty_option_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QuestionOption(option_id="", display_text="Yes", value="yes")

    def test_empty_display_text_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QuestionOption(option_id="opt-1", display_text="", value="yes")

    def test_empty_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QuestionOption(option_id="opt-1", display_text="Yes", value="")

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QuestionOption(
                option_id="opt-1", display_text="Yes", value="yes", unexpected="x"
            )  # type: ignore[call-arg]

    def test_frozen_immutable(self, option_yes: QuestionOption) -> None:
        with pytest.raises(ValidationError):
            option_yes.display_text = "Changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. Question
# ---------------------------------------------------------------------------


class TestQuestion:
    def test_valid_free_text(self, free_text_question: Question) -> None:
        assert free_text_question.question_type == QuestionType.FREE_TEXT
        assert free_text_question.options == []

    def test_valid_single_select_with_two_plus_options(
        self, single_select_question: Question
    ) -> None:
        assert single_select_question.question_type == QuestionType.SINGLE_SELECT
        assert len(single_select_question.options) == 2

    def test_valid_multi_select_with_two_plus_options(
        self, two_options: list[QuestionOption]
    ) -> None:
        question = Question(
            question_id="q-symptoms",
            text="Which symptoms do you have?",
            language="en",
            target_field="symptoms",
            question_type=QuestionType.MULTI_SELECT,
            options=two_options,
        )
        assert len(question.options) == 2

    def test_single_select_with_fewer_than_two_options_rejected(
        self, option_yes: QuestionOption
    ) -> None:
        with pytest.raises(ValidationError, match="at least 2 options"):
            Question(
                question_id="q-fever",
                text="Do you have a fever?",
                language="en",
                target_field="has_fever",
                question_type=QuestionType.SINGLE_SELECT,
                options=[option_yes],
            )

    def test_multi_select_with_fewer_than_two_options_rejected(
        self, option_yes: QuestionOption
    ) -> None:
        with pytest.raises(ValidationError, match="at least 2 options"):
            Question(
                question_id="q-symptoms",
                text="Which symptoms?",
                language="en",
                target_field="symptoms",
                question_type=QuestionType.MULTI_SELECT,
                options=[option_yes],
            )

    def test_required_defaults_to_true(self, free_text_question: Question) -> None:
        assert free_text_question.required is True

    def test_options_defaults_to_empty_list(self, free_text_question: Question) -> None:
        assert free_text_question.options == []

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Question(
                question_id="q1",
                text="Text",
                language="en",
                target_field="x",
                question_type=QuestionType.FREE_TEXT,
                unexpected="x",
            )  # type: ignore[call-arg]

    def test_frozen_immutable(self, free_text_question: Question) -> None:
        with pytest.raises(ValidationError):
            free_text_question.text = "Changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. PatientAnswer
# ---------------------------------------------------------------------------


class TestPatientAnswerVoice:
    def test_valid_voice_answer_containing_asr_response(
        self, voice_answer: PatientAnswer, asr_response: ASRResponse
    ) -> None:
        assert voice_answer.input_mode == InputMode.VOICE
        assert voice_answer.asr_response == asr_response
        assert voice_answer.selected_option_id is None
        assert voice_answer.touch_value is None

    def test_missing_asr_response_rejected(self) -> None:
        with pytest.raises(ValidationError, match="asr_response is required"):
            PatientAnswer(answer_id="a1", question_id="q1", input_mode=InputMode.VOICE)

    def test_selected_option_id_rejected_for_voice(self, asr_response: ASRResponse) -> None:
        with pytest.raises(ValidationError, match="must not be set when input_mode is VOICE"):
            PatientAnswer(
                answer_id="a1",
                question_id="q1",
                input_mode=InputMode.VOICE,
                asr_response=asr_response,
                selected_option_id="opt-yes",
            )

    def test_touch_value_rejected_for_voice(self, asr_response: ASRResponse) -> None:
        with pytest.raises(ValidationError, match="must not be set when input_mode is VOICE"):
            PatientAnswer(
                answer_id="a1",
                question_id="q1",
                input_mode=InputMode.VOICE,
                asr_response=asr_response,
                touch_value="3 days",
            )


class TestPatientAnswerTouch:
    def test_valid_selected_option_id(self, touch_answer: PatientAnswer) -> None:
        assert touch_answer.input_mode == InputMode.TOUCH
        assert touch_answer.selected_option_id == "opt-yes"
        assert touch_answer.touch_value is None
        assert touch_answer.asr_response is None

    def test_valid_touch_value(self) -> None:
        answer = PatientAnswer(
            answer_id="a2",
            question_id="q-duration",
            input_mode=InputMode.TOUCH,
            touch_value="3",
        )
        assert answer.touch_value == "3"
        assert answer.selected_option_id is None

    def test_neither_selected_option_id_nor_touch_value_rejected(self) -> None:
        with pytest.raises(ValidationError, match="one of selected_option_id or touch_value"):
            PatientAnswer(answer_id="a1", question_id="q1", input_mode=InputMode.TOUCH)

    def test_asr_response_rejected_for_touch(self, asr_response: ASRResponse) -> None:
        with pytest.raises(ValidationError, match="must not be set when input_mode is TOUCH"):
            PatientAnswer(
                answer_id="a1",
                question_id="q1",
                input_mode=InputMode.TOUCH,
                selected_option_id="opt-yes",
                asr_response=asr_response,
            )


class TestPatientAnswerResolvedText:
    def test_voice_returns_asr_response_text(
        self, voice_answer: PatientAnswer, asr_response: ASRResponse
    ) -> None:
        assert voice_answer.resolved_text() == asr_response.text

    def test_touch_with_touch_value_returns_touch_value(self) -> None:
        answer = PatientAnswer(
            answer_id="a1", question_id="q1", input_mode=InputMode.TOUCH, touch_value="3"
        )
        assert answer.resolved_text() == "3"

    def test_touch_with_selected_option_id_returns_selected_option_id(
        self, touch_answer: PatientAnswer
    ) -> None:
        assert touch_answer.resolved_text() == "opt-yes"


# ---------------------------------------------------------------------------
# 4. DialogueTurn
# ---------------------------------------------------------------------------


class TestDialogueTurn:
    def test_valid_assistant_turn_requires_question(self, free_text_question: Question) -> None:
        turn = DialogueTurn(
            turn_id="t1", turn_number=0, role=DialogueRole.ASSISTANT, question=free_text_question
        )
        assert turn.question == free_text_question
        assert turn.answer is None

    def test_assistant_turn_with_answer_rejected(
        self, free_text_question: Question, touch_answer: PatientAnswer
    ) -> None:
        with pytest.raises(ValidationError, match="answer must not be set when role is ASSISTANT"):
            DialogueTurn(
                turn_id="t1",
                turn_number=0,
                role=DialogueRole.ASSISTANT,
                question=free_text_question,
                answer=touch_answer,
            )

    def test_assistant_turn_missing_question_rejected(self) -> None:
        with pytest.raises(ValidationError, match="question is required when role is ASSISTANT"):
            DialogueTurn(turn_id="t1", turn_number=0, role=DialogueRole.ASSISTANT)

    def test_valid_patient_turn_requires_answer(self, touch_answer: PatientAnswer) -> None:
        turn = DialogueTurn(
            turn_id="t2", turn_number=1, role=DialogueRole.PATIENT, answer=touch_answer
        )
        assert turn.answer == touch_answer
        assert turn.question is None

    def test_patient_turn_with_question_rejected(
        self, free_text_question: Question, touch_answer: PatientAnswer
    ) -> None:
        with pytest.raises(ValidationError, match="question must not be set when role is PATIENT"):
            DialogueTurn(
                turn_id="t2",
                turn_number=1,
                role=DialogueRole.PATIENT,
                question=free_text_question,
                answer=touch_answer,
            )

    def test_patient_turn_missing_answer_rejected(self) -> None:
        with pytest.raises(ValidationError, match="answer is required when role is PATIENT"):
            DialogueTurn(turn_id="t2", turn_number=1, role=DialogueRole.PATIENT)

    def test_negative_turn_number_rejected(self, free_text_question: Question) -> None:
        with pytest.raises(ValidationError):
            DialogueTurn(
                turn_id="t1", turn_number=-1, role=DialogueRole.ASSISTANT, question=free_text_question
            )

    def test_frozen_immutable(self, free_text_question: Question) -> None:
        turn = DialogueTurn(
            turn_id="t1", turn_number=0, role=DialogueRole.ASSISTANT, question=free_text_question
        )
        with pytest.raises(ValidationError):
            turn.turn_number = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 5. ClinicalFieldValue
# ---------------------------------------------------------------------------


class TestClinicalFieldValue:
    @pytest.mark.parametrize(
        "value",
        ["fever", 3, 38.5, True, ["fever", "cough"]],
    )
    def test_valid_value_types(self, value: object) -> None:
        field_value = ClinicalFieldValue(
            field_name="some_field", value=value, source=FieldValueSource.TOUCH
        )
        assert field_value.value == value

    def test_confidence_0_0_accepted(self) -> None:
        field_value = ClinicalFieldValue(
            field_name="f", value="x", source=FieldValueSource.VOICE, confidence=0.0
        )
        assert field_value.confidence == 0.0

    def test_confidence_1_0_accepted(self) -> None:
        field_value = ClinicalFieldValue(
            field_name="f", value="x", source=FieldValueSource.VOICE, confidence=1.0
        )
        assert field_value.confidence == 1.0

    def test_confidence_below_0_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClinicalFieldValue(
                field_name="f", value="x", source=FieldValueSource.VOICE, confidence=-0.01
            )

    def test_confidence_above_1_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClinicalFieldValue(
                field_name="f", value="x", source=FieldValueSource.VOICE, confidence=1.01
            )

    def test_empty_field_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClinicalFieldValue(field_name="", value="x", source=FieldValueSource.TOUCH)

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClinicalFieldValue(
                field_name="f", value="x", source=FieldValueSource.TOUCH, unexpected="y"
            )  # type: ignore[call-arg]

    def test_frozen_immutable(self) -> None:
        field_value = ClinicalFieldValue(field_name="f", value="x", source=FieldValueSource.TOUCH)
        with pytest.raises(ValidationError):
            field_value.value = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 6. RedFlagResult
# ---------------------------------------------------------------------------


class TestRedFlagResult:
    def test_valid_non_detected_result(self) -> None:
        result = RedFlagResult(detected=False)
        assert result.detected is False
        assert result.flag_id is None
        assert result.priority is None

    def test_detected_true_requires_flag_id(self) -> None:
        with pytest.raises(ValidationError, match="flag_id and priority are required"):
            RedFlagResult(detected=True, priority=RedFlagPriority.HIGH)

    def test_detected_true_requires_priority(self) -> None:
        with pytest.raises(ValidationError, match="flag_id and priority are required"):
            RedFlagResult(detected=True, flag_id="chest_pain_acute")

    def test_detected_true_with_both_is_valid(self) -> None:
        result = RedFlagResult(
            detected=True, flag_id="chest_pain_acute", priority=RedFlagPriority.CRITICAL
        )
        assert result.detected is True
        assert result.flag_id == "chest_pain_acute"
        assert result.priority == RedFlagPriority.CRITICAL

    def test_matched_fields_defaults_to_empty_list(self) -> None:
        result = RedFlagResult(detected=False)
        assert result.matched_fields == []

    def test_frozen_immutable(self) -> None:
        result = RedFlagResult(detected=False)
        with pytest.raises(ValidationError):
            result.detected = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 7. DialogueState
# ---------------------------------------------------------------------------


class TestDialogueState:
    def test_valid_construction(self) -> None:
        state = DialogueState(session_id="sess-1")
        assert state.session_id == "sess-1"

    def test_phase_defaults_to_greeting(self) -> None:
        state = DialogueState(session_id="sess-1")
        assert state.phase == DialoguePhase.GREETING

    def test_turn_count_defaults_to_0(self) -> None:
        state = DialogueState(session_id="sess-1")
        assert state.turn_count == 0

    def test_has_red_flag_defaults_to_false(self) -> None:
        state = DialogueState(session_id="sess-1")
        assert state.has_red_flag is False

    def test_is_complete_defaults_to_false(self) -> None:
        state = DialogueState(session_id="sess-1")
        assert state.is_complete is False

    def test_negative_turn_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DialogueState(session_id="sess-1", turn_count=-1)

    def test_mutable_fields_can_actually_be_updated(self) -> None:
        state = DialogueState(session_id="sess-1")

        state.turn_count += 1
        assert state.turn_count == 1

        state.phase = DialoguePhase.HISTORY_TAKING
        assert state.phase == DialoguePhase.HISTORY_TAKING

        state.collected_fields["chief_complaint"] = ClinicalFieldValue(
            field_name="chief_complaint", value="fever", source=FieldValueSource.VOICE
        )
        assert "chief_complaint" in state.collected_fields

        state.is_complete = True
        assert state.is_complete is True

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DialogueState(session_id="sess-1", unexpected="x")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# 8. NextQuestionDecision
# ---------------------------------------------------------------------------


class TestNextQuestionDecision:
    def test_valid_normal_decision(self, single_select_question: Question) -> None:
        decision = NextQuestionDecision(
            next_question=single_select_question,
            reason="need to confirm fever status",
            target_field="has_fever",
        )
        assert decision.next_question == single_select_question
        assert decision.continue_interview is True
        assert decision.interview_complete is False
        assert decision.immediate_triage_required is False

    def test_interview_complete_with_continue_interview_true_rejected(self) -> None:
        with pytest.raises(ValidationError, match="continue_interview must be False"):
            NextQuestionDecision(
                reason="done", interview_complete=True, continue_interview=True
            )

    def test_interview_complete_with_next_question_set_rejected(
        self, single_select_question: Question
    ) -> None:
        with pytest.raises(ValidationError, match="next_question must not be set"):
            NextQuestionDecision(
                reason="done",
                interview_complete=True,
                continue_interview=False,
                next_question=single_select_question,
            )

    def test_immediate_triage_required_with_continue_interview_true_rejected(self) -> None:
        with pytest.raises(ValidationError, match="continue_interview must be False"):
            NextQuestionDecision(
                reason="urgent",
                immediate_triage_required=True,
                continue_interview=True,
            )

    def test_valid_completed_decision(self) -> None:
        decision = NextQuestionDecision(
            reason="all required fields collected",
            interview_complete=True,
            continue_interview=False,
        )
        assert decision.interview_complete is True
        assert decision.continue_interview is False
        assert decision.next_question is None

    def test_valid_immediate_triage_decision(self) -> None:
        decision = NextQuestionDecision(
            reason="critical red flag detected",
            immediate_triage_required=True,
            continue_interview=False,
        )
        assert decision.immediate_triage_required is True
        assert decision.continue_interview is False

    def test_frozen_immutable(self) -> None:
        decision = NextQuestionDecision(reason="need more info")
        with pytest.raises(ValidationError):
            decision.reason = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 9. InterviewSession
# ---------------------------------------------------------------------------


class TestInterviewSession:
    def test_valid_construction(self) -> None:
        state = DialogueState(session_id="sess-1")
        session = InterviewSession(session_id="sess-1", language="hi-IN", dialogue_state=state)
        assert session.session_id == "sess-1"
        assert session.language == "hi-IN"
        assert session.dialogue_state == state

    def test_session_id_required(self) -> None:
        state = DialogueState(session_id="sess-1")
        with pytest.raises(ValidationError):
            InterviewSession(language="hi-IN", dialogue_state=state)  # type: ignore[call-arg]

    def test_language_required(self) -> None:
        state = DialogueState(session_id="sess-1")
        with pytest.raises(ValidationError):
            InterviewSession(session_id="sess-1", dialogue_state=state)  # type: ignore[call-arg]

    def test_turns_defaults_to_empty_list(self) -> None:
        state = DialogueState(session_id="sess-1")
        session = InterviewSession(session_id="sess-1", language="en", dialogue_state=state)
        assert session.turns == []

    def test_collected_fields_defaults_to_empty_dict(self) -> None:
        state = DialogueState(session_id="sess-1")
        session = InterviewSession(session_id="sess-1", language="en", dialogue_state=state)
        assert session.collected_fields == {}

    def test_red_flags_defaults_to_empty_list(self) -> None:
        state = DialogueState(session_id="sess-1")
        session = InterviewSession(session_id="sess-1", language="en", dialogue_state=state)
        assert session.red_flags == []

    def test_is_complete_defaults_to_false(self) -> None:
        state = DialogueState(session_id="sess-1")
        session = InterviewSession(session_id="sess-1", language="en", dialogue_state=state)
        assert session.is_complete is False

    def test_started_at_is_automatically_populated(self) -> None:
        state = DialogueState(session_id="sess-1")
        session = InterviewSession(session_id="sess-1", language="en", dialogue_state=state)
        assert isinstance(session.started_at, datetime)

    def test_extra_fields_rejected(self) -> None:
        state = DialogueState(session_id="sess-1")
        with pytest.raises(ValidationError):
            InterviewSession(
                session_id="sess-1", language="en", dialogue_state=state, unexpected="x"
            )  # type: ignore[call-arg]

    def test_mutable_session_fields_can_be_updated(
        self, free_text_question: Question, touch_answer: PatientAnswer
    ) -> None:
        state = DialogueState(session_id="sess-1")
        session = InterviewSession(session_id="sess-1", language="en", dialogue_state=state)

        turn = DialogueTurn(
            turn_id="t1", turn_number=0, role=DialogueRole.ASSISTANT, question=free_text_question
        )
        session.turns.append(turn)
        assert len(session.turns) == 1

        session.collected_fields["has_fever"] = ClinicalFieldValue(
            field_name="has_fever", value=True, source=FieldValueSource.TOUCH
        )
        assert "has_fever" in session.collected_fields

        session.is_complete = True
        assert session.is_complete is True


# ---------------------------------------------------------------------------
# 10. Integration
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end construction using the real, unmodified ASRResponse and
    every conversation schema together, mirroring how these models are
    expected to compose in practice."""

    def test_full_session_composition_with_real_asr_response(self) -> None:
        # Real ASRResponse from ai.asr.schemas, not a stand-in.
        real_asr_response = ASRResponse(
            text="mujhe teen din se bukhar hai",
            language="hi",
            confidence=0.92,
            provider="mock",
            request_id="req-42",
            duration_ms=3100,
        )

        # PatientAnswer preserves it exactly, unmodified.
        answer = PatientAnswer(
            answer_id="ans-1",
            question_id="q-chief-complaint",
            input_mode=InputMode.VOICE,
            asr_response=real_asr_response,
        )
        assert answer.asr_response is real_asr_response
        assert answer.asr_response.text == "mujhe teen din se bukhar hai"
        assert answer.asr_response.provider == "mock"
        assert answer.resolved_text() == real_asr_response.text

        # DialogueTurn containing that PatientAnswer.
        question = Question(
            question_id="q-chief-complaint",
            text="What brings you in today?",
            language="hi",
            target_field="chief_complaint",
            question_type=QuestionType.FREE_TEXT,
        )
        assistant_turn = DialogueTurn(
            turn_id="t1", turn_number=0, role=DialogueRole.ASSISTANT, question=question
        )
        patient_turn = DialogueTurn(
            turn_id="t2", turn_number=1, role=DialogueRole.PATIENT, answer=answer
        )
        assert patient_turn.answer.asr_response.text == "mujhe teen din se bukhar hai"

        # DialogueState reflecting the collected field.
        state = DialogueState(
            session_id="sess-1",
            phase=DialoguePhase.HISTORY_TAKING,
            chief_complaint="fever",
            turn_count=2,
            collected_fields={
                "chief_complaint": ClinicalFieldValue(
                    field_name="chief_complaint",
                    value="fever",
                    source=FieldValueSource.VOICE,
                    confidence=0.92,
                    source_turn_id="t2",
                )
            },
        )
        assert state.collected_fields["chief_complaint"].value == "fever"

        # InterviewSession tying everything together.
        session = InterviewSession(
            session_id="sess-1",
            language="hi-IN",
            dialogue_state=state,
            turns=[assistant_turn, patient_turn],
            collected_fields=state.collected_fields,
        )

        assert session.turns == [assistant_turn, patient_turn]
        assert session.dialogue_state.turn_count == 2
        assert session.collected_fields["chief_complaint"].source == FieldValueSource.VOICE
        # The original ASRResponse is preserved, unmodified, through the
        # entire chain: PatientAnswer -> DialogueTurn -> InterviewSession.
        recovered_turn = session.turns[1]
        assert recovered_turn.answer.asr_response == real_asr_response