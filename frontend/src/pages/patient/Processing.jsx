import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useKiosk } from "../../context/KioskContext";

import {
  assignDoctorToSession,
  getSession,
} from "../../services/sessionService";

import { translate } from "../../i18n";

import { documentService } from "../../services/documentService";
import { api } from "../../services/api";

import "./Processing.css";

export default function Processing() {
  const navigate = useNavigate();

  const {
    state,
    setSession,
  } = useKiosk();

  const language = state.language || "en";

  const [error, setError] = useState("");
  const [isProcessing, setIsProcessing] = useState(true);

  /*
   * Prevent duplicate processing.
   *
   * StrictMode can execute effects more than once
   * during development.
   */
  const processingStartedRef = useRef(false);

  /*
   * Prevent state updates after component unmount.
   */
  const mountedRef = useRef(true);

  /*
   * Store the session ID used by this processing run.
   *
   * This protects against accidental context changes
   * while processing is still running.
   */
  const processingSessionIdRef = useRef(null);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
    };
  }, []);

  /*
   * ============================================================
   * Helpers
   * ============================================================
   */

  function getErrorMessage(errorValue) {
    if (!errorValue) {
      return translate(
        language,
        "common.error"
      );
    }

    if (typeof errorValue === "string") {
      return errorValue;
    }

    if (errorValue instanceof Error) {
      return errorValue.message;
    }

    if (typeof errorValue === "object") {
      if (
        typeof errorValue.message === "string"
      ) {
        return errorValue.message;
      }

      if (
        typeof errorValue.detail === "string"
      ) {
        return errorValue.detail;
      }

      if (
        Array.isArray(errorValue.detail)
      ) {
        return errorValue.detail
          .map((item) => {
            if (
              typeof item === "string"
            ) {
              return item;
            }

            if (
              item &&
              typeof item.msg === "string"
            ) {
              return item.msg;
            }

            return JSON.stringify(item);
          })
          .join(", ");
      }

      try {
        return JSON.stringify(
          errorValue
        );
      } catch {
        return translate(
          language,
          "common.error"
        );
      }
    }

    return String(errorValue);
  }

  /*
   * ============================================================
   * Main processing pipeline
   * ============================================================
   */

  const processSession = useCallback(
    async () => {
      const sessionId =
        state.session?.id;

      const documents =
        Array.isArray(state.documents)
          ? state.documents
          : [];

      /*
       * --------------------------------------------------------
       * Basic validation
       * --------------------------------------------------------
       */

      if (!sessionId) {
        throw new Error(
          "Session ID is missing. Please restart the consultation."
        );
      }

      if (!state.patient?.id) {
        throw new Error(
          "Patient information is missing. Please restart the consultation."
        );
      }

      processingSessionIdRef.current =
        sessionId;

      console.log(
        "================================================"
      );

      console.log(
        "PROCESSING: starting pipeline"
      );

      console.log(
        "PROCESSING: sessionId =",
        sessionId
      );

      console.log(
        "PROCESSING: patientId =",
        state.patient.id
      );

      console.log(
        "PROCESSING: documents =",
        documents
      );

      /*
       * --------------------------------------------------------
       * STEP 0: Verify session
       * --------------------------------------------------------
       *
       * The patient token is automatically attached
       * by api() because getSession() uses patient auth.
       *
       * This prevents us from continuing with an expired
       * or completed consultation.
       */

      console.log(
        "PROCESSING: verifying session"
      );

      const currentSession =
        await getSession(sessionId);

      console.log(
        "PROCESSING: current session =",
        currentSession
      );

      /*
       * Make sure the backend still considers
       * this consultation active.
       */
      if (
        currentSession?.status &&
        currentSession.status !== "active"
      ) {
        throw new Error(
          "This consultation is no longer active. Please start a new consultation."
        );
      }

      /*
       * Make sure the session being processed
       * is still the same session in context.
       */
      if (
        String(
          currentSession?.id
        ) !== String(sessionId)
      ) {
        throw new Error(
          "The consultation session changed unexpectedly. Please restart the consultation."
        );
      }

      /*
       * Keep the latest backend session data.
       */
      if (
        mountedRef.current &&
        currentSession?.id
      ) {
        setSession(currentSession);
      }

      /*
       * --------------------------------------------------------
       * STEP 1: OCR DOCUMENTS
       * --------------------------------------------------------
       */

      console.log(
        "PROCESSING: starting document processing"
      );

      for (
        let index = 0;
        index < documents.length;
        index += 1
      ) {
        const document =
          documents[index];

        /*
         * Make sure the session has not changed
         * during a long OCR operation.
         */
        if (
          String(
            processingSessionIdRef.current
          ) !== String(sessionId)
        ) {
          throw new Error(
            "Consultation session changed during document processing."
          );
        }

        if (!document?.id) {
          throw new Error(
            "Uploaded document ID is missing."
          );
        }

        console.log(
          `PROCESSING: OCR ${index + 1}/${documents.length}`,
          document.id
        );

        /*
         * The backend owns document processing state.
         *
         * We deliberately call the existing service instead
         * of trying to reproduce OCR logic in the frontend.
         */
        const ocrResult =
          await documentService.process(
            document.id
          );

        console.log(
          "PROCESSING: OCR completed",
          {
            documentId:
              document.id,
            result:
              ocrResult,
          }
        );
      }

      /*
       * --------------------------------------------------------
       * STEP 2: GENERATE SUMMARY
       * --------------------------------------------------------
       */

      console.log(
        "PROCESSING: all OCR complete"
      );

      console.log(
        "PROCESSING: generating summary"
      );

      /*
       * Verify the session again before summary
       * generation because OCR can take time.
       */
      const sessionBeforeSummary =
        await getSession(sessionId);

      if (
        sessionBeforeSummary?.status &&
        sessionBeforeSummary.status !== "active"
      ) {
        throw new Error(
          "The consultation is no longer active. Summary generation cannot continue."
        );
      }

      console.log(
        "PROCESSING: summary URL =",
        `/summaries/session/${sessionId}/generate`
      );

      /*
       * IMPORTANT:
       *
       * Patient authentication is required here.
       *
       * api() automatically adds:
       *
       * X-Patient-Session-Token
       */
      const summaryResult =
        await api(
          `/summaries/session/${sessionId}/generate`,
          {
            method: "POST",
            auth: "patient",
          }
        );

      console.log(
        "PROCESSING: summary generated",
        summaryResult
      );

      /*
       * --------------------------------------------------------
       * STEP 3: ASSIGN DOCTOR
       * --------------------------------------------------------
       */

      const consultationMode =
        state.mode || "allopathy";

      console.log(
        "PROCESSING: assigning doctor",
        {
          sessionId,
          mode: consultationMode,
        }
      );

      const assignedSession =
        await assignDoctorToSession(
          sessionId,
          consultationMode
        );

      console.log(
        "PROCESSING: doctor assignment result",
        assignedSession
      );

      if (
        !assignedSession?.id
      ) {
        throw new Error(
          "The server did not return the updated session after doctor assignment."
        );
      }

      /*
       * Make sure backend did not accidentally
       * return another session.
       */
      if (
        String(
          assignedSession.id
        ) !== String(sessionId)
      ) {
        throw new Error(
          "Doctor assignment returned an unexpected consultation session."
        );
      }

      /*
       * Store the backend-authoritative session.
       */
      if (mountedRef.current) {
        setSession(
          assignedSession
        );
      }

      /*
       * --------------------------------------------------------
       * STEP 4: CONFIRMATION
       * --------------------------------------------------------
       *
       * DO NOT complete the session here.
       *
       * The consultation is still active until the
       * final consultation lifecycle step.
       */

      console.log(
        "PROCESSING: pipeline completed successfully"
      );

      console.log(
        "PROCESSING: navigating to confirmation"
      );

      if (mountedRef.current) {
        navigate(
          "/confirmation",
          {
            replace: true,
          }
        );
      }
    },
    [
      navigate,
      setSession,
      state.documents,
      state.mode,
      state.patient,
      state.session,
      language,
    ]
  );

  /*
   * ============================================================
   * Start processing
   * ============================================================
   */

  useEffect(() => {
    if (
      processingStartedRef.current
    ) {
      console.log(
        "PROCESSING: duplicate effect ignored"
      );

      return;
    }

    processingStartedRef.current =
      true;

    setError("");
    setIsProcessing(true);

    processSession()
      .catch((err) => {
        console.error(
          "================================================"
        );

        console.error(
          "PROCESSING: FAILED"
        );

        console.error(
          "PROCESSING: error",
          err
        );

        console.error(
          "PROCESSING: message",
          err?.message
        );

        console.error(
          "================================================"
        );

        if (
          mountedRef.current
        ) {
          setError(
            getErrorMessage(err)
          );

          setIsProcessing(
            false
          );
        }
      });

    /*
     * Intentionally only run once for this
     * Processing page instance.
     */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /*
   * ============================================================
   * Retry
   * ============================================================
   */

  async function handleRetry() {
    if (isProcessing) {
      return;
    }

    /*
     * Allow a fresh processing attempt.
     */
    processingStartedRef.current =
      true;

    setError("");
    setIsProcessing(true);

    try {
      await processSession();
    } catch (err) {
      console.error(
        "PROCESSING: retry failed",
        err
      );

      if (
        mountedRef.current
      ) {
        setError(
          getErrorMessage(err)
        );

        setIsProcessing(
          false
        );
      }
    }
  }

  /*
   * ============================================================
   * Render
   * ============================================================
   */

  return (
    <main className="processing">
      <section className="processing__container">
        <div className="processing__card">

          {/* Loading indicator */}

          {isProcessing && (
            <div className="processing__indicator">
              <div className="processing__spinner" />
            </div>
          )}

          {!isProcessing && error && (
            <div className="processing__indicator">
              <div
                style={{
                  fontSize: "42px",
                }}
              >
                ⚠️
              </div>
            </div>
          )}

          {/* Heading */}

          <p className="processing__eyebrow">
            {translate(
              language,
              "processing.eyebrow"
            )}
          </p>

          <h1>
            {isProcessing
              ? translate(
                  language,
                  "processing.title"
                )
              : "Processing could not be completed"}
          </h1>

          <p className="processing__description">
            {isProcessing
              ? translate(
                  language,
                  "processing.description"
                )
              : "There was a problem while preparing your consultation. Your interview data has not been intentionally discarded."}
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

            <div
              className={
                isProcessing
                  ? "processing__step"
                  : "processing__step processing__step--active"
              }
            >
              <span>
                {isProcessing
                  ? (
                    <span className="processing__dot" />
                  )
                  : "!"}
              </span>

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
            <div
              className="processing__error"
              role="alert"
            >
              {error}
            </div>
          )}

          {/* Retry */}

          {!isProcessing && error && (
            <button
              type="button"
              onClick={
                handleRetry
              }
              style={{
                width: "100%",
                marginTop: "20px",
                padding: "14px 20px",
                borderRadius: "12px",
                border: "none",
                cursor: "pointer",
                fontSize: "16px",
                fontWeight: "700",
              }}
            >
              Try again
            </button>
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