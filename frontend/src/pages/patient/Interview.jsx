import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useKiosk } from "../../context/KioskContext";
import { translate } from "../../i18n";

import {
  startConversation,
  submitConversationAnswer,
} from "../../services/conversationService";

import { createResponse } from "../../services/responseService";

import {
  speakText,
  stopSpeech,
} from "../../services/ttsService";

import ProgressTracker from "../../components/kiosk/ProgressTracker";
import VoiceButton from "../../components/kiosk/VoiceButton";
import TouchOptions from "../../components/kiosk/TouchOptions";
import RedFlagOverlay from "../../components/kiosk/RedFlagOverlay";
import InterviewQuestion from "../../components/patient/InterviewQuestion";

import "./Interview.css";

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
   *
   * Automatically speaks the current question whenever
   * the question changes.
   * ============================================================
   */

  useEffect(() => {
    const questionText =
      displayQuestion?.trim();

    if (!questionText) {
      return;
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
      forcedAnswer !== null ? forcedAnswer : answer;

    if (!answerToUse.trim()) {
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

    setError("");
    setIsSubmitting(true);

    try {
      /*
       * --------------------------------------------------------
       * Chief complaint phase
       * --------------------------------------------------------
       */

      if (!conversationStarted) {
        await saveBackendResponse({
          question: {
            id: "chief_complaint",
            question: "Chief complaint",
          },

          answerValue:
            answerToUse,

          type:
            inputType || "touch",
        });

        await startAdaptiveConversation(
          answerToUse.trim()
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

      if (!currentQuestion) {
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
          currentQuestion,

        answerValue:
          answerToUse,

        type:
          inputType || "touch",
      });

      /*
       * --------------------------------------------------------
       * Tell DialogueManager about the answer
       * --------------------------------------------------------
       */

      const result =
        await submitConversationAnswer({
          sessionId:
            state.session.id,

          fieldId:
            currentQuestion.field_id,

          answer:
            answerToUse.trim(),

          questionId:
            getQuestionId(
              currentQuestion
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
    if (isSubmitting || isStarting) {
      return;
    }

    if (!conversationStarted) {
      const defaultComplaint =
        language === "hi" ? "बुखार" : "fever";
      await handleContinue(defaultComplaint);
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

  // 1. Inactivity Timer (60s) - counts down when no answer has been given yet
  useEffect(() => {
    if (answer.trim()) {
      return;
    }

    setInactivitySeconds(60);

    const interval = setInterval(() => {
      if (
        inputModeRef.current === "listening" ||
        isSubmittingRef.current ||
        isStartingRef.current ||
        state.redFlag ||
        isPausedRef.current
      ) {
        return;
      }

      setInactivitySeconds((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          const fallback = !conversationStartedRef.current
            ? (language === "hi" ? "बुखार" : "fever")
            : (translate(language, "interview.noResponse") || "No response");

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
    answer === "",
    language,
    state.redFlag,
  ]);

  // 2. Countdown Timer (10s) - counts down once an answer is given
  useEffect(() => {
    if (!answer.trim()) {
      setAutoAdvanceSeconds(10);
      return;
    }

    setAutoAdvanceSeconds(10);

    const interval = setInterval(() => {
      if (
        inputModeRef.current === "listening" ||
        isSubmittingRef.current ||
        isStartingRef.current ||
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
  ]);

  /*
   * ============================================================
   * Back
   * ============================================================
   */

  function handleBack() {
    if (
      isSubmitting ||
      isStarting
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
            disabled={
              isSubmitting ||
              isStarting
            }
          >
            ←{" "}
            {translate(
              language,
              "common.back"
            )}
          </button>

          <div className="interview__header-tools">
            {!answer.trim() && (
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

            <ProgressTracker
              current={
                conversationStarted
                  ? questionNumber + 1
                  : 1
              }
              total={10}
            />
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
                isStarting
              }
              aria-label={translate(
                language,
                "interview.listenQuestion"
              )}
            >
              🔊{" "}
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
                isStarting
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

          {/* Chief Complaint quick selection chips */}
          {!conversationStarted && (
            <div style={{ margin: "20px 0" }}>
              <p style={{ fontSize: "14px", fontWeight: "600", color: "var(--muted)", marginBottom: "12px" }}>
                {language === "hi" ? "👇 या नीचे दिए गए मुख्य लक्षणों में से चुनें:" : "👇 Or select a common symptom below:"}
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
                {[
                  { id: "fever", label: language === "hi" ? "🌡️ बुखार (Fever)" : "🌡️ Fever" },
                  { id: "cough", label: language === "hi" ? "💨 खांसी (Cough)" : "💨 Cough" },
                  { id: "headache", label: language === "hi" ? "🧠 सिर दर्द (Headache)" : "🧠 Headache" },
                  { id: "abdominal_pain", label: language === "hi" ? "🤢 पेट दर्द (Stomach Pain)" : "🤢 Stomach Pain" },
                  { id: "chest_pain", label: language === "hi" ? "❤️ सीने में दर्द (Chest Pain)" : "❤️ Chest Pain" },
                ].map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setAnswer(item.id);
                      setInputType("touch");
                      setInputMode("answered");
                      setAutoAdvanceSeconds(10);
                      setIsPaused(false);
                      setError("");
                    }}
                    style={{
                      padding: "10px 18px",
                      borderRadius: "24px",
                      border: answer === item.id ? "2px solid #0d9488" : "1px solid #cbd5e1",
                      background: answer === item.id ? "#f0fdfa" : "#ffffff",
                      color: answer === item.id ? "#0f766e" : "#334155",
                      fontWeight: answer === item.id ? "700" : "500",
                      fontSize: "15px",
                      cursor: "pointer",
                      boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                      transition: "all 0.15s ease",
                    }}
                  >
                    {item.label}
                  </button>
                ))}
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

          {/* Text */}

          {!hasTouchOptions && (
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
                    isStarting
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
                {answer}
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
                >
                  {isPaused ? "▶️ Resume" : "⏸️ Pause"}
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

          <div className="interview__actions">

            <button
              type="button"
              className="interview__skip"
              onClick={handleSkip}
              disabled={
                isSubmitting ||
                isStarting
              }
            >
              <span>⏭️</span>
              <span>
                {translate(
                  language,
                  "interview.skip"
                )}
              </span>
            </button>

            <button
              type="button"
              className={`interview__continue ${
                answer.trim() && !isPaused
                  ? "interview__continue--active"
                  : ""
              }`}
              onClick={() => handleContinue()}
              disabled={
                isSubmitting ||
                isStarting
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
                      <span className="interview__continue-timer-pill">
                        {autoAdvanceSeconds}s
                      </span>
                    )}

                    {!isSubmitting &&
                      !isStarting && (
                        <span>→</span>
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