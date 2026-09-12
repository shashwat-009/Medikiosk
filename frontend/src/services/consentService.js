import { api } from "./api";

/**
 * Create consent for the current patient consultation session.
 *
 * The patient-session credential is automatically attached by
 * api() through the "patient" authentication mode.
 *
 * Backend:
 *   POST /consents/
 *
 * Required:
 *   session_id
 *   capture_consent
 *   sharing_consent
 *
 * Optional:
 *   language
 */
export async function createConsent(consentData) {
  if (!consentData || typeof consentData !== "object") {
    throw new Error("Consent data is required.");
  }

  const {
    session_id,
    capture_consent,
    sharing_consent,
    language = null,
  } = consentData;

  if (!session_id) {
    throw new Error("Session ID is required for consent.");
  }

  if (typeof capture_consent !== "boolean") {
    throw new Error(
      "Capture consent must be true or false."
    );
  }

  if (typeof sharing_consent !== "boolean") {
    throw new Error(
      "Sharing consent must be true or false."
    );
  }

  return api("/consents/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id,
      capture_consent,
      sharing_consent,
      language,
    }),
    auth: "patient",
  });
}

/**
 * Get consent associated with a patient session.
 *
 * Backend:
 *   GET /consents/session/{session_id}
 */
export async function getSessionConsent(sessionId) {
  if (!sessionId) {
    throw new Error("Session ID is required.");
  }

  return api(
    `/consents/session/${encodeURIComponent(sessionId)}`,
    {
      method: "GET",
      auth: "patient",
    }
  );
}

/**
 * Revoke consent for the current patient session.
 *
 * Backend:
 *   PUT /consents/session/{session_id}/revoke
 *
 * Once revoked, the backend prevents further clinical
 * response submission where applicable.
 */
export async function revokeConsent(sessionId) {
  if (!sessionId) {
    throw new Error("Session ID is required.");
  }

  return api(
    `/consents/session/${encodeURIComponent(sessionId)}/revoke`,
    {
      method: "PUT",
      auth: "patient",
    }
  );
}