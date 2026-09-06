import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useKiosk } from "../../context/KioskContext";
import { translate } from "../../i18n";

import { documentService } from "../../services/documentService";

import "./Processing.css";

export default function Processing() {
  const navigate = useNavigate();

  const { state } = useKiosk();

  const language = state.language || "en";

  const [error, setError] = useState("");

  /*
   * Prevent duplicate processing requests.
   *
   * React StrictMode can run an effect twice
   * during development. Without this guard,
   * the same document can receive two
   * processing requests and the backend
   * correctly returns 409 for the second one.
   */
  const processingStarted = useRef(false);

  useEffect(() => {
    if (processingStarted.current) {
      return;
    }

    processingStarted.current = true;

    async function processDocuments() {
      const documents = state.documents || [];

      /*
       * No documents.
       *
       * Later this same Processing page can
       * continue into AI summary generation.
       */
      if (documents.length === 0) {
        navigate("/confirmation");
        return;
      }

      try {
        /*
         * Process every uploaded document.
         *
         * The backend performs:
         *
         * upload
         *   ↓
         * OCR
         *   ↓
         * classification
         *   ↓
         * clinical extraction
         */
        for (const document of documents) {
          if (!document?.id) {
            throw new Error(
              "Uploaded document ID is missing."
            );
          }

          await documentService.process(
            document.id
          );
        }

        /*
         * All documents completed successfully.
         */
        navigate("/confirmation");
      } catch (err) {
        console.error(
          "Document processing failed:",
          err
        );

        setError(
          err.message ||
            translate(
              language,
              "common.error"
            )
        );
      }
    }

    processDocuments();
  }, [
    navigate,
    state.documents,
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