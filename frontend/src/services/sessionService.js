import {
  api,
  setPatientSessionToken,
  clearPatientSessionToken,
} from "./api";

/**
 * Create or resume a patient consultation session.
 *
 * Backend behavior:
 *
 * - If the patient has a resumable active session
 *   (< 15 minutes inactivity), the SAME session is returned.
 *
 * - If no resumable session exists, a NEW session is created.
 *
 * In both cases the backend issues a fresh patient-session token.
 *
 * The frontend must treat the returned session as authoritative.
 */
export async function createSession(patientId) {
  if (!patientId) {
    throw new Error("Patient ID is required.");
  }

  const session = await api("/sessions/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      patient_id: patientId,
    }),
  });

  if (!session?.id) {
    throw new Error(
      "Session was not created or resumed."
    );
  }

  /*
   * Every successful login receives a fresh patient-session
   * credential, whether the backend created a new session
   * or resumed an existing one.
   */
  if (!session?.patient_token) {
    throw new Error(
      "Session was created or resumed, but no patient session credential was returned."
    );
  }

  /*
   * Replace the old token immediately.
   *
   * This is especially important after kiosk/browser restart
   * or patient re-login because the backend intentionally
   * rotates the patient-session credential.
   */
  setPatientSessionToken(
    session.patient_token
  );

  return session;
}


/**
 * Assign a doctor to the current patient session.
 *
 * The patient credential is automatically attached by
 * api() because this request uses auth: "patient".
 *
 * mode:
 *   "allopathy"
 *   "ayush"
 */
export async function assignDoctorToSession(
  sessionId,
  mode
) {
  if (!sessionId) {
    throw new Error("Session ID is required.");
  }

  if (!mode || !mode.trim()) {
    throw new Error(
      "Consultation mode is required."
    );
  }

  const normalizedMode = mode
    .trim()
    .toLowerCase();

  if (
    normalizedMode !== "allopathy" &&
    normalizedMode !== "ayush"
  ) {
    throw new Error(
      "Invalid consultation mode. Choose allopathy or ayush."
    );
  }

  return api(
    `/sessions/${encodeURIComponent(
      sessionId
    )}/assign-doctor?mode=${encodeURIComponent(
      normalizedMode
    )}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      auth: "patient",
    }
  );
}


/**
 * Fetch a single patient session using the
 * current patient-session credential.
 *
 * This is useful after restoring a session from
 * the backend to verify its current lifecycle state.
 */
export async function getSession(sessionId) {
  if (!sessionId) {
    throw new Error(
      "Session ID is required."
    );
  }

  return api(
    `/sessions/${encodeURIComponent(
      sessionId
    )}`,
    {
      method: "GET",
      auth: "patient",
    }
  );
}


/**
 * Complete the current patient consultation.
 *
 * The backend changes the session status from
 * "active" to "completed".
 *
 * A completed session can never be resumed by
 * the patient through createSession().
 */
export async function completeSession(
  sessionId
) {
  if (!sessionId) {
    throw new Error(
      "Session ID is required."
    );
  }

  return api(
    `/sessions/${encodeURIComponent(
      sessionId
    )}/complete`,
    {
      method: "POST",
      auth: "patient",
    }
  );
}


/**
 * End the local patient authentication state.
 *
 * This only removes the locally stored patient
 * credential. It does NOT delete or complete the
 * backend consultation session.
 *
 * The backend session remains resumable until its
 * lifecycle rules expire it.
 */
export function clearPatientSession() {
  clearPatientSessionToken();
}