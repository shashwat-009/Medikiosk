from ai.summary.schemas import (
    build_summary_input, VerificationStatus
)
from ai.summary.merger import merge_sources
from ai.summary.case_sheet import build_case_sheet


def test_complete_case_sheet():
    summary = merge_sources(build_summary_input(
        conversation={
            "chief_complaint": "fever",
            "symptoms": ["cough"],
            "medications": ["Drug A"],
        },
        ocr={"lab_results": ["Hb 12"]},
    ))
    sheet = build_case_sheet(summary)
    assert sheet.summary.sections.chief_complaints == ["fever"]
    assert sheet.physician_verified is False
    assert sheet.verification


def test_partial_case_sheet():
    sheet = build_case_sheet(merge_sources(build_summary_input(
        conversation={"symptoms": ["fever"]}
    )))
    assert sheet.summary.sections.relevant_symptoms == ["fever"]
    assert sheet.summary.sections.allergies == []


def test_verification_fields_exist():
    sheet = build_case_sheet(merge_sources(build_summary_input(
        conversation={"symptoms": ["fever"]}
    )))
    item = next(x for x in sheet.verification if x.field == "relevant_symptoms")
    assert item.status == VerificationStatus.UNVERIFIED


def test_missing_data():
    sheet = build_case_sheet(merge_sources(build_summary_input()))
    assert sheet.verification == []


def test_stable_structure():
    summary = merge_sources(build_summary_input(conversation={"symptoms": ["fever"]}))
    a, b = build_case_sheet(summary), build_case_sheet(summary)
    assert a.model_dump() == b.model_dump()
