import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useKiosk } from "../../context/KioskContext";
import { translate } from "../../i18n";
import { createPatient } from "../../services/patientService";
import { createSession } from "../../services/sessionService";
import VoiceButton from "../../components/kiosk/VoiceButton";

import "./Identify.css";

const AGE_MIN = 1;
const AGE_MAX = 120;

const ENGLISH_NUMBER_WORDS = {
  zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5,
  six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  eleven: 11, twelve: 12, thirteen: 13, fourteen: 14,
  fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19,
  twenty: 20, thirty: 30, forty: 40, fifty: 50,
  sixty: 60, seventy: 70, eighty: 80, ninety: 90,
};

const SPOKEN_DIGITS = {
  zero: "0", oh: "0", one: "1", two: "2", three: "3", four: "4",
  five: "5", six: "6", seven: "7", eight: "8", nine: "9",
  "शून्य": "0", "एक": "1", "दो": "2", "तीन": "3", "चार": "4",
  "पांच": "5", "पाँच": "5", "छह": "6", "छः": "6", "सात": "7",
  "आठ": "8", "नौ": "9",
};

function parseSpokenAge(text) {
  const normalized = String(text || "").trim().toLowerCase();
  const digitMatch = normalized.match(/\b([1-9]|[1-9]\d|1[01]\d|120)\b/);
  if (digitMatch) return Number(digitMatch[1]);

  const tokens = normalized.replace(/[-,]/g, " ").split(/\s+/).filter(Boolean);
  let total = 0;
  let found = false;

  for (const token of tokens) {
    if (ENGLISH_NUMBER_WORDS[token] !== undefined) {
      total += ENGLISH_NUMBER_WORDS[token];
      found = true;
    }
  }

  return found && total >= AGE_MIN && total <= AGE_MAX ? total : null;
}

function parseSpokenAadhaar(text) {
  const raw = String(text || "").trim();
  const directDigits = raw.replace(/\D/g, "");
  if (directDigits.length >= 12) return directDigits.slice(0, 12);

  const tokens = raw.toLowerCase().replace(/[-,]/g, " ").split(/\s+/).filter(Boolean);

  return tokens
    .map((token) => SPOKEN_DIGITS[token])
    .filter((digit) => digit !== undefined)
    .join("")
    .slice(0, 12);
}

function formatAadhaar(value) {
  const digits = String(value || "").replace(/\D/g, "").slice(0, 12);
  return digits.replace(/(\d{4})(?=\d)/g, "$1 ");
}

export default function Identify() {
  const navigate = useNavigate();
  const { state, setPatient, setSession } = useKiosk();

  const language = state.language || "en";

  const [form, setForm] = useState({
    name: "",
    age: "",
    gender: "",
    aadhaar: "",
  });

  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeVoiceField, setActiveVoiceField] = useState(null);
  const ageTouchStartRef = useRef(null);

  const t = (key, fallback) => {
    const value = translate(language, key);
    return value === key && fallback ? fallback : value;
  };

  function handleChange(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
    setError("");
  }

  function setAgeValue(age) {
    if (age < AGE_MIN || age > AGE_MAX) return;
    setForm((current) => ({ ...current, age: String(age) }));
    setError("");
  }

  function changeAge(delta) {
    const currentAge = Number(form.age);

    if (!Number.isFinite(currentAge) || !form.age) {
      setAgeValue(delta > 0 ? AGE_MIN : AGE_MAX);
      return;
    }

    setAgeValue(currentAge + delta);
  }

  function handleNameVoice(text) {
    const value = String(text || "")
      .trim()
      .replace(/^(my name is|mera naam hai|मेरा नाम है|मेरा नाम)\s+/i, "")
      .trim();

    if (value) {
      setForm((current) => ({ ...current, name: value }));
      setError("");
    }

    setActiveVoiceField(null);
  }

  function handleGenderVoice(text) {
    const normalized = String(text || "").trim().toLowerCase();

    if (
      normalized.includes("female") ||
      normalized.includes("woman") ||
      normalized.includes("girl") ||
      normalized.includes("महिला") ||
      normalized.includes("औरत") ||
      normalized.includes("स्त्री")
    ) {
      setForm((current) => ({ ...current, gender: "female" }));
      setError("");
    } else if (
      normalized.includes("male") ||
      normalized.includes("man") ||
      normalized.includes("boy") ||
      normalized.includes("पुरुष") ||
      normalized.includes("आदमी") ||
      normalized.includes("लड़का")
    ) {
      setForm((current) => ({ ...current, gender: "male" }));
      setError("");
    } else if (normalized.includes("other") || normalized.includes("अन्य")) {
      setForm((current) => ({ ...current, gender: "other" }));
      setError("");
    } else {
      setError(
        t(
          "identify.genderNotUnderstood",
          "We couldn't understand that. Please say male, female, or other."
        )
      );
    }

    setActiveVoiceField(null);
  }

  function handleAgePointerDown(event) {
    ageTouchStartRef.current = event.clientY;
  }

  function handleAgePointerUp(event) {
    if (ageTouchStartRef.current === null) return;

    const delta = event.clientY - ageTouchStartRef.current;
    ageTouchStartRef.current = null;

    if (Math.abs(delta) < 18) return;
    changeAge(delta < 0 ? 1 : -1);
  }

  function handleAgeWheel(event) {
    event.preventDefault();
    changeAge(event.deltaY > 0 ? -1 : 1);
  }

  function handleAgeVoice(text) {
    const age = parseSpokenAge(text);

    if (age !== null) {
      setAgeValue(age);
    } else {
      setError(
        t(
          "identify.ageNotUnderstood",
          "We couldn't understand the age. Please say the number again."
        )
      );
    }

    setActiveVoiceField(null);
  }

  function handleAadhaarVoice(text) {
    const aadhaar = parseSpokenAadhaar(text);

    if (aadhaar.length === 12) {
      setForm((current) => ({ ...current, aadhaar }));
      setError("");
    } else {
      setError(
        t(
          "identify.aadhaarIncomplete",
          "Please say all 12 digits of your Aadhaar number."
        )
      );
    }

    setActiveVoiceField(null);
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (!form.name.trim()) {
      setError(t("identify.nameRequired", "Please enter your name."));
      return;
    }

    if (!form.age) {
      setError(t("identify.ageRequired", "Please enter your age."));
      return;
    }

    if (!form.gender) {
      setError(t("identify.genderRequired", "Please select your gender."));
      return;
    }

    if (form.aadhaar.length !== 12) {
      setError(
        t(
          "identify.aadhaarRequired",
          "Please enter a valid 12-digit Aadhaar number."
        )
      );
      return;
    }

    setError("");
    setIsSubmitting(true);

    try {
      const patient = await createPatient({
        name: form.name.trim(),
        age: Number(form.age),
        gender: form.gender,
        aadhaar: form.aadhaar,
      });

      setPatient(patient);

      const session = await createSession(patient.id);
      setSession(session);

      navigate("/consent");
    } catch (err) {
      console.error("Patient/session creation failed:", err);
      setError(
        err.message ||
          t("common.error", "Something went wrong. Please try again.")
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  const selectedAge = Number(form.age);
  const previousAge = form.age && selectedAge > AGE_MIN ? selectedAge - 1 : null;
  const nextAge =
    form.age && selectedAge < AGE_MAX
      ? selectedAge + 1
      : !form.age
        ? AGE_MIN
        : null;

  const genderOptions = [
    { value: "male", symbol: "♂", label: t("identify.male", "Male") },
    { value: "female", symbol: "♀", label: t("identify.female", "Female") },
    { value: "other", symbol: "⚧", label: t("identify.other", "Other") },
  ];

  return (
    <main className="identify">
      <section className="identify__container">
        <header className="identify__header">
          <button
            type="button"
            className="identify__back"
            onClick={() => navigate("/")}
            disabled={isSubmitting}
          >
            <span aria-hidden="true">←</span>
            {t("common.back", "Back")}
          </button>

          <div className="mode-selection__step">
            1 / 3
          </div>
        </header>

        <div className="identify__intro">
          <p className="identify__eyebrow">
            {t("identify.eyebrow", "PATIENT IDENTIFICATION")}
          </p>

          <h1>{t("identify.title", "Let's get you started")}</h1>

          <p>
            {t(
              "identify.description",
              "Tell us a few basic details. You can type them or use the microphone."
            )}
          </p>
        </div>

        <form className="identify__card" onSubmit={handleSubmit}>
          <div className="identify__fields">
            <section className="identify__field-card">
              <div className="identify__field-heading">
                <div>
                  <span className="identify__field-number">01</span>
                  <div>
                    <label htmlFor="name" className="identify__field-label">
                      {t("identify.name", "Your name")}
                    </label>
                  </div>
                </div>
              </div>

              <div className="identify__input-with-voice">
                <input
                  id="name"
                  name="name"
                  type="text"
                  value={form.name}
                  onChange={handleChange}
                  placeholder={t(
                    "identify.namePlaceholder",
                    "Enter your full name"
                  )}
                  autoComplete="name"
                  disabled={isSubmitting}
                />

                <div className="identify__voice">
                  <VoiceButton
                    state={activeVoiceField === "name" ? "listening" : "idle"}
                    onStart={() => setActiveVoiceField("name")}
                    onResult={handleNameVoice}
                    onError={() => setActiveVoiceField(null)}
                  />
                </div>
              </div>
            </section>

            <section className="identify__field-card">
              <div className="identify__field-heading">
                <div>
                  <span className="identify__field-number">02</span>
                  <div>
                    <span className="identify__field-label">
                      {t("identify.age", "Age")}
                    </span>
                  </div>
                </div>
              </div>

              <div className="identify__interactive-row">
                <div
                  className="identify__age-selector"
                  aria-label={t("identify.ageSelector", "Age selector")}
                >
                  <button
                    type="button"
                    className="identify__age-control"
                    onClick={() => changeAge(-1)}
                    disabled={
                      isSubmitting || (form.age && selectedAge <= AGE_MIN)
                    }
                    aria-label={t("identify.decreaseAge", "Decrease age")}
                  >
                    −
                  </button>

                  <div
                    className="identify__age-wheel"
                    onWheel={handleAgeWheel}
                    onPointerDown={handleAgePointerDown}
                    onPointerUp={handleAgePointerUp}
                    onPointerCancel={() => {
                      ageTouchStartRef.current = null;
                    }}
                    onPointerLeave={() => {
                      ageTouchStartRef.current = null;
                    }}
                    title={t(
                      "identify.ageWheelHint",
                      "Swipe or scroll to change age"
                    )}
                  >
                    <span className="identify__age-neighbour">
                      {previousAge ?? ""}
                    </span>
                    <span className="identify__age-selected">
                      {form.age || "—"}
                    </span>
                    <span className="identify__age-neighbour">
                      {nextAge ?? ""}
                    </span>
                  </div>

                  <button
                    type="button"
                    className="identify__age-control"
                    onClick={() => changeAge(1)}
                    disabled={
                      isSubmitting || (form.age && selectedAge >= AGE_MAX)
                    }
                    aria-label={t("identify.increaseAge", "Increase age")}
                  >
                    +
                  </button>
                </div>

                <div className="identify__voice">
                  <VoiceButton
                    state={activeVoiceField === "age" ? "listening" : "idle"}
                    onStart={() => setActiveVoiceField("age")}
                    onResult={handleAgeVoice}
                    onError={() => setActiveVoiceField(null)}
                  />
                </div>
              </div>
            </section>

            <section className="identify__field-card">
              <div className="identify__field-heading">
                <div>
                  <span className="identify__field-number">03</span>
                  <div>
                    <span className="identify__field-label">
                      {t("identify.gender", "Gender")}
                    </span>
                  </div>
                </div>
              </div>

              <div className="identify__interactive-row">
                <div
                  className="identify__gender-grid"
                  role="group"
                  aria-label={t("identify.gender", "Gender")}
                >
                  {genderOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={`identify__gender-option ${
                        form.gender === option.value
                          ? "identify__gender-option--selected"
                          : ""
                      }`}
                      onClick={() => {
                        setForm((current) => ({
                          ...current,
                          gender: option.value,
                        }));
                        setError("");
                      }}
                      disabled={isSubmitting}
                      aria-pressed={form.gender === option.value}
                    >
                      <span className="identify__gender-symbol">
                        {option.symbol}
                      </span>
                      <span className="identify__gender-label">
                        {option.label}
                      </span>
                      {form.gender === option.value && (
                        <span className="identify__gender-check" aria-hidden="true">
                          ✓
                        </span>
                      )}
                    </button>
                  ))}
                </div>

                <div className="identify__voice">
                  <VoiceButton
                    state={activeVoiceField === "gender" ? "listening" : "idle"}
                    onStart={() => setActiveVoiceField("gender")}
                    onResult={handleGenderVoice}
                    onError={() => setActiveVoiceField(null)}
                  />
                </div>
              </div>
            </section>

            <section className="identify__field-card">
              <div className="identify__field-heading">
                <div>
                  <span className="identify__field-number">04</span>
                  <div>
                    <label htmlFor="aadhaar" className="identify__field-label">
                      {t("identify.aadhaar", "Aadhaar number")}
                    </label>
                  </div>
                </div>
              </div>

              <div className="identify__input-with-voice">
                <input
                  id="aadhaar"
                  name="aadhaar"
                  type="text"
                  inputMode="numeric"
                  value={formatAadhaar(form.aadhaar)}
                  onChange={(event) => {
                    const value = event.target.value
                      .replace(/\D/g, "")
                      .slice(0, 12);

                    setForm((current) => ({
                      ...current,
                      aadhaar: value,
                    }));
                    setError("");
                  }}
                  placeholder={t(
                    "identify.aadhaarPlaceholder",
                    "XXXX XXXX XXXX"
                  )}
                  autoComplete="off"
                  maxLength={14}
                  disabled={isSubmitting}
                />

                <div className="identify__voice">
                  <VoiceButton
                    state={
                      activeVoiceField === "aadhaar" ? "listening" : "idle"
                    }
                    onStart={() => setActiveVoiceField("aadhaar")}
                    onResult={handleAadhaarVoice}
                    onError={() => setActiveVoiceField(null)}
                  />
                </div>
              </div>
            </section>
          </div>

          {error && (
            <div className="identify__error" role="alert">
              {error}
            </div>
          )}

          <button
            type="submit"
            className="identify__continue"
            disabled={isSubmitting}
          >
            <span>
              {isSubmitting
                ? t("common.loading", "Loading...")
                : t("identify.continue", "Continue")}
            </span>

            {!isSubmitting && <span aria-hidden="true">→</span>}
          </button>
        </form>
      </section>
    </main>
  );
}
