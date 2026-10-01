const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const PATIENT_TOKEN_KEY = "patientSessionToken";
const DOCTOR_TOKEN_KEY = "doctorAccessToken";

/**
 * Get the configured backend URL without trailing slashes.
 */
export function getApiBaseUrl() {
  return API_BASE_URL.replace(/\/+$/, "");
}

/**
 * =========================
 * PATIENT SESSION TOKEN
 * =========================
 *
 * Patient credentials are short-lived and scoped to the current
 * browser session. They are intentionally stored in sessionStorage,
 * not localStorage.
 */

export function setPatientSessionToken(token) {
  if (!token) {
    sessionStorage.removeItem(PATIENT_TOKEN_KEY);
    return;
  }

  sessionStorage.setItem(PATIENT_TOKEN_KEY, String(token));
}

export function getPatientSessionToken() {
  return sessionStorage.getItem(PATIENT_TOKEN_KEY);
}

export function clearPatientSessionToken() {
  sessionStorage.removeItem(PATIENT_TOKEN_KEY);
}

/**
 * =========================
 * DOCTOR JWT
 * =========================
 */

export function setDoctorAccessToken(token) {
  if (!token) {
    sessionStorage.removeItem(DOCTOR_TOKEN_KEY);
    return;
  }

  sessionStorage.setItem(DOCTOR_TOKEN_KEY, String(token));
}

export function getDoctorAccessToken() {
  return sessionStorage.getItem(DOCTOR_TOKEN_KEY);
}

export function clearDoctorAccessToken() {
  sessionStorage.removeItem(DOCTOR_TOKEN_KEY);
}

/**
 * Clear all frontend authentication credentials.
 */
export function clearAuth() {
  clearPatientSessionToken();
  clearDoctorAccessToken();
}

/**
 * =========================
 * REQUEST HEADERS
 * =========================
 *
 * auth:
 *   "patient" -> X-Patient-Session-Token
 *   "doctor"  -> Authorization: Bearer <JWT>
 *
 * Caller-provided headers always take precedence.
 */
function buildHeaders(options = {}) {
  const headers = new Headers(options.headers || {});

  const authType = options.auth;

  if (authType === "patient") {
    const patientToken = getPatientSessionToken();

    if (
      patientToken &&
      !headers.has("X-Patient-Session-Token")
    ) {
      headers.set(
        "X-Patient-Session-Token",
        patientToken
      );
    }
  }

  if (authType === "doctor") {
    const doctorToken = getDoctorAccessToken();

    if (
      doctorToken &&
      !headers.has("Authorization")
    ) {
      headers.set(
        "Authorization",
        `Bearer ${doctorToken}`
      );
    }
  }

  return headers;
}

/**
 * =========================
 * API ERROR HANDLING
 * =========================
 *
 * Converts FastAPI errors into useful frontend Errors.
 *
 * Normal FastAPI error:
 * {
 *   "detail": "Some message"
 * }
 *
 * Validation error:
 * {
 *   "detail": [
 *      {
 *        "loc": ["body", "field"],
 *        "msg": "Field required"
 *      }
 *   ]
 * }
 */
async function createApiError(response) {
  let detail = null;

  try {
    const data = await response.clone().json();
    detail = data?.detail;
  } catch {
    // Response was not JSON.
  }

  let message = `Request failed (${response.status})`;

  if (
    typeof detail === "string" &&
    detail.trim()
  ) {
    message = detail;
  } else if (
    Array.isArray(detail) &&
    detail.length > 0
  ) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }

        if (
          item &&
          typeof item.msg === "string"
        ) {
          const location = Array.isArray(item.loc)
            ? item.loc
                .filter((part) => part !== "body")
                .join(".")
            : "";

          return location
            ? `${location}: ${item.msg}`
            : item.msg;
        }

        return null;
      })
      .filter(Boolean);

    if (messages.length > 0) {
      message = messages.join("\n");
    }
  }

  const error = new Error(message);

  /*
   * Allows frontend code to handle:
   *
   * 401 -> unauthenticated / expired token
   * 403 -> forbidden
   * 404 -> not found
   * 409 -> conflict
   * etc.
   */
  error.status = response.status;
  error.statusCode = response.status;

  /*
   * Useful for debugging navigation/API problems,
   * but never include credentials in the URL.
   */
  error.url = response.url;

  return error;
}

/**
 * =========================
 * MAIN API CLIENT
 * =========================
 *
 * Example:
 *
 * api("/patients/", {
 *   method: "POST",
 *   headers: {
 *     "Content-Type": "application/json"
 *   },
 *   body: JSON.stringify(data)
 * });
 *
 *
 * Patient-authenticated request:
 *
 * api("/sessions/1", {
 *   auth: "patient"
 * });
 *
 *
 * Doctor-authenticated request:
 *
 * api("/doctors/me", {
 *   auth: "doctor"
 * });
 */
export async function api(path, options = {}) {
  if (
    typeof path !== "string" ||
    !path.trim()
  ) {
    throw new Error("API path is required.");
  }

  /*
   * All MediSetu API calls must go through the
   * configured backend. This prevents accidental
   * credential leakage to an arbitrary external URL.
   */
  if (/^https?:\/\//i.test(path)) {
    throw new Error(
      "API paths must be relative to the configured MediSetu backend."
    );
  }

  const {
    auth,
    ...fetchOptions
  } = options;

  const headers = buildHeaders({
    ...fetchOptions,
    auth,
  });

  const url =
    `${getApiBaseUrl()}` +
    `${path.startsWith("/") ? path : `/${path}`}`;

  let response;

  try {
    response = await fetch(url, {
      ...fetchOptions,
      headers,
    });
  } catch (error) {
    /*
     * Network-level failures do not have an HTTP status.
     * Give the UI a useful error instead of exposing
     * browser-specific fetch errors.
     */
    const networkError = new Error(
      "Unable to connect to the MediSetu backend. Please check that the server is running."
    );

    networkError.cause = error;

    throw networkError;
  }

  if (!response.ok) {
    throw await createApiError(response);
  }

  /*
   * HTTP 204 has no response body.
   */
  if (response.status === 204) {
    return null;
  }

  const contentType =
    response.headers.get("content-type") || "";

  /*
   * Normal MediSetu API responses are JSON.
   */
  if (
    contentType
      .toLowerCase()
      .includes("application/json")
  ) {
    return response.json();
  }

  /*
   * Gracefully handle non-JSON responses instead
   * of throwing a JSON parsing error.
   */
  return response.text();
}

/**
 * =========================
 * JSON REQUEST HELPER
 * =========================
 *
 * Use this for POST/PUT/PATCH requests containing
 * JSON payloads.
 */
export function apiJson(
  path,
  method,
  data,
  options = {}
) {
  return api(path, {
    ...options,
    method,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    body: JSON.stringify(data),
  });
}

/**
 * =========================
 * FORM DATA HELPER
 * =========================
 *
 * Use this for OCR/audio/file uploads.
 *
 * IMPORTANT:
 * Do NOT manually set Content-Type here.
 * The browser automatically adds the multipart
 * boundary required by FormData.
 */
export function apiForm(
  path,
  formData,
  options = {}
) {
  return api(path, {
    ...options,
    method: options.method || "POST",
    body: formData,
  });
}