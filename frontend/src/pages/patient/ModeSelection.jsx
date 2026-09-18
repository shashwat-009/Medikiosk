import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useKiosk } from "../../context/KioskContext";
import { translate } from "../../i18n";

import {
  assignDoctorToSession,
} from "../../services/sessionService";

import "./ModeSelection.css";


export default function ModeSelection() {
  const navigate = useNavigate();

  const {
    state,
    setMode,
    setSession,
  } = useKiosk();

  const language = state.language || "en";

  const [isAssigning, setIsAssigning] =
    useState(false);

  const [error, setError] =
    useState("");


  async function handleModeSelect(mode) {
    if (isAssigning) {
      return;
    }

    if (!state.session?.id) {
      setError(
        "No active session found. Please restart the visit."
      );

      return;
    }

    setError("");
    setIsAssigning(true);

    try {
      // Store selected consultation mode
      setMode(mode);

      // Assign the appropriate doctor on the backend
      const updatedSession =
        await assignDoctorToSession(
          state.session.id,
          mode
        );

      // Store the updated session
      // This now contains doctor_id
      setSession(updatedSession);

      // Continue to interview
      navigate("/interview");

    } catch (err) {
      console.error(
        "Failed to assign doctor:",
        err
      );

      setError(
        err.message ||
          "Unable to assign a doctor. Please try again."
      );

    } finally {
      setIsAssigning(false);
    }
  }


  return (
    <main className="mode-selection">
      <section className="mode-selection__container">

        {/* Header */}

        <div className="mode-selection__header">

          <button
            type="button"
            className="mode-selection__back"
            onClick={() =>
              navigate("/consent")
            }
            disabled={isAssigning}
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

          <div className="mode-selection__step">
            3 / 3
          </div>

        </div>


        {/* Intro */}

        <div className="mode-selection__intro">

          <p className="mode-selection__eyebrow">
            {translate(
              language,
              "mode.eyebrow"
            )}
          </p>

          <h1>
            {translate(
              language,
              "mode.title"
            )}
          </h1>

          <p>
            {translate(
              language,
              "mode.description"
            )}
          </p>

        </div>


        {/* Error */}

        {error && (
          <p
            className="mode-selection__error"
            role="alert"
          >
            {error}
          </p>
        )}


        {/* Mode options */}

        <div className="mode-selection__options">

          {/* Allopathy */}

          <button
            type="button"
            className="mode-selection__card"
            onClick={() =>
              handleModeSelect(
                "allopathy"
              )
            }
            disabled={isAssigning}
            data-tts={translate(
              language,
              "mode.allopathy.title"
            )}
          >

            <div className="mode-selection__icon" data-no-tts aria-hidden="true">
              +
            </div>

            <div className="mode-selection__content">

              <h2>
                {translate(
                  language,
                  "mode.allopathy.title"
                )}
              </h2>

              <p>
                {translate(
                  language,
                  "mode.allopathy.description"
                )}
              </p>

            </div>

            <span className="mode-selection__arrow" data-no-tts aria-hidden="true">
              {isAssigning ? "..." : "→"}
            </span>

          </button>


          {/* Ayurveda / AYUSH */}

          <button
            type="button"
            className="mode-selection__card"
            onClick={() =>
              handleModeSelect(
                "ayush"
              )
            }
            disabled={isAssigning}
            data-tts={translate(
              language,
              "mode.ayush.title"
            )}
          >

            <div className="mode-selection__icon" data-no-tts aria-hidden="true">
              ॐ
            </div>

            <div className="mode-selection__content">

              <h2>
                {translate(
                  language,
                  "mode.ayush.title"
                )}
              </h2>

              <p>
                {translate(
                  language,
                  "mode.ayush.description"
                )}
              </p>

            </div>

            <span className="mode-selection__arrow" data-no-tts aria-hidden="true">
              {isAssigning ? "..." : "→"}
            </span>

          </button>

        </div>

      </section>
    </main>
  );
}