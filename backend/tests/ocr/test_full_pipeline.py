"""
Full Module B OCR pipeline test.

Runs:
    document
        -> preprocessing
        -> OCR
        -> document classification
        -> clinical entity extraction

IMPORTANT:
The extractor must receive page["ocr_text"], because that contains
the OCR items with bounding boxes and coordinates.
"""

import json
import sys
from pathlib import Path

from ai.ocr.pipeline import process_document
from ai.ocr.document_classifier import classify_document
from ai.ocr.clinical_entity_extractor import extract_clinical_entities


TEST_DOCUMENT = Path("test_documents/medisetu_b2_medical_test.pdf")


def print_section(title):
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def main():
    if not TEST_DOCUMENT.exists():
        print(f"ERROR: Test document not found: {TEST_DOCUMENT}")
        sys.exit(1)

    print_section("MEDISETU MODULE B - FULL PIPELINE TEST")

    print(f"Input document : {TEST_DOCUMENT}")

    # ------------------------------------------------------------------
    # 1. OCR + preprocessing
    # ------------------------------------------------------------------
    print_section("[1] OCR")

    result = process_document(str(TEST_DOCUMENT))

    print(f"Status       : {result.get('status')}")
    print(f"Pages        : {result.get('page_count')}")
    print(f"Successful   : {result.get('successful_pages')}")
    print(f"Confidence   : {result.get('confidence')}")

    if result.get("status") != "success":
        print("\nOCR pipeline failed.")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    pages = result.get("pages", [])

    if not pages:
        print("\nERROR: No OCR pages returned.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. Classification + extraction
    # ------------------------------------------------------------------
    print_section("[2] CLASSIFICATION + CLINICAL EXTRACTION")

    all_page_entities = []

    for page_number, page in enumerate(pages, start=1):
        print()
        print(f"--- PAGE {page_number} ---")

        # IMPORTANT:
        # page["ocr_text"] contains structured OCR items:
        # text, confidence, bbox, x, y, width, height
        #
        # page["text"] is only the combined plain-text representation.
        ocr_items = page.get("ocr_text", [])

        if not ocr_items:
            print("WARNING: page contains no structured OCR items.")
            continue

        # Verify that coordinates survived the pipeline.
        coordinate_items = [
            item
            for item in ocr_items
            if isinstance(item, dict)
            and (
                item.get("x", 0) != 0
                or item.get("y", 0) != 0
            )
        ]

        print(f"OCR items        : {len(ocr_items)}")
        print(f"Items with coords: {len(coordinate_items)}")

        if not coordinate_items:
            print(
                "ERROR: OCR coordinates were lost before extraction."
            )
            sys.exit(1)

        # --------------------------------------------------------------
        # Classification
        # --------------------------------------------------------------
        classification = classify_document(ocr_items)

        print(
            f"Document type    : "
            f"{classification.get('document_type')}"
        )

        print(
            f"Classification confidence: "
            f"{classification.get('confidence')}"
        )

        # --------------------------------------------------------------
        # Clinical extraction
        #
        # CRITICAL:
        # Pass ocr_items, NOT page["text"].
        # --------------------------------------------------------------
        entities = extract_clinical_entities(
            ocr_items,
            document_type=classification.get("document_type"),
        )

        all_page_entities.append(
            {
                "page": page_number,
                "classification": classification,
                "entities": entities,
            }
        )

        print("\nExtracted entities:")

        print(
            json.dumps(
                entities,
                indent=2,
                ensure_ascii=False,
            )
        )

    # ------------------------------------------------------------------
    # 3. Verification
    # ------------------------------------------------------------------
    print_section("[3] VERIFICATION")

    combined_medications = []
    combined_labs = []
    combined_diagnoses = []
    combined_procedures = []

    for page_result in all_page_entities:
        entities = page_result["entities"]

        combined_medications.extend(
            entities.get("medications", [])
        )

        combined_labs.extend(
            entities.get("laboratory_results", [])
        )

        combined_diagnoses.extend(
            entities.get("diagnoses", [])
        )

        combined_procedures.extend(
            entities.get("procedures", [])
        )

    medication_text = json.dumps(
        combined_medications,
        ensure_ascii=False,
    ).lower()

    lab_text = json.dumps(
        combined_labs,
        ensure_ascii=False,
    ).lower()

    diagnosis_text = json.dumps(
        combined_diagnoses,
        ensure_ascii=False,
    ).lower()

    procedure_text = json.dumps(
        combined_procedures,
        ensure_ascii=False,
    ).lower()

    # Expected entities from the test document.
    expected_medications = [
        "paracetamol",
        "cetirizine",
        "ors",
    ]

    expected_labs = [
        "hemoglobin",
        "wbc",
        "platelet",
        "neutrophils",
        "lymphocytes",
        "crp",
        "creatinine",
        "alt",
    ]

    print(
        f"Medications extracted : "
        f"{len(combined_medications)}"
    )

    print(
        f"Laboratory results    : "
        f"{len(combined_labs)}"
    )

    print(
        f"Diagnoses extracted   : "
        f"{len(combined_diagnoses)}"
    )

    print(
        f"Procedures extracted  : "
        f"{len(combined_procedures)}"
    )

    # ------------------------------------------------------------------
    # Medication verification
    # ------------------------------------------------------------------
    missing_medications = [
        name
        for name in expected_medications
        if name not in medication_text
    ]

    if missing_medications:
        print(
            "\nFAIL: Missing medications:"
        )
        for medication in missing_medications:
            print(f"  - {medication}")

    else:
        print(
            "\nPASS: Expected medications detected."
        )

    # ------------------------------------------------------------------
    # Laboratory verification
    # ------------------------------------------------------------------
    missing_labs = [
        name
        for name in expected_labs
        if name not in lab_text
    ]

    if missing_labs:
        print(
            "\nFAIL: Missing laboratory results:"
        )
        for lab in missing_labs:
            print(f"  - {lab}")

    else:
        print(
            "\nPASS: Expected laboratory results detected."
        )

    # ------------------------------------------------------------------
    # Basic diagnosis verification
    # ------------------------------------------------------------------
    if diagnosis_text:
        print(
            "PASS: Diagnosis extraction returned data."
        )
    else:
        print(
            "WARNING: No diagnoses extracted."
        )

    # ------------------------------------------------------------------
    # Basic procedure verification
    # ------------------------------------------------------------------
    if procedure_text:
        print(
            "PASS: Procedure extraction returned data."
        )
    else:
        print(
            "WARNING: No procedures extracted."
        )

    # ------------------------------------------------------------------
    # Final result
    # ------------------------------------------------------------------
    if missing_medications or missing_labs:
        print_section("RESULT: FAILED")
        sys.exit(1)

    print_section("RESULT: PASSED")


if __name__ == "__main__":
    main()