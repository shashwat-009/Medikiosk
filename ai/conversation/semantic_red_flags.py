"""
Semantic red-flag detection for MediKiosk.

Local multilingual semantic safety layer used after deterministic rules.
It does not diagnose, prescribe, generate text, or call an external API.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

from sentence_transformers import SentenceTransformer


MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)

SEMANTIC_RED_FLAG_THRESHOLD = 0.70


# ----------------------------------------------------------------------
# Clinical relevance
# ----------------------------------------------------------------------
# Similarity alone is not enough. A candidate category must have the
# clinical concept required for that category in the answer.
#
# For GI bleeding, blood + a GI/stool/vomit concept is required. This is
# deliberately stricter than simply seeing the word "blood".
# ----------------------------------------------------------------------

CATEGORY_RELEVANCE_ANCHORS: dict[str, tuple[str, ...]] = {
    "severe_breathing_difficulty": (
        "breathe", "breathing", "breath", "shortness of breath", "air",
        "saans", "sans", "dam ghut", "dam", "hawa",
        "सांस", "साँस", "श्वास", "दम", "हवा",
        "শ্বাস", "দম",
        "श्वास", "श्वास घे",
    ),
    "loss_of_consciousness": (
        "conscious", "unconscious", "faint", "fainted", "fainting",
        "passed out", "pass out", "blackout",
        "behosh", "hosh", "behoshi",
        "बेहोश", "होश", "बेहोशी",
        "অজ্ঞান", "জ্ঞান হার",
        "बेशुद्ध", "शुद्ध हर",
    ),
    "severe_chest_pain": (
        "chest", "chest pain",
        "seena", "seene", "seenay",
        "सीना", "सीने", "छाती",
        "বুক",
        "छातीत",
    ),
    "severe_bleeding": (
        "blood", "bleed", "bleeding", "bleed out",
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
    "gastrointestinal_bleeding": (
        "stool", "stools", "feces", "faeces", "bowel movement",
        "bowel movements", "poop", "poo", "black stool", "tarry stool",
        "vomit", "vomiting", "vomited", "throwing up",
        "potty", "stool mein", "stool me", "mal", "paikhana",
        "मल", "पाखाना", "पॉटी", "शौच",
        "মল", "পায়খানা", "পায়খানা",
    ),
}

BLOOD_ANCHORS = (
    "blood", "bleed", "bleeding", "khoon", "khun",
    "खून", "रक्त", "ब्लीडिंग", "रक्तस्राव",
    "রক্ত", "রক্তপাত",
)

GI_CONTEXT_ANCHORS = CATEGORY_RELEVANCE_ANCHORS["gastrointestinal_bleeding"]


def _contains_anchor(text: str, anchor: str) -> bool:
    normalized = " ".join(text.casefold().split())
    normalized_anchor = " ".join(anchor.casefold().split())
    return re.search(
        r"(?<!\w)" + re.escape(normalized_anchor) + r"(?!\w)",
        normalized,
    ) is not None


def _has_category_relevance(text: str, category: str | None) -> bool:
    if not category:
        return False

    if category == "gastrointestinal_bleeding":
        has_blood = any(_contains_anchor(text, anchor) for anchor in BLOOD_ANCHORS)
        has_gi_context = any(
            _contains_anchor(text, anchor) for anchor in GI_CONTEXT_ANCHORS
        )
        return has_blood and has_gi_context

    return any(
        _contains_anchor(text, anchor)
        for anchor in CATEGORY_RELEVANCE_ANCHORS.get(category, ())
    )


# ----------------------------------------------------------------------
# Canonical semantic concepts
# ----------------------------------------------------------------------

SEMANTIC_RED_FLAG_CONCEPTS: dict[str, list[str]] = {
    "severe_breathing_difficulty": [
        "I cannot breathe properly.",
        "I am unable to breathe.",
        "I am struggling to breathe.",
        "I am having severe difficulty breathing.",
        "I cannot get enough air.",
        "I am struggling to get enough air.",
        "I am having severe shortness of breath.",
        "Mujhe saans lene mein bahut dikkat ho rahi hai.",
        "Mujhe saans lene mein bahut zyada dikkat hai.",
        "Meri saans nahi aa rahi hai.",
        "Mujhe saans lene mein problem ho rahi hai.",
        "Saans lene mein bahut mushkil ho rahi hai.",
        "Mujhe theek se saans nahi aa rahi.",
        "मुझे सांस लेने में बहुत दिक्कत हो रही है।",
        "मुझे सांस लेने में बहुत ज्यादा दिक्कत है।",
        "मेरी सांस नहीं आ रही है।",
        "मुझे सांस लेने में परेशानी हो रही है।",
        "सांस लेने में बहुत मुश्किल हो रही है।",
        "মিন্তু শ্বাস নিতে খুব কষ্ট হচ্ছে।",
        "श्वास घेण्यास खूप त्रास होत आहे.",
    ],
    "loss_of_consciousness": [
        "I lost consciousness.",
        "I became unconscious.",
        "I fainted and lost consciousness.",
        "I passed out.",
        "I was unconscious.",
        "I suddenly became unconscious.",
        "I blacked out.",
        "Main behosh ho gaya tha.",
        "Mujhe behoshi ho gayi thi.",
        "Main behosh ho gaya.",
        "Main behosh ho gayi thi.",
        "Main achanak behosh ho gaya tha.",
        "मैं बेहोश हो गया था।",
        "मुझे बेहोशी हो गई थी।",
        "मैं बेहोश हो गया।",
        "मैं अचानक बेहोश हो गया था।",
        "আমি জ্ঞান হারিয়েছিলাম।",
        "मी बेशुद्ध झालो.",
    ],
    "severe_chest_pain": [
        "I have severe chest pain.",
        "I have very strong pain in my chest.",
        "I have intense chest pain.",
        "My chest hurts severely.",
        "I am having crushing chest pain.",
        "I have severe pressure or pain in my chest.",
        "Mere seene mein bahut tez dard hai.",
        "Mere chest mein bahut zyada pain hai.",
        "Seene mein bahut tez dard ho raha hai.",
        "Mere seene mein bahut zyada dard ho raha hai.",
        "Chest mein severe pain ho raha hai.",
        "मेरे सीने में बहुत तेज दर्द है।",
        "मेरे सीने में बहुत ज्यादा दर्द है।",
        "सीने में बहुत तेज दर्द हो रहा है।",
        "मेरे सीने में बहुत ज्यादा दर्द हो रहा है।",
        "বুকে খুব তীব্র ব্যথা হচ্ছে।",
        "छातीत खूप तीव्र वेदना होत आहेत.",
    ],
    "severe_bleeding": [
        "I am bleeding heavily.",
        "I am losing a lot of blood.",
        "The bleeding is severe.",
        "The bleeding will not stop.",
        "I have severe uncontrolled bleeding.",
        "A large amount of blood is coming out.",
        "Bahut zyada khoon beh raha hai.",
        "Mera bahut khoon nikal raha hai.",
        "Khoon bahut zyada aa raha hai.",
        "Khoon behna band nahi ho raha.",
        "Bahut tez bleeding ho rahi hai.",
        "बहुत ज्यादा खून बह रहा है।",
        "मेरा बहुत खून निकल रहा है।",
        "खून बहुत ज्यादा आ रहा है।",
        "खून बहना बंद नहीं हो रहा है।",
        "बहुत तेज ब्लीडिंग हो रही है।",
        "খুব বেশি রক্তপাত হচ্ছে।",
        "खूप जास्त रक्तस्राव होत आहे.",
    ],
    "sudden_weakness_or_paralysis": [
        "I suddenly became very weak.",
        "I suddenly lost strength.",
        "I suddenly cannot move one side of my body.",
        "One side of my body suddenly became weak.",
        "I suddenly developed paralysis.",
        "I suddenly cannot move my arm or leg.",
        "Mere sharir ke ek taraf achanak kamzori ho gayi.",
        "Mera ek haath achanak kamzor ho gaya.",
        "Mera ek pair achanak kamzor ho gaya.",
        "Main achanak ek taraf se kamzor ho gaya.",
        "Mere haath pair mein achanak taqat nahi hai.",
        "मेरे शरीर के एक तरफ अचानक कमजोरी हो गई।",
        "मेरा एक हाथ अचानक कमजोर हो गया।",
        "मेरा एक पैर अचानक कमजोर हो गया।",
        "मैं अचानक एक तरफ से कमजोर हो गया।",
        "मेरे हाथ पैर में अचानक ताकत नहीं है।",
        "হঠাৎ এক পাশ দুর্বল হয়ে গেছে।",
        "अचानक एका बाजूला कमजोरी आली.",
    ],
    "gastrointestinal_bleeding": [
        # English
        "I have blood in my stool.",
        "There is blood in my stool.",
        "I am passing blood with my stool.",
        "I am passing blood in my bowel movements.",
        "My stool is bloody.",
        "My stools are bloody.",
        "My stool is black and tarry.",
        "I have black tarry stools.",
        "I am vomiting blood.",
        "I am throwing up blood.",
        "There is blood in my vomit.",

        # Hinglish / Roman Hindi
        "Mere stool mein khoon aa raha hai.",
        "Mere stool me khoon aa raha hai.",
        "Meri potty mein khoon aa raha hai.",
        "Meri potty me khoon aa raha hai.",
        "Mere mal mein khoon aa raha hai.",
        "Mal ke saath khoon aa raha hai.",
        "Stool ke saath khoon aa raha hai.",
        "Potty ke saath khoon aa raha hai.",
        "Khoon wali potty ho rahi hai.",
        "Meri ulti mein khoon aa raha hai.",
        "Khoon ki ulti ho rahi hai.",
        "Mera stool kala aur chipchipa hai.",

        # Hindi
        "मेरे मल में खून आ रहा है।",
        "मल के साथ खून आ रहा है।",
        "पाखाने में खून आ रहा है।",
        "पॉटी में खून आ रहा है।",
        "खूनी मल हो रहा है।",
        "मेरा मल काला है।",
        "खून की उल्टी हो रही है।",
        "उल्टी में खून आ रहा है।",

        # Bengali
        "আমার পায়খানায় রক্ত আসছে।",
        "মলের সঙ্গে রক্ত আসছে।",
        "পায়খানার সঙ্গে রক্ত আসছে।",
        "আমার পায়খানা রক্তাক্ত।",
        "রক্ত বমি হচ্ছে।",

        # Marathi
        "माझ्या शौचात रक्त येत आहे.",
        "शौचासोबत रक्त येत आहे.",
        "मलामध्ये रक्त येत आहे.",
        "माझ्या उलटीत रक्त येत आहे.",
        "रक्ताची उलटी होत आहे.",
    ],
}


@dataclass(frozen=True)
class SemanticRedFlagResult:
    detected: bool
    category: str | None = None
    score: float | None = None
    matched_text: str | None = None
    explanation: str | None = None


@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


class SemanticRedFlagDetector:
    """
    Local multilingual semantic detector.

    The important safety ordering is:
        1. compute category-level semantic scores
        2. keep only clinically relevant categories
        3. choose the strongest relevant category
        4. apply the semantic threshold
    """

    def __init__(
        self,
        threshold: float = SEMANTIC_RED_FLAG_THRESHOLD,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0")

        self.threshold = threshold
        self.model = _load_model()

        self._examples: list[str] = []
        self._example_categories: list[str] = []

        for category, examples in SEMANTIC_RED_FLAG_CONCEPTS.items():
            for example in examples:
                self._examples.append(example)
                self._example_categories.append(category)

        self._example_embeddings = self.model.encode(
            self._examples,
            normalize_embeddings=True,
            convert_to_tensor=True,
        )

        # Precompute index lists so category scoring is explicit and stable.
        self._category_indices: dict[str, list[int]] = {}
        for index, category in enumerate(self._example_categories):
            self._category_indices.setdefault(category, []).append(index)

    def detect(self, text: str | None) -> SemanticRedFlagResult:
        if not text or not text.strip():
            return SemanticRedFlagResult(detected=False)

        normalized_text = " ".join(text.strip().split())

        query_embedding = self.model.encode(
            normalized_text,
            normalize_embeddings=True,
            convert_to_tensor=True,
        )

        scores = self.model.similarity(
            query_embedding,
            self._example_embeddings,
        )[0]

        # Do NOT choose a global argmax first. That was the source of a
        # major class of false negatives/false positives: an unrelated
        # category could win before relevance was checked.
        relevant_categories = [
            category
            for category in self._category_indices
            if _has_category_relevance(normalized_text, category)
        ]

        if not relevant_categories:
            return SemanticRedFlagResult(
                detected=False,
                explanation="No supported clinical category is relevant to the answer.",
            )

        category_scores: list[tuple[float, str, int]] = []

        for category in relevant_categories:
            best_index = max(
                self._category_indices[category],
                key=lambda index: float(scores[index].item()),
            )
            category_scores.append(
                (
                    float(scores[best_index].item()),
                    category,
                    best_index,
                )
            )

        best_score, best_category, best_index = max(
            category_scores,
            key=lambda item: item[0],
        )

        best_example = self._examples[best_index]

        if best_score < self.threshold:
            return SemanticRedFlagResult(
                detected=False,
                category=None,
                score=best_score,
                matched_text=None,
                explanation=(
                    "No relevant red-flag concept reached the semantic threshold."
                ),
            )

        return SemanticRedFlagResult(
            detected=True,
            category=best_category,
            score=best_score,
            matched_text=best_example,
            explanation=(
                "The patient's answer is semantically similar to a "
                "supported red-flag concept."
            ),
        )


@lru_cache(maxsize=1)
def get_semantic_red_flag_detector() -> SemanticRedFlagDetector:
    return SemanticRedFlagDetector()
