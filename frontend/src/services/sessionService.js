import {
  api,
  setPatientSessionToken,
  clearPatientSessionToken,
} from "./api";

/**
 * Create a new patient consultation session.
 *
 * Session creation is intentionally unauthenticated.
 * The backend creates the short-lived patient-session
 * credential and returns it once.
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

  /*
   * The backend returns the raw patient token only when
   * the session is created.
   *
   * Store it immediately so subsequent patient requests
   * can authenticate against this consultation session.
   */
  if (!session?.patient_token) {
    throw new Error(
      "Session was created, but no patient session credential was returned."
    );
  }

  setPatientSessionToken(session.patient_token);

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
    throw new Error("Consultation mode is required.");
  }

  const normalizedMode = mode.trim().toLowerCase();

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
 */
export async function getSession(sessionId) {
  if (!sessionId) {
    throw new Error("Session ID is required.");
  }

  return api(
    `/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: "GET",
      auth: "patient",
    }
  );
}

/**
 * End the local patient authentication state.
 *
 * The backend session lifecycle is handled by the
 * appropriate backend endpoint. This function only
 * removes the browser-held patient credential.
 */
export function clearPatientSession() {
  clearPatientSessionToken();
}