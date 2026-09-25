"""
MediSetu clinical summary integration service.

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

from ai.conversation.red_flags import RedFlagDetector
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

    The original question/answer pairs are always preserved in
    `history`.

    Responses are additionally routed into their appropriate
    clinical categories so the deterministic merger can build
    separate summary sections.

    Red flags are detected again from the persisted patient answers
    so that the final clinical summary does not depend on the
    in-memory conversation manager.

    No medical meaning is inferred from the answer.
    """

    conversation: dict[str, Any] = {
        "history": [],
        "history_of_present_illness": [],
        "chief_complaints": [],
        "symptoms": [],
        "medical_history": [],
        "medications": [],
        "allergies": [],
        "investigations": [],
        "relevant_negatives": [],
        "red_flags": [],
    }

    red_flag_detector = RedFlagDetector()

    # One doctor-facing red flag per category within this session.
    # Multiple patient statements are preserved as evidence.
    red_flags_by_category: dict[str, dict[str, Any]] = {}


    for response in responses:
        question = (response.question or "").strip()
        answer = (response.answer or "").strip()

        if not answer:
            continue

        item = {
            "question": question,
            "answer": answer,
            "input_type": response.input_type,
            "language": response.language,
        }

        # ----------------------------------------------------
        # Always preserve the original interview history.
        # ----------------------------------------------------

        conversation["history"].append(item)

        # ----------------------------------------------------
        # Red-flag detection
        #
        # Re-run detection from the persisted response.
        #
        # This is intentionally independent from the in-memory
        # DialogueManager so summary generation remains reliable
        # even after the conversation process has ended.
        #
        # IMPORTANT:
        # Red flags are aggregated ONLY from the responses
        # belonging to this session.
        #
        # Multiple detections of the same red-flag category
        # are grouped together while preserving the patient's
        # different statements as evidence.
        # ----------------------------------------------------

        detected_flag = red_flag_detector.detect(answer)

        if detected_flag.detected:

            category = (
                detected_flag.flag_id
                or detected_flag.category
            )

            if category:

                priority = (
                    detected_flag.priority.value
                    if detected_flag.priority is not None
                    else None
                )

                existing = (
                    red_flags_by_category.get(category)
                )

                if existing is None:

                    existing = {
                        "flag_id": category,
                        "category": category,
                        "priority": priority,
                        "evidence": [],
                    }

                    red_flags_by_category[category] = existing

                    conversation["red_flags"].append(
                        existing
                    )

                # Preserve the actual patient statement.
                matched_text = (
                    detected_flag.matched_text
                    or answer
                )

                evidence = {
                    "text": matched_text,
                    "question": question,
                }

                # Avoid adding the exact same evidence twice.
                if evidence not in existing["evidence"]:
                    existing["evidence"].append(
                        evidence
                    )

        question_lower = question.lower()

        # ----------------------------------------------------
        # Chief Complaint
        # ----------------------------------------------------

        if question_lower == "chief complaint":
            conversation["chief_complaints"].append(item)
            continue

        # ----------------------------------------------------
        # HPI
        #
        # Only questions explicitly related to the current
        # presenting illness belong here.
        #
        # The shared opening question is also treated as HPI,
        # but NOT as a second chief complaint.
        # ----------------------------------------------------

        is_hpi = (
            "current symptoms" in question_lower
            or "present symptoms" in question_lower
            or "how long" in question_lower
            or "since when" in question_lower
            or "duration" in question_lower
            or "associated symptoms" in question_lower
            or "other symptoms" in question_lower
            or "worsen" in question_lower
            or "improve" in question_lower
            or "severity" in question_lower
            or "how severe" in question_lower
            or "pain" in question_lower
            or "symptom" in question_lower
            or "problem" in question_lower
            or "health problem today" in question_lower
            or "समस्या" in question
            or "लक्षण" in question
            or "कितने समय से" in question
            or "कब से" in question
        )

        if is_hpi:
            conversation["history_of_present_illness"].append(
                item
            )
            continue

        # ----------------------------------------------------
        # Standard history fields
        # ----------------------------------------------------

        if (
            "allergy" in question_lower
            or "allergies" in question_lower
            or "एलर्जी" in question
        ):
            conversation["allergies"].append(item)
            continue

        if (
            "medication history" in question_lower
            or "drug history" in question_lower
            or "currently taking" in question_lower
            or "taking any medication" in question_lower
            or "taking any medicines" in question_lower
        ):
            conversation["medications"].append(item)
            continue

        if (
            "investigation" in question_lower
            or "investigations" in question_lower
            or "previous test" in question_lower
            or "previous tests" in question_lower
        ):
            conversation["investigations"].append(item)
            continue

        # ----------------------------------------------------
        # AYUSH assessment
        #
        # Add AYUSH fields as top-level unknown fields.
        # The existing normalize_conversation() places these
        # under `other`.
        # ----------------------------------------------------

        ayush_field = None

        if "prakriti" in question_lower:
            ayush_field = "Prakriti"

        elif "vikriti" in question_lower:
            ayush_field = "Vikriti"

        elif "sara" in question_lower:
            ayush_field = "Sara"

        elif "samhanana" in question_lower:
            ayush_field = "Samhanana"

        elif "pramana" in question_lower:
            ayush_field = "Pramana"

        elif "satmya" in question_lower:
            ayush_field = "Satmya"

        elif "sattva" in question_lower:
            ayush_field = "Sattva"

        elif "ahara shakti" in question_lower:
            ayush_field = "Ahara Shakti"

        elif "vyayama shakti" in question_lower:
            ayush_field = "Vyayama Shakti"

        elif "age or vaya" in question_lower:
            ayush_field = "Vaya"

        elif "usual food and eating pattern" in question_lower:
            ayush_field = "Ahara - Food Pattern"

        elif "timing and regularity of meals" in question_lower:
            ayush_field = "Ahara - Meal Timing"

        elif "usual appetite" in question_lower:
            ayush_field = "Ahara - Appetite"

        elif (
            "foods that the person does not tolerate"
            in question_lower
        ):
            ayush_field = "Ahara - Food Tolerance"

        elif (
            "dietary preferences" in question_lower
            or "dietary restrictions" in question_lower
        ):
            ayush_field = "Ahara - Dietary Preferences"

        elif "sleep pattern" in question_lower:
            ayush_field = "Vihara - Sleep"

        elif "daily physical activity" in question_lower:
            ayush_field = "Vihara - Physical Activity"

        elif (
            "exercise or physical activity routine"
            in question_lower
        ):
            ayush_field = "Vihara - Exercise"

        elif "usual daily routine" in question_lower:
            ayush_field = "Vihara - Daily Routine"

        elif (
            "stress, workload" in question_lower
            or "routine-related factors" in question_lower
        ):
            ayush_field = "Vihara - Stress / Workload"

        if ayush_field:
            conversation.setdefault(
                ayush_field,
                [],
            ).append(
                {
                    "field": ayush_field,
                    "question": question,
                    "answer": answer,
                    "input_type": response.input_type,
                    "language": response.language,
                }
            )
            continue

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
    - red flags are detected from persisted responses
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