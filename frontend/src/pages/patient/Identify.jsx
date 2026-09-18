import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useKiosk } from "../../context/KioskContext";
import { translate } from "../../i18n";
import { createPatient } from "../../services/patientService";
import { createSession } from "../../services/sessionService";
import VoiceButton from "../../components/kiosk/VoiceButton";
import { speakText } from "../../services/ttsService";

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

const HINDI_NUMBER_WORDS = {
  "शून्य": 0, "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
  "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
  "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14, "पंद्रह": 15,
  "सोलह": 16, "सत्रह": 17, "अठारह": 18, "उन्नीस": 19, "बीस": 20,
  "इक्कीस": 21, "बाईस": 22, "तेईस": 23, "चौबीस": 24, "पच्चीस": 25,
  "छब्बीस": 26, "सत्ताईस": 27, "अट्ठाईस": 28, "उनतीस": 29, "तीस": 30,
  "इकतीस": 31, "बत्तीस": 32, "तैंतीस": 33, "चौंतीस": 34, "पैंतीस": 35,
  "छत्तीस": 36, "सैंतीस": 37, "अड़तीस": 38, "उनतालीस": 39, "चालीस": 40,
  "पैंतालीस": 45, "पचास": 50, "पचपन": 55, "साठ": 60, "पैंसठ": 65,
  "सत्तर": 70, "पचहत्तर": 75, "अस्सी": 80, "पचासी": 85, "नब्बे": 90, "पंचानवे": 95, "सौ": 100
};

const HINGLISH_NUMBER_WORDS = {
  ek: 1, do: 2, teen: 3, char: 4, paanch: 5, panch: 5,
  che: 6, chheh: 6, saat: 7, aath: 8, nau: 9, das: 10,
  gyarah: 11, barah: 12, terah: 13, chaudah: 14, pandrah: 15,
  solah: 16, satrah: 17, atharah: 18, unnees: 19, unnis: 19,
  bees: 20, bis: 20,
  ikkees: 21, ikkis: 21, baees: 22, bais: 22, teees: 23, teis: 23, chaubees: 24, chaubis: 24,
  pachees: 25, pachis: 25, chhabees: 26, sattaees: 27, atthayees: 28, untees: 29,
  tees: 30, iktees: 31, battees: 32, taintees: 33, chautees: 34, paintis: 35,
  chhatees: 36, saintees: 37, adtees: 38, untalis: 39,
  chalis: 40, iktalis: 41, bayalis: 42, tentalis: 43, chauvalis: 44, paintalis: 45,
  pachas: 50, pachpan: 55,
  saath: 60, sath: 60,
  sattar: 70, pachhattar: 75,
  assi: 80, pachasi: 85,
  nabbe: 90, sau: 100,
};

const DEVANAGARI_DIGITS_MAP = {
  '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
  '५': '5', '६': '6', '७': '7', '८': '8', '९': '9',
};

const SPOKEN_DIGITS = {
  zero: "0", oh: "0", one: "1", two: "2", three: "3", four: "4",
  five: "5", six: "6", seven: "7", eight: "8", nine: "9",
  "शून्य": "0", "एक": "1", "दो": "2", "तीन": "3", "चार": "4",
  "पांच": "5", "पाँच": "5", "छह": "6", "छः": "6", "सात": "7",
  "आठ": "8", "नौ": "9",
};

function parseSpokenAge(text) {
  if (!text) return null;

  // Convert Devanagari numerals to 0-9
  let normalized = String(text)
    .replace(/[०-९]/g, (ch) => DEVANAGARI_DIGITS_MAP[ch] || ch)
    .toLowerCase();

  // Strip punctuation but keep spaces
  normalized = normalized.replace(/[.,\/#!$%\^&\*;:{}=\-_`~()]/g, " ").trim();

  // Check direct digit match
  const digitMatch = normalized.match(/\b([1-9]|[1-9]\d|1[01]\d|120)\b/);
  if (digitMatch) return Number(digitMatch[1]);

  // Check Hindi Devanagari words (e.g. "बीस")
  for (const [word, val] of Object.entries(HINDI_NUMBER_WORDS)) {
    if (normalized.includes(word) && val >= AGE_MIN && val <= AGE_MAX) {
      return val;
    }
  }

  // Check English, Hindi & Hinglish words (e.g. "twenty", "bees")
  const tokens = normalized.split(/\s+/).filter(Boolean);
  let total = 0;
  let found = false;

  for (const token of tokens) {
    if (ENGLISH_NUMBER_WORDS[token] !== undefined) {
      total += ENGLISH_NUMBER_WORDS[token];
      found = true;
    } else if (HINDI_NUMBER_WORDS[token] !== undefined) {
      total += HINDI_NUMBER_WORDS[token];
      found = true;
    } else if (HINGLISH_NUMBER_WORDS[token] !== undefined) {
      total += HINGLISH_NUMBER_WORDS[token];
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
    console.log("Transcribed age voice received:", text);
    const age = parseSpokenAge(text);
    console.log("Parsed age:", age);

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
            data-tts={t("common.back", "Back")}
          >
            <span data-no-tts aria-hidden="true">←</span>
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
            data-tts={
              isSubmitting
                ? t("common.loading", "Loading...")
                : t("identify.continue", "Continue")
            }
          >
            <span>
              {isSubmitting
                ? t("common.loading", "Loading...")
                : t("identify.continue", "Continue")}
            </span>

            {!isSubmitting && <span data-no-tts aria-hidden="true">→</span>}
          </button>
        </form>
      </section>
    </main>
  );
}
