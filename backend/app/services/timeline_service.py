import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.document import Document


def _parse_date(value: Any) -> datetime | None:
    """
    Convert supported date strings into datetime objects.

    The extractor may return dates in different formats,
    so we try the common formats used by medical documents.
    """

    if not value:
        return None

    if isinstance(value, datetime):
        return value

    value = str(value).strip()

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
        "%B %d, %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%d %b %Y",
    ]

    for date_format in formats:
        try:
            return datetime.strptime(
                value,
                date_format
            )
        except ValueError:
            continue

    return None


def _extract_date_value(date_item: Any) -> str | None:
    """
    Handle the different possible date representations
    returned by the clinical extractor.
    """

    if isinstance(date_item, str):
        return date_item

    if isinstance(date_item, dict):

        for key in (
            "date",
            "value",
            "document_date",
            "admission_date",
            "discharge_date",
        ):
            value = date_item.get(key)

            if value:
                return str(value)

    return None


def _load_extracted_data(
    document: Document,
) -> dict:
    """
    Safely parse the JSON stored in Document.extracted_data.
    """

    if not document.extracted_data:
        return {}

    try:
        data = json.loads(
            document.extracted_data
        )

        if isinstance(data, dict):
            return data

    except (json.JSONDecodeError, TypeError):
        pass

    return {}


def _build_timeline_event(
    document: Document,
    extracted_data: dict,
    event_date: str | None,
) -> dict:
    """
    Build one normalized medical timeline event.
    """

    clinical_entities = extracted_data.get(
        "clinical_entities",
        {}
    )

    if not isinstance(clinical_entities, dict):
        clinical_entities = {}

    return {
        "date": event_date,
        "document_id": document.id,
        "filename": document.filename,
        "document_type": (
            document.document_type
        ),
        "diagnoses": clinical_entities.get(
            "diagnoses",
            []
        ),
        "medications": clinical_entities.get(
            "medications",
            []
        ),
        "laboratory_results": clinical_entities.get(
            "laboratory_results",
            []
        ),
        "procedures": clinical_entities.get(
            "procedures",
            []
        ),
    }


def build_medical_timeline(
    session_id: int,
    db: Session,
) -> dict:
    """
    Build a chronological medical timeline for
    all successfully processed documents belonging
    to a session.

    Timeline dates come from dates extracted from
    the medical documents.

    Upload/DB creation time is NOT used as the
    medical event date.
    """

    documents = (
        db.query(Document)
        .filter(
            Document.session_id == session_id,
            Document.processing_status == "completed",
        )
        .all()
    )

    events: list[dict] = []

    for document in documents:

        extracted_data = _load_extracted_data(
            document
        )

        clinical_entities = extracted_data.get(
            "clinical_entities",
            {}
        )

        if not isinstance(clinical_entities, dict):
            clinical_entities = {}

        dates = clinical_entities.get(
            "dates",
            []
        )

        # ----------------------------------------------------
        # Documents with extracted clinical dates
        # ----------------------------------------------------

        if isinstance(dates, list) and dates:

            valid_date_found = False

            for date_item in dates:

                date_value = _extract_date_value(
                    date_item
                )

                parsed_date = _parse_date(
                    date_value
                )

                if parsed_date is None:
                    continue

                valid_date_found = True

                events.append(
                    {
                        **_build_timeline_event(
                            document=document,
                            extracted_data=extracted_data,
                            event_date=date_value,
                        ),
                        "_sort_date": parsed_date,
                    }
                )

            # ------------------------------------------------
            # If dates existed but none were parseable,
            # don't silently invent a medical date.
            # ------------------------------------------------

            if valid_date_found:
                continue

        # ----------------------------------------------------
        # No usable clinical date
        #
        # Keep the document in the timeline, but explicitly
        # mark its date as unknown.
        # ----------------------------------------------------

        events.append(
            {
                **_build_timeline_event(
                    document=document,
                    extracted_data=extracted_data,
                    event_date=None,
                ),
                "_sort_date": datetime.max,
            }
        )

    # --------------------------------------------------------
    # Sort chronologically.
    #
    # Unknown dates go to the end.
    # --------------------------------------------------------

    events.sort(
        key=lambda event: event["_sort_date"]
    )

    # Remove internal sorting field.
    for event in events:
        event.pop(
            "_sort_date",
            None
        )

    return {
        "session_id": session_id,
        "document_count": len(documents),
        "event_count": len(events),
        "events": events,
    }