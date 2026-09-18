import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useKiosk } from "../../context/KioskContext";
import { translate } from "../../i18n";

import DocumentUploader from "../../components/patient/DocumentUploader";
import { documentService } from "../../services/documentService";

import "./Documents.css";

const DOCUMENT_TYPES = [
  {
    id: "prescription",
    icon: "Rx",
  },
  {
    id: "labReport",
    icon: "LAB",
  },
  {
    id: "dischargeSummary",
    icon: "DOC",
  },
  {
    id: "other",
    icon: "FILE",
  },
];

const BACKEND_DOCUMENT_TYPES = {
  prescription: "prescription",
  labReport: "lab_report",
  dischargeSummary: "discharge_summary",
  other: "other",
};

function getErrorMessage(errorValue, language) {
  if (!errorValue) {
    return translate(language, "common.error");
  }

  if (typeof errorValue === "string") {
    return errorValue;
  }

  if (errorValue instanceof Error) {
    return errorValue.message;
  }

  if (typeof errorValue === "object") {
    if (typeof errorValue.message === "string") {
      return errorValue.message;
    }

    if (typeof errorValue.detail === "string") {
      return errorValue.detail;
    }

    try {
      return JSON.stringify(errorValue);
    } catch {
      return translate(language, "common.error");
    }
  }

  return String(errorValue);
}

export default function Documents() {
  const navigate = useNavigate();

  const { state, addDocument } = useKiosk();

  const language = state.language || "en";

  const [documentType, setDocumentType] =
    useState("prescription");

  const [documents, setDocuments] =
    useState([]);

  const [error, setError] =
    useState("");

  const [isUploading, setIsUploading] =
    useState(false);

  /*
   * ============================================================
   * Validate the current consultation context
   * ============================================================
   *
   * Documents belong to the current patient + session.
   *
   * IMPORTANT:
   * The session must still be ACTIVE while the patient is on
   * this page. Interview completion does NOT complete the whole
   * consultation. Final session completion belongs at the true
   * end of the workflow.
   */
  function validateSessionContext() {
    if (!state.patient?.id) {
      throw new Error(
        translate(
          language,
          "documents.patientRequired"
        )
      );
    }

    if (!state.session?.id) {
      throw new Error(
        translate(
          language,
          "documents.sessionRequired"
        )
      );
    }

    if (
      state.session.status &&
      state.session.status !== "active"
    ) {
      throw new Error(
        "This consultation session is no longer active. Please restart the consultation."
      );
    }
  }

  /*
   * ============================================================
   * Add file locally
   * ============================================================
   */
  function handleFileAdd(file) {
    if (!file || isUploading) {
      return;
    }

    setDocuments((current) => [
      ...current,
      {
        id: `${Date.now()}-${file.name}-${Math.random()
          .toString(36)
          .slice(2)}`,
        file,
        type: documentType,
      },
    ]);

    setError("");
  }

  /*
   * ============================================================
   * Remove local file
   * ============================================================
   */
  function handleRemove(id) {
    if (isUploading) {
      return;
    }

    setDocuments((current) =>
      current.filter(
        (document) =>
          document.id !== id
      )
    );

    setError("");
  }

  /*
   * ============================================================
   * Upload documents
   * ============================================================
   */
  async function uploadDocuments() {
    validateSessionContext();

    const uploadedDocuments = [];

    for (const document of documents) {
      if (!document?.file) {
        continue;
      }

      const formData = new FormData();

      formData.append(
        "patient_id",
        String(state.patient.id)
      );

      formData.append(
        "session_id",
        String(state.session.id)
      );

      formData.append(
        "document_type",
        BACKEND_DOCUMENT_TYPES[document.type] ||
          "other"
      );

      formData.append(
        "file",
        document.file
      );

      const response =
        await documentService.upload(
          formData
        );

      if (!response?.id) {
        throw new Error(
          "The document upload did not return a document ID."
        );
      }

      uploadedDocuments.push(response);

      /*
       * Keep the backend document ID in kiosk state.
       * Processing.jsx can use these IDs for OCR/processing.
       */
      addDocument(response);
    }

    return uploadedDocuments;
  }

  /*
   * ============================================================
   * Continue
   * ============================================================
   */
  async function handleContinue() {
    if (isUploading) {
      return;
    }

    setError("");

    try {
      /*
       * Always validate the session before leaving this page,
       * including when there are no documents.
       */
      validateSessionContext();

      /*
       * No documents is a valid choice.
       * Do NOT complete the session here.
       */
      if (documents.length === 0) {
        navigate("/processing");
        return;
      }

      setIsUploading(true);

      await uploadDocuments();

      navigate("/processing");
    } catch (err) {
      console.error(
        "Failed to continue from documents:",
        err
      );

      setError(
        getErrorMessage(
          err,
          language
        )
      );
    } finally {
      setIsUploading(false);
    }
  }

  /*
   * ============================================================
   * Skip
   * ============================================================
   */
  function handleSkip() {
    if (isUploading) {
      return;
    }

    setError("");

    try {
      validateSessionContext();
      navigate("/processing");
    } catch (err) {
      console.error(
        "Failed to skip documents:",
        err
      );

      setError(
        getErrorMessage(
          err,
          language
        )
      );
    }
  }

  /*
   * ============================================================
   * Back
   * ============================================================
   */
  function handleBack() {
    if (isUploading) {
      return;
    }

    setError("");
    navigate("/interview");
  }

  return (
    <main className="documents">
      <section className="documents__container">

        {/* =====================================================
            HEADER
            ===================================================== */}

        <header className="documents__header">

          <button
            type="button"
            className="documents__back"
            onClick={handleBack}
            disabled={isUploading}
          >
            ←{" "}
            {translate(
              language,
              "common.back"
            )}
          </button>

        </header>

        {/* =====================================================
            INTRO
            ===================================================== */}

        <div className="documents__intro">

          <p className="documents__eyebrow">
            {translate(
              language,
              "documents.eyebrow"
            )}
          </p>

          <h1>
            {translate(
              language,
              "documents.title"
            )}
          </h1>

          <p>
            {translate(
              language,
              "documents.description"
            )}
          </p>

        </div>

        {/* =====================================================
            DOCUMENT CARD
            ===================================================== */}

        <section className="documents__card">

          <h2>
            {translate(
              language,
              "documents.documentType"
            )}
          </h2>

          {/* DOCUMENT TYPES */}

          <div className="documents__types">

            {DOCUMENT_TYPES.map((type) => (

              <button
                key={type.id}
                type="button"
                className={`documents__type ${
                  documentType === type.id
                    ? "documents__type--selected"
                    : ""
                }`}
                onClick={() => {
                  setDocumentType(type.id);
                  setError("");
                }}
                disabled={isUploading}
              >

                <span className="documents__type-icon">
                  {type.icon}
                </span>

                <span>
                  {translate(
                    language,
                    `documents.${type.id}`
                  )}
                </span>

              </button>

            ))}

          </div>

          {/* UPLOADER */}

          <DocumentUploader
            onFileAdd={handleFileAdd}
          />

          {/* SELECTED DOCUMENTS */}

          {documents.length > 0 && (

            <div className="documents__selected">

              <h3>
                {translate(
                  language,
                  "documents.selected"
                )}
              </h3>

              <div className="documents__list">

                {documents.map(
                  (document) => (

                    <div
                      key={document.id}
                      className="documents__item"
                    >

                      <div>

                        <strong>
                          {document.file.name}
                        </strong>

                        <span>
                          {translate(
                            language,
                            `documents.${document.type}`
                          )}
                        </span>

                      </div>

                      <button
                        type="button"
                        onClick={() =>
                          handleRemove(
                            document.id
                          )
                        }
                        disabled={isUploading}
                      >
                        ×
                      </button>

                    </div>

                  )
                )}

              </div>

            </div>

          )}

          {/* ERROR */}

          {error && (
            <p className="documents__error">
              {error}
            </p>
          )}

          {/* ACTIONS */}

          <div className="documents__actions">

            <button
              type="button"
              className="documents__skip"
              onClick={handleSkip}
              disabled={isUploading}
            >
              {translate(
                language,
                "documents.skip"
              )}
            </button>

            <button
              type="button"
              className="documents__continue"
              onClick={handleContinue}
              disabled={isUploading}
            >

              {isUploading
                ? translate(
                    language,
                    "common.loading"
                  )
                : translate(
                    language,
                    "common.next"
                  )}

              {!isUploading && (
                <span>→</span>
              )}

            </button>

          </div>

        </section>

      </section>
    </main>
  );
}
