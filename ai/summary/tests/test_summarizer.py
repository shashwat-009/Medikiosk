from ai.summary.schemas import build_summary_input
from ai.summary.summarizer import DeterministicSummarizer, summarize


def test_conversation_only():
    result = summarize(build_summary_input(conversation={"symptoms": ["fever"]}))
    assert result.sections.relevant_symptoms == ["fever"]


def test_ocr_only():
    result = summarize(build_summary_input(ocr={"lab_results": ["Hb 12"]}))
    assert result.sections.investigations == ["Hb 12"]


def test_combined():
    result = summarize(build_summary_input(
        conversation={"symptoms": ["fever"]},
        ocr={"lab_results": ["Hb 12"]},
    ))
    assert result.sections.relevant_symptoms == ["fever"]
    assert result.sections.investigations == ["Hb 12"]


def test_empty():
    result = DeterministicSummarizer().summarize(build_summary_input())
    assert not result.sections.relevant_symptoms


def test_repeated_execution_is_identical():
    data = build_summary_input(
        conversation={"symptoms": ["fever"], "red_flags": ["high fever"]},
        ocr={"lab_results": ["Hb 12"]},
    )
    s = DeterministicSummarizer()
    assert s.summarize(data).model_dump() == s.summarize(data).model_dump()


def test_no_hallucinated_fields():
    result = summarize(build_summary_input(conversation={"symptoms": ["fever"]}))
    assert result.sections.medical_history == []
    assert result.sections.allergies == []
    assert result.sections.investigations == []


def test_no_network_dependency():
    # Construction and execution require no API key/client/network service.
    assert DeterministicSummarizer().summarize(build_summary_input())
