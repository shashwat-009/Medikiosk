import { useEffect, useState } from "react";
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
  }

  async function handleVoiceResult(
    transcript
  ) {
    if (!transcript?.trim()) {
      return;
    }

    setAnswer(transcript);
    setInputType("voice");
    setInputMode("answered");
    setError("");

    if (!conversationStarted) {
      try {
        await startAdaptiveConversation(
          transcript.trim()
        );
      } catch (err) {
        setError(
          formatError(err)
        );
      }

      return;
    }
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

  async function handleContinue() {
    if (!answer.trim()) {
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
            answer,

          type:
            inputType || "touch",
        });

        await startAdaptiveConversation(
          answer.trim()
        );

        setAnswer("");
        setInputMode("idle");
        setInputType("");

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
          answer,

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
            answer.trim(),

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

          <ProgressTracker
            current={
              conversationStarted
                ? questionNumber + 1
                : 1
            }
            total={10}
          />

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

          {/* Continue */}

          <div className="interview__actions">

            <button
              type="button"
              className="interview__continue"
              onClick={
                handleContinue
              }
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
                : translate(
                  language,
                  "interview.continue"
                )}

              {!isSubmitting &&
                !isStarting && (
                  <span>→</span>
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