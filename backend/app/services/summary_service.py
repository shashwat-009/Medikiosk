"""
MediKiosk clinical summary integration service.

Builds the deterministic clinical summary from:
- patient interview responses
- processed OCR documents
- medical timeline

This layer does NOT use an LLM.

The deterministic result is the trusted structured input
for the later physician-readable/Qwen generation layer.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ai.summary.case_sheet import build_case_sheet
from ai.summary.merger import merge_sources
from ai.summary.schemas import build_summary_input

from app.models.document import Document
from app.models.response import Response
from app.models.session import Session as SessionModel
from app.services.timeline_service import build_medical_timeline


def _build_conversation_data(
    responses: list[Response],
) -> dict[str, Any]:
    """
    Convert stored interview responses into the generic conversation
    structure expected by the summary adapter.

    We intentionally preserve the original question/answer pairs
    instead of trying to infer medical meaning here.
    """

    conversation: dict[str, Any] = {
        "history": [],
    }

    for response in responses:
        question = (response.question or "").strip()
        answer = (response.answer or "").strip()

        if not answer:
            continue

        conversation["history"].append(
            {
                "question": question,
                "answer": answer,
                "input_type": response.input_type,
                "language": response.language,
            }
        )

    return conversation


def _load_extracted_data(
    document: Document,
) -> dict[str, Any]:
    """
    Safely load the structured OCR payload stored in the documents table.
    """

    if not document.extracted_data:
        return {}

    try:
        data = json.loads(
            document.extracted_data
        )
    except (TypeError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


def _build_ocr_data(
    documents: list[Document],
) -> dict[str, Any]:
    """
    Convert completed OCR documents into the structure expected by
    the summary normalization adapter.

    Clinical entities are flattened so the deterministic merger can
    preserve them with OCR provenance.
    """

    ocr: dict[str, Any] = {
        "clinical_entities": [],
        "labs": [],
        "medications": [],
        "allergies": [],
        "discharge_findings": [],
        "timeline": [],
    }

    for document in documents:

        if document.processing_status != "completed":
            continue

        extracted = _load_extracted_data(
            document
        )

        clinical_entities = extracted.get(
            "clinical_entities",
            {}
        )

        if isinstance(
            clinical_entities,
            dict
        ):

            for key, values in clinical_entities.items():

                if values in (
                    None,
                    "",
                    [],
                    {},
                ):
                    continue

                if isinstance(
                    values,
                    list
                ):

                    for value in values:

                        ocr[
                            "clinical_entities"
                        ].append(
                            {
                                "field": key,
                                "value": value,
                                "document_id": document.id,
                                "filename": document.filename,
                            }
                        )

                else:

                    ocr[
                        "clinical_entities"
                    ].append(
                        {
                            "field": key,
                            "value": values,
                            "document_id": document.id,
                            "filename": document.filename,
                        }
                    )

        elif isinstance(
            clinical_entities,
            list
        ):

            ocr[
                "clinical_entities"
            ].extend(
                clinical_entities
            )

        # Preserve extracted structured fields.

        for key, target in (
            (
                "medications",
                "medications",
            ),
            (
                "allergies",
                "allergies",
            ),
            (
                "labs",
                "labs",
            ),
            (
                "laboratory_results",
                "labs",
            ),
            (
                "discharge_findings",
                "discharge_findings",
            ),
            (
                "procedures",
                "discharge_findings",
            ),
        ):

            values = extracted.get(key)

            if values in (
                None,
                "",
                [],
                {},
            ):
                continue

            if isinstance(
                values,
                list
            ):

                ocr[target].extend(
                    values
                )

            else:

                ocr[target].append(
                    values
                )

        dates = extracted.get(
            "dates"
        )

        if dates:

            if isinstance(
                dates,
                list
            ):

                ocr[
                    "timeline"
                ].extend(
                    dates
                )

            else:

                ocr[
                    "timeline"
                ].append(
                    dates
                )

    return ocr


def generate_deterministic_summary(
    session_id: int,
    db: Session,
):
    """
    Generate the deterministic clinical case sheet for a session.

    Returns a dictionary containing the ClinicalCaseSheet under
    the `case_sheet` key because the existing summary API expects
    that integration contract.

    Requirements:
    - session must exist
    - interview responses are loaded from the session
    - only completed OCR documents are included
    - medical timeline is included
    - no LLM/network call is made
    """

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id
        )
        .first()
    )

    if session is None:
        raise ValueError(
            f"Session {session_id} not found."
        )

    responses = (
        db.query(Response)
        .filter(
            Response.session_id == session_id
        )
        .order_by(
            Response.id.asc()
        )
        .all()
    )

    documents = (
        db.query(Document)
        .filter(
            Document.session_id == session_id
        )
        .order_by(
            Document.id.asc()
        )
        .all()
    )

    completed_documents = [
        document
        for document in documents
        if document.processing_status
        == "completed"
    ]

    conversation_data = (
        _build_conversation_data(
            responses
        )
    )

    ocr_data = _build_ocr_data(
        completed_documents
    )

    timeline_result = (
        build_medical_timeline(
            session_id=session_id,
            db=db,
        )
    )

    timeline_events = (
        timeline_result.get(
            "events",
            []
        )
    )

    summary_input = build_summary_input(
        conversation=conversation_data,
        ocr=ocr_data,
        timeline=timeline_events,
    )

    summary_result = merge_sources(
        summary_input
    )

    case_sheet = build_case_sheet(
        summary_result
    )

    return {
        "case_sheet": case_sheet
    }