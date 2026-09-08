import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../../services/api";
import "./edit-summary.css";

const SECTION_META = [
  {
    key: "chief_complaints",
    label: "Chief Complaint",
    short: "CC",
    description: "Why the patient is seeking care.",
    kind: "text",
  },
  {
    key: "history_of_present_illness",
    label: "History of Present Illness",
    short: "HPI",
    description:
      "Onset, duration, severity and progression of the current problem.",
    kind: "hpi",
  },
  {
    key: "medical_history",
    label: "Medical / Surgical History",
    short: "PMH",
    description: "Previous illnesses, admissions and procedures.",
    kind: "text",
  },
  {
    key: "medication_history",
    label: "Medication History",
    short: "MED",
    description: "Medicines reported by the patient.",
    kind: "text",
  },
  {
    key: "allergies",
    label: "Allergies",
    short: "ALG",
    description: "Known allergies reported during the interview.",
    kind: "text",
  },
  {
    key: "relevant_symptoms",
    label: "Relevant Symptoms",
    short: "SYM",
    description: "Additional symptoms relevant to the current complaint.",
    kind: "text",
  },
  {
    key: "relevant_negatives",
    label: "Review of Systems",
    short: "ROS",
    description:
      "Important symptoms the patient denied or did not report.",
    kind: "text",
  },
  {
    key: "investigations",
    label: "Prior Investigations",
    short: "INV",
    description: "Investigations reported by the patient.",
    kind: "text",
  },

  // Extracted clinical information from uploaded records.
  // The original uploaded file and its source evidence remain read-only.
  {
    key: "document_derived_findings",
    label: "Document Findings",
    short: "DOC",
    description:
      "Clinical findings extracted from uploaded prescriptions, lab reports and discharge records.",
    kind: "document",
  },

  {
    key: "timeline",
    label: "Clinical Timeline",
    short: "TIME",
    description: "Relevant dates and events.",
    kind: "text",
  },
  {
    key: "family_history",
    label: "Family History",
    short: "FH",
    description: "Relevant family medical history.",
    kind: "text",
  },
  {
    key: "personal_history",
    label: "Personal History",
    short: "PH",
    description: "Lifestyle and personal history.",
    kind: "text",
  },
];

const IGNORE_OBJECT_KEYS = new Set([
  "provenance",
  "source",
  "path",
  "confidence",
  "response_id",
  "responseId",
  "input_type",
  "inputType",
  "language",
  "lang",
  "matched_pattern",
  "matched_text",
  "matched_fields",
  "explanation",
  "flag_id",

  // Uploaded-document technical metadata.
  "document_id",
  "documentId",
  "filename",
  "file_name",
  "document_type",
  "documentType",
  "processing_status",
  "processingStatus",
  "ocr_text",
  "ocrText",
  "raw_text",
  "rawText",
]);

const EMPTY = new Set([
  "",
  "none",
  "none reported",
  "none recorded",
  "no",
  "n/a",
  "na",
  "nil",
  "not applicable",
  "not available",
  "—",
  "-",
]);

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function display(value) {
  if (value === null || value === undefined) return "";

  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }

  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  if (Array.isArray(value)) {
    return value.map(display).filter(Boolean).join(", ");
  }

  return "";
}

function unwrap(value) {
  if (
    value &&
    typeof value === "object" &&
    Object.prototype.hasOwnProperty.call(value, "value")
  ) {
    return value.value;
  }

  return value;
}

function isMeaningful(value) {
  const text = display(unwrap(value)).trim().toLowerCase();

  return Boolean(text && !EMPTY.has(text));
}

function visibleObjectEntries(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return [];
  }

  return Object.entries(value).filter(
    ([key, fieldValue]) =>
      !IGNORE_OBJECT_KEYS.has(key) && isMeaningful(fieldValue)
  );
}

function labelize(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

function getEditableValue(raw) {
  if (
    raw &&
    typeof raw === "object" &&
    Object.prototype.hasOwnProperty.call(raw, "value")
  ) {
    return raw.value;
  }

  return raw;
}

function setEditableValue(raw, nextValue) {
  if (
    raw &&
    typeof raw === "object" &&
    Object.prototype.hasOwnProperty.call(raw, "value")
  ) {
    // Preserve the wrapper and all provenance/source metadata.
    return {
      ...raw,
      value: nextValue,
    };
  }

  return nextValue;
}

function interviewHighlights(responses = []) {
  return responses
    .filter((item) => isMeaningful(item?.answer))
    .slice(0, 6)
    .map((item, index) => ({
      id: item?.id ?? index,
      question: item?.question || `Interview question ${index + 1}`,
      answer: display(item.answer),
    }));
}

export default function EditSummary() {
  const navigate = useNavigate();
  const { sessionId } = useParams();
  const doctorId = sessionStorage.getItem("doctorId");

  const [review, setReview] = useState(null);
  const [draft, setDraft] = useState(null);
  const [activeKey, setActiveKey] = useState("chief_complaints");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!doctorId) {
      navigate("/doctor/login");
      return;
    }

    loadReview();
  }, [doctorId, sessionId]);

  async function loadReview() {
    setLoading(true);
    setError("");

    try {
      const data = await api(
        `/doctors/${doctorId}/sessions/${sessionId}/review`
      );

      setReview(data);

      if (!data?.summary?.content) {
        setDraft(null);
        return;
      }

      const parsed = JSON.parse(data.summary.content);
      setDraft(clone(parsed));

      const available = SECTION_META.find(
        (section) =>
          Array.isArray(parsed?.summary?.sections?.[section.key]) &&
          parsed.summary.sections[section.key].length > 0
      );

      if (available) {
        setActiveKey(available.key);
      }
    } catch (err) {
      console.error("Failed to load summary editor:", err);
      setError(err.message || "Unable to open the summary editor.");
    } finally {
      setLoading(false);
    }
  }

  const sections = draft?.summary?.sections || {};

  const availableSections = useMemo(
    () =>
      SECTION_META.filter((meta) => {
        const value = sections[meta.key];

        return Array.isArray(value) && value.length > 0;
      }),
    [sections]
  );

  const highlights = useMemo(
    () => interviewHighlights(review?.responses || []),
    [review?.responses]
  );

  const activeMeta =
    SECTION_META.find((section) => section.key === activeKey) ||
    availableSections[0] ||
    SECTION_META[0];

  const activeItems = Array.isArray(sections[activeMeta.key])
    ? sections[activeMeta.key]
    : [];

  function markDirty() {
    setDirty(true);
    setSaved(false);
  }

  function updateSection(key, nextValue) {
    setDraft((current) => ({
      ...current,
      summary: {
        ...current.summary,
        sections: {
          ...current.summary.sections,
          [key]: nextValue,
        },
      },
    }));

    markDirty();
  }

  function updateItem(key, index, nextValue) {
    const current = Array.isArray(sections[key]) ? sections[key] : [];

    const next = [...current];
    next[index] = nextValue;

    updateSection(key, next);
  }

  function addTextItem(key) {
    const current = Array.isArray(sections[key]) ? sections[key] : [];

    updateSection(key, [...current, ""]);
  }

  function addHpiItem() {
    const current = Array.isArray(sections.history_of_present_illness)
      ? sections.history_of_present_illness
      : [];

    updateSection("history_of_present_illness", [
      ...current,
      {
        question: "",
        answer: "",
      },
    ]);
  }

  function removeItem(key, index) {
    const current = Array.isArray(sections[key]) ? sections[key] : [];

    updateSection(
      key,
      current.filter((_, itemIndex) => itemIndex !== index)
    );
  }

  async function saveSummary() {
    if (!review?.summary?.id || !draft) return;

    setSaving(true);
    setError("");
    setSaved(false);

    try {
      await api(`/summaries/${review.summary.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          content: JSON.stringify(draft),
        }),
      });

      setDirty(false);
      setSaved(true);

      /*
       * App.jsx currently uses the singular review route:
       *
       * /doctor/session/:sessionId
       *
       * Keep navigation consistent with that route.
       */
      navigate(`/doctor/session/${sessionId}`, {
        replace: true,
      });
    } catch (err) {
      console.error("Failed to save summary:", err);
      setError(err.message || "Unable to save your changes.");
    } finally {
      setSaving(false);
    }
  }

  function cancelEdit() {
    if (
      dirty &&
      !window.confirm("Discard your unsaved changes?")
    ) {
      return;
    }

    navigate(`/doctor/session/${sessionId}`);
  }

  if (loading) {
    return (
      <main className="mk-edit-page">
        <div className="mk-edit-loading">
          <div className="doctor-loading__spinner" />

          <strong>Opening clinical editor</strong>

          <span>
            Preparing the physician review workspace…
          </span>
        </div>
      </main>
    );
  }

  if (error && !draft) {
    return (
      <main className="mk-edit-page">
        <div className="mk-edit-error">
          <div className="mk-edit-error-icon">!</div>

          <span className="mk-edit-eyebrow">
            CLINICAL EDITOR
          </span>

          <h1>Unable to open summary</h1>

          <p>{error}</p>

          <button
            type="button"
            className="mk-edit-primary-btn"
            onClick={() =>
              navigate(`/doctor/session/${sessionId}`)
            }
          >
            Back to Clinical Review
          </button>
        </div>
      </main>
    );
  }

  if (!draft) {
    return (
      <main className="mk-edit-page">
        <div className="mk-edit-error">
          <span className="mk-edit-eyebrow">
            CLINICAL EDITOR
          </span>

          <h1>No editable summary</h1>

          <p>
            A clinical summary has not been generated for this
            session.
          </p>

          <button
            type="button"
            className="mk-edit-primary-btn"
            onClick={() =>
              navigate(`/doctor/session/${sessionId}`)
            }
          >
            Back to Clinical Review
          </button>
        </div>
      </main>
    );
  }

  const patient = review?.patient;

  return (
    <main className="mk-edit-page">
      <header className="mk-edit-topbar">
        <div className="mk-edit-brand">
          <button
            type="button"
            className="mk-edit-back"
            onClick={cancelEdit}
            aria-label="Back to clinical review"
          >
            ←
          </button>

          <img
            src="/medikiosk-logo.png"
            alt=""
          />

          <div>
            <strong>MediKiosk</strong>
            <span>Clinical Review</span>
          </div>
        </div>

        <div className="mk-edit-topbar-right">
          <span>Session #{sessionId}</span>

          <button
            type="button"
            onClick={() => {
              sessionStorage.removeItem("doctorId");
              navigate("/doctor/login");
            }}
          >
            Sign out
          </button>
        </div>
      </header>

      <div className="mk-edit-shell">
        <aside className="mk-edit-nav">
          <div className="mk-edit-patient">
            <span className="mk-edit-eyebrow">
              PATIENT
            </span>

            <div className="mk-edit-patient-main">
              <div className="mk-edit-avatar">
                {patient?.name?.charAt(0)?.toUpperCase() ||
                  "P"}
              </div>

              <div>
                <strong>
                  {patient?.name || "Unknown Patient"}
                </strong>

                <span>
                  ID {patient?.id ?? "—"}
                </span>
              </div>
            </div>

            <div className="mk-edit-patient-stats">
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
            </div>
          </div>

          <div className="mk-edit-nav-title">
            SUMMARY SECTIONS
          </div>

          <nav aria-label="Summary sections">
            {availableSections.map((section) => {
              const selected =
                section.key === activeMeta.key;

              return (
                <button
                  type="button"
                  key={section.key}
                  className={`mk-edit-nav-item ${
                    selected ? "is-active" : ""
                  }`}
                  onClick={() =>
                    setActiveKey(section.key)
                  }
                >
                  <span className="mk-edit-nav-code">
                    {section.short}
                  </span>

                  <span className="mk-edit-nav-label">
                    {section.label}
                  </span>

                  <span className="mk-edit-nav-count">
                    {sections[section.key].length}
                  </span>
                </button>
              );
            })}
          </nav>

          <div className="mk-edit-nav-note">
            <span>EDITING MODE</span>

            <strong>
              Physician draft
            </strong>

            <p>
              Correct the generated clinical history and
              extracted clinical findings. Original patient
              responses, uploaded documents and safety alerts
              remain protected.
            </p>
          </div>
        </aside>

        <section className="mk-edit-workspace">
          <div className="mk-edit-heading">
            <div>
              <span className="mk-edit-eyebrow">
                PHYSICIAN EDITOR
              </span>

              <h1>
                Edit clinical summary
              </h1>

              <p>
                Correct or clarify the generated history and
                extracted clinical information before accepting
                it for consultation.
              </p>
            </div>

            <div
              className={`mk-edit-save-state ${
                dirty ? "is-dirty" : ""
              }`}
            >
              <span className="mk-edit-save-dot" />

              {dirty
                ? "Unsaved changes"
                : saved
                ? "Saved"
                : "No changes"}
            </div>
          </div>

          {error && (
            <div className="mk-edit-message mk-edit-message-error">
              {error}
            </div>
          )}

          {saved && (
            <div className="mk-edit-message mk-edit-message-success">
              Changes saved. Returning to clinical review…
            </div>
          )}

          <div className="mk-edit-content-card">
            <div className="mk-edit-section-header">
              <div>
                <span className="mk-edit-section-code">
                  {activeMeta.short}
                </span>

                <div>
                  <h2>
                    {activeMeta.label}
                  </h2>

                  <p>
                    {activeMeta.description}
                  </p>
                </div>
              </div>

              {activeMeta.kind === "hpi" ? (
                <button
                  type="button"
                  className="mk-edit-add-btn"
                  onClick={addHpiItem}
                  disabled={saving}
                >
                  + Add question
                </button>
              ) : (
                <button
                  type="button"
                  className="mk-edit-add-btn"
                  onClick={() =>
                    addTextItem(activeMeta.key)
                  }
                  disabled={saving}
                >
                  + Add entry
                </button>
              )}
            </div>

            <div className="mk-edit-fields">
              {activeMeta.kind === "hpi" ? (
                activeItems.map((rawItem, index) => {
                  const item = unwrap(rawItem);

                  const question =
                    item &&
                    typeof item === "object"
                      ? item.question ?? ""
                      : "";

                  const answer =
                    item &&
                    typeof item === "object"
                      ? item.answer ?? ""
                      : display(item);

                  return (
                    <div
                      className="mk-hpi-editor-row"
                      key={index}
                    >
                      <div className="mk-row-index">
                        {String(index + 1).padStart(2, "0")}
                      </div>

                      <div className="mk-hpi-inputs">
                        <label>
                          <span>
                            QUESTION
                          </span>

                          <input
                            value={question}
                            placeholder="e.g. How long have you had the fever?"
                            onChange={(event) => {
                              const next = {
                                ...(item &&
                                typeof item === "object"
                                  ? item
                                  : {}),
                                question:
                                  event.target.value,
                                answer,
                              };

                              updateItem(
                                activeMeta.key,
                                index,
                                setEditableValue(
                                  rawItem,
                                  next
                                )
                              );
                            }}
                            disabled={saving}
                          />
                        </label>

                        <label>
                          <span>
                            PATIENT ANSWER
                          </span>

                          <textarea
                            rows={3}
                            value={answer}
                            placeholder="Enter the patient's answer…"
                            onChange={(event) => {
                              const next = {
                                ...(item &&
                                typeof item === "object"
                                  ? item
                                  : {}),
                                question,
                                answer:
                                  event.target.value,
                              };

                              updateItem(
                                activeMeta.key,
                                index,
                                setEditableValue(
                                  rawItem,
                                  next
                                )
                              );
                            }}
                            disabled={saving}
                          />
                        </label>
                      </div>

                      <button
                        type="button"
                        className="mk-remove-btn"
                        onClick={() =>
                          removeItem(
                            activeMeta.key,
                            index
                          )
                        }
                        aria-label={`Remove question ${
                          index + 1
                        }`}
                        title="Remove"
                        disabled={saving}
                      >
                        ×
                      </button>
                    </div>
                  );
                })
              ) : (
                activeItems.map((rawItem, index) => {
                  const item =
                    getEditableValue(rawItem);

                  /*
                   * Structured clinical information:
                   *
                   * Example:
                   * {
                   *   medicine: "Paracetamol",
                   *   dosage: "500 mg",
                   *   frequency: "BD"
                   * }
                   *
                   * For document-derived findings, this lets the
                   * doctor correct the extracted clinical values
                   * while preserving the original wrapper/provenance.
                   */
                  if (
                    item &&
                    typeof item === "object" &&
                    !Array.isArray(item)
                  ) {
                    const entries =
                      visibleObjectEntries(item);

                    return (
                      <div
                        className="mk-structured-row"
                        key={index}
                      >
                        <div className="mk-row-index">
                          {String(index + 1).padStart(
                            2,
                            "0"
                          )}
                        </div>

                        <div className="mk-structured-fields">
                          {entries.map(
                            ([field, value]) => (
                              <label key={field}>
                                <span>
                                  {labelize(field)}
                                </span>

                                <textarea
                                  rows={
                                    String(
                                      value ?? ""
                                    ).length > 70
                                      ? 3
                                      : 2
                                  }
                                  value={display(value)}
                                  onChange={(event) => {
                                    /*
                                     * Start with the original
                                     * object, not the filtered
                                     * object. This preserves
                                     * provenance/source metadata.
                                     */
                                    const original =
                                      unwrap(
                                        activeItems[index]
                                      );

                                    const next =
                                      original &&
                                      typeof original ===
                                        "object" &&
                                      !Array.isArray(
                                        original
                                      )
                                        ? {
                                            ...original,
                                            [field]:
                                              event.target
                                                .value,
                                          }
                                        : {
                                            [field]:
                                              event.target
                                                .value,
                                          };

                                    updateItem(
                                      activeMeta.key,
                                      index,
                                      setEditableValue(
                                        rawItem,
                                        next
                                      )
                                    );
                                  }}
                                  disabled={saving}
                                />
                              </label>
                            )
                          )}
                        </div>

                        <button
                          type="button"
                          className="mk-remove-btn"
                          onClick={() =>
                            removeItem(
                              activeMeta.key,
                              index
                            )
                          }
                          aria-label={`Remove entry ${
                            index + 1
                          }`}
                          title="Remove"
                          disabled={saving}
                        >
                          ×
                        </button>
                      </div>
                    );
                  }

                  /*
                   * Simple text clinical information.
                   */
                  return (
                    <div
                      className="mk-text-row"
                      key={index}
                    >
                      <div className="mk-row-index">
                        {String(index + 1).padStart(
                          2,
                          "0"
                        )}
                      </div>

                      <label>
                        <span>
                          {activeMeta.key ===
                          "chief_complaints"
                            ? "COMPLAINT"
                            : activeMeta.key ===
                              "document_derived_findings"
                            ? "CLINICAL FINDING"
                            : "CLINICAL INFORMATION"}
                        </span>

                        <textarea
                          rows={2}
                          value={display(item)}
                          placeholder={
                            activeMeta.key ===
                            "document_derived_findings"
                              ? "Enter extracted clinical finding…"
                              : "Enter clinical information…"
                          }
                          onChange={(event) =>
                            updateItem(
                              activeMeta.key,
                              index,
                              setEditableValue(
                                rawItem,
                                event.target.value
                              )
                            )
                          }
                          disabled={saving}
                        />
                      </label>

                      <button
                        type="button"
                        className="mk-remove-btn"
                        onClick={() =>
                          removeItem(
                            activeMeta.key,
                            index
                          )
                        }
                        aria-label={`Remove entry ${
                          index + 1
                        }`}
                        title="Remove"
                        disabled={saving}
                      >
                        ×
                      </button>
                    </div>
                  );
                })
              )}

              {activeItems.length === 0 && (
                <div className="mk-edit-empty-section">
                  <strong>
                    No information recorded
                  </strong>

                  <span>
                    Add an entry if the patient history needs
                    to be completed.
                  </span>
                </div>
              )}
            </div>
          </div>

          <div className="mk-edit-readonly">
            <div className="mk-edit-readonly-icon">
              i
            </div>

            <div>
              <strong>
                Original evidence and safety alerts are
                protected
              </strong>

              <p>
                Extracted clinical findings from uploaded
                records can be corrected by the physician.
                The original uploaded document, OCR/source
                evidence and patient responses remain
                unchanged. Red-flag alerts remain linked to
                their original patient responses.
              </p>
            </div>
          </div>
        </section>

        <aside className="mk-edit-context">
          <div className="mk-context-header">
            <span className="mk-edit-eyebrow">
              SOURCE CONTEXT
            </span>

            <h2>
              Patient interview
            </h2>

            <p>
              Use the original answers to verify your edits.
            </p>
          </div>

          {highlights.length ? (
            <div className="mk-interview-list">
              {highlights.map((item) => (
                <article
                  className="mk-interview-item"
                  key={item.id}
                >
                  <span>
                    QUESTION
                  </span>

                  <strong>
                    {item.question}
                  </strong>

                  <div>
                    <span>
                      ANSWER
                    </span>

                    <p>
                      {item.answer}
                    </p>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="mk-context-empty">
              No patient interview answers are available.
            </div>
          )}

          <div className="mk-context-warning">
            <span>
              Before accepting
            </span>

            <p>
              Compare the edited history with the original
              patient responses and uploaded evidence.
            </p>
          </div>
        </aside>
      </div>

      <footer className="mk-edit-actions">
        <div>
          <strong>
            {dirty
              ? "You have unsaved changes"
              : "Clinical summary draft"}
          </strong>

          <span>
            Nothing is accepted until the physician confirms
            it.
          </span>
        </div>

        <div className="mk-edit-action-buttons">
          <button
            type="button"
            className="mk-edit-secondary-btn"
            onClick={cancelEdit}
            disabled={saving}
          >
            Cancel
          </button>

          <button
            type="button"
            className="mk-edit-primary-btn"
            onClick={saveSummary}
            disabled={saving || !dirty}
          >
            {saving
              ? "Saving…"
              : "Save Changes"}
          </button>
        </div>
      </footer>
    </main>
  );
}