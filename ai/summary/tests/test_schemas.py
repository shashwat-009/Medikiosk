import pytest
from pydantic import ValidationError
from ai.summary.schemas import (
    SummaryInput, NormalizedConversation, NormalizedItem, Provenance,
    SourceType, normalize_conversation, normalize_ocr, build_summary_input,
)


def test_valid_models():
    item = NormalizedItem(
        value="fever", provenance=Provenance(source=SourceType.CONVERSATION)
    )
    data = NormalizedConversation(symptoms=[item])
    assert data.symptoms[0].value == "fever"


def test_optional_data_is_allowed():
    assert SummaryInput().conversation is None
    assert SummaryInput().ocr is None


def test_invalid_enum_is_rejected():
    with pytest.raises(ValidationError):
        Provenance(source="invented")


def test_stable_serialization():
    x = SummaryInput()
    assert x.model_dump() == x.model_dump()
    assert x.model_dump_json() == x.model_dump_json()


def test_adapter_accepts_aliases():
    c = normalize_conversation({"chief_complaint": "fever", "symptoms": ["cough"]})
    o = normalize_ocr({"lab_results": ["Hb 12"], "drug_information": ["paracetamol"]})
    assert c.chief_complaints[0].value == "fever"
    assert o.labs[0].value == "Hb 12"
    assert o.medications[0].value == "paracetamol"


def test_timeline_adapter():
    x = build_summary_input(timeline=[{"date": "2026-01-01", "event": "admission"}])
    assert x.timeline[0].event == "admission"
