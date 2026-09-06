from __future__ import annotations

import re
from typing import Any


# ============================================================
# DOCUMENT TYPES
# ============================================================

DOCUMENT_TYPES = (
    "prescription",
    "lab_report",
    "discharge_summary",
    "imaging_report",
    "unknown",
)


# ============================================================
# KEYWORD RULES
# ============================================================

KEYWORDS = {

    "prescription": {
        "prescription": 5,
        "prescribed": 4,
        "medication": 3,
        "medications": 3,
        "dosage": 3,
        "dose": 2,
        "frequency": 2,
        "route": 2,
        "tablet": 2,
        "capsule": 2,
        "syrup": 2,
        "mg": 1,
        "times daily": 2,
        "once daily": 2,
        "twice daily": 2,
        "oral": 1,
    },

    "lab_report": {
        "laboratory": 5,
        "lab report": 5,
        "investigation": 4,
        "investigations": 4,
        "result": 2,
        "reference range": 5,
        "reference": 2,
        "normal": 1,
        "high": 2,
        "low": 2,
        "hemoglobin": 4,
        "wbc": 4,
        "platelet": 4,
        "neutrophils": 3,
        "lymphocytes": 3,
        "creatinine": 3,
        "glucose": 3,
        "crp": 3,
        "mg/dl": 2,
        "mg/l": 2,
        "/µl": 2,
        "/ul": 2,
    },

    "discharge_summary": {
        "discharge summary": 8,
        "discharge date": 5,
        "admission date": 5,
        "hospital course": 5,
        "discharge medications": 5,
        "final diagnosis": 5,
        "discharge advice": 4,
        "follow-up": 3,
        "follow up": 3,
        "procedures": 3,
        "hospital id": 2,
    },

    "imaging_report": {
        "radiology": 5,
        "imaging report": 6,
        "x-ray": 5,
        "xray": 5,
        "ultrasound": 5,
        "ct scan": 5,
        "mri": 5,
        "mammography": 5,
        "impression": 3,
        "findings": 3,
        "radiologist": 4,
    },
}


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text: str) -> str:
    """
    Normalize OCR text for classification.
    """

    text = text.lower()

    # Normalize common OCR punctuation variants.
    text = text.replace("μ", "u")
    text = text.replace("–", "-")
    text = text.replace("—", "-")

    # Collapse whitespace.
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# OCR RESULT → TEXT
# ============================================================

def ocr_results_to_text(
    ocr_results: Any
) -> str:
    """
    Convert OCR result objects into one text string.

    Accepts:
        - list of OCR dictionaries
        - plain string
        - pipeline page result
    """

    if isinstance(
        ocr_results,
        str
    ):
        return ocr_results

    if not ocr_results:
        return ""

    # Pipeline page/document result.
    if isinstance(
        ocr_results,
        dict
    ):

        if "text" in ocr_results:
            value = ocr_results["text"]

            if isinstance(
                value,
                str
            ):
                return value

            return ocr_results_to_text(
                value
            )

        if "ocr_text" in ocr_results:
            return ocr_results_to_text(
                ocr_results["ocr_text"]
            )

    # List of OCR dictionaries.
    if isinstance(
        ocr_results,
        list
    ):

        text_lines = []

        for item in ocr_results:

            if isinstance(
                item,
                str
            ):
                text_lines.append(
                    item
                )

            elif isinstance(
                item,
                dict
            ):

                text = item.get(
                    "text"
                )

                if text:
                    text_lines.append(
                        str(text)
                    )

        return "\n".join(
            text_lines
        )

    return ""


# ============================================================
# CLASSIFICATION
# ============================================================

def classify_document(
    ocr_results: Any
) -> dict:
    """
    Classify a document using already-produced OCR text.

    Returns a stable structure suitable for later API use.
    """

    raw_text = ocr_results_to_text(
        ocr_results
    )

    normalized_text = normalize_text(
        raw_text
    )

    scores = {
        document_type: 0
        for document_type
        in DOCUMENT_TYPES
        if document_type != "unknown"
    }

    matched_keywords = {
        document_type: []
        for document_type
        in scores
    }

    # ========================================================
    # SCORE KEYWORDS
    # ========================================================

    for document_type, keywords in KEYWORDS.items():

        for keyword, weight in keywords.items():

            normalized_keyword = normalize_text(
                keyword
            )

            if normalized_keyword in normalized_text:

                scores[
                    document_type
                ] += weight

                matched_keywords[
                    document_type
                ].append(
                    keyword
                )

    # ========================================================
    # STRUCTURAL SIGNALS
    # ========================================================

    # Lab reports often contain several reference ranges.
    reference_ranges = len(
        re.findall(
            r"\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?",
            normalized_text
        )
    )

    if reference_ranges >= 3:

        scores["lab_report"] += 5

        matched_keywords[
            "lab_report"
        ].append(
            "multiple_reference_ranges"
        )

    # Prescription-like dosage pattern.
    dosage_matches = len(
        re.findall(
            r"\b\d+(?:\.\d+)?\s*(?:mg|g|ml|mcg|iu)\b",
            normalized_text
        )
    )

    if dosage_matches >= 2:

        scores["prescription"] += 3

        matched_keywords[
            "prescription"
        ].append(
            "multiple_medication_dosages"
        )

    # Discharge summaries commonly have admission and discharge
    # dates together.
    if (
        "admission date" in normalized_text
        and "discharge date" in normalized_text
    ):

        scores["discharge_summary"] += 6

        matched_keywords[
            "discharge_summary"
        ].append(
            "admission_and_discharge_dates"
        )

    # ========================================================
    # DETERMINE WINNER
    # ========================================================

    ranked = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True
    )

    best_type, best_score = ranked[0]

    second_score = (
        ranked[1][1]
        if len(ranked) > 1
        else 0
    )

    # Require meaningful evidence.
    if best_score < 3:

        document_type = "unknown"
        confidence = 0.0

    else:

        document_type = best_type

        # Simple deterministic confidence.
        # This is classification confidence, NOT OCR confidence.
        total_score = sum(
            scores.values()
        )

        if total_score <= 0:
            confidence = 0.0
        else:
            confidence = (
                best_score
                / total_score
            )

        # If the winner is barely ahead, reduce confidence.
        if (
            best_score > 0
            and second_score > 0
            and best_score <= second_score + 1
        ):
            confidence *= 0.75

        confidence = min(
            max(
                confidence,
                0.0
            ),
            1.0
        )

    # ========================================================
    # RESULT
    # ========================================================

    return {
        "document_type": document_type,
        "confidence": round(
            confidence,
            4
        ),
        "scores": scores,
        "matched_keywords": (
            matched_keywords
        ),
        "ocr_text": raw_text,
    }


# ============================================================
# CONVENIENCE FUNCTION
# ============================================================

def classify_from_text(
    text: str
) -> dict:

    return classify_document(
        text
    )


# ============================================================
# CLI TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("        MEDIKIOSK DOCUMENT CLASSIFIER")
    print("=" * 60)

    test_documents = {

        "prescription": """
        OUTPATIENT PRESCRIPTION

        Patient Name: Rahul Kumar

        Diagnosis: Acute febrile illness

        Medications:
        Paracetamol 500 mg
        Oral
        Twice daily
        5 days

        Cetirizine 10 mg
        Oral
        Once daily
        5 days
        """,

        "lab_report": """
        LABORATORY INVESTIGATION REPORT

        Complete Blood Count

        Hemoglobin 13.8 g/dL
        Reference Range 13.0 - 17.0
        Normal

        WBC Count 12,400 /uL
        Reference Range 4,000 - 11,000
        HIGH

        Platelet Count 185,000 /uL
        Reference Range 150,000 - 450,000
        Normal

        CRP 18.6 mg/L
        Reference Range 0 - 5
        HIGH
        """,

        "discharge_summary": """
        DISCHARGE SUMMARY

        Patient Name: Rahul Kumar

        Admission Date: 02 September 2026
        Discharge Date: 06 September 2026

        Final Diagnosis:
        Acute febrile illness with dehydration.

        Hospital Course:
        Patient admitted with fever and headache.

        Procedures:
        Intravenous fluid administration.

        Discharge Medications:
        Paracetamol 500 mg twice daily.

        Discharge Advice:
        Maintain hydration.

        Follow-up after 7 days.
        """,

        "imaging_report": """
        RADIOLOGY REPORT

        Patient Name: Rahul Kumar

        X-ray Chest

        Findings:
        No focal consolidation.

        Impression:
        No acute cardiopulmonary abnormality.
        """,
    }

    for expected, text in test_documents.items():

        result = classify_document(
            text
        )

        print()
        print(
            f"Expected : {expected}"
        )

        print(
            f"Detected : "
            f"{result['document_type']}"
        )

        print(
            f"Confidence: "
            f"{result['confidence']}"
        )

        print(
            f"Scores   : "
            f"{result['scores']}"
        )

    print()
    print("=" * 60)