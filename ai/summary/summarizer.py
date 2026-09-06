"""Deterministic offline summary generation."""
from __future__ import annotations

from .schemas import SummaryInput, SummaryResult
from .merger import merge_sources


class DeterministicSummarizer:
    """No network calls, no generative model, no inferred clinical facts."""

    def summarize(self, data: SummaryInput) -> SummaryResult:
        return merge_sources(data)


def summarize(data: SummaryInput) -> SummaryResult:
    return DeterministicSummarizer().summarize(data)
