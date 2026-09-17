"""Tests for deterministic adaptive clinical questioning.

These tests preserve the legacy compatibility contract and add scenario-level
coverage for the PS-aligned adaptive paths currently represented by the
ontology/question bank.

The test suite intentionally uses no network, LLM, ASR, or external service.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from ai.conversation.adaptive_questioning import (
    AdaptiveQuestioning,
    NextQuestionResult,
)
from ai.conversation.ontology import (
    ComplaintType,
    OntologyRegistry,
)
from ai.conversation.question_bank import (
    QuestionLanguage,
    get_question_bank,
    get_questions_for_field,
    get_questions_for_complaint,
)
import ai.conversation.question_bank as question_bank_module


# ---------------------------------------------------------------------------
# Simple compatibility doubles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FakeField:
    identifier: str


@dataclass(frozen=True)
class FakeQuestion:
    question_id: str
    field_id: str
    text: str
    language: QuestionLanguage = QuestionLanguage.ENGLISH


class FakeOntology:
    def __init__(self, fields_by_complaint: dict[str, list[FakeField]]) -> None:
        self.fields_by_complaint = fields_by_complaint

    def get_fields(self, complaint: Any) -> list[FakeField]:
        key = getattr(complaint, "value", complaint)
        return list(self.fields_by_complaint.get(str(key), []))


class FakeQuestionBank:
    def __init__(
        self,
        questions_by_field: dict[str, list[FakeQuestion]],
    ) -> None:
        self.questions_by_field = questions_by_field

    def get_questions_for_field(
        self,
        complaint: Any,
        field_id: str,
        language: QuestionLanguage | None = None,
    ) -> list[FakeQuestion]:
        questions = list(self.questions_by_field.get(field_id, []))
        if language is None:
            return questions
        return [
            question
            for question in questions
            if question.language == language
        ]


class FakeDialogueState:
    def __init__(
        self,
        *,
        complaint: Any = "fever",
        language: QuestionLanguage | str = QuestionLanguage.ENGLISH,
        collected: set[str] | None = None,
        values: dict[str, Any] | None = None,
    ) -> None:
        self.complaint = complaint
        self.language = language
        self.collected = set(collected or set())
        self.values = dict(values or {})

    def get_field_value(self, field_id: str) -> Any | None:
        return self.values.get(field_id)


@pytest.fixture
def components():
    fields = [
        FakeField("onset"),
        FakeField("duration"),
        FakeField("temperature"),
        FakeField("severity"),
    ]

    ontology = FakeOntology({"fever": fields})

    questions = {
        "onset": [
            FakeQuestion("q_onset", "onset", "When did it start?"),
        ],
        "duration": [
            FakeQuestion("q_duration", "duration", "How long has it been?"),
        ],
        "temperature": [
            FakeQuestion(
                "q_temperature",
                "temperature",
                "What is your temperature?",
            ),
        ],
        "severity": [
            FakeQuestion(
                "q_severity",
                "severity",
                "How severe is it?",
            ),
        ],
    }

    question_bank = FakeQuestionBank(questions)

    state = FakeDialogueState()

    return ontology, question_bank, state


def make_real_engine(
    complaint: ComplaintType | str,
    *,
    language: QuestionLanguage | str = QuestionLanguage.ENGLISH,
    collected: set[str] | None = None,
    values: dict[str, Any] | None = None,
) -> AdaptiveQuestioning:
    """Build an engine against the real ontology + question bank."""
    state = FakeDialogueState(
        complaint=complaint,
        language=language,
        collected=collected,
        values=values,
    )
    return AdaptiveQuestioning(
        OntologyRegistry,
        question_bank_module,
        state,
    )


def next_real(
    complaint: ComplaintType | str,
    *,
    language: QuestionLanguage | str = QuestionLanguage.ENGLISH,
    collected: set[str] | None = None,
    values: dict[str, Any] | None = None,
):
    engine = make_real_engine(
        complaint,
        language=language,
        collected=collected,
        values=values,
    )
    return engine.get_next_question()


# ---------------------------------------------------------------------------
# Existing compatibility tests
# ---------------------------------------------------------------------------


def test_module_imports_successfully() -> None:
    assert AdaptiveQuestioning is not None


def test_adaptive_questioning_can_be_initialized(components) -> None:
    ontology, question_bank, state = components

    engine = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    )

    assert isinstance(engine, AdaptiveQuestioning)


def test_works_with_ontology(components) -> None:
    ontology, question_bank, state = components

    result = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    ).get_next_question()

    assert result.question is not None


def test_works_with_question_bank(components) -> None:
    ontology, question_bank, state = components

    engine = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    )

    result = engine.get_next_question()

    assert result.question is not None
    assert result.question.field_id == "onset"


def test_works_with_dialogue_state(components) -> None:
    ontology, question_bank, state = components

    result = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    ).get_next_question()

    assert result.has_question is True


def test_selects_question_for_supported_complaint(components) -> None:
    ontology, question_bank, state = components
    state.complaint = "fever"

    result = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    ).get_next_question()

    assert result.question.field_id == "onset"


def test_selects_only_missing_field(components) -> None:
    ontology, question_bank, state = components
    state.collected.update({"onset", "duration"})

    engine = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    )

    result = engine.get_next_question()

    assert result.question.field_id == "temperature"


def test_does_not_repeat_collected_field(components) -> None:
    ontology, question_bank, state = components
    state.collected.add("onset")

    result = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    ).get_next_question()

    assert result.question.field_id != "onset"
    assert result.question.field_id == "duration"


def test_repeated_calls_are_deterministic(components) -> None:
    ontology, question_bank, state = components

    engine = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    )

    first = engine.get_next_question()
    second = engine.get_next_question()

    assert first == second


def test_next_question_changes_after_state_changes(components) -> None:
    ontology, question_bank, state = components

    engine = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    )

    first = engine.get_next_question()
    state.collected.add(first.question.field_id)
    second = engine.get_next_question()

    assert first.question.field_id != second.question.field_id


def test_returns_one_question_at_a_time(components) -> None:
    ontology, question_bank, state = components

    result = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    ).get_next_question()

    assert isinstance(result, NextQuestionResult)
    assert result.question is not None


def test_handles_all_fields_collected(components) -> None:
    ontology, question_bank, state = components
    state.collected.update(
        {"onset", "duration", "temperature", "severity"}
    )

    result = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    ).get_next_question()

    assert result.question is None
    assert result.reason == "no_available_question"


def test_handles_unknown_complaint(components) -> None:
    ontology, question_bank, state = components
    state.complaint = "unknown_complaint"

    result = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    ).get_next_question()

    assert result.question is None
    assert result.reason == "no_applicable_ontology_fields"


def test_handles_missing_question_mapping(components) -> None:
    ontology = FakeOntology({"fever": [FakeField("onset")]})
    question_bank = FakeQuestionBank({})
    state = FakeDialogueState()

    result = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    ).get_next_question()

    assert result.question is None
    assert result.reason == "no_available_question"


def test_does_not_make_network_requests(monkeypatch, components) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("Network access is not allowed")

    monkeypatch.setattr("socket.create_connection", fail)

    ontology, question_bank, state = components
    result = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    ).get_next_question()

    assert result.question is not None


def test_does_not_depend_on_sarvam() -> None:
    """The adaptive engine must be importable without Sarvam."""
    import sys

    assert "sarvamai" not in sys.modules
    assert "sarvam" not in sys.modules


def test_does_not_modify_dialogue_state(components) -> None:
    ontology, question_bank, state = components
    before_collected = set(state.collected)
    before_values = dict(state.values)

    AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    ).get_next_question()

    assert state.collected == before_collected
    assert state.values == before_values


def test_explicit_complaint_overrides_state_complaint(components) -> None:
    ontology, question_bank, state = components
    state.complaint = "unknown_complaint"

    result = AdaptiveQuestioning(
        ontology,
        question_bank,
        state,
    ).get_next_question(complaint="fever")

    assert result.question is not None
    assert result.question.field_id == "onset"


# ---------------------------------------------------------------------------
# PS-aligned adaptive behavior
# ---------------------------------------------------------------------------


def test_cough_path_contains_ps_required_nodes() -> None:
    ontology = OntologyRegistry.get(ComplaintType.COUGH)
    field_ids = {field.identifier for field in ontology.fields}

    assert {
        "fever",
        "nocturnal_sweating",
        "dyspnea_grade",
    }.issubset(field_ids)


def test_cough_path_starts_with_onset() -> None:
    result = next_real("cough")

    assert result.question is not None
    assert result.field_id == "onset"



def test_persistent_complaint_onset_question_invites_duration_once() -> None:
    expected_fragments = {
        "cough": "about how long",
        "fever": "about how long",
        "abdominal_pain": "about how long",
    }

    for complaint, expected in expected_fragments.items():
        question = get_questions_for_complaint(
            complaint,
            language=QuestionLanguage.ENGLISH,
        )[0]

        assert question.field_id == "onset"
        assert expected in question.text.casefold()


@pytest.mark.parametrize(
    ("complaint", "onset_answer"),
    [
        ("cough", "It started 5 days ago."),
        ("cough", "For the last 2 weeks I have been coughing."),
        ("fever", "I have had it for 3 days."),
        ("fever", "It started yesterday."),
    ],
)
def test_persistent_onset_answer_skips_redundant_duration_question(
    complaint: str,
    onset_answer: str,
) -> None:
    result = next_real(
        complaint,
        collected={"onset"},
        values={"onset": onset_answer},
    )

    assert result.question is not None
    assert result.field_id != "duration"
    assert "duration_already_established_by_onset" in result.reason or (
        "duration" in result.skipped_fields
    )


def test_abdominal_onset_with_duration_skips_later_duration_question() -> None:
    result = next_real(
        "abdominal_pain",
        collected={"onset", "location", "character"},
        values={"onset": "The pain started about a week ago."},
    )

    assert result.question is not None
    assert result.field_id != "duration"


@pytest.mark.parametrize(
    ("complaint", "onset_answer"),
    [
        ("cough", "It started on Monday."),
        ("cough", "It began suddenly."),
        ("fever", "It started on Monday."),
        ("abdominal_pain", "It began suddenly."),
    ],
)
def test_onset_without_clear_duration_keeps_duration_question(
    complaint: str,
    onset_answer: str,
) -> None:
    collected = {"onset"}
    if complaint == "abdominal_pain":
        collected.update({"location", "character"})

    result = next_real(
        complaint,
        collected=collected,
        values={"onset": onset_answer},
    )

    assert result.question is not None
    assert result.field_id == "duration"


def test_chest_pain_episode_duration_is_not_treated_as_redundant() -> None:
    result = next_real(
        "chest_pain",
        collected={"onset", "location", "character"},
        values={"onset": "It started 5 days ago."},
    )

    assert result.question is not None
    assert result.field_id == "duration"


def test_headache_episode_duration_is_not_treated_as_redundant() -> None:
    result = next_real(
        "headache",
        collected={"onset", "location", "character", "severity"},
        values={"onset": "It started 5 days ago."},
    )

    assert result.question is not None
    assert result.field_id == "duration"


def test_cough_productive_branch_reaches_sputum_characteristics() -> None:
    result = next_real(
        "cough",
        collected={"onset", "duration", "severity", "nature"},
        values={"nature": "With mucus"},
    )

    assert result.question is not None
    assert result.field_id == "sputum_characteristics"
    assert result.reason == "cough_productive_branch"


def test_cough_dry_branch_skips_sputum_and_characteristics() -> None:
    result = next_real(
        "cough",
        collected={"onset", "duration", "severity", "nature"},
        values={"nature": "Dry"},
    )

    assert result.question is not None
    assert result.field_id == "blood_presence"
    assert result.field_id not in {
        "sputum",
        "sputum_characteristics",
    }
    assert "sputum" in result.skipped_fields
    assert "sputum_characteristics" in result.skipped_fields


def test_cough_explicit_sputum_no_skips_characteristics() -> None:
    result = next_real(
        "cough",
        collected={"onset", "duration", "severity", "nature", "sputum"},
        values={"nature": "Other", "sputum": "no"},
    )

    assert result.question is not None
    assert result.field_id == "blood_presence"
    assert "sputum_characteristics" in result.skipped_fields


def test_cough_explicit_sputum_yes_allows_characteristics() -> None:
    result = next_real(
        "cough",
        collected={"onset", "duration", "severity", "nature", "sputum"},
        values={"nature": "Other", "sputum": "yes"},
    )

    assert result.question is not None
    assert result.field_id == "sputum_characteristics"
    assert result.reason == "sputum_present_branch"


def test_cough_ps_nodes_are_reached_in_order() -> None:
    collected = {
        "onset",
        "duration",
        "severity",
        "nature",
        "sputum_characteristics",
        "blood_presence",
    }
    values = {"nature": "With mucus"}

    result = next_real(
        "cough",
        collected=collected,
        values=values,
    )

    assert result.question is not None
    assert result.field_id == "fever"

    collected.add("fever")
    values["fever"] = "yes"

    result = next_real(
        "cough",
        collected=collected,
        values=values,
    )
    assert result.field_id == "nocturnal_sweating"

    collected.add("nocturnal_sweating")
    values["nocturnal_sweating"] = "no"

    result = next_real(
        "cough",
        collected=collected,
        values=values,
    )
    assert result.field_id == "dyspnea_grade"


def test_cough_multilingual_questions_exist_for_all_ps_nodes() -> None:
    for field_id in (
        "fever",
        "nocturnal_sweating",
        "dyspnea_grade",
    ):
        questions = get_questions_for_field("cough", field_id)
        languages = {question.language for question in questions}

        assert languages == {
            QuestionLanguage.ENGLISH,
            QuestionLanguage.HINDI,
            QuestionLanguage.BENGALI,
            QuestionLanguage.MARATHI,
        }


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (QuestionLanguage.ENGLISH, "en"),
        (QuestionLanguage.HINDI, "hi"),
        (QuestionLanguage.BENGALI, "bn"),
        (QuestionLanguage.MARATHI, "mr"),
    ],
)
def test_cough_ps_nodes_preserve_requested_language(
    language: QuestionLanguage,
    expected: str,
) -> None:
    result = next_real(
        "cough",
        language=language,
        collected={
            "onset",
            "duration",
            "severity",
            "nature",
            "sputum_characteristics",
            "blood_presence",
        },
        values={"nature": "With mucus"},
    )

    assert result.question is not None
    assert result.question.language.value == expected
    assert result.field_id == "fever"


def test_chest_pain_uses_soCRATES_aligned_existing_fields() -> None:
    result = next_real("chest_pain")

    assert result.question is not None
    assert result.field_id == "onset"

    collected = {"onset", "location", "character", "duration"}
    result = next_real(
        "chest_pain",
        collected=collected,
    )

    assert result.field_id == "radiation"

    collected.update({"radiation"})
    result = next_real(
        "chest_pain",
        collected=collected,
    )
    assert result.field_id == "aggravating_factors"


def test_abdominal_pain_preserves_existing_clinical_fields() -> None:
    ontology = OntologyRegistry.get(ComplaintType.ABDOMINAL_PAIN)
    field_ids = {field.identifier for field in ontology.fields}

    assert {
        "onset",
        "location",
        "character",
        "duration",
        "severity",
        "radiation",
        "aggravating_factors",
        "relieving_factors",
        "associated_symptoms",
        "bowel_related_symptoms",
        "vomiting_nausea",
    }.issubset(field_ids)


def test_all_supported_languages_still_have_cough_questions() -> None:
    questions = get_questions_for_complaint("cough")

    languages = {question.language for question in questions}

    assert languages == {
        QuestionLanguage.ENGLISH,
        QuestionLanguage.HINDI,
        QuestionLanguage.BENGALI,
        QuestionLanguage.MARATHI,
    }


def test_question_bank_remains_nonempty_and_structured() -> None:
    bank = get_question_bank()

    assert bank
    for complaint, questions in bank.items():
        assert questions, complaint
        assert all(question.question_id for question in questions)
        assert all(question.field_id for question in questions)
        assert all(question.text.strip() for question in questions)


def test_ayush_field_provider_contract_is_preserved(components) -> None:
    ontology, question_bank, state = components

    field_provider = SimpleNamespace(
        fields=[FakeField("prakriti"), FakeField("vikriti")]
    )

    ayush_questions = FakeQuestionBank(
        {
            "prakriti": [
                FakeQuestion(
                    "ayush_prakriti",
                    "prakriti",
                    "What is your Prakriti?",
                )
            ],
            "vikriti": [
                FakeQuestion(
                    "ayush_vikriti",
                    "vikriti",
                    "What is your Vikriti?",
                )
            ],
        }
    )

    engine = AdaptiveQuestioning(
        ontology,
        ayush_questions,
        state,
        field_provider=field_provider,
    )

    result = engine.get_next_question()

    assert result.question is not None
    assert result.field_id == "prakriti"

# ---------------------------------------------------------------------------
# Shared general-history coverage
# ---------------------------------------------------------------------------


def _complaint_hpi_field_ids(complaint: ComplaintType | str) -> set[str]:
    """Return only the complaint-specific HPI fields from the real ontology."""
    ontology = OntologyRegistry.get(complaint)
    general = {field.identifier for field in OntologyRegistry.get_general_history_fields()}
    return {field.identifier for field in ontology.fields if field.identifier not in general}


def test_general_history_fields_are_registered_without_changing_complaint_ontology() -> None:
    general_ids = tuple(
        field.identifier
        for field in OntologyRegistry.get_general_history_fields()
    )

    assert general_ids == (
        "past_medical_history",
        "past_surgical_history",
        "current_medications",
        "allergies",
        "family_history",
        "personal_history",
        "review_of_systems",
    )

    assert all(
        field.complaints == ()
        for field in OntologyRegistry.get_general_history_fields()
    )


def test_general_history_questions_exist_for_all_supported_languages() -> None:
    for field_id in (
        "past_medical_history",
        "past_surgical_history",
        "current_medications",
        "allergies",
        "family_history",
        "personal_history",
        "review_of_systems",
    ):
        questions = get_questions_for_field(
            "cough",
            field_id,
        )
        assert len(questions) == 4
        assert {question.language for question in questions} == set(QuestionLanguage)


def test_general_history_can_be_started_after_hpi() -> None:
    complaint = "cough"
    collected = _complaint_hpi_field_ids(complaint)

    result = next_real(complaint, collected=collected)

    assert result.has_question
    assert result.field_id == "past_medical_history"
    assert result.question.language == QuestionLanguage.ENGLISH


def test_general_history_is_shared_across_all_supported_complaints() -> None:
    for complaint in ComplaintType:
        collected = _complaint_hpi_field_ids(complaint)
        result = next_real(complaint, collected=collected)
        assert result.has_question
        assert result.field_id == "past_medical_history"


def test_general_history_questions_preserve_requested_language() -> None:
    collected = _complaint_hpi_field_ids("chest_pain")

    for language in QuestionLanguage:
        result = next_real(
            "chest_pain",
            language=language,
            collected=collected,
        )
        assert result.has_question
        assert result.field_id == "past_medical_history"
        assert result.question.language == language


def test_general_history_fields_follow_deterministic_order() -> None:
    complaint = "fever"
    collected = _complaint_hpi_field_ids(complaint)
    expected = [
        "past_medical_history",
        "past_surgical_history",
        "current_medications",
        "allergies",
        "family_history",
        "personal_history",
        "review_of_systems",
    ]

    for expected_field in expected:
        result = next_real(complaint, collected=collected)
        assert result.has_question
        assert result.field_id == expected_field
        collected.add(expected_field)


def test_general_history_questions_work_through_question_bank_fallback() -> None:
    for field_id in (
        "past_medical_history",
        "past_surgical_history",
        "current_medications",
        "allergies",
        "family_history",
        "personal_history",
        "review_of_systems",
    ):
        for language in QuestionLanguage:
            questions = get_questions_for_field(
                "abdominal_pain",
                field_id,
                language=language,
            )
            assert len(questions) == 1
            assert questions[0].field_id == field_id
            assert questions[0].language == language


def test_dialogue_state_accepts_shared_general_history_fields() -> None:
    from ai.conversation.dialogue_state import DialogueState

    state = DialogueState.create("cough")

    state.update_field(
        "past_medical_history",
        "No known medical conditions.",
    )

    assert state.get_field_value("past_medical_history") == "No known medical conditions."
    assert "past_medical_history" in state.collected_fields()
    assert "past_medical_history" not in state.missing_fields()
    assert "past_surgical_history" in state.missing_fields()
