from ai.summary.schemas import build_summary_input
from ai.summary.merger import merge_sources
from ai.summary.clinical_template import clinical_section_order, render_template


def test_expected_sections():
    result = merge_sources(build_summary_input())
    rendered = render_template(result)
    assert list(rendered) == clinical_section_order()


def test_missing_sections_are_safe():
    rendered = render_template(merge_sources(build_summary_input()))
    assert rendered["allergies"] == []
    assert rendered["investigations"] == []


def test_source_information_is_preserved():
    result = merge_sources(build_summary_input(conversation={"symptoms": ["fever"]}))
    assert result.provenance["relevant_symptoms"][0].source.value == "conversation"


def test_deterministic_output():
    result = merge_sources(build_summary_input(conversation={"symptoms": ["fever"]}))
    assert render_template(result) == render_template(result)
