"""
MediSetu — extensive backend API test suite.

Place this file at:
    backend/tests/test_api.py

Run from the backend directory:
    pytest -q

Recommended first run:
    pytest -q -x

IMPORTANT:
- This suite is designed for the current MediSetu API architecture.
- It uses FastAPI TestClient, so no browser/Swagger clicking is needed.
- External AI/storage services are mocked where possible.
- The tests create dedicated test records with unique Aadhaar values.
- Use a dedicated test database for repeatable/CI runs. Do NOT point a
  destructive test suite at production data.

Install if needed:
    pip install pytest httpx
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# Import-path bootstrap
# ---------------------------------------------------------------------------
# Project layout:
#
#   medisetu/
#   ├── ai/
#   └── backend/
#       ├── app/
#       └── tests/
#
# The API imports both `app.*` and the sibling top-level `ai.*` package.
# Pytest does not reliably add both directories to sys.path on Windows,
# especially when invoked from different working directories. Add both
# explicitly before importing the FastAPI application.
TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTS_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for import_root in (BACKEND_DIR, PROJECT_ROOT):
    import_root_str = str(import_root)
    if import_root_str not in sys.path:
        sys.path.insert(0, import_root_str)

import pytest
from fastapi.testclient import TestClient

from app.main import app




# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = str(time.time_ns())[-10:]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def patient_auth(token: str) -> dict[str, str]:
    return {"X-Patient-Session-Token": token}


def assert_status(response, *expected: int) -> None:
    assert response.status_code in expected, (
        f"Expected {expected}, got {response.status_code}: {response.text}"
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Test identities
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_values():
    admin_username = os.getenv("ADMIN_USERNAME")
    admin_password = os.getenv("ADMIN_PASSWORD")

    assert admin_username, "ADMIN_USERNAME is not configured"
    assert admin_password, "ADMIN_PASSWORD is not configured"

    return {
        "admin_username": admin_username,
        "admin_password": admin_password,
        "doctor1_name": f"TEST Physician One {RUN_ID}",
        "doctor1_password": "MediSetu-Test#123",
        "doctor2_name": f"TEST Physician Two {RUN_ID}",
        "doctor2_password": "MediSetu-Test#456",
        "aadhaar1": f"91{RUN_ID}1234"[-12:],
        "aadhaar2": f"92{RUN_ID}5678"[-12:],
    }


# ---------------------------------------------------------------------------
# Authentication fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def admin_token(client, test_values):
    response = client.post(
        "/auth/admin/login",
        data={
            "username": test_values["admin_username"],
            "password": test_values["admin_password"],
        },
    )

    assert_status(response, 200)

    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["role"] == "admin"

    return body["access_token"]


@pytest.fixture(scope="module")
def doctors(client, admin_token, test_values):
    headers = auth(admin_token)

    first = client.post(
        "/doctors/",
        headers=headers,
        json={
            "name": test_values["doctor1_name"],
            "password": test_values["doctor1_password"],
            "specialization": "General Medicine",
            "department": "General Medicine",
        },
    )
    assert_status(first, 200)

    second = client.post(
        "/doctors/",
        headers=headers,
        json={
            "name": test_values["doctor2_name"],
            "password": test_values["doctor2_password"],
            "specialization": "AYUSH",
            "department": "AYUSH",
        },
    )
    assert_status(second, 200)

    doctor1 = first.json()
    doctor2 = second.json()

    assert doctor1["role"] == "physician"
    assert doctor1["is_active"] is True
    assert doctor2["role"] == "physician"
    assert doctor2["is_active"] is True

    return {"one": doctor1, "two": doctor2}


@pytest.fixture(scope="module")
def physician_tokens(client, doctors, test_values):
    tokens = {}

    for key, password_key in (
        ("one", "doctor1_password"),
        ("two", "doctor2_password"),
    ):
        doctor_id = doctors[key]["id"]

        response = client.post(
            "/auth/login",
            data={
                "username": str(doctor_id),
                "password": test_values[password_key],
            },
        )

        assert_status(response, 200)

        body = response.json()
        assert body["access_token"]
        assert body["token_type"] == "bearer"
        assert body["role"] == "physician"

        tokens[key] = body["access_token"]

    return tokens


# ---------------------------------------------------------------------------
# Patient/session fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def patient(client, test_values):
    response = client.post(
        "/patients/",
        json={
            "name": f"TEST Patient One {RUN_ID}",
            "age": 35,
            "gender": "Other",
            "aadhaar": test_values["aadhaar1"],
        },
    )

    assert_status(response, 200)
    body = response.json()

    assert body["id"]
    assert body["name"]
    assert body["age"] == 35
    assert body["aadhaar"] == test_values["aadhaar1"]

    return body


@pytest.fixture(scope="module")
def patient2(client, test_values):
    response = client.post(
        "/patients/",
        json={
            "name": f"TEST Patient Two {RUN_ID}",
            "age": 42,
            "gender": "Other",
            "aadhaar": test_values["aadhaar2"],
        },
    )

    assert_status(response, 200)
    return response.json()


@pytest.fixture(scope="module")
def session(client, patient, doctors):
    response = client.post(
        "/sessions/",
        json={
            "patient_id": patient["id"],
            "doctor_id": doctors["one"]["id"],
        },
    )

    assert_status(response, 200)

    body = response.json()

    assert body["id"]
    assert body["patient_id"] == patient["id"]
    assert body["doctor_id"] == doctors["one"]["id"]
    assert body["status"] == "active"
    assert body["patient_token"]
    assert body["patient_token_expires_at"]

    # The raw patient credential should be returned to the kiosk but is not
    # expected to be part of the normal SessionResponse schema.
    return body


@pytest.fixture(scope="module")
def session2(client, patient2, doctors):
    response = client.post(
        "/sessions/",
        json={
            "patient_id": patient2["id"],
            "doctor_id": doctors["two"]["id"],
        },
    )

    assert_status(response, 200)
    body = response.json()

    assert body["patient_token"]
    return body


@pytest.fixture(scope="module")
def assignment_session(client, patient2, doctors):
    response = client.post(
        "/sessions/",
        json={
            "patient_id": patient2["id"],
            "doctor_id": doctors["one"]["id"],
        },
    )

    assert_status(response, 200)
    body = response.json()
    assert body["patient_token"]
    return body


@pytest.fixture(scope="module")
def consent(client, session):
    response = client.post(
        "/consents/",
        headers=patient_auth(session["patient_token"]),
        json={
            "session_id": session["id"],
            "capture_consent": True,
            "sharing_consent": True,
            "language": "en",
        },
    )

    assert_status(response, 200)
    body = response.json()

    assert body["session_id"] == session["id"]
    assert body["capture_consent"] is True
    assert body["sharing_consent"] is True
    assert body["revoked"] is False

    return body


# ===========================================================================
# 1. HEALTH / ROOT
# ===========================================================================

def test_root_endpoint(client):
    response = client.get("/")
    assert_status(response, 200)


def test_health_endpoint(client):
    response = client.get("/health")
    assert_status(response, 200)
    assert response.json().get("status") == "healthy"


# ===========================================================================
# 2. AUTHENTICATION
# ===========================================================================

def test_admin_login(client, test_values):
    response = client.post(
        "/auth/admin/login",
        data={
            "username": test_values["admin_username"],
            "password": test_values["admin_password"],
        },
    )

    assert_status(response, 200)

    body = response.json()
    assert body["access_token"]
    assert body["role"] == "admin"


def test_admin_wrong_password(client, test_values):
    response = client.post(
        "/auth/admin/login",
        data={
            "username": test_values["admin_username"],
            "password": "definitely-wrong",
        },
    )

    assert_status(response, 401)


def test_physician_login(client, doctors, test_values):
    response = client.post(
        "/auth/login",
        data={
            "username": str(doctors["one"]["id"]),
            "password": test_values["doctor1_password"],
        },
    )

    assert_status(response, 200)

    body = response.json()
    assert body["access_token"]
    assert body["role"] == "physician"
    assert body["token_type"] == "bearer"


def test_physician_wrong_password(client, doctors):
    response = client.post(
        "/auth/login",
        data={
            "username": str(doctors["one"]["id"]),
            "password": "wrong-password",
        },
    )

    assert_status(response, 401)


def test_physician_invalid_id(client):
    response = client.post(
        "/auth/login",
        data={
            "username": "not-an-id",
            "password": "anything",
        },
    )

    assert_status(response, 401)


def test_invalid_bearer_token(client):
    response = client.get(
        "/sessions/",
        headers=auth("not-a-real-jwt"),
    )

    assert_status(response, 401, 403)


def test_missing_auth_on_protected_session_list(client):
    response = client.get("/sessions/")
    assert_status(response, 401)


# ===========================================================================
# 3. DOCTOR MANAGEMENT
# ===========================================================================

def test_admin_can_list_doctors(client, admin_token, doctors):
    response = client.get(
        "/doctors/",
        headers=auth(admin_token),
    )

    assert_status(response, 200)

    ids = {doctor["id"] for doctor in response.json()}
    assert doctors["one"]["id"] in ids
    assert doctors["two"]["id"] in ids


def test_physician_cannot_list_all_doctors(client, physician_tokens):
    response = client.get(
        "/doctors/",
        headers=auth(physician_tokens["one"]),
    )

    assert_status(response, 403)


def test_unauthenticated_cannot_list_doctors(client):
    response = client.get("/doctors/")
    assert_status(response, 401, 403)


def test_physician_can_read_own_profile(client, doctors, physician_tokens):
    response = client.get(
        f"/doctors/{doctors['one']['id']}",
        headers=auth(physician_tokens["one"]),
    )

    assert_status(response, 200)
    assert response.json()["id"] == doctors["one"]["id"]


def test_physician_cannot_read_other_profile(client, doctors, physician_tokens):
    response = client.get(
        f"/doctors/{doctors['two']['id']}",
        headers=auth(physician_tokens["one"]),
    )

    assert_status(response, 403)


def test_admin_can_update_doctor(client, admin_token, doctors):
    response = client.put(
        f"/doctors/{doctors['one']['id']}",
        headers=auth(admin_token),
        json={
            "name": doctors["one"]["name"],
            "password": "MediSetu-Test#123",
            "specialization": "Internal Medicine",
            "department": "General Medicine",
        },
    )

    assert_status(response, 200)
    assert response.json()["specialization"] == "Internal Medicine"


def test_physician_cannot_update_doctor(client, doctors, physician_tokens):
    response = client.put(
        f"/doctors/{doctors['one']['id']}",
        headers=auth(physician_tokens["one"]),
        json={
            "name": "Unauthorized Update",
            "password": "MediSetu-Test#123",
            "specialization": "Hacker",
            "department": "Hacker",
        },
    )

    assert_status(response, 403)


def test_doctor_validation_rejects_short_password(client, admin_token):
    response = client.post(
        "/doctors/",
        headers=auth(admin_token),
        json={
            "name": "Invalid Test Doctor",
            "password": "short",
            "specialization": "Test",
            "department": "Test",
        },
    )

    assert_status(response, 422)


# ===========================================================================
# 4. PATIENTS
# ===========================================================================

def test_patient_created(patient):
    assert patient["id"] > 0


def test_duplicate_aadhaar_is_handled(client, patient):
    response = client.post(
        "/patients/",
        json={
            "name": "Same Aadhaar",
            "age": 80,
            "gender": "Other",
            "aadhaar": patient["aadhaar"],
        },
    )

    # Current MVP behavior is expected to return the existing patient.
    assert_status(response, 200)
    assert response.json()["id"] == patient["id"]


def test_invalid_patient_payload(client):
    response = client.post(
        "/patients/",
        json={
            "name": "A",
            "age": 999,
            "gender": "Other",
            "aadhaar": "123",
        },
    )

    assert_status(response, 422)


def test_unauthenticated_patient_list_is_blocked(client):
    response = client.get("/patients/")
    assert_status(response, 401, 403)


def test_patient_list_role_boundary(client, physician_tokens):
    response = client.get(
        "/patients/",
        headers=auth(physician_tokens["one"]),
    )

    assert_status(response, 403)


def test_patient_access_requires_session_credential(client, patient):
    response = client.get(f"/patients/{patient['id']}")
    assert_status(response, 401, 403)


# ===========================================================================
# 5. PATIENT SESSION AUTHENTICATION
# ===========================================================================

def test_patient_can_access_own_session(client, session):
    response = client.get(
        f"/sessions/{session['id']}",
        headers=patient_auth(session["patient_token"]),
    )

    assert_status(response, 200)
    assert response.json()["id"] == session["id"]


def test_wrong_patient_token_cannot_access_session(client, session):
    response = client.get(
        f"/sessions/{session['id']}",
        headers=patient_auth("wrong-token"),
    )

    assert_status(response, 401)


def test_cross_session_token_isolation(client, session, session2):
    response = client.get(
        f"/sessions/{session['id']}",
        headers=patient_auth(session2["patient_token"]),
    )

    assert_status(response, 401)


def test_assigned_physician_can_access_session(client, session, physician_tokens):
    response = client.get(
        f"/sessions/{session['id']}",
        headers=auth(physician_tokens["one"]),
    )

    assert_status(response, 200)


def test_unassigned_physician_cannot_access_session(
    client,
    session,
    physician_tokens,
):
    response = client.get(
        f"/sessions/{session['id']}",
        headers=auth(physician_tokens["two"]),
    )

    assert_status(response, 403)


def test_admin_can_access_any_session(client, admin_token, session):
    response = client.get(
        f"/sessions/{session['id']}",
        headers=auth(admin_token),
    )

    assert_status(response, 200)


def test_physician_session_list_is_scoped_to_assignment(
    client,
    physician_tokens,
    doctors,
    session,
):
    response = client.get(
        "/sessions/",
        headers=auth(physician_tokens["one"]),
    )

    assert_status(response, 200)

    for item in response.json():
        assert item["doctor_id"] == doctors["one"]["id"]

    assert any(item["id"] == session["id"] for item in response.json())


def test_admin_session_list_is_allowed(client, admin_token):
    response = client.get(
        "/sessions/",
        headers=auth(admin_token),
    )

    assert_status(response, 200)


def test_session_update_requires_admin(client, session):
    response = client.put(
        f"/sessions/{session['id']}",
        json={
            "patient_id": session["patient_id"],
            "doctor_id": session["doctor_id"],
        },
    )

    assert_status(response, 401)


def test_active_session_cannot_be_deleted(client, admin_token, session):
    response = client.delete(
        f"/sessions/{session['id']}",
        headers=auth(admin_token),
    )

    assert_status(response, 400)


def test_session_assignment_by_patient(
    client,
    assignment_session,
    doctors,
):
    response = client.put(
        f"/sessions/{assignment_session['id']}/assign-doctor",
        params={"mode": "allopathy"},
        headers=patient_auth(assignment_session["patient_token"]),
    )

    assert_status(response, 200)
    body = response.json()
    assert body["doctor_id"] is not None

    # Assignment is department-based. It must resolve to an active
    # General Medicine physician, not necessarily this test doctor's ID.
    assert body["doctor_id"] != doctors["two"]["id"]


def test_ayush_assignment_by_patient(client, session2, doctors):
    # Use a dedicated session so this test cannot change the assignment
    # used by the summary/document tests.
    response = client.post(
        "/sessions/",
        json={
            "patient_id": session2["patient_id"],
        },
        headers=auth(
            client.post(
                "/auth/admin/login",
                data={
                    "username": os.getenv("ADMIN_USERNAME"),
                    "password": os.getenv("ADMIN_PASSWORD"),
                },
            ).json()["access_token"]
        ),
    )
    assert_status(response, 200)
    ayush_session = response.json()

    response = client.put(
        f"/sessions/{ayush_session['id']}/assign-doctor",
        params={"mode": "ayush"},
        headers=patient_auth(ayush_session["patient_token"]),
    )

    assert_status(response, 200)
    body = response.json()
    assert body["doctor_id"] is not None

    # The individual doctor profile endpoint is intentionally physician-only.
    # Use the admin doctor-list endpoint to verify the assigned department.
    admin_login = client.post(
        "/auth/admin/login",
        data={
            "username": os.getenv("ADMIN_USERNAME"),
            "password": os.getenv("ADMIN_PASSWORD"),
        },
    )
    assert_status(admin_login, 200)

    doctors_response = client.get(
        "/doctors/",
        headers=auth(admin_login.json()["access_token"]),
    )
    assert_status(doctors_response, 200)

    assigned_doctor = next(
        (
            item
            for item in doctors_response.json()
            if item["id"] == body["doctor_id"]
        ),
        None,
    )

    assert assigned_doctor is not None
    assert assigned_doctor["department"] == "AYUSH"


def test_invalid_session_assignment_mode(client, session):
    response = client.put(
        f"/sessions/{session['id']}/assign-doctor",
        params={"mode": "unsupported"},
        headers=patient_auth(session["patient_token"]),
    )

    assert_status(response, 400)


# ===========================================================================
# 6. CONSENT
# ===========================================================================

def test_consent_requires_patient_token(client, session):
    response = client.post(
        "/consents/",
        json={
            "session_id": session["id"],
            "capture_consent": True,
            "sharing_consent": True,
        },
    )

    assert_status(response, 401)


def test_consent_created(consent, session):
    assert consent["session_id"] == session["id"]
    assert consent["revoked"] is False


def test_consent_can_be_read(client, session):
    response = client.get(
        f"/consents/session/{session['id']}",
        headers=patient_auth(session["patient_token"]),
    )

    assert_status(response, 200)
    assert response.json()["session_id"] == session["id"]


def test_duplicate_consent_is_rejected(client, session):
    response = client.post(
        "/consents/",
        headers=patient_auth(session["patient_token"]),
        json={
            "session_id": session["id"],
            "capture_consent": True,
            "sharing_consent": True,
        },
    )

    assert_status(response, 400)


def test_wrong_token_cannot_read_consent(client, session2, session):
    response = client.get(
        f"/consents/session/{session2['id']}",
        headers=patient_auth(session["patient_token"]),
    )

    assert_status(response, 401)


# ===========================================================================
# 7. RESPONSES
# ===========================================================================

def test_patient_can_create_response(client, session, consent):
    response = client.post(
        "/responses/",
        headers=patient_auth(session["patient_token"]),
        json={
            "session_id": session["id"],
            "question": "Do you have fever?",
            "answer": "No",
            "input_type": "touch",
            "language": "en",
        },
    )

    assert_status(response, 200)

    body = response.json()
    assert body["session_id"] == session["id"]
    assert body["answer"] == "No"

    assert body["id"] > 0


def test_response_requires_consent(client, session2):
    # session2 deliberately has no consent at this point.
    response = client.post(
        "/responses/",
        headers=patient_auth(session2["patient_token"]),
        json={
            "session_id": session2["id"],
            "question": "Test?",
            "answer": "Test",
            "input_type": "touch",
        },
    )

    assert_status(response, 403)


def test_response_requires_patient_auth(client, session):
    response = client.post(
        "/responses/",
        json={
            "session_id": session["id"],
            "question": "Test?",
            "answer": "Test",
            "input_type": "touch",
        },
    )

    assert_status(response, 401)


def test_physician_can_read_assigned_response(
    client,
    session,
    consent,
    physician_tokens,
):
    create = client.post(
        "/responses/",
        headers=patient_auth(session["patient_token"]),
        json={
            "session_id": session["id"],
            "question": "Duration?",
            "answer": "3 days",
            "input_type": "voice",
            "language": "hi",
        },
    )
    assert_status(create, 200)

    response_id = create.json()["id"]

    read = client.get(
        f"/responses/{response_id}",
        headers=auth(physician_tokens["one"]),
    )

    assert_status(read, 200)
    assert read.json()["id"] == response_id


def test_unassigned_physician_cannot_read_response(
    client,
    session,
    consent,
    physician_tokens,
):
    create = client.post(
        "/responses/",
        headers=patient_auth(session["patient_token"]),
        json={
            "session_id": session["id"],
            "question": "Unassigned access?",
            "answer": "No",
            "input_type": "touch",
        },
    )
    assert_status(create, 200)

    response_id = create.json()["id"]

    read = client.get(
        f"/responses/{response_id}",
        headers=auth(physician_tokens["two"]),
    )

    assert_status(read, 403)


def test_physician_can_update_assigned_response(
    client,
    session,
    consent,
    physician_tokens,
):
    create = client.post(
        "/responses/",
        headers=patient_auth(session["patient_token"]),
        json={
            "session_id": session["id"],
            "question": "Original?",
            "answer": "Original",
            "input_type": "touch",
        },
    )
    assert_status(create, 200)

    response_id = create.json()["id"]

    update = client.put(
        f"/responses/{response_id}",
        headers=auth(physician_tokens["one"]),
        json={
            "session_id": session["id"],
            "question": "Updated?",
            "answer": "Updated",
            "input_type": "voice",
            "language": "en",
        },
    )

    assert_status(update, 200)
    assert update.json()["answer"] == "Updated"


def test_response_cannot_be_moved_between_sessions(
    client,
    session,
    session2,
    consent,
    physician_tokens,
):
    create = client.post(
        "/responses/",
        headers=patient_auth(session["patient_token"]),
        json={
            "session_id": session["id"],
            "question": "Move?",
            "answer": "No",
            "input_type": "touch",
        },
    )
    assert_status(create, 200)

    response_id = create.json()["id"]

    update = client.put(
        f"/responses/{response_id}",
        headers=auth(physician_tokens["one"]),
        json={
            "session_id": session2["id"],
            "question": "Move?",
            "answer": "Attempted move",
            "input_type": "touch",
        },
    )

    assert_status(update, 400)


def test_admin_can_list_responses(client, admin_token):
    response = client.get(
        "/responses/",
        headers=auth(admin_token),
    )

    assert_status(response, 200)


# ===========================================================================
# 8. CONSENT REVOCATION
# ===========================================================================

def test_revoke_consent_blocks_future_capture(client, session, consent):
    response = client.put(
        f"/consents/session/{session['id']}/revoke",
        headers=patient_auth(session["patient_token"]),
    )

    assert_status(response, 200)

    body = response.json()
    assert body["revoked"] is True


def test_revoked_consent_blocks_new_response(client, session):
    response = client.post(
        "/responses/",
        headers=patient_auth(session["patient_token"]),
        json={
            "session_id": session["id"],
            "question": "After revoke?",
            "answer": "Should fail",
            "input_type": "touch",
        },
    )

    assert_status(response, 403)


def test_double_revoke_is_rejected(client, session):
    response = client.put(
        f"/consents/session/{session['id']}/revoke",
        headers=patient_auth(session["patient_token"]),
    )

    assert_status(response, 400)


# ===========================================================================
# 9. CONVERSATION
# ===========================================================================

def test_conversation_start_requires_patient_auth(client, session):
    response = client.post(
        "/conversation/start",
        json={
            "session_id": session["id"],
            "complaint": "fever",
            "language": "en",
            "mode": "allopathy",
        },
    )

    assert_status(response, 401)


def test_conversation_start_rejects_invalid_mode(client, session2):
    response = client.post(
        "/conversation/start",
        headers=patient_auth(session2["patient_token"]),
        json={
            "session_id": session2["id"],
            "complaint": "fever",
            "language": "en",
            "mode": "invalid-mode",
        },
    )

    assert_status(response, 400)


def test_conversation_start_rejects_invalid_language(client, session2):
    response = client.post(
        "/conversation/start",
        headers=patient_auth(session2["patient_token"]),
        json={
            "session_id": session2["id"],
            "complaint": "fever",
            "language": "xx",
            "mode": "allopathy",
        },
    )

    assert_status(response, 400)


def test_conversation_start_rejects_unknown_complaint(client, session2):
    response = client.post(
        "/conversation/start",
        headers=patient_auth(session2["patient_token"]),
        json={
            "session_id": session2["id"],
            "complaint": "completely unsupported symptom",
            "language": "en",
            "mode": "allopathy",
        },
    )

    assert_status(response, 400)


def test_conversation_allopathy_flow(client, session2):
    # session2 is still active and has its own patient credential.
    start = client.post(
        "/conversation/start",
        headers=patient_auth(session2["patient_token"]),
        json={
            "session_id": session2["id"],
            "complaint": "fever",
            "language": "en",
            "mode": "allopathy",
        },
    )

    assert_status(start, 200)

    body = start.json()

    assert body["session_id"] == session2["id"]
    assert body["complaint"] == "fever"
    assert body["mode"] == "allopathy"
    assert "question" in body

    if body["question"] is not None:
        question = body["question"]

        answer = client.post(
            "/conversation/answer",
            headers=patient_auth(session2["patient_token"]),
            json={
                "session_id": session2["id"],
                "field_id": question["field_id"],
                "question_id": question["id"],
                "answer": "No",
                "input_type": "touch",
            },
        )

        assert_status(answer, 200)
        assert "completed" in answer.json()


def test_conversation_ayush_flow(client, session2):
    start = client.post(
        "/conversation/start",
        headers=patient_auth(session2["patient_token"]),
        json={
            "session_id": session2["id"],
            "complaint": "cough",
            "language": "hi",
            "mode": "ayush",
        },
    )

    assert_status(start, 200)

    body = start.json()
    assert body["mode"] == "ayush"
    assert body["session_id"] == session2["id"]


def test_conversation_next_requires_auth(client, session2):
    response = client.get(f"/conversation/{session2['id']}/next")
    assert_status(response, 401)


def test_conversation_wrong_session_token_is_rejected(client, session, session2):
    response = client.get(
        f"/conversation/{session2['id']}/next",
        headers=patient_auth(session["patient_token"]),
    )

    assert_status(response, 401)


def test_conversation_empty_answer_is_rejected(client, session2):
    # Ensure a manager exists.
    client.post(
        "/conversation/start",
        headers=patient_auth(session2["patient_token"]),
        json={
            "session_id": session2["id"],
            "complaint": "headache",
            "language": "en",
            "mode": "allopathy",
        },
    )

    response = client.post(
        "/conversation/answer",
        headers=patient_auth(session2["patient_token"]),
        json={
            "session_id": session2["id"],
            "field_id": "test-field",
            "answer": "",
            "input_type": "touch",
        },
    )

    assert_status(response, 400)


def test_conversation_invalid_input_type_is_rejected(client, session2):
    response = client.post(
        "/conversation/answer",
        headers=patient_auth(session2["patient_token"]),
        json={
            "session_id": session2["id"],
            "field_id": "test-field",
            "answer": "test",
            "input_type": "keyboard",
        },
    )

    assert_status(response, 400)


# ===========================================================================
# 10. DOCUMENTS
# ===========================================================================

def patch_document_services(monkeypatch):
    import app.api.documents as documents_api

    monkeypatch.setattr(
        documents_api,
        "validate_file",
        lambda path: (True, None),
    )

    monkeypatch.setattr(
        documents_api,
        "upload_storage_document",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        documents_api,
        "delete_storage_document",
        lambda path: None,
    )


def test_document_upload_requires_patient_session(client, session):
    response = client.post(
        "/documents/",
        data={
            "patient_id": str(session["patient_id"]),
            "session_id": str(session["id"]),
            "document_type": "lab_report",
        },
        files={
            "file": (
                "test.pdf",
                b"fake-content",
                "application/pdf",
            )
        },
    )

    assert_status(response, 401)


def test_document_upload_rejects_cross_session_token(
    client,
    session,
    session2,
    monkeypatch,
):
    patch_document_services(monkeypatch)

    response = client.post(
        "/documents/",
        data={
            "patient_id": str(session["patient_id"]),
            "session_id": str(session["id"]),
            "document_type": "lab_report",
        },
        files={
            "file": (
                "test.pdf",
                b"fake-content",
                "application/pdf",
            )
        },
        headers=patient_auth(session2["patient_token"]),
    )

    assert_status(response, 401, 403)


def test_document_upload_rejects_invalid_type(
    client,
    session2,
    monkeypatch,
):
    # The current document API requires valid capture consent before
    # processing the upload, so establish that prerequisite first.
    consent_response = client.post(
        "/consents/",
        headers=patient_auth(session2["patient_token"]),
        json={
            "session_id": session2["id"],
            "capture_consent": True,
            "sharing_consent": True,
            "language": "en",
        },
    )
    assert consent_response.status_code in (200, 400), (
        f"Unexpected consent response: "
        f"{consent_response.status_code}: {consent_response.text}"
    )
    if consent_response.status_code == 400:
        assert "already exists" in consent_response.text.lower()

    patch_document_services(monkeypatch)

    response = client.post(
        "/documents/",
        data={
            "patient_id": str(session2["patient_id"]),
            "session_id": str(session2["id"]),
            "document_type": "not-a-real-document-type",
        },
        files={
            "file": (
                "test.pdf",
                b"fake-content",
                "application/pdf",
            )
        },
        headers=patient_auth(session2["patient_token"]),
    )

    assert_status(response, 400)


def test_document_upload_and_ocr_pipeline(
    client,
    session2,
    monkeypatch,
):
    # session2 is used because session may have revoked consent.
    # Create consent for session2.
    consent_response = client.post(
        "/consents/",
        headers=patient_auth(session2["patient_token"]),
        json={
            "session_id": session2["id"],
            "capture_consent": True,
            "sharing_consent": True,
            "language": "en",
        },
    )
    assert consent_response.status_code in (200, 400), (
        f"Unexpected consent response: "
        f"{consent_response.status_code}: {consent_response.text}"
    )
    if consent_response.status_code == 400:
        assert "already exists" in consent_response.text.lower()

    patch_document_services(monkeypatch)

    create = client.post(
        "/documents/",
        data={
            "patient_id": str(session2["patient_id"]),
            "session_id": str(session2["id"]),
            "document_type": "lab_report",
        },
        files={
            "file": (
                "lab.pdf",
                b"fake-pdf",
                "application/pdf",
            )
        },
        headers=patient_auth(session2["patient_token"]),
    )

    assert_status(create, 200)

    document = create.json()
    document_id = document["id"]

    import app.api.documents as documents_api

    def fake_ocr(*, document, db):
        document.processing_status = "completed"
        document.extracted_data = (
            '{"diagnosis":"test","medications":["demo"]}'
        )
        document.confidence = 0.99
        db.commit()
        db.refresh(document)
        return document

    monkeypatch.setattr(
        documents_api,
        "process_document_ocr",
        fake_ocr,
    )

    process = client.post(
        f"/documents/{document_id}/process",
        headers=patient_auth(session2["patient_token"]),
    )

    assert_status(process, 200)
    assert process.json()["processing_status"] == "completed"

    extracted = client.get(
        f"/documents/{document_id}/extracted",
        headers=patient_auth(session2["patient_token"]),
    )

    assert_status(extracted, 200)

    body = extracted.json()
    assert body["document_id"] == document_id
    assert body["extracted_data"]["diagnosis"] == "test"


def test_document_admin_listing(client, admin_token):
    response = client.get(
        "/documents/",
        headers=auth(admin_token),
    )

    assert_status(response, 200)


def test_document_listing_is_not_public(client):
    response = client.get("/documents/")
    assert_status(response, 401, 403)


# ===========================================================================
# 11. SUMMARIES
# ===========================================================================

def test_patient_can_create_summary(client, session2):
    create = client.post(
        "/summaries/",
        headers=patient_auth(session2["patient_token"]),
        json={
            "session_id": session2["id"],
            "content": "Initial test clinical summary",
        },
    )

    assert_status(create, 200)

    body = create.json()
    assert body["session_id"] == session2["id"]
    assert body["status"] == "draft"
    assert body["id"] > 0


def test_duplicate_summary_is_rejected(client, session2):
    response = client.post(
        "/summaries/",
        headers=patient_auth(session2["patient_token"]),
        json={
            "session_id": session2["id"],
            "content": "Duplicate summary",
        },
    )

    assert_status(response, 409)


def test_summary_patient_read_access(client, session2):
    # Locate the summary through the admin list so this test does not depend
    # on a fixed database ID.
    admin_username = os.getenv("ADMIN_USERNAME")
    admin_password = os.getenv("ADMIN_PASSWORD")

    login = client.post(
        "/auth/admin/login",
        data={"username": admin_username, "password": admin_password},
    )
    assert_status(login, 200)

    summaries = client.get(
        "/summaries/",
        headers=auth(login.json()["access_token"]),
    )
    assert_status(summaries, 200)

    matches = [
        item
        for item in summaries.json()
        if item["session_id"] == session2["id"]
    ]
    assert matches, "Expected test summary for session2"

    summary_id = matches[-1]["id"]

    response = client.get(
        f"/summaries/{summary_id}",
        headers=patient_auth(session2["patient_token"]),
    )

    assert_status(response, 200)


def test_summary_update_requires_assigned_physician(
    client,
    session2,
    physician_tokens,
):
    admin_username = os.getenv("ADMIN_USERNAME")
    admin_password = os.getenv("ADMIN_PASSWORD")

    login = client.post(
        "/auth/admin/login",
        data={"username": admin_username, "password": admin_password},
    )
    assert_status(login, 200)

    summaries = client.get(
        "/summaries/",
        headers=auth(login.json()["access_token"]),
    )
    assert_status(summaries, 200)

    matches = [
        item
        for item in summaries.json()
        if item["session_id"] == session2["id"]
    ]
    assert matches

    summary_id = matches[-1]["id"]

    wrong_doctor = client.put(
        f"/summaries/{summary_id}",
        headers=auth(physician_tokens["one"]),
        json={
            "status": "accepted",
            "content": "Unauthorized review",
        },
    )
    assert_status(wrong_doctor, 403)

    correct_doctor = client.put(
        f"/summaries/{summary_id}",
        headers=auth(physician_tokens["two"]),
        json={
            "status": "accepted",
            "content": "Physician reviewed summary",
        },
    )
    assert_status(correct_doctor, 200)

    assert correct_doctor.json()["status"] == "accepted"


def test_summary_invalid_status_is_rejected(
    client,
    session2,
    physician_tokens,
):
    admin_username = os.getenv("ADMIN_USERNAME")
    admin_password = os.getenv("ADMIN_PASSWORD")

    login = client.post(
        "/auth/admin/login",
        data={"username": admin_username, "password": admin_password},
    )
    assert_status(login, 200)

    summaries = client.get(
        "/summaries/",
        headers=auth(login.json()["access_token"]),
    )
    assert_status(summaries, 200)

    matches = [
        item
        for item in summaries.json()
        if item["session_id"] == session2["id"]
    ]
    assert matches

    summary_id = matches[-1]["id"]

    response = client.put(
        f"/summaries/{summary_id}",
        headers=auth(physician_tokens["two"]),
        json={"status": "approved"},
    )

    assert_status(response, 400)


def test_summary_admin_list(client, admin_token):
    response = client.get(
        "/summaries/",
        headers=auth(admin_token),
    )

    assert_status(response, 200)


def test_summary_list_not_public(client):
    response = client.get("/summaries/")
    assert_status(response, 401, 403)


# ===========================================================================
# 12. SUMMARY GENERATION — SERVICE MOCK
# ===========================================================================

def test_summary_generation_authorization_and_pipeline(
    client,
    session2,
    physician_tokens,
    monkeypatch,
):
    import app.api.summary as summary_api

    fake_case_sheet = SimpleNamespace(
        model_dump=lambda mode=None: {
            "chief_complaint": "fever",
            "assessment": "test summary",
        }
    )

    monkeypatch.setattr(
        summary_api,
        "generate_deterministic_summary",
        lambda **kwargs: {"case_sheet": fake_case_sheet},
    )

    # Correct assigned physician should be allowed.
    response = client.post(
        f"/summaries/session/{session2['id']}/generate",
        headers=auth(physician_tokens["two"]),
    )

    assert_status(response, 200)

    body = response.json()
    assert body["session_id"] == session2["id"]
    assert body["status"] == "draft"


def test_summary_generation_wrong_physician_is_blocked(
    client,
    session2,
    physician_tokens,
):
    response = client.post(
        f"/summaries/session/{session2['id']}/generate",
        headers=auth(physician_tokens["one"]),
    )

    assert_status(response, 403)


def test_summary_generation_without_auth_is_blocked(client, session2):
    response = client.post(
        f"/summaries/session/{session2['id']}/generate",
    )

    assert_status(response, 401)


# ===========================================================================
# 13. ASR
# ===========================================================================

def test_asr_requires_session_id(client, session):
    response = client.post(
        "/asr/transcribe",
        files={
            "file": (
                "audio.wav",
                b"fake-audio",
                "audio/wav",
            )
        },
    )

    assert_status(response, 400)


def test_asr_requires_patient_token(client, session):
    response = client.post(
        f"/asr/transcribe?session_id={session['id']}",
        files={
            "file": (
                "audio.wav",
                b"fake-audio",
                "audio/wav",
            )
        },
    )

    assert_status(response, 401)


def test_asr_rejects_unsupported_extension(client, session):
    response = client.post(
        f"/asr/transcribe?session_id={session['id']}",
        headers=patient_auth(session["patient_token"]),
        files={
            "file": (
                "audio.exe",
                b"fake-audio",
                "application/octet-stream",
            )
        },
    )

    assert_status(response, 400)


def test_asr_provider_can_be_mocked(client, session, monkeypatch):
    import app.api.asr as asr_api

    class FakeResult:
        def model_dump(self):
            return {
                "text": "namaste",
                "language": "hi",
            }

    class FakeProvider:
        def transcribe(self, path):
            assert Path(path).exists()
            return FakeResult()

    monkeypatch.setattr(
        asr_api,
        "validate_audio_file",
        lambda path: None,
    )
    monkeypatch.setattr(
        asr_api,
        "SarvamASRProvider",
        FakeProvider,
    )
    monkeypatch.setattr(
        asr_api.settings,
        "sarvam_api_key",
        "test-key",
    )

    response = client.post(
        f"/asr/transcribe?session_id={session['id']}",
        headers=patient_auth(session["patient_token"]),
        files={
            "file": (
                "audio.wav",
                b"fake-audio",
                "audio/wav",
            )
        },
    )

    assert_status(response, 200)
    assert response.json()["text"] == "namaste"


# ===========================================================================
# 14. TTS
# ===========================================================================

def test_tts_endpoint_exists(client):
    # We deliberately accept provider-dependent statuses here. The important
    # part is that malformed input is not silently treated as success.
    response = client.post(
        "/tts/synthesize",
        json={},
    )

    assert_status(response, 400, 422, 502)


def test_tts_provider_can_be_mocked(client, monkeypatch, tmp_path):
    import app.api.tts as tts_api

    fake_audio = tmp_path / "test-tts.mp3"
    fake_audio.write_bytes(b"fake-mp3")

    class FakeProvider:
        def __init__(self):
            pass

        async def synthesize(self, request):
            return SimpleNamespace(audio_path=fake_audio)

    monkeypatch.setattr(
        tts_api,
        "EdgeTTSProvider",
        FakeProvider,
    )

    response = client.post(
        "/tts/synthesize",
        json={
            "text": "Hello patient",
            "language_code": "en-IN",
        },
    )

    assert_status(response, 200)
    assert response.headers["content-type"].startswith("audio/")


# ===========================================================================
# 15. NOT-FOUND / BOUNDARY CHECKS
# ===========================================================================

def test_missing_session_returns_not_found(client, admin_token):
    response = client.get(
        "/sessions/999999999",
        headers=auth(admin_token),
    )
    assert_status(response, 404)


def test_missing_doctor_returns_not_found_or_forbidden(client, physician_tokens):
    response = client.get(
        "/doctors/999999999",
        headers=auth(physician_tokens["one"]),
    )
    # The physician ownership guard may reject before lookup.
    assert_status(response, 403, 404)


def test_missing_response_returns_not_found(client, physician_tokens):
    response = client.get(
        "/responses/999999999",
        headers=auth(physician_tokens["one"]),
    )
    assert_status(response, 404)


def test_missing_summary_returns_not_found(client, session2):
    response = client.get(
        "/summaries/999999999",
        headers=patient_auth(session2["patient_token"]),
    )
    assert_status(response, 404)


def test_missing_document_extracted_returns_not_found(client, session2):
    response = client.get(
        "/documents/999999999/extracted",
        headers=patient_auth(session2["patient_token"]),
    )
    assert_status(response, 404)


# ===========================================================================
# 16. SECURITY-SPECIFIC PATIENT TOKEN TESTS
# ===========================================================================

def test_patient_token_is_not_the_session_id(client, session):
    assert session["patient_token"] != str(session["id"])


def test_patient_token_is_nontrivial_length(session):
    assert len(session["patient_token"]) >= 32


def test_patient_token_is_scoped_to_one_session(client, session, session2):
    first = client.get(
        f"/sessions/{session['id']}",
        headers=patient_auth(session["patient_token"]),
    )
    second = client.get(
        f"/sessions/{session2['id']}",
        headers=patient_auth(session["patient_token"]),
    )

    assert_status(first, 200)
    assert_status(second, 401)


# ===========================================================================
# Notes
# ===========================================================================
#
# This file intentionally does NOT test raw database internals as API tests.
# Model-level/database constraints should get a separate test module later.
#
# It also intentionally mocks:
#   - Supabase document storage
#   - OCR processing
#   - Sarvam ASR provider
#   - Edge TTS provider
#
# That lets the suite verify your API/auth/security architecture without
# depending on network services.
