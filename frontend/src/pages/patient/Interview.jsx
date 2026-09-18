import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useKiosk } from "../../context/KioskContext";
import { translate } from "../../i18n";

import {
  startConversation,
  submitConversationAnswer,
  getNextConversationQuestion,
} from "../../services/conversationService";

import { createResponse } from "../../services/responseService";

import {
  speakText,
  stopSpeech,
} from "../../services/ttsService";

import VoiceButton from "../../components/kiosk/VoiceButton";
import TouchOptions from "../../components/kiosk/TouchOptions";
import RedFlagOverlay from "../../components/kiosk/RedFlagOverlay";
import InterviewQuestion from "../../components/patient/InterviewQuestion";

import "./Interview.css";

const CHIEF_COMPLAINT_OPTIONS = [
  {
    id: "fever",
    icon: "🌡️",
    labelByLang: {
      en: "Fever",
      hi: "बुखार (Fever)",
      mr: "ताप (Fever)",
      bn: "জ্বর (Fever)",
    },
  },
  {
    id: "cough",
    icon: "💨",
    labelByLang: {
      en: "Cough",
      hi: "खांसी (Cough)",
      mr: "खोकला (Cough)",
      bn: "কাশি (Cough)",
    },
  },
  {
    id: "headache",
    icon: "🧠",
    labelByLang: {
      en: "Headache",
      hi: "सिर दर्द (Headache)",
      mr: "डोकेदुखी (Headache)",
      bn: "মাথাব্যথা (Headache)",
    },
  },
  {
    id: "abdominal_pain",
    icon: "🤢",
    labelByLang: {
      en: "Stomach Pain",
      hi: "पेट दर्द (Stomach Pain)",
      mr: "पोटदुखी (Stomach Pain)",
      bn: "পেটে ব্যথা (Stomach Pain)",
    },
  },
  {
    id: "chest_pain",
    icon: "❤️",
    labelByLang: {
      en: "Chest Pain",
      hi: "सीने में दर्द (Chest Pain)",
      mr: "छातीत दुखणे (Chest Pain)",
      bn: "বুকে ব্যথা (Chest Pain)",
    },
  },
  {
    id: "other",
    icon: "🩺",
    labelByLang: {
      en: "Others",
      hi: "अन्य (Others)",
      mr: "इतर (Others)",
      bn: "অন্যান্য (Others)",
    },
  },
];

export default function Interview() {
  const navigate = useNavigate();

  const {
    state,
    pushTranscript,
    triggerRedFlag,
    clearRedFlag,
  } = useKiosk();

  const language = state.language || "en";
  const mode = state.mode || "allopathy";

  const [conversationStarted, setConversationStarted] =
    useState(false);

  const [chiefComplaint, setChiefComplaint] =
    useState("");

  const [currentQuestion, setCurrentQuestion] =
    useState(null);

  const [answer, setAnswer] =
    useState("");

  const [inputMode, setInputMode] =
    useState("idle");

  const [inputType, setInputType] =
    useState("");

  const [error, setError] =
    useState("");

  const [isSubmitting, setIsSubmitting] =
    useState(false);

  const [isStarting, setIsStarting] =
    useState(false);

  const [isRestoring, setIsRestoring] =
    useState(true);

  const [questionNumber, setQuestionNumber] =
    useState(1);

  const [inactivitySeconds, setInactivitySeconds] =
    useState(60);

  const [autoAdvanceSeconds, setAutoAdvanceSeconds] =
    useState(10);

  const [isPaused, setIsPaused] =
    useState(false);

  const answerRef = useRef(answer);
  answerRef.current = answer;

  const isSubmittingRef = useRef(isSubmitting);
  isSubmittingRef.current = isSubmitting;

  const isStartingRef = useRef(isStarting);
  isStartingRef.current = isStarting;

  const inputModeRef = useRef(inputMode);
  inputModeRef.current = inputMode;

  const isPausedRef = useRef(isPaused);
  isPausedRef.current = isPaused;

  const conversationStartedRef = useRef(conversationStarted);
  conversationStartedRef.current = conversationStarted;

  const handleContinueRef = useRef(null);

  /*
   * ============================================================
   * Helpers
   * ============================================================
   */

  function getQuestionText(question) {
    if (!question) {
      return "";
    }

    return (
      question.question ??
      question.text ??
      ""
    );
  }

  function getQuestionId(question) {
    if (!question) {
      return null;
    }

    return (
      question.id ??
      question.question_id ??
      null
    );
  }

  function formatError(errorValue) {
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
      if (typeof errorValue.message === "string") {
        return errorValue.message;
      }

      if (typeof errorValue.detail === "string") {
        return errorValue.detail;
      }

      try {
        return JSON.stringify(errorValue);
      } catch {
        return translate(
          language,
          "common.error"
        );
      }
    }

    return String(errorValue);
  }

  function getDisplayAnswer(val, lang) {
    if (!val) return "";
    if (!conversationStarted) {
      const match = CHIEF_COMPLAINT_OPTIONS.find((opt) => opt.id === val);
      if (match) {
        const text = match.labelByLang[lang] || match.labelByLang.en;
        return `${match.icon} ${text}`;
      }
    }
    return val;
  }

  /*
   * ============================================================
   * Resume an already-started conversation
   *
   * The backend is the source of truth. A session with persisted
   * conversation_state is resumed through /conversation/{id}/next.
   * A 404 here means this is a brand-new session that has not yet
   * started the interview, so the normal chief-complaint screen is
   * shown.
   *
   * This is deliberately guarded with a ref because React StrictMode
   * can invoke effects more than once during development.
   * ============================================================
   */

  useEffect(() => {
    const sessionId = state.session?.id;

    if (!sessionId) {
      setIsRestoring(false);
      setError(
        "No active session found. Please restart the visit."
      );
      return undefined;
    }

    let cancelled = false;

    async function restoreConversation() {
      setIsRestoring(true);
      setError("");

      try {
        const result =
          await getNextConversationQuestion(sessionId);

        if (cancelled) {
          return;
        }

        if (result?.completed || !result?.question) {
          stopSpeech();
          navigate("/documents", { replace: true });
          return;
        }

        setConversationStarted(true);
        setCurrentQuestion(result.question);
        setChiefComplaint(
          state.session?.complaint || ""
        );

        /*
         * The backend state determines the actual question.
         * We intentionally do not call startConversation here,
         * because doing so would reset the DialogueManager state.
         *
         * questionNumber is a UI-only counter. The persisted backend
         * state remains authoritative for the actual question.
         */
        setQuestionNumber(1);
        setAnswer("");
        setInputMode("idle");
        setInputType("");
        setAutoAdvanceSeconds(10);
        setInactivitySeconds(60);
        setIsPaused(false);
      } catch (err) {
        if (cancelled) {
          return;
        }

        /*
         * 404 means this session has no persisted conversation yet.
         * That is the expected state immediately after patient login,
         * before the chief complaint is submitted.
         */
        if (err?.status === 404 || err?.statusCode === 404) {
          setConversationStarted(false);
          setCurrentQuestion(null);
          setChiefComplaint("");
          setQuestionNumber(1);
          setAnswer("");
          setInputMode("idle");
          setInputType("");
          setError("");
          return;
        }

        console.error(
          "Failed to restore conversation:",
          err
        );

        setError(formatError(err));
      } finally {
        if (!cancelled) {
          setIsRestoring(false);
        }
      }
    }

    restoreConversation();

    return () => {
      cancelled = true;
    };
  }, [state.session?.id, navigate]);

  /*
   * ============================================================
   * Current question text
   * ============================================================
   */

  const displayQuestion =
    conversationStarted
      ? getQuestionText(currentQuestion)
      : translate(
        language,
        "interview.questions.chiefComplaint"
      );

  /*
   * ============================================================
   * Question TTS
   * ============================================================
   */

  useEffect(() => {
    if (isRestoring) {
      return undefined;
    }

    const questionText =
      displayQuestion?.trim();

    if (!questionText) {
      return undefined;
    }

    let cancelled = false;

    async function speakQuestion() {
      try {
        await speakText(
          questionText,
          language
        );
      } catch (error) {
        if (!cancelled) {
          console.warn(
            "Question TTS failed:",
            error
          );
        }
      }
    }

    speakQuestion();

    return () => {
      cancelled = true;
      stopSpeech();
    };
  }, [
    displayQuestion,
    language,
    isRestoring,
  ]);

  /*
   * ============================================================
   * Start adaptive conversation
   * ============================================================
   */

  async function startAdaptiveConversation(
    complaint
  ) {
    if (!state.session?.id) {
      throw new Error(
        "No active session found."
      );
    }

    setIsStarting(true);
    setError("");

    try {
      const result =
        await startConversation({
          sessionId: state.session.id,
          complaint,
          language,
          mode,
        });

      if (!result?.question) {
        if (result?.completed) {
          stopSpeech();
          navigate("/documents");
          return;
        }

        throw new Error(
          "The server did not return a first question."
        );
      }

      setConversationStarted(true);

      setCurrentQuestion(
        result.question
      );

      setQuestionNumber(1);

      setChiefComplaint(
        complaint
      );
    } catch (err) {
      console.error(
        "Failed to start conversation:",
        err
      );

      throw err;
    } finally {
      setIsStarting(false);
    }
  }

  /*
   * ============================================================
   * Voice
   * ============================================================
   */

  function handleVoiceStart() {
    setError("");
    setInputMode("listening");
    setInputType("voice");
    setIsPaused(false);
  }

  async function handleVoiceResult(
    transcript
  ) {
    if (!transcript?.trim()) {
      return;
    }

    const clean = transcript.trim();
    setAnswer(clean);
    setInputType("voice");
    setInputMode("answered");
    setAutoAdvanceSeconds(10);
    setIsPaused(false);
    setError("");
  }

  /*
   * ============================================================
   * Touch
   * ============================================================
   */

  function handleTouchAnswer(value) {
    setAnswer(value);
    setInputMode("answered");
    setInputType("touch");
    setAutoAdvanceSeconds(10);
    setIsPaused(false);
    setError("");
  }

  /*
   * ============================================================
   * Text
   * ============================================================
   */

  function handleTextChange(event) {
    const value =
      event.target.value;

    setAnswer(value);
    setInputMode("answered");
    setInputType("touch");
    setAutoAdvanceSeconds(10);
    setIsPaused(false);
    setError("");
  }

  /*
   * ============================================================
   * Save response
   * ============================================================
   */

  async function saveBackendResponse({
    question,
    answerValue,
    type,
  }) {
    if (!state.session?.id) {
      throw new Error(
        "No active session found."
      );
    }

    const questionText =
      getQuestionText(question);

    if (!questionText) {
      throw new Error(
        "Question text is missing."
      );
    }

    const response =
      await createResponse({
        session_id:
          state.session.id,

        question:
          questionText,

        answer:
          answerValue.trim(),

        input_type:
          type || "touch",

        language,
      });

    pushTranscript({
      questionId:
        getQuestionId(question),

      question:
        questionText,

      answer:
        answerValue.trim(),

      language,

      inputType:
        type || "touch",

      timestamp:
        new Date().toISOString(),

      backendResponseId:
        response.id,
    });

    return response;
  }

  /*
   * ============================================================
   * Continue
   * ============================================================
   */

  async function handleContinue(forcedAnswer = null) {
    const answerToUse =
      forcedAnswer !== null ? forcedAnswer : answerRef.current;

    if (!String(answerToUse || "").trim()) {
      setError(
        translate(
          language,
          "interview.errors.answerRequired"
        )
      );

      return;
    }

    if (!state.session?.id) {
      setError(
        "No active session found. Please restart the visit."
      );

      return;
    }

    if (isSubmittingRef.current || isStartingRef.current) {
      return;
    }

    setError("");
    setIsSubmitting(true);

    try {
      /*
       * --------------------------------------------------------
       * Chief complaint phase
       * --------------------------------------------------------
       */

      if (!conversationStartedRef.current) {
        await saveBackendResponse({
          question: {
            id: "chief_complaint",
            question: "Chief complaint",
          },

          answerValue:
            String(answerToUse),

          type:
            inputType || "touch",
        });

        await startAdaptiveConversation(
          String(answerToUse).trim()
        );

        setAnswer("");
        setInputMode("idle");
        setInputType("");
        setAutoAdvanceSeconds(10);
        setInactivitySeconds(60);
        setIsPaused(false);

        return;
      }

      /*
       * --------------------------------------------------------
       * Safety check
       * --------------------------------------------------------
       */

      const questionAtSubmission = currentQuestion;

      if (!questionAtSubmission) {
        throw new Error(
          "No current question is available."
        );
      }

      /*
       * --------------------------------------------------------
       * Save patient's answer
       * --------------------------------------------------------
       */

      await saveBackendResponse({
        question:
          questionAtSubmission,

        answerValue:
          String(answerToUse),

        type:
          inputType || "touch",
      });

      /*
       * --------------------------------------------------------
       * Tell DialogueManager about the answer.
       * The backend loads the persisted DialogueState from the DB,
       * processes the answer, and persists the new state.
       * --------------------------------------------------------
       */

      const result =
        await submitConversationAnswer({
          sessionId:
            state.session.id,

          fieldId:
            questionAtSubmission.field_id,

          answer:
            String(answerToUse).trim(),

          questionId:
            getQuestionId(
              questionAtSubmission
            ),

          inputType:
            inputType || "touch",
        });

      /*
       * --------------------------------------------------------
       * Red flag
       * --------------------------------------------------------
       */

      if (result?.red_flag) {
        triggerRedFlag(
          result.red_flag
        );
      }

      /*
       * --------------------------------------------------------
       * Conversation complete
       * --------------------------------------------------------
       */

      if (
        result?.completed ||
        !result?.next_question
      ) {
        stopSpeech();
        navigate("/documents");
        return;
      }

      /*
       * --------------------------------------------------------
       * Next adaptive question
       * --------------------------------------------------------
       */

      setCurrentQuestion(
        result.next_question
      );

      setQuestionNumber(
        (current) => current + 1
      );

      setAnswer("");
      setInputMode("idle");
      setInputType("");
      setAutoAdvanceSeconds(10);
      setInactivitySeconds(60);
      setIsPaused(false);

    } catch (err) {
      console.error(
        "Failed to process interview answer:",
        err
      );

      setError(
        formatError(err)
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  handleContinueRef.current = handleContinue;

  /*
   * ============================================================
   * Skip question
   * ============================================================
   */

  async function handleSkip() {
    if (isSubmitting || isStarting || !conversationStarted) {
      return;
    }

    const skipText =
      translate(language, "interview.skipped") ||
      "Skipped";
    await handleContinue(skipText);
  }

  /*
   * ============================================================
   * Timers: Inactivity (60s) and Auto-Advance (10s)
   * ============================================================
   */

  // 1. Inactivity Timer (60s) - counts down when no answer has been given yet (disabled for first question)
  useEffect(() => {
    if (!conversationStarted || answer.trim()) {
      return;
    }

    setInactivitySeconds(60);

    const interval = setInterval(() => {
      if (
        inputModeRef.current === "listening" ||
        isSubmittingRef.current ||
        isStartingRef.current ||
        isRestoring ||
        state.redFlag ||
        isPausedRef.current
      ) {
        return;
      }

      setInactivitySeconds((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          const fallback =
            translate(language, "interview.noResponse") || "No response";

          if (handleContinueRef.current) {
            handleContinueRef.current(fallback);
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [
    currentQuestion,
    conversationStarted,
    answer,
    language,
    state.redFlag,
    isRestoring,
  ]);

  // 2. Countdown Timer (10s) - counts down once an answer is given
  useEffect(() => {
    if (isRestoring || !answer.trim()) {
      setAutoAdvanceSeconds(10);
      return undefined;
    }

    setAutoAdvanceSeconds(10);

    const interval = setInterval(() => {
      if (
        inputModeRef.current === "listening" ||
        isSubmittingRef.current ||
        isStartingRef.current ||
        isRestoring ||
        state.redFlag ||
        isPausedRef.current
      ) {
        return;
      }

      setAutoAdvanceSeconds((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          if (handleContinueRef.current) {
            handleContinueRef.current();
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [
    answer,
    currentQuestion,
    conversationStarted,
    state.redFlag,
    isRestoring,
  ]);

  /*
   * ============================================================
   * Back
   * ============================================================
   */

  function handleBack() {
    if (
      isSubmitting ||
      isStarting ||
      isRestoring
    ) {
      return;
    }

    stopSpeech();
    navigate("/consent");
  }

  /*
   * ============================================================
   * Touch options
   * ============================================================
   */

  const hasTouchOptions =
    conversationStarted &&
    Array.isArray(
      currentQuestion?.options
    ) &&
    currentQuestion.options.length > 0;

  /*
   * ============================================================
   * Safety
   * ============================================================
   */

  if (isRestoring) {
    return (
      <main className="interview">
        <section className="interview__container">
          <div className="interview__intro">
            <p className="interview__eyebrow">
              {translate(
                language,
                "interview.eyebrow"
              )}
            </p>
            <h1>
              {translate(
                language,
                "common.loading"
              )}
            </h1>
            <p>
              Resuming your consultation…
            </p>
          </div>
        </section>
      </main>
    );
  }

  if (
    conversationStarted &&
    !currentQuestion
  ) {
    return null;
  }

  /*
   * ============================================================
   * Render
   * ============================================================
   */

  return (
    <main className="interview">
      <section className="interview__container">

        {/* Header */}

        <header className="interview__header">

          <button
            type="button"
            className="interview__back"
            onClick={handleBack}
            data-tts={translate(language, "common.back")}
            disabled={
              isSubmitting ||
              isStarting
            }
          >
            <span data-no-tts aria-hidden="true">← </span>
            {translate(
              language,
              "common.back"
            )}
          </button>

          <div className="interview__header-tools">
            {conversationStarted && !answer.trim() && (
              <div
                className={`interview__timer-badge ${
                  inactivitySeconds <= 15
                    ? "interview__timer-badge--warning"
                    : ""
                }`}
                title={translate(language, "interview.timeRemaining")}
              >
                <span>⏱️</span>
                <span>{inactivitySeconds}s</span>
              </div>
            )}
          </div>

        </header>

        {/* Intro */}

        <div className="interview__intro">

          <p className="interview__eyebrow">
            {translate(
              language,
              "interview.eyebrow"
            )}
          </p>

          <h1>
            {translate(
              language,
              "interview.title"
            )}
          </h1>

          <p>
            {translate(
              language,
              "interview.description"
            )}
          </p>

        </div>

        {/* Main card */}

        <section className="interview__card">

          <div className="interview__question-with-tts">

            <InterviewQuestion
              question={
                displayQuestion
              }
            />

            <button
              type="button"
              className="interview__listen-question"
              data-no-tts
              onClick={() =>
                speakText(
                  displayQuestion,
                  language
                )
              }
              disabled={
                !displayQuestion ||
                isStarting ||
                isRestoring
              }
              aria-label={translate(
                language,
                "interview.listenQuestion"
              )}
            >
              <span data-no-tts aria-hidden="true">🔊 </span>
              {translate(
                language,
                "interview.listenQuestion"
              )}
            </button>

          </div>

          {/* Voice */}

          <div className="interview__voice-section">

            <VoiceButton
              state={
                isStarting || isRestoring
                  ? "processing"
                  : inputMode
              }

              sessionId={
                state.session?.id
              }

              onStart={
                handleVoiceStart
              }

              onResult={
                handleVoiceResult
              }

              onError={(voiceError) => {
                setInputMode("idle");
                setInputType("");

                setError(
                  formatError(
                    voiceError
                  )
                );
              }}
            />

          </div>

          {/* Chief Complaint options (Question 1) */}
          {!conversationStarted && (
            <div className="interview__complaints">
              <p className="interview__complaints-label">
                <span>👇</span>
                <span>
                  {language === "hi"
                    ? "मुख्य लक्षणों में से चुनें:"
                    : language === "mr"
                    ? "मुख्य लक्षणांमधून निवडा:"
                    : language === "bn"
                    ? "প্রধান উপসর্গ থেকে নির্বাচন করুন:"
                    : "Select your main symptom:"}
                </span>
              </p>

              <div className="interview__complaints-grid">
                {CHIEF_COMPLAINT_OPTIONS.map((item) => {
                  const isSelected = answer === item.id;
                  const isDisabled = item.id === "other";
                  const label =
                    item.labelByLang[language] || item.labelByLang.en;

                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`interview__complaint-btn ${
                        isSelected ? "interview__complaint-btn--selected" : ""
                      } ${isDisabled ? "interview__complaint-btn--disabled" : ""}`}
                      data-tts={label}
                      disabled={isDisabled}
                      aria-disabled={isDisabled}
                      onClick={() => {
                        if (isDisabled) return;
                        setAnswer(item.id);
                        setInputType("touch");
                        setInputMode("answered");
                        setAutoAdvanceSeconds(10);
                        setIsPaused(false);
                        setError("");
                      }}
                      aria-pressed={isSelected}
                    >
                      <span
                        className="interview__complaint-icon"
                        data-no-tts
                        aria-hidden="true"
                      >
                        {item.icon}
                      </span>
                      <span className="interview__complaint-text">
                        {label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Touch options */}

          {hasTouchOptions && (
            <TouchOptions
              label={translate(
                language,
                "interview.tap"
              )}

              options={
                currentQuestion.options
              }

              values={
                currentQuestion.options
              }

              selected={answer}

              onSelect={
                handleTouchAnswer
              }
            />
          )}

          {/* Text - only rendered for subsequent questions when touch options are not available */}

          {conversationStarted && !hasTouchOptions && (
            <>
              <div className="interview__divider">
                <span>
                  {translate(
                    language,
                    "interview.type"
                  )}
                </span>
              </div>

              <div className="interview__text-input">

                <textarea
                  value={answer}
                  onChange={
                    handleTextChange
                  }
                  placeholder={translate(
                    language,
                    "interview.answerLabel"
                  )}
                  disabled={
                    isSubmitting ||
                    isStarting ||
                    isRestoring
                  }
                />

              </div>
            </>
          )}

          {/* Answer */}

          {answer && (
            <div className="interview__answer">

              <span className="interview__answer-label">
                {translate(
                  language,
                  "interview.answerLabel"
                )}
              </span>

              <p>
                {getDisplayAnswer(answer, language)}
              </p>

            </div>
          )}

          {/* Error */}

          {error && (
            <p className="interview__error">
              {error}
            </p>
          )}

          {/* Countdown Timer Banner */}
          {answer.trim() && (
            <div className="interview__auto-banner">
              <div className="interview__auto-banner-header">
                <div className="interview__auto-banner-text">
                  <span>⏱️</span>
                  <span>
                    {translate(language, "interview.autoAdvanceIn")}{" "}
                    <span className="interview__auto-banner-seconds">
                      {autoAdvanceSeconds}s
                    </span>
                  </span>
                </div>

                <button
                  type="button"
                  className="interview__pause-btn"
                  onClick={() => setIsPaused((prev) => !prev)}
                  data-tts={isPaused ? "Resume" : "Pause"}
                >
                  <span data-no-tts aria-hidden="true">
                    {isPaused ? "▶️ " : "⏸️ "}
                  </span>
                  {isPaused ? "Resume" : "Pause"}
                </button>
              </div>

              <div className="interview__progress-track">
                <div
                  className="interview__progress-bar-fill"
                  style={{
                    width: `${Math.max(
                      0,
                      Math.min(100, (autoAdvanceSeconds / 10) * 100)
                    )}%`,
                  }}
                />
              </div>
            </div>
          )}

          {/* Actions */}

          <div
            className={`interview__actions ${
              !conversationStarted ? "interview__actions--mandatory" : ""
            }`}
          >

            {conversationStarted && (
              <button
                type="button"
                className="interview__skip"
                onClick={handleSkip}
                data-tts={translate(language, "interview.skip")}
                disabled={
                  isSubmitting ||
                  isStarting
                }
              >
                <span data-no-tts aria-hidden="true">⏭️ </span>
                <span>
                  {translate(
                    language,
                    "interview.skip"
                  )}
                </span>
              </button>
            )}

            <button
              type="button"
              className={`interview__continue ${
                answer.trim() && !isPaused
                  ? "interview__continue--active"
                  : ""
              }`}
              onClick={() => handleContinue()}
              data-tts={
                isSubmitting || isStarting
                  ? translate(language, "common.loading")
                  : translate(language, "interview.continue")
              }
              disabled={
                isSubmitting ||
                isStarting ||
                (!conversationStarted && !answer.trim())
              }
            >

              {isSubmitting ||
                isStarting
                ? translate(
                  language,
                  "common.loading"
                )
                : (
                  <>
                    {translate(
                      language,
                      "interview.continue"
                    )}

                    {answer.trim() && !isPaused && (
                      <span
                        className="interview__continue-timer-pill"
                        data-no-tts
                        aria-hidden="true"
                      >
                        {autoAdvanceSeconds}s
                      </span>
                    )}

                    {!isSubmitting &&
                      !isStarting && (
                        <span data-no-tts aria-hidden="true">→</span>
                      )}
                  </>
                )}

            </button>

          </div>

        </section>

        {/* Privacy */}

        <p className="interview__privacy">
          {translate(
            language,
            "interview.privacy"
          )}
        </p>

      </section>

      {/* Red flag */}

      <RedFlagOverlay
        flag={state.redFlag}
        onClose={clearRedFlag}
        language={language}
      />

    </main>
  );
}
