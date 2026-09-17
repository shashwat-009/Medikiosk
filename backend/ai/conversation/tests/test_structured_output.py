from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ai.asr.schemas import ASRResponse
from ai.conversation.schemas import (
    ClinicalFieldValue,
    DialogueRole,
    DialogueTurn,
    FieldValueSource,
    InputMode,
    PatientAnswer,
    Question,
    QuestionType,
    RedFlagPriority,
    RedFlagResult,
)
from ai.conversation.structured_output import (
    StructuredClinicalHistory,
    generate_structured_output,
)


def test_import():
    assert StructuredClinicalHistory is not None
    assert generate_structured_output is not None


def test_empty_initialization():
    output = generate_structured_output()

    assert isinstance(output, StructuredClinicalHistory)
    assert output.clinical_fields == {}
    assert output.red_flags == []
    assert output.conversation == []


def test_explicit_empty_initialization():
    output = StructuredClinicalHistory()

    assert output.clinical_fields == {}
    assert output.red_flags == []
    assert output.conversation == []


def test_partially_collected_history():
    field = ClinicalFieldValue(
        field_name="chief_complaint",
        value="fever",
        source=FieldValueSource.VOICE,
        confidence=0.95,
    )

    output = generate_structured_output(
        collected_fields={
            "chief_complaint": field,
        }
    )

    assert list(output.clinical_fields) == ["chief_complaint"]
    assert output.clinical_fields["chief_complaint"].value == "fever"


def test_fully_collected_fields():
    fields = {
        "chief_complaint": ClinicalFieldValue(
            field_name="chief_complaint",
            value="fever",
            source=FieldValueSource.VOICE,
        ),
        "fever_duration_days": ClinicalFieldValue(
            field_name="fever_duration_days",
            value=3,
            source=FieldValueSource.TOUCH,
        ),
        "severity": ClinicalFieldValue(
            field_name="severity",
            value="moderate",
            source=FieldValueSource.VOICE,
        ),
    }

    output = generate_structured_output(collected_fields=fields)

    assert len(output.clinical_fields) == 3
    assert output.clinical_fields["chief_complaint"].value == "fever"
    assert output.clinical_fields["fever_duration_days"].value == 3
    assert output.clinical_fields["severity"].value == "moderate"


def test_missing_fields_remain_missing():
    output = generate_structured_output(
        collected_fields={
            "chief_complaint": ClinicalFieldValue(
                field_name="chief_complaint",
                value="headache",
                source=FieldValueSource.VOICE,
            )
        }
    )

    assert "chief_complaint" in output.clinical_fields
    assert "fever_duration_days" not in output.clinical_fields
    assert "severity" not in output.clinical_fields


def test_red_flag_information_is_preserved():
    red_flag = RedFlagResult(
        detected=True,
        flag_id="acute_example",
        priority=RedFlagPriority.HIGH,
        matched_fields=["chief_complaint"],
        matched_text="severe symptom",
        explanation="Existing rule matched.",
    )

    output = generate_structured_output(
        red_flags=[red_flag],
    )

    assert len(output.red_flags) == 1
    assert output.red_flags[0] == red_flag
    assert output.red_flags[0].flag_id == "acute_example"
    assert output.red_flags[0].priority == RedFlagPriority.HIGH


def test_conversation_information_is_preserved():
    question = Question(
        question_id="q1",
        text="What is your main complaint?",
        language="en-IN",
        target_field="chief_complaint",
        question_type=QuestionType.FREE_TEXT,
    )

    turn = DialogueTurn(
        turn_id="turn-1",
        turn_number=0,
        role=DialogueRole.ASSISTANT,
        question=question,
    )

    output = generate_structured_output(turns=[turn])

    assert len(output.conversation) == 1
    assert output.conversation[0] == turn
    assert output.conversation[0].question.question_id == "q1"


def test_voice_asr_is_preserved_without_modification():
    asr = ASRResponse(
        text="I have fever",
        language="en-IN",
        confidence=0.91,
        provider="test",
        request_id="req-1",
        duration_ms=1200,
    )

    answer = PatientAnswer(
        answer_id="a1",
        question_id="q1",
        input_mode=InputMode.VOICE,
        asr_response=asr,
    )

    turn = DialogueTurn(
        turn_id="turn-2",
        turn_number=1,
        role=DialogueRole.PATIENT,
        answer=answer,
    )

    output = generate_structured_output(turns=[turn])

    preserved = output.conversation[0].answer.asr_response

    assert preserved == asr
    assert preserved.text == "I have fever"
    assert preserved.language == "en-IN"
    assert preserved.confidence == 0.91
    assert preserved.provider == "test"
    assert preserved.request_id == "req-1"
    assert preserved.duration_ms == 1200


def test_output_is_deterministic_for_same_input():
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)

    field = ClinicalFieldValue(
        field_name="chief_complaint",
        value="cough",
        source=FieldValueSource.VOICE,
        updated_at=timestamp,
    )

    first = generate_structured_output(
        collected_fields={"chief_complaint": field}
    )

    second = generate_structured_output(
        collected_fields={"chief_complaint": field}
    )

    assert first == second
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_repeated_generation_is_identical():
    field = ClinicalFieldValue(
        field_name="age",
        value=45,
        source=FieldValueSource.TOUCH,
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    results = [
        generate_structured_output(
            collected_fields={"age": field}
        )
        for _ in range(5)
    ]

    assert all(result == results[0] for result in results)


def test_output_can_be_serialized_to_json():
    output = generate_structured_output(
        collected_fields={
            "chief_complaint": ClinicalFieldValue(
                field_name="chief_complaint",
                value="cough",
                source=FieldValueSource.VOICE,
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        }
    )

    json_text = output.model_dump_json()

    parsed = json.loads(json_text)

    assert isinstance(parsed, dict)
    assert parsed["clinical_fields"]["chief_complaint"]["value"] == "cough"


def test_model_dump_is_machine_readable():
    output = generate_structured_output()

    data = output.model_dump(mode="json")

    assert isinstance(data, dict)
    assert set(data.keys()) == {
        "clinical_fields",
        "red_flags",
        "conversation",
    }


def test_no_invented_information():
    output = generate_structured_output()

    data = output.model_dump(mode="json")

    assert data["clinical_fields"] == {}
    assert data["red_flags"] == []
    assert data["conversation"] == []


def test_invalid_collected_fields_input():
    with pytest.raises(TypeError, match="collected_fields"):
        generate_structured_output(
            collected_fields=[],
        )


def test_invalid_red_flags_input():
    with pytest.raises(TypeError, match="red_flags"):
        generate_structured_output(
            red_flags={},
        )


def test_invalid_turns_input():
    with pytest.raises(TypeError, match="turns"):
        generate_structured_output(
            turns={},
        )


def test_pydantic_rejects_unknown_output_fields():
    with pytest.raises(Exception):
        StructuredClinicalHistory(
            unknown_field="not allowed",
        )


def test_input_collections_are_not_reused():
    field = ClinicalFieldValue(
        field_name="chief_complaint",
        value="pain",
        source=FieldValueSource.TOUCH,
    )

    fields = {"chief_complaint": field}
    flags = []
    turns = []

    output = generate_structured_output(
        collected_fields=fields,
        red_flags=flags,
        turns=turns,
    )

    assert output.clinical_fields is not fields
    assert output.red_flags is not flags
    assert output.conversation is not turns


def test_compatibility_with_existing_models():
    field = ClinicalFieldValue(
        field_name="has_fever",
        value=True,
        source=FieldValueSource.TOUCH,
    )

    flag = RedFlagResult(
        detected=False,
        matched_fields=[],
    )

    output = generate_structured_output(
        collected_fields={"has_fever": field},
        red_flags=[flag],
    )

    assert output.clinical_fields["has_fever"].value is True
    assert output.red_flags[0].detected is False