import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, clearDoctorAccessToken, getApiBaseUrl } from "../../services/api";

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
  const [editorContent, setEditorContent] = useState(null);
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
        `/doctors/${doctorId}/sessions/${sessionId}/review`,
        {
          auth: "doctor",
        }
      );

      setReview(data);

      if (data?.summary?.content) {
        setEditedContent(data.summary.content);

        try {
          setEditorContent(
            JSON.parse(data.summary.content)
          );
        } catch (err) {
          console.error(
            "Unable to prepare summary editor:",
            err
          );

          setEditorContent(null);
        }
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
  // Red-flag presentation helpers
  // ============================================================

  const redFlags = useMemo(() => {
    const rawFlags = sections?.red_flags;

    if (!Array.isArray(rawFlags)) {
      return [];
    }

    const grouped = new Map();

    rawFlags.forEach((flag) => {
      if (!flag || typeof flag !== "object") {
        return;
      }

      const category =
        flag.category ||
        flag.flag_id ||
        "Clinical safety finding";

      const priority =
        flag.priority ||
        "critical";

      const existing = grouped.get(category);

      const evidence = Array.isArray(flag.evidence)
        ? flag.evidence
          .filter(Boolean)
          .map((item) => ({
            question: item?.question || "",
            text: item?.text || item?.matched_text || "",
          }))
          .filter((item) => item.text || item.question)
        : [
          {
            question: flag.question || "",
            text:
              flag.matched_text ||
              flag.answer ||
              "",
          },
        ].filter((item) => item.text || item.question);

      if (!existing) {
        grouped.set(category, {
          category,
          priority,
          evidence,
        });
        return;
      }

      evidence.forEach((item) => {
        const alreadyExists = existing.evidence.some(
          (existingItem) =>
            existingItem.text === item.text &&
            existingItem.question === item.question
        );

        if (!alreadyExists) {
          existing.evidence.push(item);
        }
      });
    });

    return Array.from(grouped.values());
  }, [sections?.red_flags]);


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
    if (value === null || value === undefined) {
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
          if (typeof item === "object" && item !== null) {
            if (item.answer !== undefined) {
              return formatValue(item.answer);
            }

            if (item.value !== undefined) {
              return formatValue(item.value);
            }

            return Object.entries(item)
              .filter(([key]) => !isDoctorIrrelevantField(key))
              .map(([key, child]) => `${formatLabel(key)}: ${formatValue(child)}`)
              .join("\n");
          }

          return String(item);
        })
        .filter(Boolean)
        .join("\n");
    }

    if (typeof value === "object") {
      return Object.entries(value)
        .filter(([key]) => !isDoctorIrrelevantField(key))
        .map(
          ([key, item]) =>
            `${formatLabel(key)}: ${formatValue(item)}`
        )
        .join("\n");
    }

    return String(value);
  }


  function isDoctorIrrelevantField(key) {
    return [
      "input_type",
      "inputType",
      "language",
      "lang",
      "response_id",
      "responseId",
      "matched_pattern",
      "matched_text",
      "matched_fields",
      "explanation",
      "flag_id",
    ].includes(key);
  }



  // ============================================================
  // Medical document presentation helpers
  // ============================================================

  const documentFindings = useMemo(() => {
    const raw = Array.isArray(sections.document_derived_findings)
      ? sections.document_derived_findings
      : [];

    const provenance = Array.isArray(
      summaryContent?.provenance?.document_derived_findings
    )
      ? summaryContent.provenance.document_derived_findings
      : [];

    const groups = {
      diagnoses: [],
      labs: [],
      medications: [],
      allergies: [],
      procedures: [],
      findings: [],
    };

    const normalizeField = (value) =>
      String(value || "")
        .trim()
        .toLowerCase()
        .replace(/[-\s]+/g, "_");

    const ignoredFields = new Set([
      "document_type",
      "document_id",
      "filename",
      "file_name",
      "patient",
      "patient_name",
      "patient_id",
      "hospital_id",
      "age",
      "sex",
      "gender",
      "source",
      "provenance",
      "confidence",
      "raw_text",
      "ocr_text",
      "text",
      "processing_status",
      "dates",
    ]);

    const classify = (field, value) => {
      const normalized = normalizeField(field);

      if (
        [
          "diagnosis",
          "diagnoses",
          "condition",
          "conditions",
        ].includes(normalized)
      ) {
        return "diagnoses";
      }

      if (
        [
          "lab",
          "labs",
          "laboratory_result",
          "laboratory_results",
          "lab_result",
          "lab_results",
          "test",
          "tests",
          "test_result",
          "test_results",
          "investigation",
          "investigations",
        ].includes(normalized)
      ) {
        return "labs";
      }

      if (
        [
          "medication",
          "medications",
          "medicine",
          "medicines",
          "drug",
          "drugs",
          "prescription",
          "prescriptions",
          "drug_information",
        ].includes(normalized)
      ) {
        return "medications";
      }

      if (["allergy", "allergies"].includes(normalized)) {
        return "allergies";
      }

      if (
        [
          "procedure",
          "procedures",
          "surgery",
          "surgeries",
        ].includes(normalized)
      ) {
        return "procedures";
      }

      // Discharge extraction can contain clinically useful findings, but
      // document dates/metadata are intentionally not shown here.
      if (
        [
          "discharge_findings",
          "discharge_extraction",
          "clinical_finding",
          "clinical_findings",
          "finding",
          "findings",
        ].includes(normalized)
      ) {
        return "findings";
      }

      if (normalized && !ignoredFields.has(normalized)) {
        return "findings";
      }

      // When provenance is unavailable (older summaries), infer from shape.
      if (value && typeof value === "object") {
        const keys = Object.keys(value).map(normalizeField);

        if (keys.includes("name") && keys.some((key) =>
          ["dosage", "dose", "frequency", "duration", "route"].includes(key)
        )) {
          return "medications";
        }

        if (
          keys.includes("reference_range") ||
          keys.includes("unit") ||
          keys.includes("abnormal") ||
          keys.includes("risk_flag")
        ) {
          return "labs";
        }
      }

      return null;
    };

    const stableKey = (value) => {
      if (value === null || value === undefined) return "null";
      if (typeof value === "string") return value.trim().replace(/\s+/g, " ").toLowerCase();
      if (typeof value !== "object") return String(value);

      if (Array.isArray(value)) {
        return `[${value.map(stableKey).sort().join("|")}]`;
      }

      return Object.keys(value)
        .filter((key) => !ignoredFields.has(normalizeField(key)))
        .sort()
        .map((key) => `${normalizeField(key)}=${stableKey(value[key])}`)
        .join("|");
    };

    const pushUnique = (target, value) => {
      if (value === null || value === undefined || value === "") return;

      const signature = stableKey(value);

      if (
        !target.some(
          (entry) => entry.signature === signature
        )
      ) {
        target.push({
          value,
          signature,
        });
      }
    };

    raw.forEach((rawItem, index) => {
      if (rawItem === null || rawItem === undefined) return;

      const source = provenance[index] || {};
      const provenanceField = normalizeField(source.path);
      const explicitField = normalizeField(
        rawItem?.field || rawItem?.type
      );
      const value =
        rawItem?.value !== undefined
          ? rawItem.value
          : rawItem;

      const kind = classify(
        explicitField || provenanceField,
        value
      );

      if (!kind) return;

      if (Array.isArray(value)) {
        value.forEach((item) => pushUnique(groups[kind], item));
      } else {
        pushUnique(groups[kind], value);
      }
    });

    return {
      diagnoses: groups.diagnoses.map((entry) => entry.value),
      labs: groups.labs.map((entry) => entry.value),
      medications: groups.medications.map((entry) => entry.value),
      allergies: groups.allergies.map((entry) => entry.value),
      procedures: groups.procedures.map((entry) => entry.value),
      findings: groups.findings.map((entry) => entry.value),
    };
  }, [
    sections.document_derived_findings,
    summaryContent?.provenance?.document_derived_findings,
  ]);

  const documentFindingCount =
    documentFindings.diagnoses.length +
    documentFindings.labs.length +
    documentFindings.medications.length +
    documentFindings.allergies.length +
    documentFindings.procedures.length +
    documentFindings.findings.length;

  const interviewHighlights = useMemo(() => {
    const responses = Array.isArray(review?.responses) ? review.responses : [];
    const emptyAnswers = new Set([
      "", "no", "none", "nothing", "not applicable", "n/a",
      "na", "not available", "nil", "negative",
    ]);

    return responses
      .map((response, index) => ({
        id: response?.id || index,
        question: String(response?.question || `Question ${index + 1}`).trim(),
        answer: String(response?.answer || "").trim(),
      }))
      .filter(({ answer }) => answer && !emptyAnswers.has(answer.toLowerCase()))
      .slice(0, 8);
  }, [review?.responses]);

  function displayDocumentValue(value) {
    if (value === null || value === undefined || value === "") {
      return "Not available";
    }

    if (
      typeof value === "string" ||
      typeof value === "number" ||
      typeof value === "boolean"
    ) {
      return String(value);
    }

    if (Array.isArray(value)) {
      return value
        .map(displayDocumentValue)
        .filter(Boolean)
        .join(" • ");
    }

    return Object.entries(value)
      .filter(
        ([key]) =>
          !isDoctorIrrelevantField(key) &&
          ![
            "document_id",
            "filename",
            "file_name",
            "provenance",
            "confidence",
          ].includes(key)
      )
      .map(
        ([key, item]) =>
          `${formatLabel(key)}: ${displayDocumentValue(item)}`
      )
      .join("\n");
  }

  function renderDocumentDataCard(title, items, kind) {
    if (!items?.length) return null;

    const normalizeKey = (key) => String(key || "").toLowerCase().replace(/[-\s]/g, "_");
    const get = (item, ...keys) => {
      if (!item || typeof item !== "object") return null;
      for (const key of keys) {
        const found = Object.entries(item).find(([entryKey]) => normalizeKey(entryKey) === normalizeKey(key));
        if (found && found[1] !== null && found[1] !== undefined && String(found[1]).trim() !== "") return found[1];
      }
      return null;
    };

    const isLab = kind === "labs";
    const isMedication = kind === "medications";

    return (
      <div className={`doctor-document-data-group doctor-document-data-group--${kind}`}>
        <div className="doctor-document-data-group__title">
          <span>{title}</span>
          <small>{items.length} {items.length === 1 ? "record" : "records"}</small>
        </div>

        {isLab ? (
          <div className="doctor-clinical-table-wrap">
            <table className="doctor-clinical-table">
              <thead>
                <tr><th>Test</th><th>Result</th><th>Reference range</th><th>Status</th></tr>
              </thead>
              <tbody>
                {items.map((item, index) => {
                  const name = get(item, "name", "test_name", "test") || "Laboratory test";
                  const value = get(item, "value", "result", "result_value");
                  const unit = get(item, "unit", "units");
                  const range = get(item, "reference_range", "referenceRange");
                  const status = get(item, "status") || (String(get(item, "abnormal")).toLowerCase() === "true" ? "abnormal" : "");
                  const risk = get(item, "risk_flag", "riskFlag");
                  const statusText = risk && String(risk).toLowerCase() !== "not available" ? formatLabel(risk) : status ? formatLabel(status) : "—";
                  const statusClass = String(status || risk || "").toLowerCase().includes("high") || String(status || risk || "").toLowerCase().includes("low") || String(status || risk || "").toLowerCase().includes("abnormal") || String(status || risk || "").toLowerCase().includes("review") ? "doctor-table-status--alert" : "doctor-table-status--normal";
                  return (
                    <tr key={index}>
                      <td><strong>{displayDocumentValue(name)}</strong></td>
                      <td><strong>{displayDocumentValue(value)}</strong>{unit && <span className="doctor-table-unit"> {displayDocumentValue(unit)}</span>}</td>
                      <td>{displayDocumentValue(range) === "Not available" ? "—" : displayDocumentValue(range)}</td>
                      <td><span className={`doctor-table-status ${statusClass}`}>{statusText}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : isMedication ? (
          <div className="doctor-clinical-table-wrap">
            <table className="doctor-clinical-table doctor-medication-table">
              <thead>
                <tr><th>Medicine</th><th>Dose</th><th>Route</th><th>Frequency</th><th>Duration</th></tr>
              </thead>
              <tbody>
                {items.map((item, index) => {
                  const name = get(item, "name", "medicine", "drug") || "Medication";
                  const dosage = get(item, "dosage", "dose");
                  const route = get(item, "route");
                  const frequency = get(item, "frequency", "freq");
                  const duration = get(item, "duration");
                  return (
                    <tr key={index}>
                      <td><strong>{displayDocumentValue(name)}</strong></td>
                      <td>{dosage ? displayDocumentValue(dosage) : "—"}</td>
                      <td>{route ? displayDocumentValue(route) : "—"}</td>
                      <td>{frequency ? displayDocumentValue(frequency) : "—"}</td>
                      <td>{duration ? displayDocumentValue(duration) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="doctor-document-compact-list">
            {items.map((item, index) => (
              <div className="doctor-document-compact-row" key={index}>
                {typeof item === "object" && item !== null
                  ? Object.entries(item)
                    .filter(([key]) => !isDoctorIrrelevantField(key))
                    .filter(([key]) => !["document_id", "filename", "file_name", "provenance", "confidence"].includes(normalizeKey(key)))
                    .map(([key, value]) => <span key={key}><b>{formatLabel(key)}</b>{displayDocumentValue(value)}</span>)
                  : <span>{displayDocumentValue(item)}</span>}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ============================================================
  // Render clinical section
  // ============================================================

  function isLegacyOCRMetadataItem(item) {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      return false;
    }

    const field = String(
      item.field || item.type || ""
    )
      .trim()
      .toLowerCase()
      .replace(/[-\s]+/g, "_");

    return (
      [
        "document_type",
        "document_id",
        "filename",
        "file_name",
        "patient",
        "patient_name",
        "patient_id",
        "hospital_id",
        "age",
        "sex",
        "gender",
      ].includes(field) ||
      item.document_id !== undefined ||
      item.filename !== undefined ||
      item.file_name !== undefined
    );
  }

  function cleanLegacySection(section) {
    if (!Array.isArray(section)) {
      return section;
    }

    return section.filter(
      (item) => !isLegacyOCRMetadataItem(item)
    );
  }

  function renderSection(title, section) {
    const visibleSection = cleanLegacySection(section);
    section = visibleSection;

    let hasContent = false;

    if (Array.isArray(section)) {
      hasContent = section.length > 0;
    } else if (section && typeof section === "object") {
      hasContent = Object.entries(section).some(
        ([key, value]) =>
          !isDoctorIrrelevantField(key) &&
          value !== null &&
          value !== undefined &&
          (
            !Array.isArray(value) ||
            value.length > 0
          )
      );
    } else if (section !== null && section !== undefined) {
      hasContent = String(section).trim().length > 0;
    }

    if (!hasContent) {
      return null;
    }

    return (
      <section
        className={`review-section review-section--${title
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-|-$/g, "")}`}
        key={title}
        style={{
          background: "#ffffff",
          border: "1px solid rgba(22, 96, 92, 0.12)",
          borderRadius: "16px",
          overflow: "hidden",
          marginBottom: "14px",
        }}
      >
        <div
          className="review-section__header"
          style={{
            padding: "15px 20px",
            borderBottom: hasContent ? "1px solid rgba(22, 96, 92, 0.10)" : "none",
            background: "rgba(22, 96, 92, 0.025)",
          }}
        >
          <h2 style={{ margin: 0, fontSize: "16px" }}>{title}</h2>
        </div>

        {hasContent ? (
          <div
            className="review-section__content"
            style={{ padding: "18px 20px" }}
          >
            {Array.isArray(section) ? (
              section.map((item, index) => {
                if (item && typeof item === "object") {
                  const visibleEntries = Object.entries(item).filter(
                    ([key]) => !isDoctorIrrelevantField(key)
                  );
                  const question = item.question;
                  const answer = item.answer;

                  if (question || answer !== undefined) {
                    return (
                      <div
                        className="review-item"
                        key={index}
                        style={{
                          padding: "0 0 15px",
                          marginBottom: index < section.length - 1 ? "15px" : 0,
                          borderBottom:
                            index < section.length - 1
                              ? "1px solid rgba(22, 96, 92, 0.10)"
                              : "none",
                        }}
                      >
                        {question && (
                          <div
                            className="review-item__question"
                            style={{
                              fontSize: "12px",
                              fontWeight: 700,
                              marginBottom: "6px",
                              opacity: 0.68,
                            }}
                          >
                            {question}
                          </div>
                        )}
                        {answer !== undefined && (
                          <div
                            className="review-item__answer"
                            style={{
                              fontSize: "15px",
                              lineHeight: 1.65,
                              whiteSpace: "pre-wrap",
                            }}
                          >
                            {formatValue(answer)}
                          </div>
                        )}
                      </div>
                    );
                  }

                  return (
                    <div
                      className="review-item"
                      key={index}
                      style={{
                        padding: "0 0 15px",
                        marginBottom: index < section.length - 1 ? "15px" : 0,
                        borderBottom:
                          index < section.length - 1
                            ? "1px solid rgba(22, 96, 92, 0.10)"
                            : "none",
                      }}
                    >
                      <div
                        className="review-item__answer"
                        style={{ fontSize: "15px", lineHeight: 1.65, whiteSpace: "pre-wrap" }}
                      >
                        {formatValue(item)}
                      </div>
                    </div>
                  );
                }

                return (
                  <div
                    className="review-item"
                    key={index}
                    style={{
                      fontSize: "15px",
                      lineHeight: 1.65,
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {formatValue(item)}
                  </div>
                );
              })
            ) : typeof section === "object" ? (
              Object.entries(section)
                .filter(([key]) => !isDoctorIrrelevantField(key))
                .map(([key, value]) => (
                  <div
                    className="review-item"
                    key={key}
                    style={{
                      padding: "0 0 15px",
                      marginBottom: "15px",
                      borderBottom: "1px solid rgba(22, 96, 92, 0.10)",
                    }}
                  >
                    <div
                      className="review-item__question"
                      style={{
                        fontSize: "12px",
                        fontWeight: 700,
                        marginBottom: "6px",
                        opacity: 0.68,
                      }}
                    >
                      {formatLabel(key)}
                    </div>
                    <div
                      className="review-item__answer"
                      style={{ fontSize: "15px", lineHeight: 1.65, whiteSpace: "pre-wrap" }}
                    >
                      {formatValue(value)}
                    </div>
                  </div>
                ))
            ) : (
              <div
                className="review-item__answer"
                style={{ fontSize: "15px", lineHeight: 1.65, whiteSpace: "pre-wrap" }}
              >
                {formatValue(section)}
              </div>
            )}
          </div>
        ) : (
          <div
            className="review-section__empty"
            style={{ padding: "17px 20px", opacity: 0.55, fontSize: "14px" }}
          >
            No information recorded.
          </div>
        )}
      </section>
    );
  }



  // ============================================================
  // Structured summary editor helpers
  // ============================================================

  function updateEditorValue(path, value) {
    setEditorContent((current) => {
      if (!current) {
        return current;
      }

      const updated = structuredClone(current);
      let target = updated;

      for (let i = 0; i < path.length - 1; i += 1) {
        target = target[path[i]];
      }

      target[path[path.length - 1]] = value;

      return updated;
    });
  }


  function renderEditableValue(value, path, label) {
    if (value === null || value === undefined) {
      return (
        <div className="doctor-editor-field" key={path.join(".")}>
          <label>{label}</label>
          <input
            type="text"
            value=""
            placeholder="Not available"
            onChange={(event) =>
              updateEditorValue(path, event.target.value)
            }
          />
        </div>
      );
    }

    if (Array.isArray(value)) {
      return (
        <div className="doctor-editor-array" key={path.join(".")}>
          <div className="doctor-editor-array__label">{label}</div>

          {value.length === 0 ? (
            <div className="doctor-editor-empty">
              None recorded
            </div>
          ) : (
            value.map((item, index) => {
              if (item && typeof item === "object" && !Array.isArray(item)) {
                const hasQuestionAnswer =
                  item.question !== undefined ||
                  item.answer !== undefined;

                if (hasQuestionAnswer) {
                  return (
                    <div
                      className="doctor-editor-array__item"
                      key={`${path.join(".")}-${index}`}
                      style={{
                        padding: "16px",
                        marginBottom: "10px",
                        background: "rgba(22, 96, 92, 0.035)",
                        border: "1px solid rgba(22, 96, 92, 0.10)",
                        borderRadius: "12px",
                      }}
                    >
                      {item.question !== undefined && (
                        <div
                          style={{
                            fontSize: "12px",
                            fontWeight: 700,
                            lineHeight: 1.45,
                            marginBottom: "8px",
                            opacity: 0.68,
                          }}
                        >
                          {item.question}
                        </div>
                      )}

                      {item.answer !== undefined && (
                        <div className="doctor-editor-field">
                          <label>Patient answer</label>
                          <textarea
                            value={String(item.answer ?? "")}
                            rows={4}
                            onChange={(event) =>
                              updateEditorValue(
                                [...path, index, "answer"],
                                event.target.value
                              )
                            }
                          />
                        </div>
                      )}
                    </div>
                  );
                }
              }

              return (
                <div
                  className="doctor-editor-array__item"
                  key={`${path.join(".")}-${index}`}
                >
                  {renderEditableValue(
                    item,
                    [...path, index],
                    `${label} ${index + 1}`
                  )}
                </div>
              );
            })
          )}
        </div>
      );
    }

    if (typeof value === "object") {
      const visibleEntries = Object.entries(value).filter(
        ([key]) => !isDoctorIrrelevantField(key)
      );

      return (
        <div
          className="doctor-editor-object"
          key={path.join(".")}
        >
          <div className="doctor-editor-object__title">
            {label}
          </div>

          <div className="doctor-editor-object__body">
            {visibleEntries.map(([key, childValue]) =>
              renderEditableValue(
                childValue,
                [...path, key],
                formatLabel(key)
              )
            )}
          </div>
        </div>
      );
    }

    const stringValue = String(value);
    const isLongText =
      stringValue.length > 120 ||
      stringValue.includes("\n");

    return (
      <div
        className="doctor-editor-field"
        key={path.join(".")}
      >
        <label>{label}</label>

        {isLongText ? (
          <textarea
            value={stringValue}
            rows={5}
            onChange={(event) =>
              updateEditorValue(path, event.target.value)
            }
          />
        ) : (
          <input
            type="text"
            value={stringValue}
            onChange={(event) =>
              updateEditorValue(path, event.target.value)
            }
          />
        )}
      </div>
    );
  }



  function renderEditableSection(
    title,
    section,
    path
  ) {
    if (
      section === null ||
      section === undefined
    ) {
      return null;
    }

    return (
      <div className="doctor-editor-section">
        <div className="doctor-editor-section__title">
          {title}
        </div>

        <div className="doctor-editor-section__body">
          {renderEditableValue(
            section,
            path,
            title
          )}
        </div>
      </div>
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
          auth: "doctor",
        }
      );

      setReview((current) =>
        current?.summary
          ? {
              ...current,
              summary: {
                ...current.summary,
                status: "accepted",
              },
            }
          : current
      );

      setShowEditor(false);

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
          auth: "doctor",
        }
      );

      setReview((current) =>
        current?.summary
          ? {
              ...current,
              summary: {
                ...current.summary,
                status: "rejected",
              },
            }
          : current
      );

      setShowEditor(false);

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
    if (!review?.summary?.content) {
      return;
    }

    try {
      const parsed = JSON.parse(
        review.summary.content
      );

      setEditedContent(
        review.summary.content
      );

      setEditorContent(
        structuredClone(parsed)
      );

      setActionError("");
      setShowEditor(true);

    } catch (err) {
      console.error(
        "Unable to open summary editor:",
        err
      );

      setActionError(
        "Unable to edit this summary."
      );
    }
  }


  // ============================================================
  // Save edited summary
  // ============================================================

  async function saveEditedSummary() {
    if (!review?.summary?.id) {
      return;
    }

    if (!editorContent) {
      setActionError(
        "Summary cannot be empty."
      );
      return;
    }

    setIsSaving(true);
    setActionError("");

    try {
      const serializedContent =
        JSON.stringify(editorContent);

      await api(
        `/summaries/${review.summary.id}`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            content: serializedContent,
          }),
          auth: "doctor",
        }
      );

      setEditedContent(
        serializedContent
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
    summaryStatus === "accepted"
      ? "verified"
      : summaryStatus === "rejected"
        ? "rejected"
        : summaryContent?.summary
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
              MEDISETU LOGO
              ================================================== */}

          <div className="doctor-brand-mini">
            <img
              src="/medisetu-logo.png"
              alt="MediSetu logo"
            />
          </div>


          <div>

            <div className="doctor-topbar__title">
              MediSetu
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
              clearDoctorAccessToken();
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
              className={`doctor-status doctor-status--${verificationStatus ===
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


          {redFlags.length > 0 && (

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
                CLINICAL SUMMARY
              </p>

              <h2>
                Clinical History Summary
              </h2>

              <p>
                Review the patient history and key clinical information before consultation.
              </p>

            </div>


            {review?.summary && summaryStatus === "draft" && (
              <span className="doctor-draft-badge">
                Physician review required
              </span>
            )}

            {summaryStatus === "accepted" && (
              <span className="doctor-draft-badge">
                Physician accepted
              </span>
            )}

            {summaryStatus === "rejected" && (
              <span className="doctor-draft-badge">
                Summary rejected
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

          ) : summaryStatus === "rejected" ? (

            <div className="doctor-empty-state">

              <h3>
                Clinical summary rejected
              </h3>

              <p>
                This AI-generated summary was rejected by the physician
                and is no longer available for consultation.
              </p>

            </div>

          ) : showEditor ? (

            /* ==================================================
               STRUCTURED EDITOR
               ================================================== */

            <div
              className="doctor-editor"
              style={{
                background: "#fbfdfd",
                border: "1px solid rgba(22, 96, 92, 0.12)",
                borderRadius: "16px",
                overflow: "hidden",
              }}
            >

              <div className="doctor-editor__heading">

                <div>

                  <label>
                    Edit clinical summary
                  </label>

                  <p className="doctor-editor__hint">
                    Update only the clinical information that needs correction.
                    Interview metadata such as language and input method is kept
                    in the record but is not shown here. Saving changes does not
                    accept the summary.
                  </p>

                </div>

              </div>


              <div className="doctor-editor__content">

                {editorContent?.summary?.sections
                  ? Object.entries(
                    editorContent.summary.sections
                  )
                    .filter(([key]) => key !== "red_flags")
                    .map(([key, value]) =>
                      renderEditableSection(
                        formatLabel(key),
                        value,
                        [
                          "summary",
                          "sections",
                          key,
                        ]
                      )
                    )
                  : (
                    <div className="doctor-editor-empty">
                      No editable clinical information
                      is available.
                    </div>
                  )}

              </div>


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
                  onClick={saveEditedSummary}
                  disabled={
                    isSaving ||
                    !editorContent
                  }
                >
                  {isSaving
                    ? "Saving..."
                    : "Save Changes"}
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

        {redFlags.length > 0 && (

          <section
            className="doctor-alert-card"
            style={{
              display: "flex",
              gap: "18px",
              alignItems: "flex-start",
              padding: "22px 24px",
            }}
          >

            <div
              className="doctor-alert-card__icon"
              style={{
                flex: "0 0 auto",
                width: "42px",
                height: "42px",
                display: "grid",
                placeItems: "center",
                borderRadius: "50%",
                fontSize: "20px",
                fontWeight: 800,
              }}
            >
              !
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "12px",
                  marginBottom: "4px",
                  flexWrap: "wrap",
                }}
              >
                <div>
                  <h2 style={{ margin: 0 }}>
                    Red Flags
                  </h2>
                  <p
                    style={{
                      margin: "5px 0 0",
                      opacity: 0.8,
                    }}
                  >
                    Safety findings requiring physician attention.
                  </p>
                </div>

                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    padding: "6px 10px",
                    borderRadius: "999px",
                    fontSize: "12px",
                    fontWeight: 700,
                    whiteSpace: "nowrap",
                    background: "rgba(180, 35, 35, 0.10)",
                    border: "1px solid rgba(180, 35, 35, 0.20)",
                  }}
                >
                  {redFlags.length} {redFlags.length === 1 ? "finding" : "findings"}
                </span>
              </div>

              <div
                style={{
                  display: "grid",
                  gap: "10px",
                  marginTop: "16px",
                }}
              >
                {redFlags.map((flag, index) => (
                  <article
                    key={`${flag.category}-${index}`}
                    style={{
                      background: "rgba(255, 255, 255, 0.78)",
                      border: "1px solid rgba(180, 35, 35, 0.16)",
                      borderRadius: "12px",
                      padding: "14px 16px",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: "10px",
                        flexWrap: "wrap",
                        marginBottom: "10px",
                      }}
                    >
                      <strong
                        style={{
                          fontSize: "16px",
                          lineHeight: 1.3,
                        }}
                      >
                        {formatLabel(flag.category)}
                      </strong>

                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "4px 9px",
                          borderRadius: "999px",
                          fontSize: "11px",
                          fontWeight: 800,
                          textTransform: "uppercase",
                          letterSpacing: "0.04em",
                          background: "rgba(180, 35, 35, 0.10)",
                          border: "1px solid rgba(180, 35, 35, 0.16)",
                        }}
                      >
                        {formatLabel(flag.priority)}
                      </span>
                    </div>

                    {flag.evidence.length > 0 ? (
                      <div
                        style={{
                          display: "grid",
                          gap: "8px",
                        }}
                      >
                        {flag.evidence.map((evidence, evidenceIndex) => (
                          <div
                            key={evidenceIndex}
                            style={{
                              padding: "9px 11px",
                              borderLeft: "3px solid rgba(180, 35, 35, 0.55)",
                              background: "rgba(180, 35, 35, 0.045)",
                              borderRadius: "0 8px 8px 0",
                            }}
                          >
                            {evidence.question && (
                              <div
                                style={{
                                  fontSize: "12px",
                                  fontWeight: 600,
                                  opacity: 0.72,
                                  marginBottom: "3px",
                                }}
                              >
                                {evidence.question}
                              </div>
                            )}

                            {evidence.text && (
                              <div
                                style={{
                                  fontSize: "14px",
                                  lineHeight: 1.5,
                                }}
                              >
                                “{evidence.text}”
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div
                        style={{
                          fontSize: "13px",
                          opacity: 0.7,
                        }}
                      >
                        The system identified a safety finding, but no patient statement was recorded.
                      </div>
                    )}
                  </article>
                ))}
              </div>

            </div>

          </section>

        )}


        {/* ====================================================
            PATIENT INTERVIEW HIGHLIGHTS
            ==================================================== */}

        {interviewHighlights.length > 0 && (
          <section className="doctor-interview-highlights-card">
            <div className="doctor-card-heading">
              <div>
                <p className="doctor-section-eyebrow">PATIENT INTERVIEW</p>
                <h2>Patient-reported highlights</h2>
                <p className="doctor-card-heading__description">
                  Key answers stated directly by the patient during the kiosk interview.
                </p>
              </div>
              <span>{interviewHighlights.length} responses</span>
            </div>
            <div className="doctor-interview-highlight-grid">
              {interviewHighlights.map((item) => {
                const isSafety = redFlags.some((flag) =>
                  flag.evidence?.some((evidence) =>
                    evidence.text && evidence.text.trim().toLowerCase() === item.answer.toLowerCase()
                  )
                );
                return (
                  <article key={item.id} className={`doctor-interview-highlight${isSafety ? " doctor-interview-highlight--alert" : ""}`}>
                    <span className="doctor-interview-highlight__label">Patient answer</span>
                    <strong>{item.question}</strong>
                    <p>{item.answer}</p>
                    {isSafety && <span className="doctor-interview-highlight__alert">Safety alert — physician attention required</span>}
                  </article>
                );
              })}
            </div>
          </section>
        )}


        {/* ====================================================
            DOCUMENTS
            ==================================================== */}

        <section className="doctor-documents-card">
          <div className="doctor-card-heading">
            <div>
              <p className="doctor-section-eyebrow">MODULE B</p>
              <h2>Medical Documents</h2>
              <p className="doctor-card-heading__description">
                Uploaded records and the clinically relevant information extracted from them.
              </p>
            </div>
            <span>
              {review?.documents?.length || 0} {review?.documents?.length === 1 ? "document" : "documents"}
            </span>
          </div>

          {review?.documents?.length ? (
            <>
              <div className="doctor-documents-content">
                {review.documents.map((document) => (
                  <article className="doctor-document-card" key={document.id}>
                    <div className="doctor-document-card__identity">
                      <div className="doctor-document-icon">DOC</div>
                      <div>
                        <strong>{document.filename || "Medical document"}</strong>
                        <span>
                          {document.document_type
                            ? formatLabel(document.document_type)
                            : "Medical document"}
                        </span>
                      </div>
                    </div>

                    <div
                      className="doctor-document-card__actions"
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                        flexWrap: "wrap",
                        justifyContent: "flex-end",
                      }}
                    >
                      <span
                        className={`doctor-document-status doctor-document-status--${document.processing_status || "unknown"
                          }`}
                      >
                        {formatLabel(document.processing_status || "unknown")}
                      </span>

                      <button
                        type="button"
                        className="doctor-document-view-button"
                        onClick={() => {
                          window.open(
                            `${getApiBaseUrl()}/documents/${document.id}/file`,
                            "_blank",
                            "noopener,noreferrer"
                          );
                        }}
                        style={{
                          border: "1px solid rgba(22, 96, 92, 0.18)",
                          background: "#ffffff",
                          color: "#16605c",
                          borderRadius: "8px",
                          padding: "8px 12px",
                          fontSize: "12px",
                          fontWeight: 700,
                          cursor: "pointer",
                          whiteSpace: "nowrap",
                        }}
                      >
                        View Report →
                      </button>
                    </div>
                  </article>
                ))}
              </div>

              {documentFindingCount > 0 && (
                <div className="doctor-extracted-clinical">
                  <div className="doctor-extracted-clinical__heading">
                    <div>
                      <p className="doctor-section-eyebrow">DOCUMENT EXTRACTION</p>
                      <h3>Clinically Relevant Findings</h3>
                      <p>
                        Only information extracted from the uploaded record is shown here.
                        Document IDs, patient metadata and OCR bookkeeping are hidden.
                      </p>
                    </div>
                    <span>
                      {documentFindingCount} clinical{" "}
                      {documentFindingCount === 1 ? "finding" : "findings"}
                    </span>
                  </div>

                  <div className="doctor-document-source-strip">
                    <span>Sources</span>
                    {review.documents.map((document) => (
                      <span
                        className="doctor-document-source-chip"
                        key={document.id}
                      >
                        {document.filename || "Medical document"}
                      </span>
                    ))}
                  </div>

                  <div className="doctor-document-findings-grid">
                    {renderDocumentDataCard(
                      "Diagnoses",
                      documentFindings.diagnoses,
                      "diagnoses"
                    )}
                    {renderDocumentDataCard(
                      "Laboratory / Test Results",
                      documentFindings.labs,
                      "labs"
                    )}
                    {renderDocumentDataCard(
                      "Prescription / Medications",
                      documentFindings.medications,
                      "medications"
                    )}
                    {renderDocumentDataCard(
                      "Allergies",
                      documentFindings.allergies,
                      "allergies"
                    )}
                    {renderDocumentDataCard(
                      "Procedures",
                      documentFindings.procedures,
                      "procedures"
                    )}
                    {renderDocumentDataCard(
                      "Clinical Findings",
                      documentFindings.findings,
                      "findings"
                    )}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="doctor-card-empty">
              No documents were uploaded for this session.
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
          summaryStatus !== "accepted" &&
          summaryStatus !== "rejected" && (

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
                  onClick={() => navigate(`/doctor/sessions/${sessionId}/edit-summary`)}
                  disabled={isSaving}
                >
                  Edit Summary
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