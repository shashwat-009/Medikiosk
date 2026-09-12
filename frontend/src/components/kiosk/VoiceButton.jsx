import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { apiForm } from "../../services/api";

import "./VoiceButton.css";

export default function VoiceButton({
  state: _state,
  sessionId,
  language = "en",
  onStart,
  onResult,
  onError,
}) {
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const mountedRef = useRef(true);
  const operationRef = useRef(0);

  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);

  const isListening = isRecording;
  const isProcessing = isTranscribing;

  /*
   * ------------------------------------------------------------
   * Cleanup microphone stream
   * ------------------------------------------------------------
   */

  const stopMicrophoneStream = useCallback(() => {
    const stream = streamRef.current;

    if (stream) {
      stream.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch {
          // Already stopped.
        }
      });
    }

    streamRef.current = null;
  }, []);

  /*
   * ------------------------------------------------------------
   * Error handling
   * ------------------------------------------------------------
   */

  const reportError = useCallback(
    (message) => {
      if (!mountedRef.current) {
        return;
      }

      onError?.(
        message || "Unable to process your voice."
      );
    },
    [onError]
  );

  /*
   * ------------------------------------------------------------
   * Component cleanup
   * ------------------------------------------------------------
   */

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      operationRef.current += 1;

      const recorder = mediaRecorderRef.current;

      if (
        recorder &&
        recorder.state !== "inactive"
      ) {
        try {
          recorder.stop();
        } catch {
          // Already stopped.
        }
      }

      mediaRecorderRef.current = null;

      stopMicrophoneStream();
      chunksRef.current = [];
    };
  }, [stopMicrophoneStream]);

  /*
   * ------------------------------------------------------------
   * Start recording
   *
   * IMPORTANT:
   * Both pre-session and clinical voice input use the
   * same MediaRecorder -> backend -> Sarvam architecture.
   *
   * If sessionId exists:
   *   /asr/transcribe?session_id=...
   *   authenticated using patient session token
   *
   * If sessionId does not exist:
   *   /asr/pre-session
   *   used by Identify
   * ------------------------------------------------------------
   */

  const startRecording = useCallback(async () => {
    if (mediaRecorderRef.current) {
      return;
    }

    if (
      sessionId === undefined ||
      sessionId === null ||
      sessionId === ""
    ) {
      // Pre-session recording is intentionally allowed.
      // It uses /asr/pre-session.
    }

    const operationId = ++operationRef.current;

    let stream = null;
    let recorder = null;

    try {
      if (
        !navigator.mediaDevices?.getUserMedia
      ) {
        throw new Error(
          "Microphone access is not supported by this browser."
        );
      }

      if (
        typeof MediaRecorder === "undefined"
      ) {
        throw new Error(
          "Audio recording is not supported by this browser."
        );
      }

      stream =
        await navigator.mediaDevices.getUserMedia({
          audio: true,
        });

      if (
        !mountedRef.current ||
        operationId !== operationRef.current
      ) {
        stream.getTracks().forEach((track) => {
          try {
            track.stop();
          } catch {
            // Already stopped.
          }
        });

        return;
      }

      streamRef.current = stream;
      chunksRef.current = [];

      recorder = new MediaRecorder(stream);

      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data?.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onerror = () => {
        if (
          operationId !== operationRef.current
        ) {
          return;
        }

        mediaRecorderRef.current = null;
        stopMicrophoneStream();

        if (mountedRef.current) {
          setIsRecording(false);
          setIsTranscribing(false);
        }

        reportError("Unable to record audio.");
      };

      recorder.onstop = async () => {
        if (
          operationId !== operationRef.current
        ) {
          return;
        }

        mediaRecorderRef.current = null;

        stopMicrophoneStream();

        if (mountedRef.current) {
          setIsRecording(false);
          setIsTranscribing(true);
        }

        try {
          const audioBlob = new Blob(
            chunksRef.current,
            {
              type:
                recorder.mimeType ||
                "audio/webm",
            }
          );

          chunksRef.current = [];

          if (audioBlob.size === 0) {
            throw new Error(
              "No audio was recorded. Please try again."
            );
          }

          const formData = new FormData();

          formData.append(
            "file",
            audioBlob,
            "voice-input.webm"
          );

          let result;

          /*
           * --------------------------------------------------
           * CLINICAL SESSION
           * --------------------------------------------------
           */

          if (sessionId) {
            result = await apiForm(
              `/asr/transcribe?session_id=${encodeURIComponent(
                sessionId
              )}`,
              formData,
              {
                auth: "patient",
              }
            );
          }

          /*
           * --------------------------------------------------
           * PRE-SESSION IDENTIFICATION
           * --------------------------------------------------
           *
           * No patient session exists yet, so this endpoint
           * deliberately does not use patient authentication.
           *
           * The backend sends the temporary audio to the
           * SAME SarvamASRProvider.
           * --------------------------------------------------
           */

          else {
            result = await apiForm(
              "/asr/pre-session",
              formData
            );
          }

          if (
            operationId !== operationRef.current
          ) {
            return;
          }

          if (
            !result ||
            typeof result.text !== "string"
          ) {
            throw new Error(
              "Speech recognition did not return text."
            );
          }

          const transcript = result.text.trim();

          if (!transcript) {
            throw new Error(
              "No speech was detected. Please try again."
            );
          }

          onResult?.(transcript);
        } catch (error) {
          if (
            operationId !== operationRef.current
          ) {
            return;
          }

          console.error(
            "Sarvam voice transcription failed:",
            error
          );

          reportError(
            error?.message ||
              "Unable to process your voice."
          );
        } finally {
          if (
            operationId === operationRef.current
          ) {
            chunksRef.current = [];

            if (mountedRef.current) {
              setIsTranscribing(false);
            }
          }
        }
      };

      recorder.start();

      if (mountedRef.current) {
        setIsRecording(true);
        onStart?.();
      }
    } catch (error) {
      console.error(
        "Unable to start voice recording:",
        error
      );

      if (recorder) {
        try {
          if (recorder.state !== "inactive") {
            recorder.stop();
          }
        } catch {
          // Already stopped.
        }
      }

      mediaRecorderRef.current = null;

      stopMicrophoneStream();

      if (mountedRef.current) {
        setIsRecording(false);
        setIsTranscribing(false);
      }

      reportError(
        error?.message ||
          "Unable to access the microphone."
      );
    }
  }, [
    onResult,
    onStart,
    reportError,
    sessionId,
    stopMicrophoneStream,
    language,
  ]);

  /*
   * ------------------------------------------------------------
   * Stop recording
   * ------------------------------------------------------------
   */

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;

    if (!recorder) {
      if (mountedRef.current) {
        setIsRecording(false);
      }

      stopMicrophoneStream();
      return;
    }

    try {
      if (recorder.state !== "inactive") {
        recorder.stop();
      } else {
        mediaRecorderRef.current = null;
        stopMicrophoneStream();

        if (mountedRef.current) {
          setIsRecording(false);
        }
      }
    } catch (error) {
      console.error(
        "Unable to stop recording:",
        error
      );

      mediaRecorderRef.current = null;

      stopMicrophoneStream();

      if (mountedRef.current) {
        setIsRecording(false);
        setIsTranscribing(false);
      }

      reportError(
        "Unable to stop the recording. Please try again."
      );
    }
  }, [
    reportError,
    stopMicrophoneStream,
  ]);

  /*
   * ------------------------------------------------------------
   * Button
   *
   * First click  -> record
   * Second click -> stop
   * Stop         -> upload to Sarvam
   * ------------------------------------------------------------
   */

  const handleClick = () => {
    if (!isListening && !isProcessing) {
      void startRecording();
      return;
    }

    if (isListening) {
      stopRecording();
    }
  };

  /*
   * ------------------------------------------------------------
   * UI state
   * ------------------------------------------------------------
   */

  const currentState = isListening
    ? "listening"
    : isProcessing
      ? "processing"
      : "idle";

  const label =
    currentState === "listening"
      ? "Listening..."
      : currentState === "processing"
        ? "Processing..."
        : "Speak";

  return (
    <div
      className={`voice-button voice-button--${currentState}`}
    >
      <button
        type="button"
        className="voice-button__control"
        onClick={handleClick}
        disabled={isProcessing}
        aria-label={label}
        aria-pressed={isListening}
      >
        {currentState === "listening" ? (
          <span
            className="voice-button__stop-icon"
            aria-hidden="true"
          />
        ) : currentState === "processing" ? (
          <span
            className="voice-button__processing-icon"
            aria-hidden="true"
          >
            …
          </span>
        ) : (
          <span
            className="voice-button__mic-icon"
            aria-hidden="true"
          >
            🎙
          </span>
        )}
      </button>

      <span
        className="voice-button__label"
        aria-live="polite"
      >
        {label}
      </span>
    </div>
  );
}