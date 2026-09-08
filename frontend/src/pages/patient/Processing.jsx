import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useKiosk } from "../../context/KioskContext";

import { assignDoctorToSession } from "../../services/sessionService";
import { translate } from "../../i18n";

import { documentService } from "../../services/documentService";
import { api } from "../../services/api";

import "./Processing.css";

export default function Processing() {
  const navigate = useNavigate();

  const { state, setSession } = useKiosk();

  const language = state.language || "en";

  const [error, setError] = useState("");

  /*
   * Prevent duplicate processing requests.
   *
   * React StrictMode can run an effect twice
   * during development.
   */
  const processingStarted = useRef(false);

  useEffect(() => {
    if (processingStarted.current) {
      console.log(
        "PROCESSING: effect skipped - already started"
      );
      return;
    }

    processingStarted.current = true;

    console.log(
      "================================================"
    );
    console.log(
      "PROCESSING: effect started"
    );
    console.log(
      "================================================"
    );

    async function processSession() {
      const documents = state.documents || [];
      const sessionId = state.session?.id;

      console.log(
        "PROCESSING: sessionId =",
        sessionId
      );

      console.log(
        "PROCESSING: documents =",
        documents
      );

      try {
        /*
         * ============================================
         * SESSION CHECK
         * ============================================
         */

        if (!sessionId) {
          console.error(
            "PROCESSING: SESSION ID MISSING"
          );

          throw new Error(
            "Session ID is missing."
          );
        }

        /*
         * ============================================
         * STEP 1: OCR DOCUMENTS
         * ============================================
         */

        console.log(
          "PROCESSING: starting document processing"
        );

        for (const document of documents) {
          console.log(
            "PROCESSING: document found =",
            document
          );

          if (!document?.id) {
            console.error(
              "PROCESSING: DOCUMENT ID MISSING",
              document
            );

            throw new Error(
              "Uploaded document ID is missing."
            );
          }

          console.log(
            "PROCESSING: starting OCR for document =",
            document.id
          );

          const ocrResult =
            await documentService.process(
              document.id
            );

          console.log(
            "PROCESSING: OCR finished successfully =",
            document.id
          );

          console.log(
            "PROCESSING: OCR response =",
            ocrResult
          );
        }

        /*
         * ============================================
         * STEP 2: SUMMARY
         * ============================================
         */

        console.log(
          "================================================"
        );

        console.log(
          "PROCESSING: ALL OCR COMPLETE"
        );

        console.log(
          "PROCESSING: starting summary generation"
        );

        console.log(
          "PROCESSING: summary URL =",
          `/summaries/session/${sessionId}/generate`
        );

        const summaryResult = await api(
          `/summaries/session/${sessionId}/generate`,
          {
            method: "POST",
          }
        );

        console.log(
          "PROCESSING: SUMMARY GENERATED SUCCESSFULLY"
        );

        console.log(
          "PROCESSING: summary response =",
          summaryResult
        );

        /*
         * ============================================
         * STEP 3: ASSIGN DOCTOR
         * ============================================
         *
         * The selected consultation mode determines
         * the department used by the backend to assign
         * the appropriate doctor.
         *
         * No doctor is hardcoded here.
         */

        console.log(
          "PROCESSING: assigning doctor for mode =",
          state.mode
        );

        const assignedSession =
          await assignDoctorToSession(
            sessionId,
            state.mode || "allopathy"
          );

        console.log(
          "PROCESSING: doctor assigned successfully =",
          assignedSession
        );

        /*
         * Keep the updated session in KioskContext.
         *
         * This makes the backend-provided doctor_id
         * available to the confirmation screen.
         */

        if (assignedSession?.id) {
          setSession(assignedSession);
        } else {
          throw new Error(
            "The server did not return the updated session after doctor assignment."
          );
        }

        /*
         * ============================================
         * STEP 4: CONFIRMATION
         * ============================================
         */

        console.log(
          "PROCESSING: navigating to confirmation"
        );

        navigate("/confirmation");

      } catch (err) {
        console.error(
          "================================================"
        );

        console.error(
          "PROCESSING: FAILED"
        );

        console.error(
          "PROCESSING: error =",
          err
        );

        console.error(
          "PROCESSING: error message =",
          err?.message
        );

        console.error(
          "================================================"
        );

        setError(
          err?.message ||
            translate(
              language,
              "common.error"
            )
        );
      }
    }

    processSession();

  }, [
    navigate,
    state.documents,
    state.session,
    language,
  ]);

  return (
    <main className="processing">
      <section className="processing__container">
        <div className="processing__card">

          {/* Loading indicator */}

          <div className="processing__indicator">
            <div className="processing__spinner" />
          </div>

          {/* Heading */}

          <p className="processing__eyebrow">
            {translate(
              language,
              "processing.eyebrow"
            )}
          </p>

          <h1>
            {translate(
              language,
              "processing.title"
            )}
          </h1>

          <p className="processing__description">
            {translate(
              language,
              "processing.description"
            )}
          </p>

          {/* Processing steps */}

          <div className="processing__steps">

            <div className="processing__step processing__step--active">
              <span>✓</span>

              <p>
                {translate(
                  language,
                  "processing.stepResponses"
                )}
              </p>
            </div>

            <div className="processing__step processing__step--active">
              <span>✓</span>

              <p>
                {translate(
                  language,
                  "processing.stepHistory"
                )}
              </p>
            </div>

            <div className="processing__step">
              <span className="processing__dot" />

              <p>
                {translate(
                  language,
                  "processing.stepReview"
                )}
              </p>
            </div>

          </div>

          {/* Processing error */}

          {error && (
            <p className="processing__error">
              {error}
            </p>
          )}

          {/* Privacy / instruction */}

          <p className="processing__note">
            {translate(
              language,
              "processing.note"
            )}
          </p>

        </div>
      </section>
    </main>
  );
}