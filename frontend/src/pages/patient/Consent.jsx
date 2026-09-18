import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useKiosk } from "../../context/KioskContext";
import { translate } from "../../i18n";

import { createConsent } from "../../services/consentService";

import "./Consent.css";

export default function Consent() {
  const navigate = useNavigate();

  const {
    state,
    setConsent,
  } = useKiosk();

  const language = state.language || "en";

  const [captureConsent, setCaptureConsent] =
    useState(false);

  const [sharingConsent, setSharingConsent] =
    useState(false);

  const [error, setError] = useState("");

  const [isSubmitting, setIsSubmitting] =
    useState(false);


  async function handleContinue(event) {
    event.preventDefault();

    // =========================
    // Frontend validation
    // =========================

    if (!captureConsent || !sharingConsent) {
      setError(
        translate(
          language,
          "consent.required"
        )
      );

      return;
    }

    // Make sure we have an active session
    if (!state.session?.id) {
      setError(
        "No active session found. Please restart the visit."
      );

      return;
    }

    setError("");
    setIsSubmitting(true);

    try {
      // =========================
      // Save consent to backend
      // =========================

      const consent = await createConsent({
        session_id: state.session.id,
        capture_consent: captureConsent,
        sharing_consent: sharingConsent,
        language,
      });

      // =========================
      // Store backend consent
      // =========================

      setConsent(consent);

      // =========================
      // Continue
      // =========================

      navigate("/mode");

    } catch (err) {
      console.error(
        "Failed to save consent:",
        err
      );

      setError(
        err.message ||
        translate(
          language,
          "common.error"
        )
      );
    } finally {
      setIsSubmitting(false);
    }
  }


  return (
    <main className="consent">
      <section className="consent__container">

        {/* =========================
            Header
            ========================= */}

        <div className="consent__header">

          <button
            type="button"
            className="consent__back"
            onClick={() =>
              navigate("/identify")
            }
            disabled={isSubmitting}
            data-tts={translate(
              language,
              "common.back"
            )}
          >
            <span data-no-tts aria-hidden="true">← </span>
            {translate(
              language,
              "common.back"
            )}
          </button>

          <div className="consent__step">
            2 / 3
          </div>

        </div>


        {/* =========================
            Intro
            ========================= */}

        <div className="consent__intro">

          <p className="consent__eyebrow">
            {translate(
              language,
              "consent.eyebrow"
            )}
          </p>

          <h1>
            {translate(
              language,
              "consent.title"
            )}
          </h1>

          <p>
            {translate(
              language,
              "consent.description"
            )}
          </p>

        </div>


        {/* =========================
            Consent form
            ========================= */}

        <form
          className="consent__card"
          onSubmit={handleContinue}
        >

          {/* Capture consent */}

          <label className="consent__option">

            <input
              type="checkbox"
              checked={captureConsent}
              onChange={(event) => {
                setCaptureConsent(
                  event.target.checked
                );

                setError("");
              }}
              disabled={isSubmitting}
            />

            <span className="consent__check" />

            <span className="consent__content">

              <strong>
                {translate(
                  language,
                  "consent.captureTitle"
                )}
              </strong>

              <span>
                {translate(
                  language,
                  "consent.capture"
                )}
              </span>

            </span>

          </label>


          {/* Sharing consent */}

          <label className="consent__option">

            <input
              type="checkbox"
              checked={sharingConsent}
              onChange={(event) => {
                setSharingConsent(
                  event.target.checked
                );

                setError("");
              }}
              disabled={isSubmitting}
            />

            <span className="consent__check" />

            <span className="consent__content">

              <strong>
                {translate(
                  language,
                  "consent.sharingTitle"
                )}
              </strong>

              <span>
                {translate(
                  language,
                  "consent.sharing"
                )}
              </span>

            </span>

          </label>


          {/* Notice */}

          <div className="consent__notice">

            <span className="consent__notice-icon">
              ⓘ
            </span>

            <p>
              {translate(
                language,
                "consent.notice"
              )}
            </p>

          </div>

          <p className="consent__dpdp-notice">
            {translate(
              language,
              "consent.dpdpNotice"
            )}
          </p>


          {/* Error */}

          {error && (
            <p className="consent__error">
              {error}
            </p>
          )}


          {/* Continue */}

          <button
            type="submit"
            className="consent__continue"
            disabled={isSubmitting}
            data-tts={
              isSubmitting
                ? translate(
                  language,
                  "common.loading"
                )
                : translate(
                  language,
                  "consent.continue"
                )
            }
          >

            {isSubmitting
              ? translate(
                language,
                "common.loading"
              )
              : translate(
                language,
                "consent.continue"
              )}

            {!isSubmitting && (
              <span data-no-tts aria-hidden="true">→</span>
            )}

          </button>

        </form>

      </section>
    </main>
  );
}