from __future__ import annotations

import inspect

import pytest

from ai.conversation.conversation_history import (
    ConversationHistory,
    create_conversation_history,
)
from ai.conversation.schemas import (
    DialogueRole,
    DialogueTurn,
    PatientAnswer,
    Question,
)



def _make_question(
    question_id: str = "q1",
    target_field: str = "chief_complaint",
) -> Question:
    """
    Create a Question using the existing schema.

    The construction is intentionally based on the actual model fields
    used by the project rather than defining a duplicate Question model.
    """
    from ai.conversation.schemas import QuestionType

    fields = Question.model_fields

    values = {}

    if "question_id" in fields:
        values["question_id"] = question_id
    elif "id" in fields:
        values["id"] = question_id

    if "target_field" in fields:
        values["target_field"] = target_field

    if "text" in fields:
        values["text"] = "What is your main problem?"

    if "question_text" in fields:
        values["question_text"] = "What is your main problem?"

    # Required fields in the current Question schema.
    if "language" in fields:
        values["language"] = "en-IN"

    if "question_type" in fields:
        values["question_type"] = QuestionType.FREE_TEXT

    return Question(**values)





def _make_answer(
    value: str = "fever",
    answer_id: str = "a1",
    question_id: str = "q1",
) -> PatientAnswer:
    """
    Create a PatientAnswer using the existing schema.

    Uses TOUCH input because it does not require constructing an ASRResponse.
    """
    from ai.conversation.schemas import InputMode

    fields = PatientAnswer.model_fields

    values = {}

    if "answer_id" in fields:
        values["answer_id"] = answer_id

    if "question_id" in fields:
        values["question_id"] = question_id

    if "input_mode" in fields:
        values["input_mode"] = InputMode.TOUCH

    if "touch_value" in fields:
        values["touch_value"] = value

    return PatientAnswer(**values)




def _make_assistant_turn(
    turn_id: str,
    turn_number: int,
) -> DialogueTurn:
    return DialogueTurn(
        turn_id=turn_id,
        turn_number=turn_number,
        role=DialogueRole.ASSISTANT,
        question=_make_question(
            question_id=f"question-{turn_id}",
        ),
    )



def _make_patient_turn(
    turn_id: str,
    turn_number: int,
) -> DialogueTurn:
    return DialogueTurn(
        turn_id=turn_id,
        turn_number=turn_number,
        role=DialogueRole.PATIENT,
        answer=_make_answer(
            answer_id=f"answer-{turn_id}",
            question_id=f"question-{turn_id}",
            value=f"answer-{turn_id}",
        ),
    )




def test_module_imports_successfully():
    assert ConversationHistory is not None
    assert create_conversation_history is not None


def test_empty_history_works():
    history = ConversationHistory()

    assert len(history) == 0
    assert history.is_empty() is True
    assert history.get_turns() == []
    assert history.latest_turn() is None


def test_factory_creates_empty_history():
    history = create_conversation_history()

    assert isinstance(history, ConversationHistory)
    assert len(history) == 0


def test_adding_one_turn():
    history = ConversationHistory()
    turn = _make_assistant_turn("turn-1", 0)

    stored = history.add_turn(turn)

    assert len(history) == 1
    assert stored.turn_id == "turn-1"
    assert history.latest_turn().turn_id == "turn-1"


def test_adding_multiple_turns():
    history = ConversationHistory()

    first = _make_assistant_turn("turn-1", 0)
    second = _make_patient_turn("turn-2", 1)
    third = _make_assistant_turn("turn-3", 2)

    history.add_turn(first)
    history.add_turn(second)
    history.add_turn(third)

    assert len(history) == 3


def test_chronological_order_is_preserved():
    history = ConversationHistory()

    turns = [
        _make_assistant_turn("turn-1", 0),
        _make_patient_turn("turn-2", 1),
        _make_assistant_turn("turn-3", 2),
    ]

    for turn in turns:
        history.add_turn(turn)

    result = history.get_turns()

    assert [turn.turn_id for turn in result] == [
        "turn-1",
        "turn-2",
        "turn-3",
    ]


def test_latest_turn_retrieval():
    history = ConversationHistory()

    history.add_turn(_make_assistant_turn("turn-1", 0))
    history.add_turn(_make_patient_turn("turn-2", 1))

    latest = history.latest_turn()

    assert latest is not None
    assert latest.turn_id == "turn-2"


def test_empty_latest_turn_behavior():
    history = ConversationHistory()

    assert history.latest_turn() is None


def test_length():
    history = ConversationHistory()

    assert len(history) == 0

    history.add_turn(_make_assistant_turn("turn-1", 0))
    assert len(history) == 1

    history.add_turn(_make_patient_turn("turn-2", 1))
    assert len(history) == 2


def test_structured_export():
    history = ConversationHistory()

    history.add_turn(
        _make_assistant_turn("turn-1", 0)
    )

    exported = history.export()

    assert isinstance(exported, list)
    assert len(exported) == 1
    assert isinstance(exported[0], dict)
    assert exported[0]["turn_id"] == "turn-1"


def test_model_dump_matches_export():
    history = ConversationHistory()

    history.add_turn(
        _make_assistant_turn("turn-1", 0)
    )

    assert history.model_dump() == history.export()


def test_to_list_returns_turns():
    history = ConversationHistory()

    history.add_turn(
        _make_assistant_turn("turn-1", 0)
    )

    turns = history.to_list()

    assert len(turns) == 1
    assert isinstance(turns[0], DialogueTurn)


def test_invalid_input_is_rejected():
    history = ConversationHistory()

    with pytest.raises(TypeError):
        history.add_turn("not a dialogue turn")


def test_duplicate_turn_id_is_rejected():
    history = ConversationHistory()

    first = _make_assistant_turn("turn-1", 0)
    second = _make_patient_turn("turn-1", 1)

    history.add_turn(first)

    with pytest.raises(ValueError):
        history.add_turn(second)

    assert len(history) == 1


def test_original_turn_is_not_mutated_by_history():
    history = ConversationHistory()

    turn = _make_assistant_turn("turn-1", 0)
    history.add_turn(turn)

    assert turn.turn_id == "turn-1"
    assert turn.turn_number == 0


def test_returned_turn_is_defensive_copy():
    history = ConversationHistory()

    turn = _make_assistant_turn("turn-1", 0)
    returned = history.add_turn(turn)

    assert returned is not turn
    assert returned == turn


def test_get_turns_returns_defensive_copy():
    history = ConversationHistory()

    history.add_turn(
        _make_assistant_turn("turn-1", 0)
    )

    first = history.get_turns()
    second = history.get_turns()

    assert first is not second
    assert first == second
    assert first[0] is not second[0]


def test_export_is_independent():
    history = ConversationHistory()

    history.add_turn(
        _make_assistant_turn("turn-1", 0)
    )

    first_export = history.export()
    first_export[0]["turn_id"] = "changed"

    second_export = history.export()

    assert second_export[0]["turn_id"] == "turn-1"


def test_clear_works():
    history = ConversationHistory()

    history.add_turn(
        _make_assistant_turn("turn-1", 0)
    )
    history.add_turn(
        _make_patient_turn("turn-2", 1)
    )

    history.clear()

    assert len(history) == 0
    assert history.latest_turn() is None
    assert history.is_empty() is True


def test_reset_works():
    history = ConversationHistory()

    history.add_turn(
        _make_assistant_turn("turn-1", 0)
    )

    history.reset()

    assert len(history) == 0


def test_repeated_reads_are_deterministic():
    history = ConversationHistory()

    history.add_turn(
        _make_assistant_turn("turn-1", 0)
    )
    history.add_turn(
        _make_patient_turn("turn-2", 1)
    )

    first = history.export()
    second = history.export()

    assert first == second


def test_existing_dialogue_turn_schema_is_used():
    history = ConversationHistory()

    turn = _make_assistant_turn("turn-1", 0)
    history.add_turn(turn)

    stored = history.latest_turn()

    assert isinstance(stored, DialogueTurn)


def test_no_asr_dependency():
    source = inspect.getsource(
        ConversationHistory
    )

    assert "Sarvam" not in source
    assert "ASR" not in source


def test_no_network_dependency():
    source = inspect.getsource(
        ConversationHistory
    )

    assert "requests" not in source
    assert "http://" not in source
    assert "https://" not in source