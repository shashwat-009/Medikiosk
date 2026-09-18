import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useKiosk } from "../../context/KioskContext";
import { translate } from "../../i18n";

import {
  completeSession,
  clearPatientSession,
} from "../../services/sessionService";

import { api } from "../../services/api";

import "./Confirmation.css";

export default function Confirmation() {
  const navigate = useNavigate();

  const { state } = useKiosk();

  const language = state.language || "en";

  const session = state.session;

  const sessionId =
    session?.id ??
    session?.session_id ??
    null;

  const [doctor, setDoctor] = useState(null);

  const [isCompleting, setIsCompleting] =
    useState(false);

  const [completed, setCompleted] =
    useState(false);

  const [error, setError] =
    useState("");

  /*
   * ============================================================
   * Load assigned doctor
   * ============================================================
   */

  useEffect(() => {
    let cancelled = false;

    async function loadAssignedDoctor() {
      if (!sessionId) {
        if (!cancelled) {
          setDoctor(null);
        }

        return;
      }

      try {
        const doctorData =
          await api(
            `/sessions/${encodeURIComponent(
              sessionId
            )}/doctor`,
            {
              method: "GET",
              auth: "patient",
            }
          );

        if (!cancelled) {
          setDoctor(
            doctorData
          );
        }
      } catch (doctorError) {
        console.error(
          "Unable to load assigned doctor:",
          doctorError
        );

        if (!cancelled) {
          setDoctor(null);
        }
      }
    }

    loadAssignedDoctor();

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  /*
   * ============================================================
   * Complete consultation
   * ============================================================
   *
   * IMPORTANT:
   *
   * This is the actual lifecycle transition:
   *
   * active → completed
   *
   * The backend remains the source of truth.
   *
   * We do NOT clear the patient token before the
   * completion request succeeds.
   */

  async function handleContinue() {
    /*
     * Prevent double-click / duplicate completion requests.
     */
    if (
      isCompleting ||
      completed
    ) {
      return;
    }

    if (!sessionId) {
      setError(
        "No active consultation session was found."
      );

      return;
    }

    setError("");
    setIsCompleting(true);

    try {
      console.log(
        "CONFIRMATION: completing session",
        sessionId
      );

      /*
       * Complete the backend session.
       */
      const completedSession =
        await completeSession(
          sessionId
        );

      console.log(
        "CONFIRMATION: session completed successfully",
        completedSession
      );

      /*
       * Only after the backend confirms completion
       * do we consider the local workflow finished.
       */
      setCompleted(true);

      /*
       * Invalidate the patient authentication token.
       *
       * This prevents the completed patient's old
       * credential from being reused after leaving
       * the kiosk workflow.
       */
      clearPatientSession();

      console.log(
        "CONFIRMATION: patient session credential cleared"
      );

      /*
       * Return to kiosk entry page.
       *
       * replace prevents the user from pressing Back
       * and accidentally returning to the completed
       * consultation.
       */
      navigate(
        "/",
        {
          replace: true,
        }
      );
    } catch (err) {
      console.error(
        "CONFIRMATION: failed to complete session",
        err
      );

      let message =
        translate(
          language,
          "common.error"
        );

      if (
        typeof err === "string"
      ) {
        message = err;
      } else if (
        err instanceof Error
      ) {
        message =
          err.message;
      } else if (
        err &&
        typeof err.detail === "string"
      ) {
        message =
          err.detail;
      } else if (
        err &&
        typeof err.message === "string"
      ) {
        message =
          err.message;
      }

      setError(
        message ||
          "Unable to complete the consultation."
      );
    } finally {
      setIsCompleting(false);
    }
  }

  /*
   * ============================================================
   * Doctor initials
   * ============================================================
   */

  function getDoctorInitials(
    name
  ) {
    if (!name) {
      return "D";
    }

    const cleanName =
      name
        .replace(
          /^Dr\.?\s*/i,
          ""
        )
        .trim();

    const parts =
      cleanName
        .split(/\s+/)
        .filter(Boolean);

    if (
      parts.length === 1
    ) {
      return parts[0]
        .charAt(0)
        .toUpperCase();
    }

    return (
      parts[0].charAt(0) +
      parts[
        parts.length - 1
      ].charAt(0)
    ).toUpperCase();
  }

  /*
   * ============================================================
   * Render
   * ============================================================
   */

  return (
    <main className="confirmation">
      <section className="confirmation__container">
        <div className="confirmation__card">

          {/* Completion indicator */}

          <div
            className="confirmation__icon"
            aria-hidden="true"
          >
            ✓
          </div>

          {/* Completion message */}

          <p className="confirmation__eyebrow">
            {translate(
              language,
              "confirmation.eyebrow"
            )}
          </p>

          <h1>
            {translate(
              language,
              "confirmation.title"
            )}
          </h1>

          <p className="confirmation__description">
            {translate(
              language,
              "confirmation.description"
            )}
          </p>

          {/* Assigned doctor */}

          {doctor && (
            <section
              className="confirmation__doctor"
              aria-labelledby="confirmation-doctor-heading"
            >
              <div className="confirmation__doctor-heading">
                <p className="confirmation__doctor-label">
                  {translate(
                    language,
                    "confirmation.doctorLabel"
                  )}
                </p>

                <span
                  className="confirmation__doctor-badge"
                  aria-hidden="true"
                >
                  ✓
                </span>
              </div>

              <div className="confirmation__doctor-card">
                <div
                  className="confirmation__doctor-icon"
                  aria-hidden="true"
                >
                  {getDoctorInitials(
                    doctor.name
                  )}
                </div>

                <div className="confirmation__doctor-details">
                  <h2 id="confirmation-doctor-heading">
                    {doctor.name}
                  </h2>

                  {doctor.specialization && (
                    <p className="confirmation__doctor-specialization">
                      {
                        doctor.specialization
                      }
                    </p>
                  )}

                  {doctor.department &&
                    doctor.department !==
                      doctor.specialization && (
                      <p className="confirmation__doctor-department">
                        {
                          doctor.department
                        }
                      </p>
                    )}
                </div>
              </div>

              <div className="confirmation__direction">
                <span
                  className="confirmation__direction-icon"
                  aria-hidden="true"
                >
                  →
                </span>

                <p>
                  {translate(
                    language,
                    "confirmation.doctorInstruction"
                  )}
                </p>
              </div>
            </section>
          )}

          {/* Completion status */}

          <div className="confirmation__status">

            <div className="confirmation__status-item">
              <span aria-hidden="true">
                ✓
              </span>

              <p>
                {translate(
                  language,
                  "confirmation.statusPatient"
                )}
              </p>
            </div>

            <div className="confirmation__status-item">
              <span aria-hidden="true">
                ✓
              </span>

              <p>
                {translate(
                  language,
                  "confirmation.statusHistory"
                )}
              </p>
            </div>

            <div className="confirmation__status-item">
              <span aria-hidden="true">
                ✓
              </span>

              <p>
                {translate(
                  language,
                  "confirmation.statusReview"
                )}
              </p>
            </div>

          </div>

          {/* Error */}

          {error && (
            <p
              className="confirmation__error"
              role="alert"
            >
              {error}
            </p>
          )}

          {/* Finish kiosk session */}

          <button
            type="button"
            className="confirmation__continue"
            onClick={
              handleContinue
            }
            disabled={
              isCompleting ||
              completed
            }
          >
            {isCompleting
              ? translate(
                  language,
                  "common.loading"
                )
              : completed
                ? "Completed"
                : translate(
                    language,
                    "confirmation.continue"
                  )}

            {!isCompleting &&
              !completed && (
                <span
                  aria-hidden="true"
                >
                  →
                </span>
              )}
          </button>

          {/* Patient reminder */}

          <p className="confirmation__note">
            {translate(
              language,
              "confirmation.note"
            )}
          </p>

        </div>
      </section>
    </main>
  );
}