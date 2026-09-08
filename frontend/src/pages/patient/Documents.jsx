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

export default function Documents() {
  const navigate = useNavigate();

  const {
    state,
    addDocument,
  } = useKiosk();

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
   * =========================
   * Add file locally
   * =========================
   */

  function handleFileAdd(file) {
    if (!file) return;

    setDocuments((current) => [
      ...current,
      {
        id: `${Date.now()}-${file.name}`,
        file,
        type: documentType,
      },
    ]);

    setError("");
  }

  /*
   * =========================
   * Remove local file
   * =========================
   */

  function handleRemove(id) {
    setDocuments((current) =>
      current.filter(
        (document) =>
          document.id !== id
      )
    );
  }

  /*
   * =========================
   * Upload documents
   * =========================
   */

  async function uploadDocuments() {
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

    const uploadedDocuments = [];

    for (const document of documents) {
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
        BACKEND_DOCUMENT_TYPES[document.type] || "other"
      );

      formData.append(
        "file",
        document.file
      );

      const response =
        await documentService.upload(
          formData
        );

      uploadedDocuments.push(response);

      /*
       * Store the backend document.
       *
       * Processing.jsx will use these
       * backend IDs to start OCR processing.
       */
      addDocument(response);
    }

    return uploadedDocuments;
  }

  /*
   * =========================
   * Continue
   * =========================
   */

  async function handleContinue() {
    setError("");

    /*
     * No documents → continue normally.
     *
     * Processing page can later be extended
     * for AI summary generation.
     */
    if (documents.length === 0) {
      navigate("/processing");
      return;
    }

    setIsUploading(true);

    try {
      await uploadDocuments();

      navigate("/processing");
    } catch (err) {
      console.error(
        "Failed to upload documents:",
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
      setIsUploading(false);
    }
  }

  /*
   * =========================
   * Skip
   * =========================
   */

  function handleSkip() {
    if (isUploading) return;

    navigate("/processing");
  }

  /*
   * =========================
   * Back
   * =========================
   */

  function handleBack() {
    if (isUploading) return;

    navigate("/interview");
  }

  return (
    <main className="documents">
      <section className="documents__container">

        {/* =========================
            HEADER
            ========================= */}

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

        {/* =========================
            INTRO
            ========================= */}

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

        {/* =========================
            DOCUMENT CARD
            ========================= */}

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
                className={`documents__type ${documentType === type.id
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