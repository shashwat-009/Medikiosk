"""
MediKiosk Module B - Unified Document AI Pipeline

Pipeline:

    document
        ↓
    file validation
        ↓
    PDF/image preparation
        ↓
    image enhancement
        ↓
    PaddleOCR
        ↓
    document classification
        ↓
    clinical entity extraction
        ↓
    complete structured result

This is the canonical Module B AI pipeline.

The backend should call:

    process_document(file_path)

and receive OCR + classification + clinical extraction
in one result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

try:
    from .document_preprocessor import prepare_document
    from .image_enhancer import enhance_image
    from .ocr_engine import run_ocr
    from .document_classifier import classify_document
    from .clinical_entity_extractor import extract_clinical_entities
except ImportError:
    try:
        from ocr.document_preprocessor import prepare_document
        from ocr.image_enhancer import enhance_image
        from ocr.ocr_engine import run_ocr
        from ocr.document_classifier import classify_document
        from ocr.clinical_entity_extractor import extract_clinical_entities
    except ImportError:
        from ai.ocr.document_preprocessor import prepare_document
        from ai.ocr.image_enhancer import enhance_image
        from ai.ocr.ocr_engine import run_ocr
        from ai.ocr.document_classifier import classify_document
        from ai.ocr.clinical_entity_extractor import extract_clinical_entities


# ============================================================================
# OCR PIPELINE
# ============================================================================

def process_document(
    file_path: str,
    prepared_dir: str = "prepared",
    processed_dir: str = "processed",
) -> Dict[str, Any]:
    """
    Run the complete Module B document-AI pipeline.

    Stages:

        1. Validate input path
        2. Prepare PDF/image pages
        3. Enhance each page
        4. Run PaddleOCR
        5. Classify each page
        6. Extract clinical entities from REAL OCR coordinates
        7. Combine document-level results

    Parameters
    ----------
    file_path:
        Path to the uploaded document.

    prepared_dir:
        Directory used for prepared page images.

    processed_dir:
        Directory used for enhanced images.

    Returns
    -------
    dict
        Complete OCR + classification + extraction result.
    """

    path = Path(file_path)

    # ========================================================================
    # 1. VALIDATE INPUT
    # ========================================================================

    if not path.exists():
        raise FileNotFoundError(
            f"Document not found: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Path is not a file: {path}"
        )

    # ========================================================================
    # 2. PREPARE DOCUMENT
    # ========================================================================

    image_paths = prepare_document(
        str(path),
        output_dir=prepared_dir,
    )

    if not image_paths:
        return {
            "status": "no_pages",
            "source_file": str(path),
            "file_type": path.suffix.lower(),
            "page_count": 0,
            "successful_pages": 0,
            "confidence": 0.0,
            "text": "",
            "pages": [],
            "classification": None,
            "clinical_entities": {
                "patient": {},
                "diagnoses": [],
                "medications": [],
                "laboratory_results": [],
                "procedures": [],
                "dates": [],
            },
        }

    pages: List[Dict[str, Any]] = []

    # ========================================================================
    # 3. PROCESS EACH PAGE
    # ========================================================================

    for page_number, image_path in enumerate(
        image_paths,
        start=1,
    ):

        print()
        print("=" * 60)
        print(
            f"PROCESSING PAGE {page_number}"
        )
        print("=" * 60)

        # --------------------------------------------------------------------
        # IMAGE ENHANCEMENT
        # --------------------------------------------------------------------

        enhanced_path = enhance_image(
            image_path,
            output_dir=processed_dir,
        )

        if enhanced_path is None:

            pages.append(
                {
                    "page_number": page_number,
                    "source_image": image_path,
                    "processed_image": None,
                    "status": "failed",
                    "ocr_text": [],
                    "text": "",
                    "average_confidence": 0.0,
                    "classification": None,
                    "clinical_entities": None,
                }
            )

            continue

        # --------------------------------------------------------------------
        # OCR
        # --------------------------------------------------------------------

        ocr_results = run_ocr(
            enhanced_path
        )

        # --------------------------------------------------------------------
        # BUILD PAGE TEXT
        # --------------------------------------------------------------------

        text_lines = [
            item["text"]
            for item in ocr_results
            if item.get("text")
        ]

        full_text = "\n".join(
            text_lines
        )

        # --------------------------------------------------------------------
        # OCR CONFIDENCE
        # --------------------------------------------------------------------

        if ocr_results:

            confidence_values = [
                float(
                    item.get(
                        "confidence",
                        0.0,
                    )
                )
                for item in ocr_results
            ]

            average_confidence = (
                sum(confidence_values)
                / len(confidence_values)
            )

            status = "success"

        else:

            average_confidence = 0.0
            status = "no_text"

        # --------------------------------------------------------------------
        # CLASSIFICATION
        # --------------------------------------------------------------------

        classification = None

        clinical_entities = None

        if ocr_results:

            try:

                classification = (
                    classify_document(
                        ocr_results
                    )
                )

            except Exception as exc:

                print(
                    "WARNING: "
                    f"Document classification failed: {exc}"
                )

                classification = {
                    "document_type": "unknown",
                    "confidence": 0.0,
                    "scores": {},
                    "matched_keywords": [],
                    "error": str(exc),
                }

            # ----------------------------------------------------------------
            # CLINICAL EXTRACTION
            #
            # IMPORTANT:
            # Pass structured OCR results containing coordinates.
            # Do NOT pass full_text here.
            # ----------------------------------------------------------------

            try:

                clinical_entities = (
                    extract_clinical_entities(
                        ocr_results,
                        document_type=classification.get(
                            "document_type",
                            "unknown",
                        ),
                    )
                )

            except Exception as exc:

                print(
                    "WARNING: "
                    f"Clinical extraction failed: {exc}"
                )

                clinical_entities = {
                    "document_type": classification.get(
                        "document_type",
                        "unknown",
                    ),
                    "patient": {
                        "name": None,
                        "patient_id": None,
                        "hospital_id": None,
                        "age": None,
                        "sex": None,
                    },
                    "diagnoses": [],
                    "medications": [],
                    "laboratory_results": [],
                    "procedures": [],
                    "dates": [],
                    "source": {
                        "ocr_line_count": len(
                            ocr_results
                        ),
                        "error": str(exc),
                    },
                }

        # --------------------------------------------------------------------
        # STORE PAGE RESULT
        # --------------------------------------------------------------------

        pages.append(
            {
                "page_number": page_number,
                "source_image": image_path,
                "processed_image": enhanced_path,
                "status": status,
                "ocr_text": ocr_results,
                "text": full_text,
                "average_confidence": round(
                    average_confidence,
                    3,
                ),
                "classification": classification,
                "clinical_entities": clinical_entities,
            }
        )

    # ========================================================================
    # 4. COMBINE DOCUMENT TEXT
    # ========================================================================

    document_text_parts = []

    for page in pages:

        if page.get("text"):

            document_text_parts.append(
                page["text"]
            )

    document_text = "\n\n".join(
        document_text_parts
    )

    # ========================================================================
    # 5. DOCUMENT OCR CONFIDENCE
    # ========================================================================

    confidence_values = [
        page["average_confidence"]
        for page in pages
        if page["average_confidence"] > 0
    ]

    if confidence_values:

        document_confidence = (
            sum(confidence_values)
            / len(confidence_values)
        )

    else:

        document_confidence = 0.0

    # ========================================================================
    # 6. SUCCESSFUL PAGE COUNT
    # ========================================================================

    successful_pages = sum(
        1
        for page in pages
        if page["status"] == "success"
    )

    # ========================================================================
    # 7. DOCUMENT-LEVEL CLASSIFICATION
    # ========================================================================

    page_classifications = [
        page["classification"]
        for page in pages
        if page.get("classification")
        and page["classification"].get(
            "document_type"
        )
    ]

    document_type = "unknown"
    classification_confidence = 0.0

    if page_classifications:

        # For a multi-page document, use the most frequent
        # detected document type.

        type_counts: Dict[str, int] = {}

        for classification in page_classifications:

            detected_type = classification.get(
                "document_type",
                "unknown",
            )

            type_counts[detected_type] = (
                type_counts.get(
                    detected_type,
                    0,
                )
                + 1
            )

        document_type = max(
            type_counts,
            key=type_counts.get,
        )

        matching_confidences = [
            float(
                classification.get(
                    "confidence",
                    0.0,
                )
            )
            for classification in page_classifications
            if classification.get(
                "document_type"
            ) == document_type
        ]

        if matching_confidences:

            classification_confidence = (
                sum(matching_confidences)
                / len(matching_confidences)
            )

    # ========================================================================
    # 8. COMBINE CLINICAL ENTITIES
    # ========================================================================

    combined_entities = {
        "document_type": document_type,
        "patient": {
            "name": None,
            "patient_id": None,
            "hospital_id": None,
            "age": None,
            "sex": None,
        },
        "diagnoses": [],
        "medications": [],
        "laboratory_results": [],
        "procedures": [],
        "dates": [],
    }

    for page in pages:

        entities = page.get(
            "clinical_entities"
        )

        if not entities:
            continue

        # --------------------------------------------------------------------
        # Patient
        # --------------------------------------------------------------------

        page_patient = entities.get(
            "patient",
            {},
        )

        for key in (
            "name",
            "patient_id",
            "hospital_id",
            "age",
            "sex",
        ):

            value = page_patient.get(
                key
            )

            if (
                value is not None
                and combined_entities[
                    "patient"
                ].get(key) is None
            ):
                combined_entities[
                    "patient"
                ][key] = value

        # --------------------------------------------------------------------
        # Diagnoses
        # --------------------------------------------------------------------

        for diagnosis in entities.get(
            "diagnoses",
            [],
        ):

            if diagnosis not in combined_entities[
                "diagnoses"
            ]:

                combined_entities[
                    "diagnoses"
                ].append(
                    diagnosis
                )

        # --------------------------------------------------------------------
        # Medications
        # --------------------------------------------------------------------

        for medication in entities.get(
            "medications",
            [],
        ):

            if medication not in combined_entities[
                "medications"
            ]:

                combined_entities[
                    "medications"
                ].append(
                    medication
                )

        # --------------------------------------------------------------------
        # Laboratory results
        # --------------------------------------------------------------------

        for laboratory_result in entities.get(
            "laboratory_results",
            [],
        ):

            if laboratory_result not in combined_entities[
                "laboratory_results"
            ]:

                combined_entities[
                    "laboratory_results"
                ].append(
                    laboratory_result
                )

        # --------------------------------------------------------------------
        # Procedures
        # --------------------------------------------------------------------

        for procedure in entities.get(
            "procedures",
            [],
        ):

            if procedure not in combined_entities[
                "procedures"
            ]:

                combined_entities[
                    "procedures"
                ].append(
                    procedure
                )

        # --------------------------------------------------------------------
        # Dates
        # --------------------------------------------------------------------

        for date in entities.get(
            "dates",
            [],
        ):

            if date not in combined_entities[
                "dates"
            ]:

                combined_entities[
                    "dates"
                ].append(
                    date
                )

    # ========================================================================
    # 9. FINAL RESULT
    # ========================================================================

    result = {
        "status": (
            "success"
            if successful_pages > 0
            else "no_text"
        ),
        "source_file": str(path),
        "file_type": path.suffix.lower(),
        "page_count": len(pages),
        "successful_pages": successful_pages,
        "confidence": round(
            document_confidence,
            3,
        ),
        "text": document_text,
        "document_type": document_type,
        "classification_confidence": round(
            classification_confidence,
            3,
        ),
        "clinical_entities": combined_entities,
        "pages": pages,
    }

    return result


# ============================================================================
# SIMPLE TEXT HELPER
# ============================================================================

def extract_text(
    file_path: str,
) -> str:
    """
    Convenience helper.

    Runs the complete OCR pipeline and returns
    only the combined OCR text.
    """

    result = process_document(
        file_path
    )

    return result.get(
        "text",
        "",
    )


# ============================================================================
# CLI TEST
# ============================================================================

if __name__ == "__main__":

    print("=" * 60)
    print(
        "       MEDIKIOSK MODULE B DOCUMENT AI PIPELINE"
    )
    print("=" * 60)

    test_file = Path(
        "test_documents/medikiosk_b2_medical_test.pdf"
    )

    if not test_file.exists():

        print()
        print(
            f"Test document not found: {test_file}"
        )

    else:

        try:

            result = process_document(
                str(test_file)
            )

            print()
            print("=" * 60)
            print("             PIPELINE RESULT")
            print("=" * 60)

            print(
                f"Status: "
                f"{result['status']}"
            )

            print(
                f"Pages: "
                f"{result['page_count']}"
            )

            print(
                f"Successful pages: "
                f"{result['successful_pages']}"
            )

            print(
                f"OCR confidence: "
                f"{result['confidence']}"
            )

            print(
                f"Document type: "
                f"{result['document_type']}"
            )

            print(
                f"Classification confidence: "
                f"{result['classification_confidence']}"
            )

            print()
            print("CLINICAL ENTITIES")
            print("-" * 60)

            print(
                json.dumps(
                    result[
                        "clinical_entities"
                    ],
                    indent=2,
                    ensure_ascii=False,
                )
            )

            print()
            print("OCR TEXT")
            print("-" * 60)

            print(
                result["text"]
                or "[NO TEXT DETECTED]"
            )

            print("=" * 60)

        except Exception as exc:

            print()
            print("STATUS: FAILED")
            print(
                f"Reason: {exc}"
            )

    print("=" * 60)