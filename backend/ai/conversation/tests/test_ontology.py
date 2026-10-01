"""Tests for the MediSetu clinical history ontology."""

import json

import pytest

from ai.conversation.ontology import (
    ClinicalDataType,
    ComplaintType,
    OntologyRegistry,
    get_ontology,
)


EXPECTED_FIELDS = {
    ComplaintType.FEVER: {
        "onset",
        "duration",
        "severity",
        "temperature",
        "chills",
        "sweating",
        "headache",
        "cough",
        "associated_symptoms",
    },
    ComplaintType.CHEST_PAIN: {
        "onset",
        "location",
        "character",
        "duration",
        "radiation",
        "aggravating_factors",
        "relieving_factors",
        "severity",
        "associated_symptoms",
    },
    ComplaintType.COUGH: {
        "onset",
        "duration",
        "severity",
        "nature",
        "sputum",
        "sputum_characteristics",
        "blood_presence",
        "associated_symptoms",
        "aggravating_factors",
        "fever",
"nocturnal_sweating",
"dyspnea_grade",
    },
    ComplaintType.HEADACHE: {
        "onset",
        "duration",
        "location",
        "character",
        "severity",
        "frequency_pattern",
        "aggravating_factors",
        "relieving_factors",
        "associated_symptoms",
    },
    ComplaintType.ABDOMINAL_PAIN: {
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
    },
}


def field_ids(complaint: ComplaintType) -> set[str]:
    """Return identifiers for fields in an ontology."""
    return {
        field.identifier
        for field in get_ontology(complaint).fields
    }


@pytest.mark.parametrize("complaint", list(ComplaintType))
def test_all_supported_complaints_have_ontology(
    complaint: ComplaintType,
) -> None:
    ontology = get_ontology(complaint)

    assert ontology.complaint is complaint
    assert ontology.fields


@pytest.mark.parametrize(
    ("complaint", "expected"),
    EXPECTED_FIELDS.items(),
)
def test_expected_fields_are_present(
    complaint: ComplaintType,
    expected: set[str],
) -> None:
    assert expected <= field_ids(complaint)


def test_fever_ontology_contains_expected_fields() -> None:
    assert field_ids(ComplaintType.FEVER) == EXPECTED_FIELDS[ComplaintType.FEVER]


def test_chest_pain_ontology_contains_expected_fields() -> None:
    assert (
        field_ids(ComplaintType.CHEST_PAIN)
        == EXPECTED_FIELDS[ComplaintType.CHEST_PAIN]
    )


def test_cough_ontology_contains_expected_fields() -> None:
    assert field_ids(ComplaintType.COUGH) == EXPECTED_FIELDS[ComplaintType.COUGH]


def test_headache_ontology_contains_expected_fields() -> None:
    assert (
        field_ids(ComplaintType.HEADACHE)
        == EXPECTED_FIELDS[ComplaintType.HEADACHE]
    )


def test_abdominal_pain_ontology_contains_expected_fields() -> None:
    assert (
        field_ids(ComplaintType.ABDOMINAL_PAIN)
        == EXPECTED_FIELDS[ComplaintType.ABDOMINAL_PAIN]
    )


@pytest.mark.parametrize("complaint", list(ComplaintType))
def test_field_order_is_deterministic(complaint: ComplaintType) -> None:
    first = [
        field.identifier
        for field in get_ontology(complaint).fields
    ]
    second = [
        field.identifier
        for field in get_ontology(complaint).fields
    ]

    assert first == second

    priorities = [
        field.priority
        for field in get_ontology(complaint).fields
    ]

    assert priorities == sorted(priorities)
    assert len(priorities) == len(set(priorities))


def test_core_fields_are_distinguished_from_additional_fields() -> None:
    ontology = get_ontology(ComplaintType.CHEST_PAIN)

    core = {field.identifier for field in ontology.core_fields}
    additional = {
        field.identifier
        for field in ontology.additional_fields
    }

    assert {
        "onset",
        "location",
        "character",
        "duration",
        "severity",
    } <= core

    assert {
        "radiation",
        "aggravating_factors",
        "relieving_factors",
        "associated_symptoms",
    } <= additional

    assert core.isdisjoint(additional)


def test_field_data_types_are_structured() -> None:
    fever = get_ontology(ComplaintType.FEVER)

    assert fever.get_field("duration").data_type == ClinicalDataType.DURATION
    assert fever.get_field("temperature").data_type == ClinicalDataType.NUMERIC
    assert fever.get_field("chills").data_type == ClinicalDataType.YES_NO


def test_triage_relevant_is_metadata_only() -> None:
    chest_pain = get_ontology(ComplaintType.CHEST_PAIN)

    associated = chest_pain.get_field("associated_symptoms")

    assert associated is not None
    assert associated.triage_relevant is True

    # The ontology only describes relevance; it does not produce
    # a diagnosis or emergency decision.
    assert not hasattr(chest_pain, "is_emergency")


def test_unknown_complaint_is_handled_explicitly() -> None:
    with pytest.raises(ValueError, match="Unknown clinical complaint"):
        get_ontology("unknown_complaint")


def test_registry_returns_correct_ontology() -> None:
    ontology = OntologyRegistry.get(ComplaintType.FEVER)

    assert ontology is get_ontology("fever")
    assert ontology.complaint == ComplaintType.FEVER


def test_registry_accepts_string_values() -> None:
    assert (
        OntologyRegistry.get("chest_pain").complaint
        == ComplaintType.CHEST_PAIN
    )


def test_registry_all_is_deterministic() -> None:
    first = [ontology.complaint for ontology in OntologyRegistry.all()]
    second = [ontology.complaint for ontology in OntologyRegistry.all()]

    assert first == second
    assert len(first) == 5
    assert set(first) == set(ComplaintType)


def test_ontology_is_serializable() -> None:
    ontology = get_ontology(ComplaintType.FEVER)

    payload = ontology.model_dump(mode="json")
    encoded = json.dumps(payload)

    assert isinstance(encoded, str)
    assert payload["complaint"] == "fever"
    assert len(payload["fields"]) == 9


def test_ontology_models_are_immutable() -> None:
    ontology = get_ontology(ComplaintType.FEVER)

    with pytest.raises((TypeError, ValueError)):
        ontology.complaint = ComplaintType.COUGH


def test_ontology_does_not_require_network_access() -> None:
    """
    Static ontology retrieval is purely local.

    This test intentionally exercises the registry repeatedly; no
    external provider or network dependency is involved.
    """
    for complaint in ComplaintType:
        ontology = OntologyRegistry.get(complaint)
        assert ontology.complaint == complaint


def test_field_lookup_returns_none_for_unknown_field() -> None:
    ontology = get_ontology(ComplaintType.HEADACHE)

    assert ontology.get_field("not_a_real_field") is None


def test_field_lookup_returns_expected_field() -> None:
    ontology = get_ontology(ComplaintType.CHEST_PAIN)

    field = ontology.get_field("radiation")

    assert field is not None
    assert field.identifier == "radiation"
    assert field.name == "Radiation"