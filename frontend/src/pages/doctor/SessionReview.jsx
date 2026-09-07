import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../../services/api";

import "./doctor.css";


export default function SessionReview() {
  const navigate = useNavigate();
  const { sessionId } = useParams();

  const doctorId = sessionStorage.getItem("doctorId");

  const [review, setReview] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const [isSaving, setIsSaving] = useState(false);
  const [showEditor, setShowEditor] = useState(false);
  const [editedContent, setEditedContent] = useState("");
  const [actionError, setActionError] = useState("");


  // ============================================================
  // Load review
  // ============================================================

  useEffect(() => {
    if (!doctorId) {
      navigate("/doctor/login");
      return;
    }

    loadReview();
  }, [doctorId, sessionId]);


  async function loadReview() {
    setIsLoading(true);
    setError("");

    try {
      const data = await api(
        `/doctors/${doctorId}/sessions/${sessionId}/review`
      );

      setReview(data);

      if (data?.summary?.content) {
        setEditedContent(data.summary.content);
      }

    } catch (err) {
      console.error(
        "Failed to load session review:",
        err
      );

      setError(
        err.message ||
          "Unable to load this patient session."
      );

    } finally {
      setIsLoading(false);
    }
  }


  // ============================================================
  // Parse summary
  // ============================================================

  const summaryContent = useMemo(() => {
    if (!review?.summary?.content) {
      return null;
    }

    try {
      return JSON.parse(review.summary.content);
    } catch (err) {
      console.error(
        "Unable to parse summary content:",
        err
      );

      return null;
    }
  }, [review]);


  const sections =
    summaryContent?.summary?.sections || {};


  // ============================================================
  // Formatting helpers
  // ============================================================

  function formatLabel(value) {
    return String(value)
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) =>
        letter.toUpperCase()
      );
  }


  function formatValue(value) {
    if (
      value === null ||
      value === undefined
    ) {
      return "Not available";
    }

    if (typeof value === "string") {
      return value || "Not available";
    }

    if (Array.isArray(value)) {
      if (value.length === 0) {
        return "None recorded";
      }

      return value
        .map((item) => {
          if (
            typeof item === "object" &&
            item !== null
          ) {
            if (
              item.answer !== undefined
            ) {
              return item.answer;
            }

            if (
              item.value !== undefined
            ) {
              return formatValue(item.value);
            }

            return JSON.stringify(item);
          }

          return String(item);
        })
        .join("\n");
    }

    if (typeof value === "object") {
      return Object.entries(value)
        .map(
          ([key, item]) =>
            `${formatLabel(key)}: ${formatValue(item)}`
        )
        .join("\n");
    }

    return String(value);
  }


  // ============================================================
  // Render clinical section
  // ============================================================

  function renderSection(title, section) {
    let hasContent = false;

    if (Array.isArray(section)) {
      hasContent = section.length > 0;
    } else if (
      section &&
      typeof section === "object"
    ) {
      hasContent =
        Object.keys(section).length > 0;
    }

    return (
      <section
        className="review-section"
        key={title}
      >
        <div className="review-section__header">
          <h2>{title}</h2>
        </div>

        {hasContent ? (
          <div className="review-section__content">

            {Array.isArray(section) ? (
              section.map((item, index) => (
                <div
                  className="review-item"
                  key={index}
                >
                  {typeof item === "object" &&
                  item !== null ? (
                    <>
                      {item.question && (
                        <div className="review-item__question">
                          {item.question}
                        </div>
                      )}

                      {item.answer !== undefined && (
                        <div className="review-item__answer">
                          {formatValue(item.answer)}
                        </div>
                      )}

                      {!item.question &&
                        item.answer === undefined && (
                          <div className="review-item__answer">
                            {formatValue(item)}
                          </div>
                        )}
                    </>
                  ) : (
                    <div className="review-item__answer">
                      {formatValue(item)}
                    </div>
                  )}
                </div>
              ))
            ) : (
              Object.entries(section).map(
                ([key, value]) => (
                  <div
                    className="review-item"
                    key={key}
                  >
                    <div className="review-item__question">
                      {formatLabel(key)}
                    </div>

                    <div className="review-item__answer">
                      {formatValue(value)}
                    </div>
                  </div>
                )
              )
            )}

          </div>
        ) : (
          <div className="review-section__empty">
            No information recorded.
          </div>
        )}
      </section>
    );
  }


  // ============================================================
  // Accept summary
  // ============================================================

  async function acceptSummary() {
    if (!review?.summary?.id) {
      setActionError(
        "No summary is available to approve."
      );
      return;
    }

    setIsSaving(true);
    setActionError("");

    try {
      await api(
        `/summaries/${review.summary.id}`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            status: "accepted",
          }),
        }
      );

      await loadReview();

    } catch (err) {
      console.error(
        "Failed to accept summary:",
        err
      );

      setActionError(
        err.message ||
          "Failed to approve the summary."
      );

    } finally {
      setIsSaving(false);
    }
  }


  // ============================================================
  // Reject summary
  // ============================================================

  async function rejectSummary() {
    if (!review?.summary?.id) {
      setActionError(
        "No summary is available to reject."
      );
      return;
    }

    const confirmed = window.confirm(
      "Reject this clinical summary?"
    );

    if (!confirmed) {
      return;
    }

    setIsSaving(true);
    setActionError("");

    try {
      await api(
        `/summaries/${review.summary.id}`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            status: "rejected",
          }),
        }
      );

      await loadReview();

    } catch (err) {
      console.error(
        "Failed to reject summary:",
        err
      );

      setActionError(
        err.message ||
          "Failed to reject the summary."
      );

    } finally {
      setIsSaving(false);
    }
  }


  // ============================================================
  // Start editing
  // ============================================================

  function startEditing() {
    if (!review?.summary) {
      return;
    }

    setEditedContent(
      review.summary.content || ""
    );

    setActionError("");
    setShowEditor(true);
  }


  // ============================================================
  // Save edited summary
  // ============================================================

  async function saveEditedSummary() {
    if (!review?.summary?.id) {
      return;
    }

    if (!editedContent.trim()) {
      setActionError(
        "Summary cannot be empty."
      );
      return;
    }

    try {
      JSON.parse(editedContent);
    } catch {
      setActionError(
        "The edited summary must contain valid JSON."
      );
      return;
    }

    setIsSaving(true);
    setActionError("");

    try {
      await api(
        `/summaries/${review.summary.id}`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            content: editedContent.trim(),
            status: "accepted",
          }),
        }
      );

      setShowEditor(false);

      await loadReview();

    } catch (err) {
      console.error(
        "Failed to save edited summary:",
        err
      );

      setActionError(
        err.message ||
          "Failed to save the edited summary."
      );

    } finally {
      setIsSaving(false);
    }
  }


  // ============================================================
  // Loading
  // ============================================================

  if (isLoading) {
    return (
      <main className="doctor-page">

        <div className="doctor-loading">
          <div className="doctor-loading__spinner" />

          <p>
            Loading patient record...
          </p>
        </div>

      </main>
    );
  }


  // ============================================================
  // Error
  // ============================================================

  if (error) {
    return (
      <main className="doctor-page">

        <div className="doctor-error-card">

          <div className="doctor-error-card__icon">
            !
          </div>

          <h1>
            Unable to load case
          </h1>

          <p>{error}</p>

          <button
            type="button"
            className="doctor-button doctor-button--primary"
            onClick={() =>
              navigate("/doctor")
            }
          >
            Back to Dashboard
          </button>

        </div>

      </main>
    );
  }


  // ============================================================
  // Patient / summary information
  // ============================================================

  const patient = review?.patient;

  const summaryStatus =
    review?.summary?.status || "draft";

  const verificationStatus =
    summaryContent?.summary
      ?.verification_status ||
    "needs_review";


  // ============================================================
  // Main UI
  // ============================================================

  return (
    <main className="doctor-page">

      {/* ======================================================
          TOP BAR
          ====================================================== */}

      <header className="doctor-topbar">

        <div className="doctor-topbar__brand">

          <button
            type="button"
            className="doctor-topbar__back"
            onClick={() =>
              navigate("/doctor")
            }
            aria-label="Back to dashboard"
          >
            ←
          </button>


          {/* ==================================================
              MEDIKIOSK LOGO
              ================================================== */}

          <div className="doctor-brand-mini">
            <img
              src="/medikiosk-logo.png"
              alt="MediKiosk logo"
            />
          </div>


          <div>

            <div className="doctor-topbar__title">
              MediKiosk
            </div>

            <div className="doctor-topbar__subtitle">
              Clinical Review
            </div>

          </div>

        </div>


        <div className="doctor-topbar__right">

          <span className="doctor-session-id">
            Session #{sessionId}
          </span>

          <button
            type="button"
            className="doctor-topbar__logout"
            onClick={() => {
              sessionStorage.removeItem(
                "doctorId"
              );

              navigate("/doctor/login");
            }}
          >
            Sign out
          </button>

        </div>

      </header>


      {/* ======================================================
          REVIEW PAGE
          ====================================================== */}

      <div className="doctor-review-layout">

        {/* ====================================================
            PATIENT HEADER
            ==================================================== */}

        <section className="doctor-patient-header">

          <div className="doctor-patient-header__identity">

            <div className="doctor-patient-avatar">
              {patient?.name
                ?.charAt(0)
                ?.toUpperCase() || "P"}
            </div>

            <div>

              <p className="doctor-patient-header__label">
                Patient
              </p>

              <h1>
                {patient?.name ||
                  "Unknown Patient"}
              </h1>

              <p>
                Patient ID:{" "}
                {patient?.id || "—"}
              </p>

            </div>

          </div>


          <div className="doctor-patient-header__details">

            <div>
              <span>Age</span>

              <strong>
                {patient?.age ?? "—"}
              </strong>
            </div>

            <div>
              <span>Gender</span>

              <strong>
                {patient?.gender || "—"}
              </strong>
            </div>

            <div>
              <span>Phone</span>

              <strong>
                {patient?.phone || "—"}
              </strong>
            </div>

          </div>

        </section>


        {/* ====================================================
            STATUS BAR
            ==================================================== */}

        <section className="doctor-review-status">

          <div>

            <span className="doctor-review-status__label">
              Summary status
            </span>

            <span
              className={`doctor-status doctor-status--${summaryStatus}`}
            >
              {formatLabel(summaryStatus)}
            </span>

          </div>


          <div>

            <span className="doctor-review-status__label">
              Verification
            </span>

            <span
              className={`doctor-status doctor-status--${
                verificationStatus ===
                "verified"
                  ? "accepted"
                  : "warning"
              }`}
            >
              {formatLabel(
                verificationStatus
              )}
            </span>

          </div>


          {summaryContent
            ?.summary
            ?.red_flags
            ?.length > 0 && (

            <div>

              <span className="doctor-review-status__label">
                Safety
              </span>

              <span className="doctor-status doctor-status--danger">
                Red flags detected
              </span>

            </div>

          )}

        </section>


        {/* ====================================================
            ACTION ERROR
            ==================================================== */}

        {actionError && (
          <div className="doctor-action-error">
            {actionError}
          </div>
        )}


        {/* ====================================================
            CLINICAL SUMMARY
            ==================================================== */}

        <section className="doctor-summary-card">

          <div className="doctor-summary-card__header">

            <div>

              <p className="doctor-section-eyebrow">
                AI-GENERATED DRAFT
              </p>

              <h2>
                Clinical History Summary
              </h2>

              <p>
                Review the generated history
                before consultation.
              </p>

            </div>


            {review?.summary && (
              <span className="doctor-draft-badge">
                Physician review required
              </span>
            )}

          </div>


          {/* No summary */}

          {!review?.summary ? (

            <div className="doctor-empty-state">

              <h3>
                No summary available
              </h3>

              <p>
                A clinical summary has not
                been generated for this session.
              </p>

            </div>

          ) : showEditor ? (

            /* ==================================================
               EDITOR
               ================================================== */

            <div className="doctor-editor">

              <label htmlFor="summary-editor">
                Edit clinical summary
              </label>

              <p className="doctor-editor__hint">
                The summary is stored as structured
                JSON. Make your corrections and save
                when the information is clinically
                accurate.
              </p>

              <textarea
                id="summary-editor"
                value={editedContent}
                onChange={(event) =>
                  setEditedContent(
                    event.target.value
                  )
                }
                rows={26}
              />


              <div className="doctor-editor__actions">

                <button
                  type="button"
                  className="doctor-button doctor-button--secondary"
                  onClick={() => {
                    setShowEditor(false);
                    setActionError("");
                  }}
                  disabled={isSaving}
                >
                  Cancel
                </button>


                <button
                  type="button"
                  className="doctor-button doctor-button--primary"
                  onClick={
                    saveEditedSummary
                  }
                  disabled={isSaving}
                >
                  {isSaving
                    ? "Saving..."
                    : "Save & Accept"}
                </button>

              </div>

            </div>

          ) : (

            /* ==================================================
               READ-ONLY SUMMARY
               ================================================== */

            <div className="doctor-summary-content">

              {renderSection(
                "Chief Complaint",
                sections.chief_complaints
              )}

              {renderSection(
                "History of Present Illness",
                sections.history_of_present_illness
              )}

              {renderSection(
                "Past Medical / Surgical History",
                sections.medical_history
              )}

              {renderSection(
                "Drug History",
                sections.medication_history
              )}

              {renderSection(
                "Allergies",
                sections.allergies
              )}

              {renderSection(
                "Relevant Symptoms",
                sections.relevant_symptoms
              )}

              {renderSection(
                "Review of Systems",
                sections.relevant_negatives
              )}

              {renderSection(
                "Prior Investigations",
                sections.investigations
              )}

              {renderSection(
                "Document-Derived Findings",
                sections.document_derived_findings
              )}

              {renderSection(
                "Timeline",
                sections.timeline
              )}

              {renderSection(
                "Family History",
                sections.family_history
              )}

              {renderSection(
                "Personal History",
                sections.personal_history
              )}

              {renderSection(
                "Other Information",
                sections.other
              )}

            </div>

          )}

        </section>


        {/* ====================================================
            RED FLAGS
            ==================================================== */}

        {summaryContent
          ?.summary
          ?.red_flags
          ?.length > 0 && (

          <section className="doctor-alert-card">

            <div className="doctor-alert-card__icon">
              !
            </div>

            <div>

              <h2>
                Red Flags
              </h2>

              <p>
                The system detected information
                requiring physician attention.
              </p>

              <ul>

                {summaryContent.summary.red_flags.map(
                  (flag, index) => (
                    <li key={index}>
                      {formatValue(flag)}
                    </li>
                  )
                )}

              </ul>

            </div>

          </section>

        )}


        {/* ====================================================
            DOCUMENTS
            ==================================================== */}

        <section className="doctor-documents-card">

          <div className="doctor-card-heading">

            <div>

              <p className="doctor-section-eyebrow">
                MODULE B
              </p>

              <h2>
                Medical Documents
              </h2>

            </div>

            <span>
              {review?.documents?.length || 0}{" "}
              document(s)
            </span>

          </div>


          {review?.documents?.length ? (

            <div className="doctor-documents-list">

              {review.documents.map(
                (document) => (

                  <div
                    className="doctor-document-row"
                    key={document.id}
                  >

                    <div className="doctor-document-icon">
                      DOC
                    </div>


                    <div className="doctor-document-info">

                      <strong>
                        {document.filename ||
                          "Medical document"}
                      </strong>

                      <span>
                        {document.document_type ||
                          "Medical document"}
                      </span>

                    </div>


                    <span
                      className={`doctor-document-status doctor-document-status--${
                        document.processing_status ||
                        "unknown"
                      }`}
                    >
                      {formatLabel(
                        document.processing_status ||
                          "unknown"
                      )}
                    </span>

                  </div>

                )
              )}

            </div>

          ) : (

            <div className="doctor-card-empty">
              No documents were uploaded
              for this session.
            </div>

          )}

        </section>


        {/* ====================================================
            RAW RESPONSES
            ==================================================== */}

        <section className="doctor-responses-card">

          <details>

            <summary>
              View patient interview responses
            </summary>

            <div className="doctor-responses-list">

              {review?.responses?.length ? (

                review.responses.map(
                  (response, index) => (

                    <div
                      className="doctor-response-row"
                      key={
                        response.id ||
                        index
                      }
                    >

                      <div className="doctor-response-question">
                        {response.question ||
                          `Question ${index + 1}`}
                      </div>

                      <div className="doctor-response-answer">
                        {response.answer ||
                          "No answer recorded"}
                      </div>

                    </div>

                  )
                )

              ) : (

                <p>
                  No interview responses
                  available.
                </p>

              )}

            </div>

          </details>

        </section>


        {/* ====================================================
            PHYSICIAN DECISION
            ==================================================== */}

        {review?.summary &&
          !showEditor && (

          <section className="doctor-decision-card">

            <div>

              <p className="doctor-section-eyebrow">
                PHYSICIAN DECISION
              </p>

              <h2>
                Verify this clinical summary
              </h2>

              <p>
                Review the generated information
                and confirm whether it is suitable
                for consultation.
              </p>

            </div>


            <div className="doctor-decision-actions">

              <button
                type="button"
                className="doctor-button doctor-button--secondary"
                onClick={
                  startEditing
                }
                disabled={isSaving}
              >
                Edit & Accept
              </button>


              <button
                type="button"
                className="doctor-button doctor-button--primary"
                onClick={
                  acceptSummary
                }
                disabled={
                  isSaving ||
                  summaryStatus ===
                    "accepted"
                }
              >
                {isSaving
                  ? "Saving..."
                  : summaryStatus ===
                      "accepted"
                    ? "Accepted"
                    : "Accept Summary"}
              </button>


              <button
                type="button"
                className="doctor-button doctor-button--danger"
                onClick={
                  rejectSummary
                }
                disabled={
                  isSaving ||
                  summaryStatus ===
                    "rejected"
                }
              >
                {summaryStatus ===
                "rejected"
                  ? "Rejected"
                  : "Reject"}
              </button>

            </div>

          </section>

        )}

      </div>

    </main>
  );
}