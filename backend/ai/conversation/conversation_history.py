"""
Conversation history management for MediKiosk.

This module maintains an in-memory chronological collection of the
project's existing DialogueTurn objects.

It does not create duplicate conversation schemas, persist data,
perform network operations, or modify ASR/conversation state.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from copy import deepcopy
from typing import Any

from .schemas import DialogueTurn


class ConversationHistory:
    """
    In-memory chronological conversation history.

    The history owns its stored turn snapshots so callers cannot
    accidentally mutate previously stored data through references
    returned by the API.
    """

    def __init__(
        self,
        turns: Iterable[DialogueTurn] | None = None,
    ) -> None:
        self._turns: list[DialogueTurn] = []

        if turns is not None:
            for turn in turns:
                self.add_turn(turn)

    def add_turn(self, turn: DialogueTurn) -> DialogueTurn:
        """
        Append one DialogueTurn to the history.

        A defensive copy is stored and returned, preventing accidental
        mutation through the caller's original object.

        Raises:
            TypeError: if the supplied object is not a DialogueTurn.
            ValueError: if the exact same turn_id already exists.
        """
        if not isinstance(turn, DialogueTurn):
            raise TypeError(
                "turn must be an instance of DialogueTurn"
            )

        if any(existing.turn_id == turn.turn_id for existing in self._turns):
            raise ValueError(
                f"Duplicate turn_id is not allowed: {turn.turn_id}"
            )

        stored_turn = deepcopy(turn)
        self._turns.append(stored_turn)

        return deepcopy(stored_turn)

    def get_turns(self) -> list[DialogueTurn]:
        """
        Return all turns in chronological insertion order.

        A defensive copy is returned.
        """
        return deepcopy(self._turns)

    @property
    def turns(self) -> list[DialogueTurn]:
        """Read-only-style access returning copied turn data."""
        return self.get_turns()

    def latest_turn(self) -> DialogueTurn | None:
        """
        Return the most recently stored turn.

        Returns None when the history is empty.
        """
        if not self._turns:
            return None

        return deepcopy(self._turns[-1])

    def __len__(self) -> int:
        """Return the number of stored turns."""
        return len(self._turns)

    def __iter__(self) -> Iterator[DialogueTurn]:
        """Iterate over defensive copies of stored turns."""
        return iter(self.get_turns())

    def clear(self) -> None:
        """Remove all stored conversation turns."""
        self._turns.clear()

    def reset(self) -> None:
        """Alias for clear()."""
        self.clear()

    def is_empty(self) -> bool:
        """Return True when no turns are stored."""
        return not self._turns

    def export(self) -> list[dict[str, Any]]:
        """
        Export the history as Pydantic-compatible dictionaries.

        The returned dictionaries are independent from internal state.
        """
        return [
            deepcopy(turn.model_dump(mode="python"))
            for turn in self._turns
        ]

    def model_dump(self) -> list[dict[str, Any]]:
        """Alias for export()."""
        return self.export()

    def to_list(self) -> list[DialogueTurn]:
        """Return a defensive copy of the stored turns."""
        return self.get_turns()

    def __repr__(self) -> str:
        return (
            f"ConversationHistory(turn_count={len(self._turns)})"
        )


def create_conversation_history() -> ConversationHistory:
    """Create an empty conversation history."""
    return ConversationHistory()