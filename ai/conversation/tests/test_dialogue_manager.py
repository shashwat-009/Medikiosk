from ai.conversation.dialogue_manager import (
    ConversationResult,
    DialogueManager,
)
from ai.conversation.dialogue_state import DialogueState
from ai.conversation.question_bank import QuestionLanguage


def test_create_manager_returns_first_question():
    manager = DialogueManager.create(
        "fever",
        language=QuestionLanguage.ENGLISH,
    )

    question = manager.start()

    assert question is not None
    assert question.field_id == "onset"
    assert question.language == QuestionLanguage.ENGLISH


def test_manager_uses_dialogue_state():
    manager = DialogueManager.create("fever")

    assert isinstance(manager.state, DialogueState)
    assert manager.complaint == "fever"


def test_record_answer_updates_state():
    manager = DialogueManager.create("fever")

    question = manager.start()

    result = manager.record_answer(
        field_id=question.field_id,
        value="2 days",
        question_id=question.question_id,
        source="text",
    )

    assert isinstance(result, ConversationResult)
    assert "onset" in manager.collected_fields
    assert manager.state.get_field_value("onset") == "2 days"


def test_next_question_changes_after_answer():
    manager = DialogueManager.create("fever")

    first = manager.start()

    result = manager.record_answer(
        first.field_id,
        "2 days",
        question_id=first.question_id,
    )

    assert result.next_question is not None
    assert result.next_question.field_id == "severity"


def test_hindi_question_selection():
    manager = DialogueManager.create(
        "fever",
        language=QuestionLanguage.HINDI,
    )

    question = manager.start()

    assert question is not None
    assert question.language == QuestionLanguage.HINDI
    assert question.field_id == "onset"


def test_voice_answer_is_stored():
    manager = DialogueManager.create("headache")

    question = manager.start()

    result = manager.process_voice_answer(
        question.field_id,
        "Mujhe teen din se sir dard hai",
        question_id=question.question_id,
    )

    assert result.next_question is not None
    assert (
        manager.state.get_field_value(question.field_id)
        == "Mujhe teen din se sir dard hai"
    )


def test_text_answer_is_stored():
    manager = DialogueManager.create("cough")

    question = manager.start()

    manager.process_text_answer(
        question.field_id,
        "Since yesterday",
        question_id=question.question_id,
    )

    assert manager.state.get_field_value(
        question.field_id
    ) == "Since yesterday"


def test_red_flag_is_returned_for_breathing_difficulty():
    manager = DialogueManager.create("cough")

    question = manager.start()

    result = manager.process_voice_answer(
        question.field_id,
        "I am having difficulty breathing",
        question_id=question.question_id,
    )

    assert result.red_flag is not None
    assert result.red_flag.detected is True
    assert result.red_flag.category == "severe_breathing_difficulty"


def test_normal_answer_has_no_red_flag():
    manager = DialogueManager.create("fever")

    question = manager.start()

    result = manager.process_voice_answer(
        question.field_id,
        "I have had fever for two days",
        question_id=question.question_id,
    )

    assert result.red_flag is None


def test_snapshot_is_available():
    manager = DialogueManager.create("fever")

    snapshot = manager.get_snapshot()

    assert snapshot.complaint == "fever"
    assert snapshot.answers == ()
    assert snapshot.turns == ()


def test_progress_starts_at_zero():
    manager = DialogueManager.create("fever")

    assert manager.progress == 0.0


def test_unknown_complaint_is_rejected():
    try:
        DialogueManager.create("unknown_complaint")
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Expected unsupported complaint to raise ValueError"
        )


def test_empty_voice_transcript_is_rejected():
    manager = DialogueManager.create("fever")

    try:
        manager.process_voice_answer(
            "onset",
            "",
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Expected empty transcript to raise ValueError"
        )