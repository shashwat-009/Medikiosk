import { useEffect } from "react";
import { useKiosk } from "../../context/KioskContext";
import { speakText } from "../../services/ttsService";

const LANGUAGE_MAP = {
  english: "en",
  "हिन्दी": "hi",
  "हिंदी": "hi",
  "मराठी": "mr",
  "বাংলা": "bn",
  bengali: "bn",
  marathi: "mr",
  hindi: "hi",
};

const IGNORED_TAGS = new Set([
  "INPUT",
  "TEXTAREA",
  "SELECT",
  "OPTION",
]);

function normalize(text) {
  return String(text || "")
    .replace(/\s+/g, " ")
    .trim();
}

function getClickableElement(target) {
  if (!(target instanceof Element)) {
    return null;
  }

  return target.closest(
    "button, a, label, [role='button'], [data-tts]"
  );
}

function getSpeechText(element) {
  if (!element) {
    return "";
  }

  // Explicit TTS text has highest priority.
  const explicitText = element.getAttribute("data-tts");

  if (explicitText) {
    return normalize(explicitText);
  }

  /*
   * Language buttons contain:
   *
   * <span class="...lang-native">English</span>
   * <span class="...lang-sub">English</span>
   *
   * Only use the native label.
   */
  const nativeLanguageLabel = element.querySelector(
    ".kiosk-home__lang-native"
  );

  if (nativeLanguageLabel) {
    return normalize(nativeLanguageLabel.textContent);
  }

  return normalize(
    element.innerText || element.textContent
  );
}

function getSpeechLanguage(element, currentLanguage) {
  const explicitLanguage =
    element.getAttribute("data-tts-language");

  if (explicitLanguage && LANGUAGE_MAP[explicitLanguage]) {
    return LANGUAGE_MAP[explicitLanguage];
  }

  const text = getSpeechText(element).toLowerCase();

  if (LANGUAGE_MAP[text]) {
    return LANGUAGE_MAP[text];
  }

  return currentLanguage || "en";
}

function shouldIgnore(element) {
  if (!element) {
    return true;
  }

  if (IGNORED_TAGS.has(element.tagName)) {
    return true;
  }

  if (
    element.matches("[data-no-tts]") ||
    element.closest("[data-no-tts]")
  ) {
    return true;
  }

  // Never speak ASR microphone controls.
  if (
    element.matches(".voice-button") ||
    element.closest(".voice-button")
  ) {
    return true;
  }

  if (
    element.matches("[contenteditable='true']") ||
    element.closest("[contenteditable='true']")
  ) {
    return true;
  }

  return false;
}

export default function KioskTTS() {
  const { state } = useKiosk();

  const language = state?.language || "en";

  useEffect(() => {
    let destroyed = false;

    const handleClick = async (event) => {
      const element = getClickableElement(event.target);

      if (!element || shouldIgnore(element)) {
        return;
      }

      const text = getSpeechText(element);

      if (!text) {
        return;
      }

      /*
       * Don't read long pages/paragraphs.
       * TTS is intended for patient-facing controls.
       */
      const speechText =
        text.length > 250
          ? `${text.slice(0, 250)}…`
          : text;

      const speechLanguage = getSpeechLanguage(
        element,
        language
      );

      try {
        await speakText(
          speechText,
          speechLanguage
        );
      } catch (error) {
        if (!destroyed) {
          console.warn(
            "Kiosk TTS failed:",
            error
          );
        }
      }
    };

    document.addEventListener(
      "click",
      handleClick,
      true
    );

    return () => {
      destroyed = true;

      document.removeEventListener(
        "click",
        handleClick,
        true
      );
    };
  }, [language]);

  return null;
}