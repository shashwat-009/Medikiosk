"""Unit tests for MediKiosk Dialogue State."""

import pytest

from ai.conversation.dialogue_state import (
    DialogueState,
    DialogueStateError,
    DialogueTurn,
    InvalidAnswerError,
    PatientAnswer,
    UnknownComplaintError,
    UnknownFieldError,
    create_dialogue_state,
    get_collected_fields,
    get_completion_ratio,
    get_field_value,
    get_missing_fields,
    record_patient_answer,
    update_clinical_field,
)


def test_dialogue_state_imports_successfully():
    state = create_dialogue_state("fever")

    assert isinstance(state, DialogueState)


def test_initial_state_can_be_created():
    state = create_dialogue_state("fever")

    assert state.complaint == "fever"
    assert state.total_fields > 0


def test_initial_state_contains_no_collected_fields():
    state = create_dialogue_state("fever")

    assert state.collected_fields() == ()


def test_initial_state_contains_all_fields_as_missing():
    state = create_dialogue_state("fever")

    assert state.missing_field_count == state.total_fields
    assert len(state.missing_fields()) == state.total_fields


def test_valid_patient_answer_updates_correct_field():
    state = create_dialogue_state("fever")

    answer = PatientAnswer(
        field_id="duration",
        value="3 days",
    )

    record_patient_answer(state, answer)

    assert state.is_field_known("duration")
    assert state.get_field_value("duration") == "3 days"


def test_updating_one_field_does_not_modify_another():
    state = create_dialogue_state("fever")

    update_clinical_field(
        state,
        "duration",
        "3 days",
    )

    assert state.get_field_value("duration") == "3 days"
    assert state.is_field_missing("temperature")
    assert state.is_field_missing("severity")
    assert state.is_field_missing("chills")


def test_collected_fields_can_be_retrieved():
    state = create_dialogue_state("fever")

    update_clinical_field(
        state,
        "duration",
        "3 days",
    )

    update_clinical_field(
        state,
        "temperature",
        "101 F",
    )

    collected = state.collected_fields()

    assert "duration" in collected
    assert "temperature" in collected
    assert len(collected) == 2


def test_missing_fields_can_be_retrieved():
    state = create_dialogue_state("fever")

    update_clinical_field(
        state,
        "duration",
        "3 days",
    )

    missing = state.missing_fields()

    assert "duration" not in missing
    assert "temperature" in missing
    assert "severity" in missing


def test_known_field_is_correctly_identified():
    state = create_dialogue_state("fever")

    assert state.is_field_missing("duration")

    update_clinical_field(
        state,
        "duration",
        "3 days",
    )

    assert state.is_field_known("duration")
    assert not state.is_field_missing("duration")


def test_unknown_field_is_rejected():
    state = create_dialogue_state("fever")

    with pytest.raises(UnknownFieldError):
        update_clinical_field(
            state,
            "does_not_exist",
            "some value",
        )


def test_field_from_different_complaint_is_rejected():
    state = create_dialogue_state("fever")

    with pytest.raises(UnknownFieldError):
        update_clinical_field(
            state,
            "radiation",
            "left arm",
        )


def test_unknown_complaint_is_rejected():
    with pytest.raises(UnknownComplaintError):
        create_dialogue_state("unknown_complaint")


def test_empty_complaint_is_rejected():
    with pytest.raises(UnknownComplaintError):
        create_dialogue_state("")


def test_empty_field_identifier_is_rejected():
    state = create_dialogue_state("fever")

    with pytest.raises(UnknownFieldError):
        update_clinical_field(
            state,
            "",
            "value",
        )


def test_none_value_is_rejected():
    state = create_dialogue_state("fever")

    with pytest.raises(InvalidAnswerError):
        update_clinical_field(
            state,
            "duration",
            None,
        )


def test_empty_string_value_is_rejected():
    state = create_dialogue_state("fever")

    with pytest.raises(InvalidAnswerError):
        update_clinical_field(
            state,
            "duration",
            "   ",
        )


def test_completion_starts_at_zero():
    state = create_dialogue_state("fever")

    assert state.completion_ratio == 0.0
    assert state.completion_percentage == 0.0


def test_completion_is_deterministic():
    state = create_dialogue_state("fever")

    update_clinical_field(
        state,
        "duration",
        "3 days",
    )

    update_clinical_field(
        state,
        "temperature",
        "101 F",
    )

    first = state.completion_ratio
    second = state.completion_ratio

    assert first == second


def test_completion_increases_when_fields_are_collected():
    state = create_dialogue_state("fever")

    initial = state.completion_ratio

    update_clinical_field(
        state,
        "duration",
        "3 days",
    )

    assert state.completion_ratio > initial


def test_completion_matches_collected_divided_by_total():
    state = create_dialogue_state("fever")

    update_clinical_field(
        state,
        "duration",
        "3 days",
    )

    update_clinical_field(
        state,
        "temperature",
        "101 F",
    )

    expected = 2 / state.total_fields

    assert state.completion_ratio == expected


def test_multiple_updates_work():
    state = create_dialogue_state("chest_pain")

    update_clinical_field(
        state,
        "location",
        "center of chest",
    )

    update_clinical_field(
        state,
        "severity",
        7,
    )

    update_clinical_field(
        state,
        "duration",
        "20 minutes",
    )

    assert state.get_field_value("location") == "center of chest"
    assert state.get_field_value("severity") == 7
    assert state.get_field_value("duration") == "20 minutes"

    assert state.collected_field_count == 3


def test_repeated_update_uses_latest_value():
    state = create_dialogue_state("fever")

    update_clinical_field(
        state,
        "duration",
        "2 days",
    )

    update_clinical_field(
        state,
        "duration",
        "3 days",
    )

    assert state.get_field_value("duration") == "3 days"
    assert state.collected_field_count == 1


def test_repeated_patient_answers_are_preserved_in_answer_history():
    state = create_dialogue_state("fever")

    record_patient_answer(
        state,
        PatientAnswer(
            field_id="duration",
            value="2 days",
        ),
    )

    record_patient_answer(
        state,
        PatientAnswer(
            field_id="duration",
            value="3 days",
        ),
    )

    assert state.get_field_value("duration") == "3 days"
    assert len(state.answers) == 2
    assert state.answers[0].value == "2 days"
    assert state.answers[1].value == "3 days"


def test_patient_answer_updates_only_specified_field():
    state = create_dialogue_state("fever")

    record_patient_answer(
        state,
        PatientAnswer(
            field_id="duration",
            value="3 days",
        ),
    )

    assert state.collected_fields() == ("duration",)


def test_conversation_turn_can_be_recorded():
    state = create_dialogue_state("fever")

    turn = DialogueTurn(
        turn_id="turn-1",
        role="patient",
        text="I have fever for three days.",
        field_id="duration",
    )

    state.record_turn(turn)

    assert len(state.turns) == 1
    assert state.turns[0].turn_id == "turn-1"


def test_question_information_can_be_recorded():
    state = create_dialogue_state("fever")

    state.set_current_question("fever_duration_en")

    assert state.current_question_id == "fever_duration_en"


def test_previous_question_is_preserved():
    state = create_dialogue_state("fever")

    state.set_current_question("fever_duration_en")
    state.set_current_question("fever_temperature_en")

    assert state.previous_question_id == "fever_duration_en"
    assert state.current_question_id == "fever_temperature_en"


def test_record_turn_with_question_updates_question_state():
    state = create_dialogue_state("fever")

    state.record_turn(
        DialogueTurn(
            turn_id="turn-1",
            role="assistant",
            text="How long have you had the fever?",
            question_id="fever_duration_en",
        )
    )

    assert state.current_question_id == "fever_duration_en"


def test_snapshot_contains_current_state():
    state = create_dialogue_state("fever")

    update_clinical_field(
        state,
        "duration",
        "3 days",
    )

    snapshot = state.snapshot()

    assert snapshot.complaint == "fever"
    assert "duration" in snapshot.clinical_fields
    assert snapshot.clinical_fields["duration"].value == "3 days"


def test_snapshot_is_independent_of_future_answer_list_changes():
    state = create_dialogue_state("fever")

    snapshot = state.snapshot()

    record_patient_answer(
        state,
        PatientAnswer(
            field_id="duration",
            value="3 days",
        ),
    )

    assert len(snapshot.answers) == 0
    assert len(state.answers) == 1


def test_no_medical_inference_is_performed():
    state = create_dialogue_state("fever")

    record_patient_answer(
        state,
        PatientAnswer(
            field_id="duration",
            value="3 days",
        ),
    )

    assert state.collected_fields() == ("duration",)

    assert "severity" not in state.clinical_fields
    assert "temperature" not in state.clinical_fields
    assert "chills" not in state.clinical_fields


def test_state_does_not_select_next_question():
    state = create_dialogue_state("fever")

    record_patient_answer(
        state,
        PatientAnswer(
            field_id="duration",
            value="3 days",
        ),
    )

    # Dialogue State only knows what is missing.
    # It must not decide what should be asked next.
    assert "temperature" in state.missing_fields()
    assert "severity" in state.missing_fields()

    assert state.current_question_id is None


def test_all_supported_complaints_can_create_state():
    complaints = (
        "fever",
        "chest_pain",
        "cough",
        "headache",
        "abdominal_pain",
    )

    for complaint in complaints:
        state = create_dialogue_state(complaint)

        assert state.complaint == complaint
        assert state.total_fields > 0
        assert state.collected_field_count == 0


def test_convenience_getters_work():
    state = create_dialogue_state("fever")

    update_clinical_field(
        state,
        "duration",
        "3 days",
    )

    assert "duration" in get_collected_fields(state)
    assert "temperature" in get_missing_fields(state)
    assert get_field_value(state, "duration") == "3 days"
    assert get_completion_ratio(state) == state.completion_ratio


def test_state_rejects_wrong_state_type():
    with pytest.raises(DialogueStateError):
        get_collected_fields("not a state")  # type: ignore[arg-type]