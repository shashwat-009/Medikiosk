import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.session import Session as SessionModel
from app.models.summary import Summary
from app.schemas.summary import (
    SummaryCreate,
    SummaryResponse,
    SummaryUpdate,
)
from app.services.summary_service import (
    generate_deterministic_summary,
)


router = APIRouter(
    prefix="/summaries",
    tags=["Summaries"],
)


@router.post(
    "/session/{session_id}/generate",
    response_model=SummaryResponse,
)
def generate_summary(
    session_id: int,
    db: Session = Depends(get_db),
):
    """
    Generate and persist the deterministic clinical summary
    for a patient session.

    This is the pre-Qwen Module C integration point.
    """

    session = (
        db.query(SessionModel)
        .filter(SessionModel.id == session_id)
        .first()
    )

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    try:
        result = generate_deterministic_summary(
            session_id=session_id,
            db=db,
        )

        case_sheet = result["case_sheet"]

        # ----------------------------------------------------
        # Convert the ClinicalCaseSheet object into a
        # JSON-serializable dictionary.
        #
        # Pydantic models expose model_dump().
        # ----------------------------------------------------

        if hasattr(case_sheet, "model_dump"):
            content = case_sheet.model_dump(
                mode="json"
            )

        elif hasattr(case_sheet, "dict"):
            # Compatibility with older Pydantic versions.
            content = case_sheet.dict()

        else:
            raise TypeError(
                "ClinicalCaseSheet is not a supported "
                "serializable model."
            )

        serialized_content = json.dumps(
            content,
            ensure_ascii=False,
        )

        # ----------------------------------------------------
        # Create or update the session summary
        # ----------------------------------------------------

        summary = (
            db.query(Summary)
            .filter(
                Summary.session_id == session_id
            )
            .first()
        )

        if summary is None:

            summary = Summary(
                session_id=session_id,
                content=serialized_content,
                status="draft",
            )

            db.add(summary)

        else:

            summary.content = serialized_content
            summary.status = "draft"

        db.commit()
        db.refresh(summary)

        return summary

    except ValueError as exc:

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                f"Summary generation failed: {exc}"
            ),
        ) from exc


# ============================================================
# CREATE SUMMARY
# ============================================================

@router.post(
    "/",
    response_model=SummaryResponse,
)
def create_summary(
    summary_data: SummaryCreate,
    db: Session = Depends(get_db),
):

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id
            == summary_data.session_id
        )
        .first()
    )

    if session is None:

        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    new_summary = Summary(
        session_id=summary_data.session_id,
        content=summary_data.content,
        status="draft",
    )

    db.add(new_summary)
    db.commit()
    db.refresh(new_summary)

    return new_summary


# ============================================================
# GET ALL SUMMARIES
# ============================================================

@router.get(
    "/",
    response_model=list[SummaryResponse],
)
def get_summaries(
    db: Session = Depends(get_db),
):

    return db.query(Summary).all()


# ============================================================
# GET ONE SUMMARY
# ============================================================

@router.get(
    "/{summary_id}",
    response_model=SummaryResponse,
)
def get_summary(
    summary_id: int,
    db: Session = Depends(get_db),
):

    summary = (
        db.query(Summary)
        .filter(
            Summary.id == summary_id
        )
        .first()
    )

    if summary is None:

        raise HTTPException(
            status_code=404,
            detail="Summary not found",
        )

    return summary


# ============================================================
# UPDATE SUMMARY
# ============================================================

@router.put(
    "/{summary_id}",
    response_model=SummaryResponse,
)
def update_summary(
    summary_id: int,
    summary_data: SummaryUpdate,
    db: Session = Depends(get_db),
):

    summary = (
        db.query(Summary)
        .filter(
            Summary.id == summary_id
        )
        .first()
    )

    if summary is None:

        raise HTTPException(
            status_code=404,
            detail="Summary not found",
        )

    if summary_data.content is not None:

        summary.content = (
            summary_data.content
        )

    if summary_data.status is not None:

        if summary_data.status not in [
            "draft",
            "accepted",
            "rejected",
        ]:

            raise HTTPException(
                status_code=400,
                detail="Invalid summary status",
            )

        summary.status = (
            summary_data.status
        )

    db.commit()
    db.refresh(summary)

    return summary


# ============================================================
# DELETE SUMMARY
# ============================================================

@router.delete(
    "/{summary_id}",
)
def delete_summary(
    summary_id: int,
    db: Session = Depends(get_db),
):

    summary = (
        db.query(Summary)
        .filter(
            Summary.id == summary_id
        )
        .first()
    )

    if summary is None:

        raise HTTPException(
            status_code=404,
            detail="Summary not found",
        )

    db.delete(summary)
    db.commit()

    return {
        "message": "Summary deleted successfully",
    }