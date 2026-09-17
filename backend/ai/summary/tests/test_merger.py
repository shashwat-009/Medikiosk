from ai.summary.schemas import build_summary_input
from ai.summary.merger import merge_sources


def test_conversation_and_ocr_merge():
    data = build_summary_input(
        conversation={"symptoms": ["fever"], "medications": ["Drug A"]},
        ocr={"lab_results": ["Hb 12"], "drug_information": ["Drug B"]},
    )
    result = merge_sources(data)
    assert result.sections.relevant_symptoms == ["fever"]
    assert result.sections.investigations == ["Hb 12"]
    assert result.sections.medication_history == ["Drug A", "Drug B"]


def test_conversation_only():
    result = merge_sources(build_summary_input(conversation={"symptoms": ["fever"]}))
    assert result.sections.relevant_symptoms == ["fever"]


def test_ocr_only():
    result = merge_sources(build_summary_input(ocr={"lab_results": ["Hb 12"]}))
    assert result.sections.investigations == ["Hb 12"]


def test_timeline_inclusion():
    result = merge_sources(build_summary_input(
        timeline=[{"date": "2026-01-01", "event": "visit"}]
    ))
    assert result.sections.timeline[0].event == "visit"


def test_duplicate_data_is_deduplicated():
    result = merge_sources(build_summary_input(
        conversation={"medications": ["Drug A"]},
        ocr={"drug_information": ["Drug A"]},
    ))
    assert result.sections.medication_history == ["Drug A"]


def test_conflict_is_preserved():
    result = merge_sources(build_summary_input(
        conversation={"medications": ["Drug A"]},
        ocr={"drug_information": ["Drug B"]},
    ))
    assert result.sections.medication_history == ["Drug A", "Drug B"]
    assert "medication_history" in result.conflicts
    assert result.verification_status.value == "needs_review"


def test_empty_inputs():
    result = merge_sources(build_summary_input())
    assert result.sections.model_dump() == {
        "chief_complaints": [],
        "history_of_present_illness": [],
        "relevant_symptoms": [],
        "medical_history": [],
        "medication_history": [],
        "allergies": [],
        "investigations": [],
        "document_derived_findings": [],
        "timeline": [],
        "red_flags": [],
        "relevant_negatives": [],
        "other": {},
    }


def test_deterministic():
    data = build_summary_input(
        conversation={"symptoms": ["fever", "cough"]},
        ocr={"lab_results": ["Hb 12"]},
    )
    assert merge_sources(data).model_dump() == merge_sources(data).model_dump()


def test_provenance_is_preserved():
    result = merge_sources(build_summary_input(
        conversation={"symptoms": ["fever"]}
    ))
    assert result.provenance["relevant_symptoms"][0].source.value == "conversation"
