const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  "http://localhost:8000";

const LANGUAGE_MAP = {
  en: "en-IN",
  hi: "hi-IN",
  mr: "mr-IN",
  bn: "bn-IN",
};

// Generated audio cache.
// Same text + same language will never be synthesized twice.
const audioCache = new Map();

// Requests currently being generated.
// Prevents duplicate requests if the user clicks quickly.
const pendingRequests = new Map();

let currentAudio = null;
let currentObjectUrl = null;

function makeCacheKey(text, language) {
  return `${language}::${text}`;
}

async function generateAudio(text, languageCode) {
  const cacheKey = makeCacheKey(
    text,
    languageCode
  );

  // Already generated.
  if (audioCache.has(cacheKey)) {
    return audioCache.get(cacheKey);
  }

  // Already being generated.
  if (pendingRequests.has(cacheKey)) {
    return pendingRequests.get(cacheKey);
  }

  const request = fetch(
    `${API_BASE_URL}/tts/synthesize`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        text,
        language_code: languageCode,
      }),
    }
  )
    .then(async (response) => {
      if (!response.ok) {
        const errorData =
          await response.json().catch(() => null);

        throw new Error(
          errorData?.detail ||
            "Unable to generate speech."
        );
      }

      const blob = await response.blob();

      if (!blob.size) {
        throw new Error(
          "TTS returned empty audio."
        );
      }

      audioCache.set(
        cacheKey,
        blob
      );

      return blob;
    })
    .finally(() => {
      pendingRequests.delete(cacheKey);
    });

  pendingRequests.set(
    cacheKey,
    request
  );

  return request;
}

export async function speakText(
  text,
  language
) {
  const cleanText = String(
    text ?? ""
  ).trim();

  if (!cleanText) {
    return;
  }

  const languageCode =
    LANGUAGE_MAP[language] ??
    LANGUAGE_MAP.en;

  // Stop previous speech immediately.
  stopSpeech();

  const audioBlob =
    await generateAudio(
      cleanText,
      languageCode
    );

  const objectUrl =
    URL.createObjectURL(audioBlob);

  currentObjectUrl = objectUrl;

  const audio =
    new Audio(objectUrl);

  /*
   * 1.0 = normal browser volume.
   * 1.25 gives the kiosk a little more presence.
   */
  audio.volume = 1.0;

  currentAudio = audio;

  audio.onended = () => {
    cleanup(
      audio,
      objectUrl
    );
  };

  audio.onerror = () => {
    cleanup(
      audio,
      objectUrl
    );
  };

  try {
    await audio.play();
  } catch (error) {
    cleanup(
      audio,
      objectUrl
    );

    throw error;
  }

  return audio;
}

function cleanup(
  audio,
  objectUrl
) {
  if (currentAudio === audio) {
    currentAudio = null;
  }

  if (
    currentObjectUrl ===
    objectUrl
  ) {
    currentObjectUrl = null;
  }

  URL.revokeObjectURL(
    objectUrl
  );
}

export function stopSpeech() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
  }

  if (currentObjectUrl) {
    URL.revokeObjectURL(
      currentObjectUrl
    );

    currentObjectUrl = null;
  }
}