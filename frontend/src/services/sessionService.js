const API_BASE_URL = "http://localhost:8000";


export async function createSession(patientId) {
  const response = await fetch(
    `${API_BASE_URL}/sessions/`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        patient_id: patientId,
      }),
    }
  );

  if (!response.ok) {
    const errorData =
      await response.json().catch(() => null);

    throw new Error(
      errorData?.detail ||
        "Failed to create session."
    );
  }

  return response.json();
}


/**
 * Assign a doctor to a session based on
 * the selected consultation mode.
 *
 * mode:
 *   "allopathy"
 *   "ayush"
 */
export async function assignDoctorToSession(
  sessionId,
  mode
) {
  const response = await fetch(
    `${API_BASE_URL}/sessions/${sessionId}/assign-doctor?mode=${encodeURIComponent(mode)}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );

  if (!response.ok) {
    const errorData =
      await response.json().catch(() => null);

    throw new Error(
      errorData?.detail ||
        "Failed to assign doctor to session."
    );
  }

  return response.json();
}