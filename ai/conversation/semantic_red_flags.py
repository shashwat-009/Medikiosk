"""
Semantic red-flag detection for MediKiosk.

This module provides a broader semantic safety layer on top of the
deterministic red-flag detector.

It does NOT:
- generate text
- diagnose diseases
- prescribe treatment
- call an LLM API

It uses a multilingual sentence-embedding model locally.

The detector compares a patient answer against multiple canonical
examples for each supported red-flag category.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from sentence_transformers import SentenceTransformer


# ============================================================
# Configuration
# ============================================================

MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)

# Start conservatively.
#
# This is deliberately NOT treated as a medical truth boundary.
# We will tune it using our test cases.
SEMANTIC_RED_FLAG_THRESHOLD = 0.70




# ============================================================
# Category relevance anchors
# ============================================================
#
# Semantic similarity is intentionally broad, but the winning
# category must still have a clinical word/concept in the answer.
# This prevents generic multilingual words from becoming an
# unrelated emergency finding.
#
# Supported languages in this module:
# English, Hinglish/Roman Hindi, Hindi, Bengali and Marathi.
# ============================================================

CATEGORY_RELEVANCE_ANCHORS: dict[str, tuple[str, ...]] = {
    "severe_breathing_difficulty": (
        "breathe", "breathing", "breath", "air",
        "saans", "sans", "dam ghut", "dam", "hawa",
        "सांस", "साँस", "श्वास", "दम", "हवा",
        "শ্বাস", "দম",
    ),
    "loss_of_consciousness": (
        "conscious", "unconscious", "faint", "fainted", "fainting",
        "passed out", "pass out",
        "behosh", "hosh", "behoshi",
        "बेहोश", "होश", "बेहोशी",
        "অজ্ঞান", "জ্ঞান",
        "बेशुद्ध", "शुद्ध", "भान",
    ),
    "severe_chest_pain": (
        "chest",
        "seena", "seene", "seenay",
        "सीना", "सीने", "छाती",
        "বুক",
    ),
    "severe_bleeding": (
        "blood", "bleed", "bleeding",
        "khoon", "khun",
        "खून", "रक्त", "ब्लीडिंग", "रक्तस्राव",
        "রক্ত", "রক্তপাত",
    ),
    "sudden_weakness_or_paralysis": (
        "weak", "weakness", "numb", "numbness",
        "paralysis", "paralyzed", "strength", "move",
        "kamzori", "kamzor", "sunn", "lakwa", "taqat",
        "कमजोरी", "कमजोर", "सुन्न", "लकवा", "पक्षाघात", "ताकत",
        "দুর্বল", "দুর্বলতা", "অবশ", "পক্ষাঘাত", "শক্তি",
        "अशक्त", "ताकद",
    ),
}


def _has_category_relevance(text: str, category: str | None) -> bool:
    """Require a category-specific clinical anchor before flagging."""
    if not category:
        return False

    normalized = " ".join(text.casefold().split())
    anchors = CATEGORY_RELEVANCE_ANCHORS.get(category, ())

    return any(
        re.search(
            r"(?<!\w)" + re.escape(anchor.casefold()) + r"(?!\w)",
            normalized,
        )
        for anchor in anchors
    )

# ============================================================
# Canonical examples
# ============================================================
#
# We intentionally keep a LIMITED number of examples.
#
# The purpose of the embedding model is to recognize different
# wording with similar meaning rather than maintain thousands
# of manually-written regex phrases.
#
# Examples are provided in English, Hindi and Hinglish so that
# the multilingual model has semantic anchors in the languages
# MediKiosk expects.
# ============================================================

SEMANTIC_RED_FLAG_CONCEPTS: dict[str, list[str]] = {

    "severe_breathing_difficulty": [

        # English
        "I cannot breathe properly.",
        "I am unable to breathe.",
        "I am struggling to breathe.",
        "I am having severe difficulty breathing.",
        "I cannot get enough air.",
        "I am struggling to get enough air.",
        "I am having severe shortness of breath.",

        # Hinglish / Roman Hindi
        "Mujhe saans lene mein bahut dikkat ho rahi hai.",
        "Mujhe saans lene mein bahut zyada dikkat hai.",
        "Meri saans nahi aa rahi hai.",
        "Mujhe saans lene mein problem ho rahi hai.",
        "Saans lene mein bahut mushkil ho rahi hai.",
        "Mujhe theek se saans nahi aa rahi.",

        # Devanagari Hindi
        "मुझे सांस लेने में बहुत दिक्कत हो रही है।",
        "मुझे सांस लेने में बहुत ज्यादा दिक्कत है।",
        "मेरी सांस नहीं आ रही है।",
        "मुझे सांस लेने में परेशानी हो रही है।",
        "सांस लेने में बहुत मुश्किल हो रही है।",
        "मुझे ठीक से सांस नहीं आ रही है।",
    ],

    "loss_of_consciousness": [

        # English
        "I lost consciousness.",
        "I became unconscious.",
        "I fainted and lost consciousness.",
        "I passed out.",
        "I was unconscious.",
        "I suddenly became unconscious.",

        # Hinglish / Roman Hindi
        "Main behosh ho gaya tha.",
        "Mujhe behoshi ho gayi thi.",
        "Main behosh ho gaya.",
        "Main behosh ho gayi thi.",
        "Main achanak behosh ho gaya tha.",

        # Devanagari Hindi
        "मैं बेहोश हो गया था।",
        "मुझे बेहोशी हो गई थी।",
        "मैं बेहोश हो गया।",
        "मैं अचानक बेहोश हो गया था।",
    ],

    "severe_chest_pain": [

        # English
        "I have severe chest pain.",
        "I have very strong pain in my chest.",
        "I have intense chest pain.",
        "My chest hurts severely.",
        "I am having crushing chest pain.",
        "I have severe pressure or pain in my chest.",

        # Hinglish / Roman Hindi
        "Mere seene mein bahut tez dard hai.",
        "Mere chest mein bahut zyada pain hai.",
        "Seene mein bahut tez dard ho raha hai.",
        "Mere seene mein bahut zyada dard ho raha hai.",
        "Chest mein severe pain ho raha hai.",

        # Devanagari Hindi
        "मेरे सीने में बहुत तेज दर्द है।",
        "मेरे सीने में बहुत ज्यादा दर्द है।",
        "सीने में बहुत तेज दर्द हो रहा है।",
        "मेरे सीने में बहुत ज्यादा दर्द हो रहा है।",
    ],

    "severe_bleeding": [

        # English
        "I am bleeding heavily.",
        "I am losing a lot of blood.",
        "The bleeding is severe.",
        "The bleeding will not stop.",
        "I have severe uncontrolled bleeding.",
        "A large amount of blood is coming out.",

        # Hinglish / Roman Hindi
        "Bahut zyada khoon beh raha hai.",
        "Mera bahut khoon nikal raha hai.",
        "Khoon bahut zyada aa raha hai.",
        "Khoon behna band nahi ho raha.",
        "Bahut tez bleeding ho rahi hai.",

        # Devanagari Hindi
        "बहुत ज्यादा खून बह रहा है।",
        "मेरा बहुत खून निकल रहा है।",
        "खून बहुत ज्यादा आ रहा है।",
        "खून बहना बंद नहीं हो रहा है।",
        "बहुत तेज ब्लीडिंग हो रही है।",
    ],

    "sudden_weakness_or_paralysis": [

        # English
        "I suddenly became very weak.",
        "I suddenly lost strength.",
        "I suddenly cannot move one side of my body.",
        "One side of my body suddenly became weak.",
        "I suddenly developed paralysis.",
        "I suddenly cannot move my arm or leg.",

        # Hinglish / Roman Hindi
        "Mere sharir ke ek taraf achanak kamzori ho gayi.",
        "Mera ek haath achanak kamzor ho gaya.",
        "Mera ek pair achanak kamzor ho gaya.",
        "Main achanak ek taraf se kamzor ho gaya.",
        "Mere haath pair mein achanak taqat nahi hai.",

        # Devanagari Hindi
        "मेरे शरीर के एक तरफ अचानक कमजोरी हो गई।",
        "मेरा एक हाथ अचानक कमजोर हो गया।",
        "मेरा एक पैर अचानक कमजोर हो गया।",
        "मैं अचानक एक तरफ से कमजोर हो गया।",
        "मेरे हाथ पैर में अचानक ताकत नहीं है।",
    ],
}


# ============================================================
# Result
# ============================================================

@dataclass(frozen=True)
class SemanticRedFlagResult:
    """
    Result produced by the semantic detector.
    """

    detected: bool
    category: str | None = None
    score: float | None = None
    matched_text: str | None = None
    explanation: str | None = None


# ============================================================
# Model
# ============================================================

@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    """
    Load the multilingual embedding model once.

    The first call downloads the model if necessary.
    Later calls reuse the cached model.
    """

    return SentenceTransformer(MODEL_NAME)


# ============================================================
# Detector
# ============================================================

class SemanticRedFlagDetector:
    """
    Local multilingual semantic red-flag detector.

    It compares patient text with canonical examples and returns
    the strongest semantic match.

    It does not generate language and does not diagnose.
    """

    def __init__(
        self,
        threshold: float = SEMANTIC_RED_FLAG_THRESHOLD,
    ) -> None:

        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                "threshold must be between 0.0 and 1.0"
            )

        self.threshold = threshold
        self.model = _load_model()

        self._examples: list[str] = []
        self._example_categories: list[str] = []

        for category, examples in (
            SEMANTIC_RED_FLAG_CONCEPTS.items()
        ):
            for example in examples:
                self._examples.append(example)
                self._example_categories.append(category)

        self._example_embeddings = self.model.encode(
            self._examples,
            normalize_embeddings=True,
            convert_to_tensor=True,
        )

    def detect(
        self,
        text: str | None,
    ) -> SemanticRedFlagResult:
        """
        Detect semantic similarity to a supported red-flag concept.
        """

        if not text or not text.strip():
            return SemanticRedFlagResult(
                detected=False
            )

        normalized_text = " ".join(
            text.strip().split()
        )

        query_embedding = self.model.encode(
            normalized_text,
            normalize_embeddings=True,
            convert_to_tensor=True,
        )

        scores = self.model.similarity(
            query_embedding,
            self._example_embeddings,
        )[0]

        best_index = int(
            scores.argmax().item()
        )

        best_score = float(
            scores[best_index].item()
        )

        best_category = (
            self._example_categories[
                best_index
            ]
        )

        best_example = (
            self._examples[
                best_index
            ]
        )

        # ----------------------------------------------------
        # Category relevance gate
        #
        # Similarity alone is not sufficient. The answer must contain
        # a clinical anchor belonging to the winning category. This
        # prevents generic words such as "difficulty", "no", etc.
        # from becoming unrelated emergency findings.
        #
        # This does not alter the existing semantic threshold.
        # ----------------------------------------------------

        if not _has_category_relevance(
            normalized_text,
            best_category,
        ):
            return SemanticRedFlagResult(
                detected=False,
                category=None,
                score=best_score,
                matched_text=None,
                explanation=(
                    "No category-specific clinical anchor was found."
                ),
            )

        # ----------------------------------------------------
        # Important safety behavior:
        #
        # A low similarity score must NOT be assigned to a
        # seemingly random category.
        #
        # Example:
        #
        # "I have a headache"
        #
        # might technically be closest to one category, but
        # that does not mean it is a red flag.
        # ----------------------------------------------------

        if best_score < self.threshold:

            return SemanticRedFlagResult(
                detected=False,
                category=None,
                score=best_score,
                matched_text=None,
                explanation=(
                    "No supported red-flag concept "
                    "reached the semantic threshold."
                ),
            )

        return SemanticRedFlagResult(
            detected=True,
            category=best_category,
            score=best_score,
            matched_text=best_example,
            explanation=(
                "The patient's answer is semantically "
                "similar to a supported emergency "
                "red-flag concept."
            ),
        )


# ============================================================
# Shared detector
# ============================================================

@lru_cache(maxsize=1)
def get_semantic_red_flag_detector() -> SemanticRedFlagDetector:
    """
    Return one shared semantic detector instance.
    """

    return SemanticRedFlagDetector()