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
// Prevents duplicate requests if the same text is requested quickly.
const pendingRequests = new Map();

let currentAudio = null;
let currentObjectUrl = null;

// Used to invalidate old async playback requests.
// If a new question/speech starts, an older pending request
// is no longer allowed to start playing when it finishes.
let speechGeneration = 0;

function makeCacheKey(text, language) {
  return `${language}::${text}`;
}

async function generateAudio(text, languageCode) {
  const cacheKey = makeCacheKey(text, languageCode);

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

      // Cache the generated audio so repeated playback
      // does not require another backend request.
      audioCache.set(cacheKey, blob);

      return blob;
    })
    .finally(() => {
      pendingRequests.delete(cacheKey);
    });

  pendingRequests.set(cacheKey, request);

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

  /*
   * Every new speech request invalidates any older
   * asynchronous speech request.
   *
   * This is important for adaptive questions:
   *
   * Question 1 starts generating
   *        ↓
   * Question 2 appears
   *        ↓
   * Question 1 finishes later
   *
   * Question 1 must NOT start playing.
   */
  const generation = ++speechGeneration;

  // Stop currently playing audio immediately.
  stopCurrentAudio();

  let audioBlob;

  try {
    audioBlob = await generateAudio(
      cleanText,
      languageCode
    );
  } catch (error) {
    // Do not swallow the error.
    // The caller can decide how to handle/log it.
    throw error;
  }

  /*
   * While the audio was being generated, another
   * speech request may have started.
   *
   * If so, this audio is stale and must never play.
   */
  if (generation !== speechGeneration) {
    return;
  }

  const objectUrl =
    URL.createObjectURL(audioBlob);

  // A newer speech request could theoretically start
  // between the check above and audio creation.
  if (generation !== speechGeneration) {
    URL.revokeObjectURL(objectUrl);
    return;
  }

  currentObjectUrl = objectUrl;

  const audio =
    new Audio(objectUrl);

  /*
   * Normal browser volume.
   *
   * Do not artificially amplify through Web Audio;
   * that can introduce clipping/distortion.
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

  /*
   * Another request could have started while
   * audio.play() was being resolved.
   *
   * Stop this audio if it has become stale.
   */
  if (generation !== speechGeneration) {
    audio.pause();
    audio.currentTime = 0;

    cleanup(
      audio,
      objectUrl
    );

    return;
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

function stopCurrentAudio() {
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

export function stopSpeech() {
  /*
   * Invalidate all pending async speech.
   *
   * This is different from merely stopping the
   * currently playing Audio element.
   */
  speechGeneration++;

  stopCurrentAudio();
}