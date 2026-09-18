import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useKiosk } from "../../context/KioskContext";
import { translate } from "../../i18n";
import { api } from "../../services/api";

import "./Confirmation.css";

export default function Confirmation() {
  const navigate = useNavigate();

  const { state } = useKiosk();

  const language = state.language || "en";
  const session = state.session;
  const sessionId = session?.id ?? session?.session_id ?? null;

  const [doctor, setDoctor] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function loadAssignedDoctor() {
      if (!sessionId) {
        setDoctor(null);
        return;
      }

      try {
        const doctorData = await api(
          `/sessions/${encodeURIComponent(sessionId)}/doctor`,
          {
            method: "GET",
            auth: "patient",
          }
        );

        if (!cancelled) {
          setDoctor(doctorData);
        }
      } catch (error) {
        console.error("Unable to load assigned doctor:", error);

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

  function handleContinue() {
    navigate("/");
  }

  function getDoctorInitials(name) {
    if (!name) {
      return "D";
    }

    const cleanName = name
      .replace(/^Dr\.?\s*/i, "")
      .trim();

    const parts = cleanName.split(/\s+/).filter(Boolean);

    if (parts.length === 1) {
      return parts[0].charAt(0).toUpperCase();
    }

    return (
      parts[0].charAt(0) +
      parts[parts.length - 1].charAt(0)
    ).toUpperCase();
  }

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

          {/* Assigned doctor — primary patient handoff */}

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
                  {getDoctorInitials(doctor.name)}
                </div>

                <div className="confirmation__doctor-details">
                  <h2 id="confirmation-doctor-heading">
                    {doctor.name}
                  </h2>

                  {doctor.specialization && (
                    <p className="confirmation__doctor-specialization">
                      {doctor.specialization}
                    </p>
                  )}

                  {doctor.department &&
                    doctor.department !== doctor.specialization && (
                      <p className="confirmation__doctor-department">
                        {doctor.department}
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
              <span aria-hidden="true">✓</span>

              <p>
                {translate(
                  language,
                  "confirmation.statusPatient"
                )}
              </p>
            </div>

            <div className="confirmation__status-item">
              <span aria-hidden="true">✓</span>

              <p>
                {translate(
                  language,
                  "confirmation.statusHistory"
                )}
              </p>
            </div>

            <div className="confirmation__status-item">
              <span aria-hidden="true">✓</span>

              <p>
                {translate(
                  language,
                  "confirmation.statusReview"
                )}
              </p>
            </div>
          </div>

          {/* Finish kiosk session */}

          <button
            type="button"
            className="confirmation__continue"
            onClick={handleContinue}
            data-tts={translate(
              language,
              "confirmation.continue"
            )}
          >
            {translate(
              language,
              "confirmation.continue"
            )}

            <span data-no-tts aria-hidden="true">→</span>
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