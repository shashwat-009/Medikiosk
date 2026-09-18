"""
Persistent conversation-state serialization for MediKiosk.

Responsibilities:
    - Serialize DialogueState into JSON-safe data for database storage.
    - Deserialize stored JSON back into DialogueState.
    - Preserve clinical fields, answers, turns, and question tracking.

This module does NOT:
    - choose questions
    - perform AI inference
    - perform red-flag detection
    - access external services
    - modify DialogueManager behavior
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ai.conversation.dialogue_state import (
    ClinicalFieldValue,
    DialogueState,
    DialogueTurn,
    PatientAnswer,
)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_datetime(value: datetime | None) -> str | None:
    """Convert datetime to JSON-safe ISO format."""
    if value is None:
        return None

    return value.isoformat()


def _deserialize_datetime(value: str | None) -> datetime | None:
    """Convert ISO datetime back into datetime."""
    if value is None:
        return None

    return datetime.fromisoformat(value)


# ---------------------------------------------------------------------------
# DialogueState -> JSON
# ---------------------------------------------------------------------------


def serialize_dialogue_state(
    state: DialogueState,
) -> dict[str, Any]:
    """
    Convert DialogueState into JSON-safe dictionary data.

    The returned dictionary can be stored directly in a SQLAlchemy JSON
    column.
    """

    if not isinstance(state, DialogueState):
        raise TypeError("state must be a DialogueState instance.")

    return {
        "complaint": state.complaint,
        "clinical_fields": {
            field_id: {
                "field_id": field_value.field_id,
                "value": field_value.value,
                "source": field_value.source,
                "updated_at": _serialize_datetime(
                    field_value.updated_at
                ),
            }
            for field_id, field_value in state.clinical_fields.items()
        },
        "answers": [
            {
                "field_id": answer.field_id,
                "value": answer.value,
                "question_id": answer.question_id,
                "source": answer.source,
            }
            for answer in state.answers
        ],
        "turns": [
            {
                "turn_id": turn.turn_id,
                "role": turn.role,
                "text": turn.text,
                "question_id": turn.question_id,
                "field_id": turn.field_id,
                "timestamp": _serialize_datetime(
                    turn.timestamp
                ),
            }
            for turn in state.turns
        ],
        "current_question_id": state.current_question_id,
        "previous_question_id": state.previous_question_id,
        "allowed_fields": (
            list(state.allowed_fields)
            if state.allowed_fields is not None
            else None
        ),
    }


# ---------------------------------------------------------------------------
# JSON -> DialogueState
# ---------------------------------------------------------------------------


def deserialize_dialogue_state(
    data: dict[str, Any],
) -> DialogueState:
    """
    Reconstruct DialogueState from persisted JSON data.
    """

    if not isinstance(data, dict):
        raise TypeError("conversation state must be a dictionary.")

    complaint = data.get("complaint")

    if not complaint:
        raise ValueError(
            "Persisted conversation state is missing complaint."
        )

    allowed_fields_data = data.get("allowed_fields")

    allowed_fields = (
        tuple(allowed_fields_data)
        if allowed_fields_data is not None
        else None
    )

    state = DialogueState.create(
        complaint,
        allowed_fields=allowed_fields,
    )

    # Restore clinical fields.
    clinical_fields = data.get("clinical_fields", {})

    for field_id, raw_field in clinical_fields.items():
        state.clinical_fields[field_id] = ClinicalFieldValue(
            field_id=raw_field["field_id"],
            value=raw_field.get("value"),
            source=raw_field.get("source"),
            updated_at=(
                _deserialize_datetime(
                    raw_field.get("updated_at")
                )
                or datetime.now().astimezone()
            ),
        )

    # Restore patient answers.
    answers = data.get("answers", [])

    state.answers = [
        PatientAnswer(
            field_id=answer["field_id"],
            value=answer.get("value"),
            question_id=answer.get("question_id"),
            source=answer.get("source"),
        )
        for answer in answers
    ]

    # Restore conversation turns.
    turns = data.get("turns", [])

    state.turns = [
        DialogueTurn(
            turn_id=turn["turn_id"],
            role=turn["role"],
            text=turn.get("text"),
            question_id=turn.get("question_id"),
            field_id=turn.get("field_id"),
            timestamp=(
                _deserialize_datetime(
                    turn.get("timestamp")
                )
                or datetime.now().astimezone()
            ),
        )
        for turn in turns
    ]

    # Restore question tracking.
    state.current_question_id = data.get(
        "current_question_id"
    )

    state.previous_question_id = data.get(
        "previous_question_id"
    )

    return state