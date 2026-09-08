import { useEffect, useRef, useState } from "react";
import "./VoiceButton.css";

export default function VoiceButton({
  state = "idle",
  onStart,
  onResult,
  onError,
}) {
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);

  const isListening = isRecording || state === "listening";
  const isProcessing = isTranscribing || state === "processing";

  useEffect(() => {
    return () => {
      const recorder = mediaRecorderRef.current;

      if (recorder && recorder.state !== "inactive") {
        recorder.stop();
      }

      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  const startRecording = async () => {
    if (isProcessing || isListening) return;

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Microphone access is not supported by this browser.");
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });

      streamRef.current = stream;
      chunksRef.current = [];

      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onerror = () => {
        setIsRecording(false);
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        onError?.("Unable to record audio.");
      };

      recorder.onstop = async () => {
        setIsRecording(false);
        setIsTranscribing(true);

        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;

        try {
          const audioBlob = new Blob(chunksRef.current, {
            type: recorder.mimeType || "audio/webm",
          });

          const formData = new FormData();
          formData.append("file", audioBlob, "interview.webm");

          const apiBaseUrl =
            import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

          const response = await fetch(`${apiBaseUrl}/asr/transcribe`, {
            method: "POST",
            body: formData,
          });

          if (!response.ok) {
            throw new Error(`ASR request failed: ${response.status}`);
          }

          const result = await response.json();

          if (typeof result.text !== "string") {
            throw new Error("ASR response did not contain text.");
          }

          onResult?.(result.text);
        } catch (error) {
          console.error("Voice transcription failed:", error);
          onError?.(error?.message || "Unable to process your voice.");
        } finally {
          setIsTranscribing(false);
          chunksRef.current = [];
        }
      };

      recorder.start();
      setIsRecording(true);
      onStart?.();
    } catch (error) {
      console.error("Unable to start voice recording:", error);
      setIsRecording(false);
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      onError?.(error?.message || "Unable to access the microphone.");
    }
  };

  const stopRecording = () => {
    const recorder = mediaRecorderRef.current;

    if (!recorder || recorder.state === "inactive") {
      setIsRecording(false);
      return;
    }

    recorder.stop();
  };

  const handleClick = () => {
    if (isListening) {
      stopRecording();
      return;
    }

    if (isProcessing) return;

    startRecording();
  };

  const label = isListening
    ? "Listening..."
    : isProcessing
      ? "Processing..."
      : "Speak";

  return (
    <div className="voice-button">
      <button
        type="button"
        className={[
          "voice-button__control",
          isListening ? "voice-button__control--listening" : "",
          isProcessing ? "voice-button__control--processing" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={handleClick}
        disabled={isProcessing}
        aria-label={label}
        aria-pressed={isRecording}
      >
        <span className="voice-button__icon" aria-hidden="true">
          {isListening ? "■" : isProcessing ? "…" : "🎙"}
        </span>
      </button>

      <span className="voice-button__label" aria-live="polite">
        {label}
      </span>
    </div>
  );
}
