"""Focused tests for the MediKiosk AYUSH conversation layer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai.conversation.ayush_mode import (
    AYUSH_FIELDS,
    DASHAVIDHA_FIELDS,
    GENERAL_FIELDS,
    AHARA_FIELDS,
    VIHARA_FIELDS,
    AyushFieldValue,
    AyushMode,
    AyushModeState,
    AyushSection,
    create_ayush_mode,
    is_ayush_mode,
)


EXPECTED_DASHAVIDHA = {
    "prakriti",
    "vikriti",
    "sara",
    "samhanana",
    "pramana",
    "satmya",
    "sattva",
    "ahara_shakti",
    "vyayama_shakti",
    "vaya",
}

EXPECTED_AHARA = {
    "ahara_pattern",
    "ahara_timing",
    "ahara_appetite",
    "ahara_tolerance",
    "ahara_preferences",
}

EXPECTED_VIHARA = {
    "vihara_sleep",
    "vihara_activity",
    "vihara_exercise",
    "vihara_daily_routine",
    "vihara_stress",
}


def test_ayush_mode_initializes() -> None:
    mode = AyushMode()

    assert mode.mode == "ayush"
    assert mode.is_ayush()
    assert mode.collected_information() == {}


def test_factory_creates_ayush_mode() -> None:
    mode = create_ayush_mode()

    assert isinstance(mode, AyushMode)
    assert mode.mode == "ayush"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ayush", True),
        ("AYUSH", True),
        ("AyUsH", True),
        ("allopathy", False),
        ("", False),
    ],
)
def test_ayush_mode_identification(value: str, expected: bool) -> None:
    assert is_ayush_mode(value) is expected


def test_all_dashavidha_fields_are_present() -> None:
    assert set(DASHAVIDHA_FIELDS) == EXPECTED_DASHAVIDHA


def test_all_ahara_fields_are_present() -> None:
    assert set(AHARA_FIELDS) == EXPECTED_AHARA


def test_all_vihara_fields_are_present() -> None:
    assert set(VIHARA_FIELDS) == EXPECTED_VIHARA


def test_ayush_field_collection_contains_required_domains() -> None:
    assert EXPECTED_DASHAVIDHA.issubset(set(AYUSH_FIELDS))
    assert EXPECTED_AHARA.issubset(set(AYUSH_FIELDS))
    assert EXPECTED_VIHARA.issubset(set(AYUSH_FIELDS))


def test_general_history_is_compatible_with_ayush_mode() -> None:
    mode = AyushMode(include_general_history=True)

    assert set(GENERAL_FIELDS).issubset(set(mode.fields))


def test_general_history_can_be_disabled() -> None:
    mode = AyushMode(include_general_history=False)

    assert mode.general_history_fields == ()
    assert not set(GENERAL_FIELDS).intersection(mode.fields)


def test_field_update_and_retrieval() -> None:
    mode = AyushMode()

    mode.update_field("prakriti", "Previously assessed as part of consultation")

    assert mode.get_field("prakriti") == (
        "Previously assessed as part of consultation"
    )
    assert mode.has_field("prakriti")


def test_structured_field_update() -> None:
    mode = AyushMode()

    field = AyushFieldValue(
        field_id="ahara_pattern",
        value="Regular meals",
    )

    mode.update(field)

    assert mode.get_field("ahara_pattern") == "Regular meals"


def test_latest_valid_value_replaces_previous_value() -> None:
    mode = AyushMode()

    mode.update_field("vaya", 30)
    mode.update_field("vaya", 31)

    assert mode.get_field("vaya") == 31


def test_collected_and_missing_fields_are_deterministic() -> None:
    mode = AyushMode()

    mode.update_field("prakriti", "recorded")
    mode.update_field("vaya", 30)

    collected = mode.collected_fields()
    missing = mode.missing_fields()

    assert collected == ("prakriti", "vaya")
    assert "prakriti" not in missing
    assert "vaya" not in missing


def test_invalid_field_is_rejected() -> None:
    mode = AyushMode()

    with pytest.raises(ValueError, match="Unknown AYUSH field"):
        mode.update_field("not_an_ayush_field", "value")


def test_invalid_field_lookup_is_rejected() -> None:
    mode = AyushMode()

    with pytest.raises(ValueError, match="Unknown AYUSH field"):
        mode.get_field("unknown")


def test_none_value_is_rejected() -> None:
    mode = AyushMode()

    with pytest.raises(ValueError, match="cannot be None"):
        mode.update_field("prakriti", None)


def test_empty_string_value_is_rejected() -> None:
    mode = AyushMode()

    with pytest.raises(ValueError, match="cannot be empty"):
        mode.update_field("prakriti", "   ")


def test_progress_initial_state() -> None:
    mode = AyushMode()

    progress = mode.progress()

    assert progress.total_fields == len(mode.fields)
    assert progress.collected_fields == 0
    assert progress.remaining_fields == len(mode.fields)
    assert progress.percentage == 0.0
    assert progress.completed is False


def test_progress_updates_deterministically() -> None:
    mode = AyushMode()

    total = len(mode.fields)

    mode.update_field("prakriti", "recorded")
    progress = mode.progress()

    assert progress.total_fields == total
    assert progress.collected_fields == 1
    assert progress.remaining_fields == total - 1
    assert progress.percentage == round(100 / total, 2)
    assert progress.completed is False


def test_completion_after_all_fields_are_collected() -> None:
    mode = AyushMode()

    for index, field_id in enumerate(mode.fields):
        mode.update_field(field_id, f"value-{index}")

    progress = mode.progress()

    assert progress.total_fields == len(mode.fields)
    assert progress.collected_fields == len(mode.fields)
    assert progress.remaining_fields == 0
    assert progress.percentage == 100.0
    assert progress.completed is True
    assert mode.is_complete()


def test_state_is_serializable() -> None:
    mode = AyushMode()
    mode.update_field("prakriti", "recorded")

    state = mode.state()

    assert isinstance(state, AyushModeState)
    assert state.mode == "ayush"
    assert state.values["prakriti"] == "recorded"

    dumped = state.model_dump()

    assert dumped["mode"] == "ayush"
    assert dumped["values"]["prakriti"] == "recorded"


def test_question_retrieval_is_deterministic() -> None:
    mode = AyushMode()

    first = mode.questions()
    second = mode.questions()

    assert first == second
    assert [question.order for question in first] == sorted(
        question.order for question in first
    )


def test_dashavidha_questions_cover_all_fields() -> None:
    mode = AyushMode()

    questions = mode.questions(
        section=AyushSection.DASHAVIDHA_PARIKSHA,
    )

    question_fields = {question.field_id for question in questions}

    assert question_fields == EXPECTED_DASHAVIDHA


def test_ahara_questions_cover_all_fields() -> None:
    mode = AyushMode()

    questions = mode.questions(section=AyushSection.AHARA)

    question_fields = {question.field_id for question in questions}

    assert question_fields == EXPECTED_AHARA


def test_vihara_questions_cover_all_fields() -> None:
    mode = AyushMode()

    questions = mode.questions(section=AyushSection.VIHARA)

    question_fields = {question.field_id for question in questions}

    assert question_fields == EXPECTED_VIHARA


def test_unknown_question_is_rejected() -> None:
    mode = AyushMode()

    with pytest.raises(ValueError, match="Unknown AYUSH question"):
        mode.get_question("ayush.invalid.question")


def test_question_ids_are_unique() -> None:
    mode = AyushMode()

    question_ids = [question.id for question in mode.questions()]

    assert len(question_ids) == len(set(question_ids))


def test_questions_reference_valid_fields() -> None:
    mode = AyushMode()

    for question in mode.questions():
        assert question.field_id in mode.fields


def test_reset_clears_collected_values() -> None:
    mode = AyushMode()

    mode.update_field("prakriti", "recorded")
    mode.update_field("vaya", 30)

    mode.reset()

    assert mode.collected_information() == {}
    assert mode.collected_fields() == ()
    assert not mode.has_field("prakriti")


def test_pydantic_rejects_invalid_mode_state() -> None:
    with pytest.raises(ValidationError):
        AyushModeState(mode="allopathy", values={})


def test_no_external_service_is_required() -> None:
    mode = create_ayush_mode()

    # Construction and deterministic question retrieval are entirely local.
    assert mode.questions()