from __future__ import annotations

import pytest

from ai.conversation.dialogue_manager import DialogueManager
from ai.conversation.red_flags import RedFlagDetector


@pytest.mark.parametrize(
    ("complaint", "onset_answer"),
    [
        ("fever", "It started yesterday."),
        ("cough", "मुझे दो दिन से खांसी है।"),
        ("abdominal_pain", "তিন দিন ধরে পেটে ব্যথা হচ্ছে।"),
        ("cough", "मला दोन दिवसांपासून खोकला आहे."),
    ],
    ids=["english", "hindi", "bengali", "marathi"],
)
def test_explicit_onset_duration_is_stored_and_not_asked_twice(
    complaint: str,
    onset_answer: str,
) -> None:
    manager = DialogueManager.create(
        complaint,
        red_flag_detector=RedFlagDetector(use_semantic=False),
    )

    first_question = manager.start()
    assert first_question is not None
    assert first_question.field_id == "onset"

    result = manager.process_text_answer(
        "onset",
        onset_answer,
    )

    assert manager.state.get_field_value("duration") == onset_answer
    assert "duration" not in manager.missing_fields

    assert result.next_question is not None
    assert result.next_question.field_id != "duration"


@pytest.mark.parametrize(
    ("complaint", "onset_answer"),
    [
        ("fever", "It started on Monday."),
        ("cough", "मुझे खांसी अचानक शुरू हुई है।"),
    ],
)
def test_duration_is_asked_when_onset_does_not_contain_duration(
    complaint: str,
    onset_answer: str,
) -> None:
    manager = DialogueManager.create(
        complaint,
        red_flag_detector=RedFlagDetector(use_semantic=False),
    )

    manager.start()

    result = manager.process_text_answer(
        "onset",
        onset_answer,
    )

    assert manager.state.is_field_missing("duration")
    assert result.next_question is not None
    assert result.next_question.field_id == "duration"