"""
Structured clinical-history output for the conversation layer.

This module only projects already-collected conversation data into a
deterministic, machine-readable Pydantic model.

It does not:
- diagnose
- infer missing clinical information
- call an LLM
- call an external API
- modify ASR responses
- evaluate red-flag rules
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai.conversation.schemas import (
    ClinicalFieldValue,
    DialogueTurn,
    RedFlagResult,
)


class StructuredClinicalHistory(BaseModel):
    """
    Machine-readable projection of the collected clinical history.

    Missing clinical fields remain absent from ``clinical_fields`` rather
    than being guessed or populated with invented values.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    clinical_fields: dict[str, ClinicalFieldValue] = Field(
        default_factory=dict,
        description="Collected clinical fields keyed by canonical field name.",
    )
    red_flags: list[RedFlagResult] = Field(
        default_factory=list,
        description="Red-flag results already produced by the red-flag subsystem.",
    )
    conversation: list[DialogueTurn] = Field(
        default_factory=list,
        description="Ordered conversation turns preserved from conversation history.",
    )

    def to_dict(self) -> dict[str, Any]:
        """Return the structured output as a JSON-compatible dictionary."""
        return self.model_dump(mode="json")


def generate_structured_output(
    *,
    collected_fields: dict[str, ClinicalFieldValue] | None = None,
    red_flags: list[RedFlagResult] | None = None,
    turns: list[DialogueTurn] | None = None,
) -> StructuredClinicalHistory:
    """
    Build deterministic structured clinical history from existing data.

    No clinical information is inferred. ``None`` means that the
    corresponding information was not supplied to this function.

    Input collections are copied into the output so the caller's mutable
    containers are not reused internally.
    """
    if collected_fields is None:
        collected_fields = {}

    if red_flags is None:
        red_flags = []

    if turns is None:
        turns = []

    if not isinstance(collected_fields, dict):
        raise TypeError("collected_fields must be a dictionary")

    if not isinstance(red_flags, list):
        raise TypeError("red_flags must be a list")

    if not isinstance(turns, list):
        raise TypeError("turns must be a list")

    return StructuredClinicalHistory(
        clinical_fields=dict(collected_fields),
        red_flags=list(red_flags),
        conversation=list(turns),
    )