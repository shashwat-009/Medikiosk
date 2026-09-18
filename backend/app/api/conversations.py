from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.sessions import get_patient_session
from app.db.database import get_db
from app.models.session import Session as SessionModel
from app.models.response import Response
from app.services.conversation_state import (
    deserialize_dialogue_state,
    serialize_dialogue_state,
)

from ai.conversation.ayush_mode import AyushMode
from ai.conversation.dialogue_manager import DialogueManager
from ai.conversation.question_bank import QuestionLanguage


router = APIRouter(
    prefix="/conversation",
    tags=["Conversation"],
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Persistent conversation state helpers
# ---------------------------------------------------------------------------

def build_manager_from_session(session: SessionModel) -> DialogueManager:
    if not session.conversation_state:
        raise HTTPException(
            status_code=404,
            detail=(
                "No active conversation found for this session. "
                "Start the conversation first."
            ),
        )

    try:
        state = deserialize_dialogue_state(session.conversation_state)
        language = QuestionLanguage(session.language or "en")
    except (ValueError, TypeError, KeyError) as exc:
        logger.exception(
            "Invalid persisted conversation state for session %s",
            session.id,
        )
        raise HTTPException(
            status_code=500,
            detail="Stored conversation state is invalid.",
        ) from exc

    ayush_mode = (
        AyushMode()
        if (session.mode or "allopathy") == "ayush"
        else None
    )

    return DialogueManager(
        state,
        language=language,
        ayush_mode=ayush_mode,
    )


def persist_conversation_state(
    session: SessionModel,
    manager: DialogueManager,
    db: Session,
) -> None:
    session.conversation_state = serialize_dialogue_state(manager.state)
    db.add(session)
    db.commit()


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ConversationStartRequest(BaseModel):
    session_id: int
    complaint: str
    language: str = "en"
    mode: str = "allopathy"


class ConversationAnswerRequest(BaseModel):
    session_id: int
    field_id: str
    answer: Any
    question_id: str | None = None
    input_type: str = "touch"


# ---------------------------------------------------------------------------
# Patient session authentication
# ---------------------------------------------------------------------------


def require_conversation_session(
    session_id: int,
    patient_token: str | None,
    db: Session,
):
    """
    Authenticate the patient before allowing access to the
    conversation belonging to a session.

    The token must belong to the requested session and the
    session must still be active.
    """

    if not patient_token:
        raise HTTPException(
            status_code=401,
            detail="Patient session credential required",
        )

    return get_patient_session(
        session_id=session_id,
        patient_token=patient_token,
        db=db,
    )


# ---------------------------------------------------------------------------
# Complaint resolver
# ---------------------------------------------------------------------------


_COMPLAINT_KEYWORDS = {
    "fever": (
        "fever",
        "feverish",
        "temperature",
        "high temperature",
        "pyrexia",
        "bukhar",
        "bukhaar",
        "बुखार",
        "ज्वर",
        "জ্বর",
        "বুকার",
        "ताप",
        "अंगात ताप",
        "body heat",
    ),
    "chest_pain": (
        "chest pain",
        "pain in chest",
        "chest discomfort",
        "chest pressure",
        "chest tight",
        "seene mein dard",
        "seene me dard",
        "seene ka dard",
        "seena dard",
        "seena me dard",
        "chhati mein dard",
        "chhati me dard",
        "heart pain",
        "heart ache",
        "dil me dard",
        "dil mein dard",
        "angina",
        "सीने में दर्द",
        "सीने का दर्द",
        "छाती में दर्द",
        "বুকে ব্যথা",
        "বুকে ব্যাথা",
        "বুকের ব্যথা",
        "छातीत दुखणे",
        "छातीत दुखत",
        "छाती दुखणे",
    ),
    "cough": (
        "cough",
        "coughing",
        "dry cough",
        "wet cough",
        "phlegm",
        "balgam",
        "kaph",
        "khansi",
        "khaansi",
        "khasi",
        "खांसी",
        "खाँसी",
        "काশি",
        "খোকলা",
    ),
    "headache": (
        "headache",
        "head ache",
        "head pain",
        "migraine",
        "sir dard",
        "sar dard",
        "sir me dard",
        "sir mein dard",
        "sar me dard",
        "sar mein dard",
        "sir ka dard",
        "matha dard",
        "सिर दर्द",
        "सर दर्द",
        "सिर में दर्द",
        "सर में दर्द",
        "माथাব্যথা",
        "মাথা ব্যথা",
        "डोकेदुखी",
        "डोके दुखणे",
    ),
    "abdominal_pain": (
        "abdominal pain",
        "abdomen pain",
        "abdominal",
        "stomach pain",
        "stomach ache",
        "stomach",
        "belly pain",
        "belly ache",
        "tummy ache",
        "tummy pain",
        "pet pain",
        "pet dard",
        "pet me dard",
        "pet mein dard",
        "pet ka dard",
        "gastric pain",
        "gas pain",
        "cramps",
        "पेट दर्द",
        "पेट में दर्द",
        "পেট ব্যথা",
        "পেটে ব্যথা",
        "পেটের ব্যথা",
        "पोटदुखी",
        "पोटात दुखणे",
        "पोटात दुखत",
    ),
}


def resolve_complaint(
    text: str,
) -> str | None:
    """
    Resolve a patient's chief complaint to a supported
    complaint category.

    This is deterministic and does not diagnose the patient.
    """

    normalized = text.strip().lower()

    if not normalized:
        return None

    supported = {
        "fever",
        "chest_pain",
        "cough",
        "headache",
        "abdominal_pain",
    }

    if normalized in supported:
        return normalized

    for complaint, keywords in _COMPLAINT_KEYWORDS.items():
        if any(
            keyword in normalized
            for keyword in keywords
        ):
            return complaint

    return None


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_question(
    question,
    language: str = "en",
):
    """
    Convert an internal question object into the API response format.

    Allopathy questions already contain their configured language.

    AYUSH questions contain translations and use text_for(language)
    so the patient's selected language is preserved.
    """

    if question is None:
        return None

    # Standard Allopathy question
    if hasattr(question, "question_id"):
        return {
            "id": question.question_id,
            "field_id": question.field_id,
            "question": question.text,
            "language": question.language.value,
            "answer_type": question.answer_type,
            "options": list(question.options),
            "priority": question.priority,
        }

    # AYUSH question
    return {
        "id": question.id,
        "field_id": question.field_id,
        "question": question.text_for(language),
        "language": language,
        "answer_type": "text",
        "options": [],
        "priority": None,
    }


def serialize_result(
    result,
    language: str = "en",
):
    """
    Serialize a conversation result while preserving
    the active language.
    """

    return {
        "next_question": serialize_question(
            result.next_question,
            language,
        ),
        "completed": result.completed,
        "red_flag": (
            {
                "detected": result.red_flag.detected,
                "category": result.red_flag.category,
                "matched_pattern": (
                    result.red_flag.matched_pattern
                ),
                "flag_id": result.red_flag.flag_id,
                "priority": (
                    result.red_flag.priority.value
                    if result.red_flag.priority is not None
                    else None
                ),
                "matched_fields": list(
                    result.red_flag.matched_fields
                ),
                "matched_text": result.red_flag.matched_text,
                "explanation": result.red_flag.explanation,
            }
            if result.red_flag is not None
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Start conversation
# ---------------------------------------------------------------------------


@router.post("/start")
def start_conversation(
    request: ConversationStartRequest,
    x_patient_session_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    db: Session = Depends(get_db),
):
    """
    Start a clinical history-taking conversation.

    Patient authentication is required.

    The supplied session_id must belong to the authenticated
    patient session.
    """

    # ---------------------------------------------------------------
    # Authenticate patient session
    # ---------------------------------------------------------------

    session = require_conversation_session(
        session_id=request.session_id,
        patient_token=x_patient_session_token,
        db=db,
    )

    # ---------------------------------------------------------------
    # Validate mode
    # ---------------------------------------------------------------

    normalized_mode = request.mode.strip().lower()

    if normalized_mode not in {
        "allopathy",
        "ayush",
    }:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported conversation mode. "
                "Use 'allopathy' or 'ayush'."
            ),
        )

    # ---------------------------------------------------------------
    # Resolve chief complaint
    # ---------------------------------------------------------------

    complaint = resolve_complaint(
        request.complaint
    )

    logger.info(
        "Starting conversation for session %s with complaint: %r (resolved to: %s)",
        request.session_id,
        request.complaint,
        complaint,
    )

    if complaint is None:
        logger.warning(
            "Chief complaint %r could not be mapped to supported complaints",
            request.complaint,
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "Chief complaint could not be mapped to a supported "
                "complaint. Supported complaints are: fever, chest pain, "
                "cough, headache, and abdominal pain."
            ),
        )

    # ---------------------------------------------------------------
    # Validate language
    # ---------------------------------------------------------------

    try:
        language = QuestionLanguage(
            request.language
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported conversation language: "
                f"{request.language}"
            ),
        ) from exc

    # ---------------------------------------------------------------
    # Create AYUSH mode when requested
    # ---------------------------------------------------------------

    ayush_mode = (
        AyushMode()
        if normalized_mode == "ayush"
        else None
    )

    # ---------------------------------------------------------------
    # Create dialogue manager
    # ---------------------------------------------------------------

    manager = DialogueManager.create(
        complaint,
        language=language,
        ayush_mode=ayush_mode,
    )

    # ---------------------------------------------------------------
    # Start interview
    # ---------------------------------------------------------------

    question = manager.start()

    session.complaint = complaint
    session.language = language.value
    session.mode = normalized_mode
    session.conversation_state = serialize_dialogue_state(manager.state)
    db.add(session)
    db.commit()

    return {
        "session_id": request.session_id,
        "complaint": complaint,
        "mode": normalized_mode,
        "question": serialize_question(
            question,
            language.value,
        ),
        "completed": question is None,
    }


# ---------------------------------------------------------------------------
# Process answer
# ---------------------------------------------------------------------------


@router.post("/answer")
def answer_conversation(
    request: ConversationAnswerRequest,
    x_patient_session_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    db: Session = Depends(get_db),
):
    """
    Process a patient's answer.

    The patient must authenticate against the same session
    whose conversation is being modified.
    """

    # ---------------------------------------------------------------
    # Authenticate patient session
    # ---------------------------------------------------------------

    session = require_conversation_session(
        session_id=request.session_id,
        patient_token=x_patient_session_token,
        db=db,
    )

    # ---------------------------------------------------------------
    # Load conversation state
    # ---------------------------------------------------------------

    manager = build_manager_from_session(session)

    # ---------------------------------------------------------------
    # Validate answer
    # ---------------------------------------------------------------

    if request.answer is None:
        raise HTTPException(
            status_code=400,
            detail="Answer cannot be empty.",
        )

    if (
        isinstance(request.answer, str)
        and not request.answer.strip()
    ):
        raise HTTPException(
            status_code=400,
            detail="Answer cannot be empty.",
        )

    # ---------------------------------------------------------------
    # Validate input type
    # ---------------------------------------------------------------

    input_type = (
        request.input_type
        .strip()
        .lower()
    )

    if input_type not in {
        "voice",
        "touch",
    }:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid input_type. "
                "Use 'voice' or 'touch'."
            ),
        )

    # ---------------------------------------------------------------
    # Process answer
    # ---------------------------------------------------------------

    try:

        if input_type == "voice":

            result = manager.process_voice_answer(
                field_id=request.field_id,
                transcript=str(
                    request.answer
                ),
                question_id=request.question_id,
            )

        else:

            result = manager.process_text_answer(
                field_id=request.field_id,
                text=str(
                    request.answer
                ),
                question_id=request.question_id,
            )

    except (
        ValueError,
        TypeError,
    ) as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    # Persist both the updated conversation state and the answer
    # history in the same database transaction.
    session.conversation_state = serialize_dialogue_state(
        manager.state
    )
    db.add(session)

    db.add(
        Response(
            session_id=session.id,
            question=(
                request.question_id
                or request.field_id
            ),
            answer=str(request.answer),
            input_type=input_type,
            language=manager.language.value,
        )
    )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return serialize_result(
        result,
        manager.language.value,
    )


# ---------------------------------------------------------------------------
# Get current / next question
# ---------------------------------------------------------------------------


@router.get("/{session_id}/next")
def get_next_question(
    session_id: int,
    x_patient_session_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    db: Session = Depends(get_db),
):
    """
    Return the next question for the authenticated patient
    session.
    """

    # ---------------------------------------------------------------
    # Authenticate patient session
    # ---------------------------------------------------------------

    session = require_conversation_session(
        session_id=session_id,
        patient_token=x_patient_session_token,
        db=db,
    )

    # ---------------------------------------------------------------
    # Load conversation state
    # ---------------------------------------------------------------

    manager = build_manager_from_session(session)

    question = manager.get_next_question()

    # get_next_question() updates the current-question state,
    # so persist it before returning.
    persist_conversation_state(
        session,
        manager,
        db,
    )

    return {
        "question": serialize_question(
            question,
            manager.language.value,
        ),
        "completed": question is None,
    }