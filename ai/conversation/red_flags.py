"""
Hybrid red-flag detection for MediKiosk.

This module detects predefined safety indicators from patient-reported
text using two layers:

1. Deterministic rule-based detection
   - Fast
   - High precision
   - Explicit multilingual phrases
   - Existing safety/negation handling

2. Local semantic detection
   - Broader wording coverage
   - Uses a multilingual sentence-embedding model
   - Does not generate text
   - Does not diagnose
   - Does not call an external API

The deterministic layer always runs first.
The semantic layer is only used when no deterministic rule matches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .schemas import RedFlagPriority, RedFlagResult
from .semantic_red_flags import (
    SemanticRedFlagResult,
    get_semantic_red_flag_detector,
)


@dataclass(frozen=True)
class DetectedRedFlag:
    """
    Compatibility result used by the existing red-flag tests.

    The actual project RedFlagResult is validated before this
    compatibility representation is returned.
    """

    detected: bool
    category: str | None = None
    matched_pattern: str | None = None

    flag_id: str | None = None
    priority: RedFlagPriority | None = None
    matched_fields: tuple[str, ...] = ()
    matched_text: str | None = None
    explanation: str | None = None


# ======================================================================
# DETERMINISTIC RED-FLAG PATTERNS
# ======================================================================

RED_FLAG_PATTERNS: dict[str, tuple[str, ...]] = {
    # ==================================================================
    # SEVERE BREATHING DIFFICULTY
    # ==================================================================
    "severe_breathing_difficulty": (
        # English
        "cannot breathe",
        "can't breathe",
        "difficulty breathing",
        "breathing difficulty",
        "having difficulty breathing",
        "i cannot breathe",
        "i can't breathe",
        "i am having difficulty breathing",
        "i am having severe difficulty breathing",
        "severe difficulty breathing",
        "shortness of breath",
        "severe shortness of breath",

        # Hindi - Hinglish
        "saans nahi aa rahi",
        "saans lene mein dikkat",
        "saans lene me dikkat",
        "saans lene mein bahut dikkat",
        "saans lene me bahut dikkat",
        "saans phool rahi",
        "saans phool rahi hai",
        "bahut saans phool rahi hai",

        # Hindi - Devanagari
        "सांस नहीं आ रही",
        "साँस नहीं आ रही",
        "सांस लेने में दिक्कत",
        "साँस लेने में दिक्कत",
        "सांस लेने में बहुत दिक्कत",
        "साँस लेने में बहुत दिक्कत",
        "सांस फूल रही है",
        "साँस फूल रही है",

        # Bengali
        "শ্বাস নিতে পারছি না",
        "শ্বাস নিতে কষ্ট হচ্ছে",
        "শ্বাস নিতে খুব কষ্ট হচ্ছে",
        "শ্বাসকষ্ট হচ্ছে",
        "খুব শ্বাসকষ্ট হচ্ছে",

        # Marathi
        "श्वास घेता येत नाही",
        "श्वास घेण्यास त्रास होत आहे",
        "श्वास घेण्यास खूप त्रास होत आहे",
        "श्वास घेण्यास अडचण होत आहे",
        "खूप श्वास घेण्यास त्रास होत आहे",
    ),

    # ==================================================================
    # LOSS OF CONSCIOUSNESS
    # ==================================================================
    "loss_of_consciousness": (
        # English
        "lost consciousness",
        "passed out",
        "pass out",
        "unconscious",
        "i was unconscious",
        "i became unconscious",
        "i fainted",
        "fainted",

        # Hindi - Hinglish
        "behosh ho gaya",
        "behosh ho gayi",
        "behosh ho gaya tha",
        "behosh ho gayi thi",
        "main behosh ho gaya",
        "main behosh ho gayi",
        "hosh kho diya",

        # Hindi - Devanagari
        "बेहोश हो गया",
        "बेहोश हो गई",
        "बेहोश हो गया था",
        "बेहोश हो गई थी",
        "मैं बेहोश हो गया",
        "मैं बेहोश हो गई",
        "होश खो दिया",

        # Bengali
        "অজ্ঞান হয়ে গিয়েছিলাম",
        "আমি অজ্ঞান হয়ে গিয়েছিলাম",
        "জ্ঞান হারিয়েছিলাম",
        "জ্ঞান হারিয়ে ফেলেছিলাম",

        # Marathi
        "बेशुद्ध झालो",
        "बेशुद्ध झाले",
        "बेशुद्ध झालो होतो",
        "बेशुद्ध झाले होते",
        "मी बेशुद्ध झालो",
        "मी बेशुद्ध झाले",
        "शुद्ध हरपली",
    ),

    # ==================================================================
    # SEVERE CHEST PAIN
    # ==================================================================
    "severe_chest_pain": (
        # English
        "severe chest pain",
        "very severe chest pain",
        "chest pain is severe",
        "i have severe chest pain",
        "extreme chest pain",
        "very bad chest pain",
        "unbearable chest pain",

        # Hindi - Hinglish
        "bahut tez seene ka dard",
        "bahut zyada seene mein dard",
        "bahut zyada seene me dard",
        "seene mein bahut tez dard",
        "seene me bahut tez dard",
        "seene ka bahut zyada dard",

        # Hindi - Devanagari
        "बहुत तेज सीने का दर्द",
        "बहुत ज्यादा सीने में दर्द",
        "सीने में बहुत तेज दर्द",
        "सीने में बहुत ज्यादा दर्द",
        "सीने का बहुत ज्यादा दर्द",

        # Bengali
        "বুকে খুব তীব্র ব্যথা",
        "বুকে প্রচণ্ড ব্যথা",
        "বুকে খুব বেশি ব্যথা",
        "বুকে অসহ্য ব্যথা",
        "তীব্র বুকে ব্যথা",

        # Marathi
        "छातीत खूप तीव्र वेदना",
        "छातीत खूप जास्त वेदना",
        "छातीत तीव्र वेदना",
        "छातीत असह्य वेदना",
        "छातीत खूप दुखत आहे",
    ),

    # ==================================================================
    # SEVERE BLEEDING
    # ==================================================================
    "severe_bleeding": (
        # English
        "heavy bleeding",
        "bleeding heavily",
        "bleeding a lot",
        "i am bleeding heavily",
        "i am bleeding a lot",
        "severe bleeding",
        "blood is pouring",

        # Hindi - Hinglish
        "bahut zyada khoon",
        "bahut khoon beh raha",
        "khoon bahut beh raha",
        "bahut zyada khoon beh raha",
        "bahut khoon nikal raha",

        # Hindi - Devanagari
        "बहुत ज्यादा खून",
        "बहुत खून बह रहा",
        "खून बहुत बह रहा",
        "बहुत ज्यादा खून बह रहा",
        "बहुत खून निकल रहा",

        # Bengali
        "অনেক রক্তপাত হচ্ছে",
        "খুব বেশি রক্তপাত হচ্ছে",
        "অনেক রক্ত বের হচ্ছে",
        "খুব বেশি রক্ত বের হচ্ছে",
        "প্রচুর রক্তপাত হচ্ছে",

        # Marathi
        "खूप रक्तस्राव होत आहे",
        "खूप जास्त रक्तस्राव होत आहे",
        "खूप रक्त वाहत आहे",
        "खूप जास्त रक्त वाहत आहे",
        "प्रचंड रक्तस्राव होत आहे",
    ),

    # ==================================================================
    # SUDDEN WEAKNESS / PARALYSIS
    # ==================================================================
    # ==================================================================
    # GASTROINTESTINAL BLEEDING
    # ==================================================================
    "gastrointestinal_bleeding": (
        # English
        "blood in my stool",
        "blood in my stools",
        "blood in my poop",
        "blood in my bowel movement",
        "blood in my bowel movements",
        "passing blood in stool",
        "passing blood with stool",
        "blood mixed with stool",
        "blood mixed with my stool",
        "bloody stool",
        "bloody stools",
        "black tarry stool",
        "black tarry stools",
        "vomiting blood",
        "throwing up blood",
        "vomit blood",
        "blood in vomit",
        "vomiting coffee ground material",

        # Hinglish / Roman Hindi
        "stool mein khoon",
        "stool me khoon",
        "potty mein khoon",
        "potty me khoon",
        "mal mein khoon",
        "mal me khoon",
        "paikhane mein khoon",
        "paikhane me khoon",
        "mal ke saath khoon",
        "stool ke saath khoon",
        "potty ke saath khoon",
        "khoon wala stool",
        "khooni stool",
        "kaala stool",
        "kala stool",
        "kaali potty",
        "kali potty",
        "khoon ki ulti",
        "ulti mein khoon",
        "ulti me khoon",

        # Hindi - Devanagari
        "मल में खून",
        "मल में रक्त",
        "मल के साथ खून",
        "पाखाने में खून",
        "पाखाने के साथ खून",
        "पॉटी में खून",
        "पॉटी के साथ खून",
        "खूनी मल",
        "खून की उल्टी",
        "उल्टी में खून",
        "काला मल",
        "काली पॉटी",

        # Bengali
        "পায়খানায় রক্ত",
        "পায়খানার সঙ্গে রক্ত",
        "মলের সঙ্গে রক্ত",
        "মলের মধ্যে রক্ত",
        "পায়খানায় রক্তপাত",
        "রক্ত বমি",

        # Marathi
        "शौचात रक्त",
        "शौचामध्ये रक्त",
        "मलात रक्त",
        "मलामध्ये रक्त",
        "शौचासोबत रक्त",
        "रक्ताची उलटी",
        "उलटीत रक्त",
    ),

    "sudden_weakness_or_paralysis": (
        # English
        "sudden weakness",
        "sudden paralysis",
        "one side is weak",
        "one side weakness",
        "suddenly weak",
        "suddenly have weakness on one side",
        "weakness on one side",
        "weak on one side",
        "sudden numbness",
        "one side is numb",
        "one side numbness",

        # Hindi - Hinglish
        "ek taraf kamzori",
        "ek side kamzor",
        "achanak kamzori",
        "ek taraf achanak kamzori",
        "ek side achanak kamzor",
        "ek taraf sunn",
        "ek side sunn",
        "haath pair mein achanak kamzori",

        # Hindi - Devanagari
        "एक तरफ कमजोरी",
        "एक तरफ़ कमजोरी",
        "एक साइड कमजोर",
        "अचानक कमजोरी",
        "एक तरफ अचानक कमजोरी",
        "एक तरफ सुन्न",
        "एक साइड सुन्न",
        "हाथ पैर में अचानक कमजोरी",

        # Bengali
        "হঠাৎ দুর্বলতা",
        "হঠাৎ এক পাশ দুর্বল",
        "শরীরের এক পাশ দুর্বল",
        "এক পাশ অবশ",
        "হঠাৎ পক্ষাঘাত",
        "এক পাশে হঠাৎ দুর্বলতা",

        # Marathi
        "अचानक अशक्तपणा",
        "अचानक कमजोरी",
        "शरीराची एक बाजू कमजोर",
        "एक बाजू सुन्न",
        "अचानक पक्षाघात",
        "एका बाजूला अचानक कमजोरी",
    ),
}


# ======================================================================
# MVP TRIAGE PRIORITY
# ======================================================================

RED_FLAG_PRIORITIES: dict[str, RedFlagPriority] = {
    "severe_breathing_difficulty": RedFlagPriority.CRITICAL,
    "loss_of_consciousness": RedFlagPriority.CRITICAL,
    "severe_chest_pain": RedFlagPriority.CRITICAL,
    "severe_bleeding": RedFlagPriority.CRITICAL,
    "sudden_weakness_or_paralysis": RedFlagPriority.CRITICAL,
    "gastrointestinal_bleeding": RedFlagPriority.CRITICAL,
}


# ======================================================================
# TEXT HELPERS
# ======================================================================

def _normalize(text: str) -> str:
    """Normalize case and repeated whitespace."""

    text = text.casefold()
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    """Match a complete phrase rather than an arbitrary substring."""

    normalized_text = _normalize(text)
    normalized_phrase = _normalize(phrase)

    if not normalized_text or not normalized_phrase:
        return False

    pattern = (
        r"(?<!\w)"
        + re.escape(normalized_phrase)
        + r"(?!\w)"
    )

    return re.search(pattern, normalized_text) is not None


def _is_negated_or_contextual(
    text: str,
    phrase: str,
    phrase_index: int | None = None,
) -> bool:
    """
    Reject an occurrence when the patient clearly denies it or the
    occurrence belongs to another person / a story or movie.

    This is occurrence-aware: if a sentence contains both a third-person
    example and a genuine first-person symptom, the genuine occurrence
    can still be detected.
    """

    normalized_text = _normalize(text)
    normalized_phrase = _normalize(phrase)

    if phrase_index is None:
        phrase_index = normalized_text.find(normalized_phrase)

    if phrase_index < 0:
        return False

    before = normalized_text[:phrase_index].strip()
    context = before[-180:]

    # If a relationship reference appears before this occurrence but the
    # patient subsequently switches to a first-person statement, do not
    # discard the patient's occurrence.
    relationship_patterns = (
        r"\bmy brother\b",
        r"\bmy sister\b",
        r"\bmy father\b",
        r"\bmy mother\b",
        r"\bmy friend\b",
        r"\bmy husband\b",
        r"\bmy wife\b",
        r"\bmy son\b",
        r"\bmy daughter\b",
        r"\bmy child\b",
        r"\bmy relative\b",
        r"\bmy bhai\b",
        r"\bmy behen\b",
        r"\bmere bhai\b",
        r"\bmeri behen\b",
        r"\bmere papa\b",
        r"\bmeri maa\b",
        r"\bmere dost\b",
        r"\bmera beta\b",
        r"\bmeri beti\b",
    )
    first_person_patterns = (
        r"\bi\b",
        r"\bme\b",
        r"\bmujhe\b",
        r"\bmain\b",
        r"\bमैं\b",
        r"\bमुझे\b",
        r"\bमी\b",
        r"\bमला\b",
        r"\bআমি\b",
        r"\bআমার\b",
    )

    for relationship_pattern in relationship_patterns:
        relationship_match = re.search(relationship_pattern, before)
        if relationship_match:
            after_relationship = before[relationship_match.end():]
            if any(
                re.search(pattern, after_relationship)
                for pattern in first_person_patterns
            ):
                context = ""

    # Explicit symptom denial. Do not use a blanket "not" rule because
    # "I am not able to breathe" is itself a positive emergency statement.
    negation_patterns = (
        r"\bdid not have\s*$",
        r"\bdidn't have\s*$",
        r"\bdo not have\s*$",
        r"\bdon't have\s*$",
        r"\bdoes not have\s*$",
        r"\bdoesn't have\s*$",
        r"\bdid not experience\s*$",
        r"\bdidn't experience\s*$",
        r"\bdo not experience\s*$",
        r"\bdon't experience\s*$",
        r"\bdoes not experience\s*$",
        r"\bdoesn't experience\s*$",
        r"\bnot experiencing\s*$",
        r"\bnot having\s*$",
        r"\bwithout\s*$",
        r"\bno\s*$",
        r"\bnever\s*$",
        r"\bnahi\s*$",
        r"\bnahin\s*$",
    )

    if any(re.search(pattern, before) for pattern in negation_patterns):
        return True

    # Third-person / narrative context.
    contextual_patterns = (
        r"\bsomeone\b",
        r"\bsomebody\b",
        r"\ba person\b",
        r"\banother person\b",
        r"\bmy brother\b",
        r"\bmy sister\b",
        r"\bmy father\b",
        r"\bmy mother\b",
        r"\bmy friend\b",
        r"\bmy husband\b",
        r"\bmy wife\b",
        r"\bmy son\b",
        r"\bmy daughter\b",
        r"\bmy child\b",
        r"\bmy relative\b",
        r"\bmy bhai\b",
        r"\bmy behen\b",
        r"\bmere bhai\b",
        r"\bmeri behen\b",
        r"\bmere papa\b",
        r"\bmeri maa\b",
        r"\bmere dost\b",
        r"\bmera beta\b",
        r"\bmeri beti\b",
        r"\bin a movie\b",
        r"\bin the movie\b",
        r"\bmovie about\b",
        r"\bwatched a movie\b",
        r"\bwatching a movie\b",
        r"\bstory about\b",
        r"\bstory of\b",
        r"\bin a story\b",
    )

    return any(re.search(pattern, context) for pattern in contextual_patterns)


def _iter_phrase_occurrences(text: str, phrase: str):
    """Yield every occurrence of a phrase so contextual first matches do not hide later patient matches."""
    normalized_text = _normalize(text)
    normalized_phrase = _normalize(phrase)
    if not normalized_phrase:
        return

    start = 0
    while True:
        index = normalized_text.find(normalized_phrase, start)
        if index < 0:
            break
        yield index
        start = index + max(len(normalized_phrase), 1)


def _looks_like_semantic_negation(text: str) -> bool:
    """
    Detect explicit English negation of a symptom.

    This is intentionally conservative.

    We do NOT reject every sentence containing "not" because
    statements such as:

        "I am not able to breathe"

    are themselves concerning.

    We only reject common constructions where the patient clearly
    denies experiencing a symptom.
    """

    normalized = _normalize(text)

    denial_patterns = (
        r"\bdo not have\b",
        r"\bdon't have\b",
        r"\bdoes not have\b",
        r"\bdoesn't have\b",
        r"\bdo not experience\b",
        r"\bdon't experience\b",
        r"\bdoes not experience\b",
        r"\bdoesn't experience\b",
        r"\bnot experiencing\b",
        r"\bnot having\b",
        r"\bno signs of\b",
        r"\bno symptom of\b",
        r"\bno symptoms of\b",
        r"\bwithout any\b",
        r"\bthere is no\b",
        r"\bthere are no\b",
        r"\bno\s+(?:blood|bleeding|chest pain|pain|weakness|numbness)\b",
        r"\bnahi hai\b",
        r"\bnahi ho raha\b",
        r"\bnahi ho rahi\b",
        r"\bnahin hai\b",
        r"\bnahin ho raha\b",
        r"\bnahin ho rahi\b",
    )

    return any(
        re.search(pattern, normalized)
        for pattern in denial_patterns
    )


def _extract_text(answer: Any) -> str:
    """
    Extract text from a string or existing PatientAnswer-like object.
    """

    if answer is None:
        return ""

    if isinstance(answer, str):
        return answer

    resolved_text = getattr(
        answer,
        "resolved_text",
        None,
    )

    if callable(resolved_text):
        value = resolved_text()

        if isinstance(value, str):
            return value

    for attribute in (
        "text",
        "answer",
        "transcript",
        "value",
        "content",
    ):
        value = getattr(
            answer,
            attribute,
            None,
        )

        if isinstance(value, str):
            return value

    return ""


# ======================================================================
# RED FLAG DETECTOR
# ======================================================================

class RedFlagDetector:
    """
    Hybrid red-flag detector.

    Detection order:

        1. Deterministic rules
        2. Semantic similarity

    This preserves the existing deterministic behavior while
    allowing novel wording to be recognized.
    """

    def __init__(
        self,
        patterns: dict[str, tuple[str, ...]] | None = None,
        use_semantic: bool = True,
    ) -> None:

        self.patterns = (
            RED_FLAG_PATTERNS.copy()
            if patterns is None
            else patterns
        )

        self.use_semantic = use_semantic

        self._semantic_detector = None

    # ------------------------------------------------------------------
    # Lazy semantic detector
    # ------------------------------------------------------------------

    def _get_semantic_detector(self):
        """
        Load the semantic model only when it is actually needed.

        This is important because normal deterministic matches
        should not need to initialize the embedding model.
        """

        if not self.use_semantic:
            return None

        if self._semantic_detector is None:
            self._semantic_detector = (
                get_semantic_red_flag_detector()
            )

        return self._semantic_detector

    # ------------------------------------------------------------------
    # Main detection
    # ------------------------------------------------------------------

    def detect(self, answer: Any) -> DetectedRedFlag:
        """
        Detect a red flag using rules first and semantic similarity second.
        """

        text = _extract_text(answer)
        normalized_text = _normalize(text)

        if not normalized_text:
            return self._no_flag()

        # ==============================================================
        # LAYER 1 — DETERMINISTIC RULE DETECTION
        # ==============================================================

        for flag_id, patterns in self.patterns.items():

            for phrase in patterns:

                for phrase_index in _iter_phrase_occurrences(
                    normalized_text,
                    phrase,
                ):
                    if _is_negated_or_contextual(
                        normalized_text,
                        phrase,
                        phrase_index=phrase_index,
                    ):
                        continue

                    return self._detected_flag(
                        flag_id=flag_id,
                        matched_phrase=phrase,
                        matched_text=text,
                        detection_method="rule",
                    )

        # ==============================================================
        # LAYER 2 — SEMANTIC DETECTION
        # ==============================================================

        if self.use_semantic:
            # Context/ownership is handled here rather than simply
            # discarding every answer that mentions another person.
            # The semantic detector itself is category-aware; this guard
            # only blocks obvious narrative/third-person answers.
            normalized_lower = normalized_text.casefold()

            narrative_context_patterns = (
                r"\bsomeone\b",
                r"\bsomebody\b",
                r"\ba person\b",
                r"\banother person\b",
                r"\bin a movie\b",
                r"\bin the movie\b",
                r"\bmovie about\b",
                r"\bwatched a movie\b",
                r"\bwatching a movie\b",
                r"\bstory about\b",
                r"\bstory of\b",
                r"\bin a story\b",
            )

            relationship_context_patterns = (
                r"\bmy brother\b",
                r"\bmy sister\b",
                r"\bmy father\b",
                r"\bmy mother\b",
                r"\bmy friend\b",
                r"\bmy husband\b",
                r"\bmy wife\b",
                r"\bmy son\b",
                r"\bmy daughter\b",
                r"\bmy child\b",
                r"\bmy relative\b",
                r"\bmy bhai\b",
                r"\bmy behen\b",
                r"\bmere bhai\b",
                r"\bmeri behen\b",
                r"\bmere papa\b",
                r"\bmeri maa\b",
                r"\bmere dost\b",
                r"\bmera beta\b",
                r"\bmeri beti\b",
            )

            is_narrative_description = any(
                re.search(pattern, normalized_lower)
                for pattern in narrative_context_patterns
            )

            has_relationship_context = any(
                re.search(pattern, normalized_lower)
                for pattern in relationship_context_patterns
            )

            # A relationship mention alone must not suppress a genuine
            # first-person symptom:
            # "My brother fainted, but I have severe chest pain."
            first_person_markers = (
                r"\bi\b",
                r"\bme\b",
                r"\bmyself\b",
                r"\bmujhe\b",
                r"\bmain\b",
                r"\bमैं\b",
                r"\bमुझे\b",
                r"\bमी\b",
                r"\bमला\b",
                r"\bআমার\b",
                r"\bআমি\b",
            )
            has_first_person = any(
                re.search(pattern, normalized_lower)
                for pattern in first_person_markers
            )

            is_contextual_description = (
                is_narrative_description
                or (has_relationship_context and not has_first_person)
            )

            is_semantic_negation = _looks_like_semantic_negation(
                normalized_lower
            )

            if not is_contextual_description and not is_semantic_negation:
                semantic_detector = self._get_semantic_detector()

                if semantic_detector is not None:
                    semantic_result = semantic_detector.detect(
                        normalized_text
                    )

                    if semantic_result.detected:
                        return self._detected_semantic_flag(
                            semantic_result=semantic_result,
                            matched_text=text,
                        )

        return self._no_flag()

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def has_red_flag(self, answer: Any) -> bool:
        """Return only whether a red flag was detected."""

        return self.detect(answer).detected

    # ------------------------------------------------------------------
    # No flag
    # ------------------------------------------------------------------

    @staticmethod
    def _no_flag() -> DetectedRedFlag:
        """
        Validate a non-detected result using the real project schema,
        then expose the compatibility result expected by existing tests.
        """

        RedFlagResult(
            detected=False,
            flag_id=None,
            priority=None,
            matched_fields=[],
            matched_text=None,
            explanation=None,
        )

        return DetectedRedFlag(
            detected=False,
            category=None,
            matched_pattern=None,
        )

    # ------------------------------------------------------------------
    # Rule-based flag
    # ------------------------------------------------------------------

    @staticmethod
    def _detected_flag(
        flag_id: str,
        matched_phrase: str,
        matched_text: str,
        detection_method: str = "rule",
    ) -> DetectedRedFlag:
        """
        Validate and expose a deterministic red flag.
        """

        priority = RED_FLAG_PRIORITIES.get(
            flag_id,
            RedFlagPriority.HIGH,
        )

        validated = RedFlagResult(
            detected=True,
            flag_id=flag_id,
            priority=priority,
            matched_fields=[],
            matched_text=matched_text,
            explanation=(
                "Predefined red-flag pattern matched: "
                f"{matched_phrase}"
                f" ({detection_method})"
            ),
        )

        return DetectedRedFlag(
            detected=validated.detected,
            category=validated.flag_id,
            matched_pattern=matched_phrase,
            flag_id=validated.flag_id,
            priority=validated.priority,
            matched_fields=tuple(
                validated.matched_fields
            ),
            matched_text=validated.matched_text,
            explanation=validated.explanation,
        )

    # ------------------------------------------------------------------
    # Semantic flag
    # ------------------------------------------------------------------

    @staticmethod
    def _detected_semantic_flag(
        semantic_result: SemanticRedFlagResult,
        matched_text: str,
    ) -> DetectedRedFlag:
        """
        Convert the semantic detector result into the project's
        existing DetectedRedFlag representation.
        """

        flag_id = semantic_result.category

        if not flag_id:
            return DetectedRedFlag(
                detected=False,
                category=None,
                matched_pattern=None,
            )

        priority = RED_FLAG_PRIORITIES.get(
            flag_id,
            RedFlagPriority.HIGH,
        )

        score_text = (
            f"{semantic_result.score:.3f}"
            if semantic_result.score is not None
            else "unknown"
        )

        validated = RedFlagResult(
            detected=True,
            flag_id=flag_id,
            priority=priority,
            matched_fields=[],
            matched_text=matched_text,
            explanation=(
                "Semantic red-flag detection matched "
                f"'{flag_id}' with similarity score "
                f"{score_text}."
            ),
        )

        return DetectedRedFlag(
            detected=validated.detected,
            category=validated.flag_id,
            matched_pattern=(
                semantic_result.matched_text
            ),
            flag_id=validated.flag_id,
            priority=validated.priority,
            matched_fields=tuple(
                validated.matched_fields
            ),
            matched_text=validated.matched_text,
            explanation=validated.explanation,
        )


# ======================================================================
# CONVENIENCE FUNCTION
# ======================================================================

def detect_red_flags(answer: Any) -> DetectedRedFlag:
    """
    Convenience function for hybrid red-flag detection.
    """

    return RedFlagDetector().detect(answer)