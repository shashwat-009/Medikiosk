"""
Deterministic adaptive questioning for the MediSetu conversation layer.

This module keeps the existing AdaptiveQuestioning public API while upgrading
question selection from a simple "first missing field" walk into a
clinical-history state machine that is:

    complaint -> relevant fields -> applicability/branching -> next question

Design goals:
    - deterministic and testable
    - no LLM, ASR, network, diagnosis, or red-flag logic
    - preserve the existing ontology/question-bank/dialogue-state contracts
    - support reusable conditional branches
    - preserve question-bank language selection
    - remain backward compatible with legacy/simple test doubles

Important:
    The PS calls for ontology-tree/state-machine branching. This file can
    implement that behavior only for fields/questions that exist in the
    current ontology and question bank. It therefore never invents missing
    clinical questions. PS-required additions such as dedicated nocturnal
    sweating or dyspnea-grade nodes must be added to those source files before
    this engine can select them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from ai.conversation.question_bank import QuestionLanguage


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NextQuestionResult:
    """Result returned by AdaptiveQuestioning."""

    question: Any | None
    reason: str
    field_id: str | None = None
    skipped_fields: tuple[str, ...] = ()

    @property
    def has_question(self) -> bool:
        """Return True when a question is available."""
        return self.question is not None


@dataclass(frozen=True)
class BranchRule:
    """
    Optional reusable conditional rule for a field.

    ``predicate`` receives the currently stored value of ``source_field`` and
    returns True when the target field is applicable.
    """

    source_field: str
    target_field: str
    predicate: Callable[[Any], bool]
    reason: str = "conditional_branch"


@dataclass(frozen=True)
class FieldDecision:
    """Internal decision explaining whether a field can be asked."""

    field_id: str
    applicable: bool
    reason: str


# ---------------------------------------------------------------------------
# Answer normalization helpers
# ---------------------------------------------------------------------------


def _normalize_text(value: Any) -> str:
    """Normalize an answer to lowercase searchable text."""

    if value is None:
        return ""

    if isinstance(value, bool):
        return "yes" if value else "no"

    if isinstance(value, (list, tuple, set)):
        return " ".join(_normalize_text(item) for item in value)

    if isinstance(value, Mapping):
        return " ".join(
            f"{_normalize_text(key)} {_normalize_text(item)}"
            for key, item in value.items()
        )

    return str(value).strip().lower()


def _is_yes(value: Any) -> bool:
    text = _normalize_text(value)
    return text in {
        "yes",
        "y",
        "true",
        "1",
        "haan",
        "हां",
        "हाँ",
        "हो",
        "होय",
        "होय्",
        "হ্যাঁ",
    }


def _is_no(value: Any) -> bool:
    text = _normalize_text(value)
    return text in {
        "no",
        "n",
        "false",
        "0",
        "nahin",
        "nahi",
        "नहीं",
        "नही",
        "नाही",
        "না",
    }


def _is_productive_cough(value: Any) -> bool:
    """Return True for common structured/text representations of productive cough."""

    text = _normalize_text(value)

    return any(
        token in text
        for token in (
            "productive",
            "with mucus",
            "with sputum",
            "mucus",
            "sputum",
            "बलगम",
            "कफ",
            "কফ",
            "कफासह",
        )
    )


def _is_dry_cough(value: Any) -> bool:
    """Return True for common structured/text representations of dry cough."""

    text = _normalize_text(value)

    return any(
        token in text
        for token in (
            "dry",
            "सूखी",
            "सूखा",
            "कोरडा",
            "শুকনো",
        )
    )


def _contains_negative_statement(value: Any) -> bool:
    """
    Conservative negative-answer detection for conditional questions.

    This is intentionally small and only used for applicability decisions;
    clinical red-flag detection remains outside this module.
    """

    text = _normalize_text(value)

    negative_markers = (
        "no",
        "not",
        "don't",
        "do not",
        "doesn't",
        "does not",
        "never",
        "nahin",
        "nahi",
        "नहीं",
        "नही",
        "नाही",
        "না",
    )

    return any(marker in text for marker in negative_markers)


def answer_establishes_persistent_duration(value: Any) -> bool:
    """
    Return True when an answer already gives a reasonably clear duration for
    a persistent symptom.

    This is a UX guard, not a clinical parser. It is deliberately conservative:
    it recognizes explicit duration phrases (for example, "5 days", "2 weeks"),
    relative-duration phrases ("since last week", "3 days ago", "for a month"),
    and common speech-transcription forms, including written number words and
    Roman-Hindi/Hinglish expressions. It does not treat a bare calendar date
    such as "Monday" as a duration.
    """

    text = _normalize_text(value)
    if not text:
        return False

    # Numeric durations, including common Indian-language variants.
    numeric_duration_patterns = (
        r"\b\d+(?:\.\d+)?\s*(?:hour|hours|hr|hrs|day|days|week|weeks|month|months|year|years)\b",
        r"\b\d+(?:\.\d+)?\s*(?:घंटा|घंटे|दिन|दिनों|हफ्ता|हफ्ते|हफ्तों|सप्ताह|सप्ताहों|महीना|महीने|माह|साल)\b",
        r"\b\d+(?:\.\d+)?\s*(?:दिवस|आठवडा|आठवडे|महिना|महिने)\b",
        r"\b\d+(?:\.\d+)?\s*(?:দিন|সপ্তাহ|মাস|বছর)\b",
    )
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in numeric_duration_patterns):
        return True

    # Written-out English number durations are common in speech transcripts.
    # Keep this bounded so ordinary number words do not accidentally become a
    # duration signal.
    english_word_number = (
        r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
        r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
        r"nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|"
        r"ninety|hundred)"
    )
    written_number_duration_patterns = (
        rf"\b{english_word_number}(?:[- ]{english_word_number})?\s+"
        r"(?:hour|hours|hr|hrs|day|days|week|weeks|month|months|year|years)\b",
        rf"\b(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|few|couple)\s+"
        r"(?:hour|hours|day|days|week|weeks|month|months|year|years)\b",
    )
    if any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in written_number_duration_patterns
    ):
        return True

    # Written-out Indian-language number durations are also common in ASR
    # transcripts. Keep the vocabulary bounded to duration units so ordinary
    # words such as a bare weekday are not mistaken for elapsed time.
    indian_word_number_duration_patterns = (
        r"\b(?:एक|दो|तीन|चार|पाँच|पाच|छह|छः|सात|आठ|नौ|दस|ग्यारह|बारह|"
        r"तेरह|चौदह|पंद्रह|पन्द्रह|सोलह|सत्रह|अठारह|उन्नीस|बीस|कई|कुछ|"
        r"दो-तीन|चार-पाँच)\s+"
        r"(?:घंटा|घंटे|घंटों|दिन|दिनों|हफ्ता|हफ्ते|हफ्तों|सप्ताह|सप्ताहों|"
        r"महीना|महीने|महीनों|माह|साल|सालों|दिवस)\b",
        r"\b(?:এক|দুই|তিন|চার|পাঁচ|ছয়|ছয়|সাত|আট|নয়|নয়|দশ|কয়েক|কয়েক|কিছু)\s+"
        r"(?:দিন|দিনগুলি|সপ্তাহ|মাস|বছর)\b",
        r"\b(?:एक|दोन|तीन|चार|पाच|सहा|सात|आठ|नऊ|दहा|अकरा|बारा|"
        r"तेरा|चौदा|पंधरा|सोळा|सतरा|अठरा|एकोणीस|वीस|काही|काही\s+"
        r"दिवस|आठवडे|महिने|साल)\b",
    )
    if any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in indian_word_number_duration_patterns
    ):
        return True

    # Common Roman-Hindi/Hinglish duration expressions.
    roman_hindi_duration_patterns = (
        r"\b(?:do|teen|char|paanch|chhe|cheh|saat|aath|nau|das|gyarah|barah|"
        r"pandrah|bees|tees|chaalis|pachaas|saath|sattar|assi|nabbe|sau)\s+"
        r"(?:din|dino|dinon|hafta|hafte|hafton|saptah|mahina|mahine|mahino|"
        r"mahiney|saal|saalon|week|weeks|month|months|year|years)"
        r"(?:\s*(?:se|pehle|ago|for|tak))?\b",
        r"\b(?:kuch|kai|kaafi|bahut)\s+(?:din|dino|dinon|hafte|hafton|mahine|"
        r"mahino|saalon)\s*(?:se|sai|tak)\b",
    )
    if any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in roman_hindi_duration_patterns
    ):
        return True

    # Explicit "ago / since / for" constructions.
    relative_duration_patterns = (
        r"\b(?:\d+|" + english_word_number + r")\s*(?:day|days|week|weeks|month|months|year|years)\s*ago\b",
        r"\b(?:started|began|started\s+about|began\s+about)\s+(?:yesterday|today|this\s+morning|last\s+(?:night|week|month|year))\b",
        r"\bsince\s+(?:yesterday|today|last\s+(?:night|week|month|year)|(?:\d+|" + english_word_number + r")\s*(?:day|days|week|weeks|month|months|year|years))\b",
        r"\b(?:about\s+)?(?:a|an|one|few|couple)\s+(?:day|days|week|weeks|month|months|year|years)\s+ago\b",
        r"\bfor\s+(?:about\s+)?(?:a|an|the|one|few|couple|" + english_word_number + r")\s*(?:day|days|week|weeks|month|months|year|years|few\s+days|few\s+weeks|long\s+time)\b",
        r"\b(?:दिन|दिनों|हफ्ते|हफ्तों|सप्ताह|महीने|माह|साल)\s*(?:पहले|से)\b",
        r"\b\d+\s*(?:दिन|दिनों|हफ्ते|हफ्तों|सप्ताह|महीने|माह|साल)\s*(?:पहले|से)\b",
        r"\b(?:कल|आज|आज सुबह)\s*(?:से|शुरू)\b",
        r"\bपिछले\s+(?:कुछ\s+दिनों|हफ्ते|कुछ\s+हफ्तों|महीने|कुछ\s+महीनों)\s+से\b",
        r"\b\d+\s*(?:দিন|সপ্তাহ|মাস|বছর)\s*(?:আগে|ধরে|থেকে)\b",
        r"\b(?:গতকাল|আজ|আজ\s+সকাল)\s*(?:থেকে|শুরু)\b",
        r"\bগত\s+(?:কয়েক\s+দিন|কয়েক\s+সপ্তাহ|কয়েক\s+মাস)\s+ধরে\b",
        r"\b\d+\s*(?:दिवस|आठवडे|महिने|महिना)\s*(?:पूर्वी|पासून)\b",
        r"\b(?:काल|आज|आज\s+सकाळपासून)\s*(?:पासून|सुरू)\b",
        r"\bगेल्या\s+(?:काही\s+दिवसांपासून|आठवड्यापासून|काही\s+आठवड्यांपासून|महिन्यापासून)\b",
    )
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in relative_duration_patterns):
        return True

    # Very clear non-numeric duration statements.
    clear_duration_phrases = (
        "since yesterday",
        "started yesterday",
        "began yesterday",
        "started today",
        "started this morning",
        "since last week",
        "since last month",
        "for a long time",
        "for quite a while",
        "for some time",
        "for a few days",
        "for a few weeks",
        "for several days",
        "for several weeks",
        "for the last few days",
        "for the last few weeks",
        "for the past few days",
        "for the past few weeks",
        "the last few days",
        "the last few weeks",
        "the past few days",
        "the past few weeks",
        "childhood",
        "बचपन से",
        "काफी समय से",
        "कई दिनों से",
        "कई हफ्तों से",
        "काफी दिनों से",
        "बराच वेळ",
        "बर्‍याच दिवसांपासून",
        "काही दिवसांपासून",
        "অনেকদিন ধরে",
        "অনেক দিন ধরে",
        "কয়েকদিন ধরে",
        "কিছুদিন ধরে",
        "दो तीन दिन",
        "दो-तीन दिन",
        "चार पांच दिन",
        "चार-पाँच दिन",
        "कई दिन से",
        "कुछ दिन से",
        "कई दिनों से",
        "कुछ दिनों से",
        "दोन दिवसांपासून",
        "काही दिवसांपासून",
        "काही दिवसांपासून",
        "কয়েক দিন ধরে",
        "কয়েক দিন ধরে",
        "কিছু দিন ধরে",
    )
    return any(phrase in text for phrase in clear_duration_phrases)


def _should_skip_duration_after_onset(
    complaint: str,
    *,
    onset_value: Any | None,
) -> bool:
    """
    Decide whether asking the duration question would be redundant.

    For persistent complaints, an explicit onset answer such as "5 days ago"
    already establishes how long the symptom has been present. Chest-pain and
    headache duration are intentionally excluded because their duration field
    describes episode length and is therefore clinically distinct from onset.
    """

    complaint_id = _normalize_text(complaint)
    if complaint_id not in {"cough", "fever", "abdominal_pain"}:
        return False

    return onset_value is not None and answer_establishes_persistent_duration(
    onset_value
    )


class AdaptiveQuestioning:
    """
    Deterministic, ontology-guided clinical question selector.

    Existing callers are preserved. The engine now evaluates branch
    applicability from the answers already stored in DialogueState before
    selecting the next unanswered question.

    The engine does not mutate DialogueState. This preserves the existing
    contract used by the current tests and by DialogueManager.
    """

    def __init__(
        self,
        ontology: Any,
        question_bank: Any,
        dialogue_state: Any,
        *,
        field_provider: Any | None = None,
    ) -> None:
        self.ontology = ontology
        self.question_bank = question_bank
        self.dialogue_state = dialogue_state
        self.field_provider = field_provider

        # Explicit reusable rules can be injected later without changing the
        # public API. Current PS-aligned rules are evaluated in
        # _evaluate_builtin_branch below so existing callers need no changes.
        self._branch_rules: tuple[BranchRule, ...] = ()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_next_question(
        self,
        complaint: Any | None = None,
        language: QuestionLanguage | str | None = None,
    ) -> NextQuestionResult:
        """
        Return exactly one applicable unanswered question.

        Selection flow:
            1. resolve complaint and language
            2. retrieve ontology/domain fields
            3. collect already-known field IDs
            4. evaluate conditional applicability for each field
            5. preserve ontology order for deterministic clinical flow
            6. choose the first applicable field with a question

        Conditional fields are skipped only when their applicability can be
        established conservatively from known answers. Unknown answers do not
        cause a field to be skipped.
        """

        complaint = self._resolve_complaint(complaint)

        if complaint is None:
            return NextQuestionResult(
                question=None,
                reason="unknown_or_missing_complaint",
            )

        selected_language = self._resolve_language(language)
        fields = self._get_relevant_fields(complaint)
        fields = self._order_fields_for_complaint(complaint, fields)

        if not fields:
            return NextQuestionResult(
                question=None,
                reason="no_applicable_ontology_fields",
            )

        collected = self._get_collected_fields()
        skipped: list[str] = []

        for field in fields:
            field_id = self._field_id(field)

            if field_id is None:
                continue

            if field_id in collected:
                continue

            decision = self._evaluate_field_applicability(
                complaint=complaint,
                field=field,
            )

            if not decision.applicable:
                skipped.append(field_id)
                continue

            question = self._get_question_for_field(
                complaint=complaint,
                field=field,
                language=selected_language,
            )

            if question is None:
                # Do not stop the interview because an applicable field has no
                # localized/mapped question. Continue to the next field, just
                # as the old implementation did.
                continue

            reason = decision.reason
            if skipped and reason == "next_missing_field":
                reason = "branch_skip_then_next"

            return NextQuestionResult(
                question=question,
                reason=reason,
                field_id=field_id,
                skipped_fields=tuple(skipped),
            )

        return NextQuestionResult(
            question=None,
            reason=("all_remaining_fields_inapplicable" if skipped else "no_available_question"),
            skipped_fields=tuple(skipped),
        )

    def next_question(
        self,
        complaint: Any | None = None,
        language: QuestionLanguage | str | None = None,
    ) -> Any | None:
        """Compatibility API returning only the next question."""

        return self.get_next_question(
            complaint=complaint,
            language=language,
        ).question

    # ------------------------------------------------------------------
    # Applicability / branching
    # ------------------------------------------------------------------

    def _evaluate_field_applicability(
        self,
        *,
        complaint: Any,
        field: Any,
    ) -> FieldDecision:
        """
        Decide whether a field is relevant given current answers.

        The method first honors explicit dependency metadata if a future
        ontology/question implementation provides it. Built-in complaint
        rules then cover the branching already representable by the current
        MediSetu MVP question bank.
        """

        field_id = self._field_id(field)
        if field_id is None:
            return FieldDecision(
                field_id="",
                applicable=False,
                reason="invalid_field",
            )

        explicit = self._evaluate_explicit_metadata(field)
        if explicit is not None:
            return FieldDecision(
                field_id=field_id,
                applicable=explicit,
                reason=(
                    "explicit_branch" if explicit else "explicit_dependency_not_met"
                ),
            )

        # Reusable injected rules, currently empty by default for backwards
        # compatibility. The engine is ready for future ontology metadata.
        for rule in self._branch_rules:
            if rule.target_field != field_id:
                continue

            value = self._get_field_value(rule.source_field)
            if value is None:
                # Unknown dependency => do not skip. Ask conservatively.
                continue

            if rule.predicate(value):
                return FieldDecision(
                    field_id=field_id,
                    applicable=True,
                    reason=rule.reason,
                )

            return FieldDecision(
                field_id=field_id,
                applicable=False,
                reason="conditional_branch_not_met",
            )

        built_in = self._evaluate_builtin_branch(
            complaint=complaint,
            field_id=field_id,
        )
        if built_in is not None:
            return FieldDecision(
                field_id=field_id,
                applicable=built_in[0],
                reason=built_in[1],
            )

        return FieldDecision(
            field_id=field_id,
            applicable=True,
            reason="next_missing_field",
        )

    def _evaluate_builtin_branch(
        self,
        *,
        complaint: Any,
        field_id: str,
    ) -> tuple[bool, str] | None:
        """
        Built-in PS-aligned rules for fields currently present in main.

        These rules are intentionally conservative and only prune a field
        when the preceding answer gives a sufficiently clear result.
        """

        complaint_value = self._normalise_identifier(complaint)

        # --------------------------------------------------------------
        # TEMPORAL UX: do not ask onset and duration back-to-back when the
        # onset answer already contains an explicit duration.
        #
        # Keep chest-pain/headache duration separate because those fields
        # describe episode length, not merely how long the complaint has been
        # present.
        # --------------------------------------------------------------
        if field_id == "duration":
            onset = self._get_field_value("onset")
            if _should_skip_duration_after_onset(
                complaint_value,
                onset_value=onset,
            ):
                return False, "duration_already_established_by_onset"

        # --------------------------------------------------------------
        # COUGH: sputum production branch
        # --------------------------------------------------------------
        if complaint_value == "cough":
            nature = self._get_field_value("nature")
            sputum = self._get_field_value("sputum")

            if field_id == "sputum":
                # The "dry vs with mucus" node itself establishes whether
                # sputum is present when the answer is unambiguous. In that
                # case do not ask the same clinical fact twice.
                if nature is not None:
                    if _is_dry_cough(nature):
                        return False, "cough_nature_dry"
                    if _is_productive_cough(nature):
                        return False, "cough_nature_productive_already_establishes_sputum"

                return True, "next_missing_field"

            if field_id == "sputum_characteristics":
                # Ask characteristics only when sputum is known/present.
                if nature is not None:
                    if _is_productive_cough(nature):
                        return True, "cough_productive_branch"
                    if _is_dry_cough(nature):
                        return False, "cough_nature_dry"

                    # Unknown nature: if the explicit sputum answer says no,
                    # do not ask for sputum characteristics.
                    if _is_no(sputum):
                        return False, "sputum_absent"
                    if _is_yes(sputum):
                        return True, "sputum_present_branch"

                if sputum is not None:
                    if _is_yes(sputum):
                        return True, "sputum_present_branch"
                    if _is_no(sputum):
                        return False, "sputum_absent"

                # Unknown -> ask rather than silently omit information.
                return True, "next_missing_field"

            # The PS calls for fever, nocturnal sweating, and dyspnea grading
            # in the cough pathway. These are now explicit ontology nodes, so
            # they are naturally reached in the deterministic cough path.
            if field_id in {"fever", "nocturnal_sweating", "dyspnea_grade"}:
                return True, "cough_ps_assessment"

        # --------------------------------------------------------------
        # FEVER: cough/headache are explicitly asked as associated features
        # --------------------------------------------------------------
        if complaint_value == "fever":
            # These fields are binary associated symptoms in the existing
            # question bank. They remain ordinary questions; no inferred
            # sub-question is invented here.
            if field_id in {"cough", "headache"}:
                return True, "associated_symptom_screen"

        # --------------------------------------------------------------
        # CHEST PAIN / ABDOMINAL PAIN / HEADACHE
        # --------------------------------------------------------------
        # Ordering is handled by _order_fields_for_complaint(). Here we keep
        # every existing pain-related field askable and let the ordered path
        # drive the state-machine progression. No missing clinical node is
        # invented by this module.
        if complaint_value in {
            "chest_pain",
            "abdominal_pain",
            "headache",
        }:
            return True, "structured_hpi_path"

        return None

    def _evaluate_explicit_metadata(self, field: Any) -> bool | None:
        """
        Evaluate optional dependency metadata without requiring schema changes.

        Supported forms when present on a future ClinicalField are:
            depends_on = ("nature",)
            required_if = {"nature": "productive"}
            condition = callable(value_map) -> bool

        Existing current ontology fields have none of these, so this is a
        no-op for today's implementation.
        """

        depends_on = getattr(field, "depends_on", None)
        required_if = getattr(field, "required_if", None)
        condition = getattr(field, "condition", None)

        if callable(condition):
            values = self._all_field_values()
            try:
                return bool(condition(values))
            except TypeError:
                try:
                    return bool(condition(self.dialogue_state))
                except Exception:
                    return None
            except Exception:
                return None

        if required_if is not None:
            if not isinstance(required_if, Mapping):
                return None

            for dependency, expected in required_if.items():
                actual = self._get_field_value(str(dependency))

                if actual is None:
                    return None

                if not self._values_match(actual, expected):
                    return False

            return True

        if depends_on:
            # Dependency declarations without a condition only mean the field
            # is downstream of another field. Do not skip it merely because
            # the dependency exists; unknown state must remain askable.
            if isinstance(depends_on, str):
                dependencies = (depends_on,)
            else:
                try:
                    dependencies = tuple(depends_on)
                except TypeError:
                    return None

            for dependency in dependencies:
                if self._get_field_value(str(dependency)) is None:
                    return None

        return None

    @staticmethod
    def _values_match(actual: Any, expected: Any) -> bool:
        """Compare structured answers conservatively."""

        if actual == expected:
            return True

        actual_text = _normalize_text(actual)
        expected_text = _normalize_text(expected)

        if actual_text == expected_text:
            return True

        if expected_text in {"yes", "true"}:
            return _is_yes(actual)

        if expected_text in {"no", "false"}:
            return _is_no(actual)

        if expected_text in {
            "productive",
            "with mucus",
            "with sputum",
        }:
            return _is_productive_cough(actual)

        if expected_text == "dry":
            return _is_dry_cough(actual)

        return False

    # ------------------------------------------------------------------
    # Clinical path ordering
    # ------------------------------------------------------------------

    def _order_fields_for_complaint(
        self,
        complaint: Any,
        fields: list[Any],
    ) -> list[Any]:
        """
        Apply a deterministic complaint-specific clinical path.

        The ordering is deliberately implemented only for field identifiers
        that may already exist in the current ontology/question bank. Missing
        nodes are simply omitted, so this method never invents questions.

        This makes the selector closer to the PS's adaptive/state-machine
        behavior while preserving the existing ontology as the source of truth.
        """
        complaint_id = self._normalise_identifier(complaint)

        paths: dict[str, tuple[str, ...]] = {
            # Pain complaints: SOCRATES-style progression using only nodes
            # already exposed by the ontology/question bank.
            "chest_pain": (
                "onset",
                "location",
                "character",
                "duration",
                "radiation",
                "aggravating_factors",
                "relieving_factors",
                "severity",
                "associated_symptoms",
            ),
            "abdominal_pain": (
                "onset",
                "location",
                "character",
                "duration",
                "radiation",
                "aggravating_factors",
                "relieving_factors",
                "severity",
                "associated_symptoms",
            ),
            "headache": (
                "onset",
                "location",
                "character",
                "duration",
                "aggravating_factors",
                "relieving_factors",
                "severity",
                "associated_symptoms",
            ),
            # Cough: establish the cough itself before drilling into sputum.
            "cough": (
                "onset",
                "duration",
                "severity",
                "nature",
                "sputum",
                "sputum_characteristics",
                "blood_presence",
                "fever",
                "nocturnal_sweating",
                "dyspnea_grade",
                "associated_symptoms",
                "aggravating_factors",
            ),
        }

        path = paths.get(complaint_id)
        if not path:
            return list(fields)

        by_id: dict[str, list[Any]] = {}
        for field in fields:
            field_id = self._field_id(field)
            if field_id is None:
                continue
            normalized = self._normalise_identifier(field_id)
            by_id.setdefault(normalized, []).append(field)

        ordered: list[Any] = []
        used: set[int] = set()

        for identifier in path:
            for field in by_id.get(identifier, ()):
                marker = id(field)
                if marker in used:
                    continue
                ordered.append(field)
                used.add(marker)

        # Preserve ontology order for any fields that are not explicitly
        # represented in the complaint path. This keeps existing functionality
        # instead of dropping legitimate ontology fields.
        for field in fields:
            marker = id(field)
            if marker not in used:
                ordered.append(field)
                used.add(marker)

        return ordered

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------

    def _resolve_language(
        self,
        language: QuestionLanguage | str | None,
    ) -> QuestionLanguage:
        """Resolve requested language with the existing fallbacks."""

        if language is not None:
            return self._normalise_language(language)

        state = self.dialogue_state

        for attribute in (
            "language",
            "preferred_language",
            "current_language",
        ):
            value = getattr(state, attribute, None)
            if value is not None:
                try:
                    return self._normalise_language(value)
                except ValueError:
                    pass

        for method_name in (
            "get_language",
            "get_preferred_language",
            "get_current_language",
        ):
            method = getattr(state, method_name, None)
            if callable(method):
                value = method()
                if value is not None:
                    try:
                        return self._normalise_language(value)
                    except ValueError:
                        pass

        return QuestionLanguage.ENGLISH

    @staticmethod
    def _normalise_language(
        language: QuestionLanguage | str,
    ) -> QuestionLanguage:
        """Convert a language value into QuestionLanguage."""

        if isinstance(language, QuestionLanguage):
            return language

        if not isinstance(language, str):
            raise ValueError(
                "Language must be a string or QuestionLanguage."
            )

        value = language.strip().lower()

        aliases = {
            "en": QuestionLanguage.ENGLISH,
            "english": QuestionLanguage.ENGLISH,
            "hi": QuestionLanguage.HINDI,
            "hindi": QuestionLanguage.HINDI,
            "bn": QuestionLanguage.BENGALI,
            "bengali": QuestionLanguage.BENGALI,
            "mr": QuestionLanguage.MARATHI,
            "marathi": QuestionLanguage.MARATHI,
        }

        try:
            return aliases[value]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported language: {language!r}"
            ) from exc

    # ------------------------------------------------------------------
    # Complaint / ontology
    # ------------------------------------------------------------------

    def _resolve_complaint(self, complaint: Any | None) -> Any | None:
        """Resolve complaint from argument or DialogueState."""

        if complaint is not None:
            return complaint

        state = self.dialogue_state

        for attribute in (
            "complaint",
            "chief_complaint",
            "current_complaint",
        ):
            value = getattr(state, attribute, None)
            if value is not None:
                return value

        for method_name in (
            "get_complaint",
            "get_chief_complaint",
            "get_current_complaint",
        ):
            method = getattr(state, method_name, None)
            if callable(method):
                value = method()
                if value is not None:
                    return value

        return None

    @staticmethod
    def _normalise_identifier(value: Any) -> str:
        """Normalize complaint/field identifiers for safe comparison."""

        if value is None:
            return ""

        if hasattr(value, "value"):
            try:
                value = value.value
            except Exception:
                pass

        return str(value).strip().lower().replace(" ", "_")

    def _get_relevant_fields(self, complaint: Any) -> list[Any]:
        """Retrieve complaint fields plus shared general-history fields."""

        if self.field_provider is not None:
            fields = getattr(self.field_provider, "fields", None)
            if fields is not None:
                return list(fields)

        ontology = self.ontology
        complaint_fields: list[Any] | None = None

        for method_name in (
            "get_fields",
            "get_relevant_fields",
            "get_fields_for_complaint",
        ):
            method = getattr(ontology, method_name, None)
            if callable(method):
                result = method(complaint)
                complaint_fields = list(result or [])
                break

        if complaint_fields is None:
            for method_name in (
                "get_ontology",
                "get",
            ):
                method = getattr(ontology, method_name, None)
                if callable(method):
                    result = method(complaint)
                    if result is None:
                        complaint_fields = []
                        break

                    for attribute in (
                        "fields",
                        "relevant_fields",
                        "clinical_fields",
                    ):
                        fields = getattr(result, attribute, None)
                        if fields is not None:
                            complaint_fields = list(fields)
                            break
                    if complaint_fields is not None:
                        break

        if complaint_fields is None:
            for attribute in (
                "fields",
                "relevant_fields",
                "clinical_fields",
            ):
                fields = getattr(complaint, attribute, None)
                if fields is not None:
                    complaint_fields = list(fields)
                    break

        if complaint_fields is None:
            complaint_fields = []

        general_method = getattr(ontology, "get_general_history_fields", None)
        if callable(general_method):
            general_fields = list(general_method() or [])
            existing_ids = {
                self._normalise_identifier(self._field_id(field))
                for field in complaint_fields
                if self._field_id(field) is not None
            }
            complaint_fields.extend(
                field
                for field in general_fields
                if self._normalise_identifier(self._field_id(field))
                not in existing_ids
            )

        return complaint_fields

    @staticmethod
    def _field_id(field: Any) -> str | None:
        """Extract a stable field identifier."""

        if field is None:
            return None

        if isinstance(field, str):
            return field

        for attribute in (
            "field_id",
            "id",
            "identifier",
            "name",
            "value",
        ):
            value = getattr(field, attribute, None)
            if value is not None:
                return str(value)

        return str(field)

    # ------------------------------------------------------------------
    # Dialogue State access
    # ------------------------------------------------------------------

    def _get_collected_fields(self) -> set[str]:
        """Obtain collected field IDs using the existing DialogueState API."""

        state = self.dialogue_state

        for method_name in (
            "get_collected_fields",
            "collected_fields",
        ):
            value = getattr(state, method_name, None)
            if callable(value):
                return self._normalise_field_ids(value())
            if value is not None:
                return self._normalise_field_ids(value)

        for method_name in (
            "get_known_fields",
            "get_known_field_ids",
        ):
            method = getattr(state, method_name, None)
            if callable(method):
                return self._normalise_field_ids(method())

        for attribute in (
            "collected",
            "known_fields",
            "clinical_fields",
            "values",
        ):
            value = getattr(state, attribute, None)
            if value is not None:
                return self._normalise_field_ids(value)

        return set()

    def _get_field_value(self, field_id: str) -> Any | None:
        """Read one stored field value without mutating DialogueState."""

        state = self.dialogue_state
        key = self._normalise_identifier(field_id)

        for method_name in (
            "get_field_value",
            "get_value",
            "value_for_field",
        ):
            method = getattr(state, method_name, None)
            if callable(method):
                try:
                    value = method(field_id)
                except (KeyError, ValueError):
                    continue
                except Exception:
                    continue
                return value

        for attribute in (
            "clinical_fields",
            "values",
            "fields",
        ):
            container = getattr(state, attribute, None)
            if container is None:
                continue

            if isinstance(container, Mapping):
                for candidate_key, candidate_value in container.items():
                    candidate = self._field_id(candidate_key)
                    if candidate is None:
                        continue
                    if self._normalise_identifier(candidate) != key:
                        continue

                    if hasattr(candidate_value, "value"):
                        return getattr(candidate_value, "value")
                    if isinstance(candidate_value, Mapping) and "value" in candidate_value:
                        return candidate_value["value"]
                    return candidate_value

        return None

    def _all_field_values(self) -> dict[str, Any]:
        """Return a normalized view of currently available clinical values."""

        result: dict[str, Any] = {}

        fields = self._get_collected_fields()
        for field_id in fields:
            result[field_id] = self._get_field_value(field_id)

        # Include values from direct mappings even when their implementation
        # doesn't expose a collected-field helper.
        for attribute in ("clinical_fields", "values"):
            container = getattr(self.dialogue_state, attribute, None)
            if not isinstance(container, Mapping):
                continue
            for key in container:
                normalized = self._normalise_identifier(self._field_id(key))
                if normalized:
                    result[normalized] = self._get_field_value(normalized)

        return result

    def _normalise_field_ids(self, fields: Any) -> set[str]:
        """Normalize a collection of field identifiers."""

        if fields is None:
            return set()

        if isinstance(fields, Mapping):
            result: set[str] = set()
            for key, value in fields.items():
                if value is None:
                    continue
                field_id = self._field_id(key)
                if field_id is not None:
                    result.add(self._normalise_identifier(field_id))
            return result

        if isinstance(fields, str):
            return {self._normalise_identifier(fields)}

        try:
            values: Iterable[Any] = fields
        except TypeError:
            return set()

        result: set[str] = set()
        for field in values:
            field_id = self._field_id(field)
            if field_id is not None:
                result.add(self._normalise_identifier(field_id))

        return result

    # ------------------------------------------------------------------
    # Question Bank
    # ------------------------------------------------------------------

    def _get_question_for_field(
        self,
        complaint: Any,
        field: Any,
        language: QuestionLanguage,
    ) -> Any | None:
        """Retrieve the first suitable question for a field and language."""

        question_bank = self.question_bank
        field_id = self._field_id(field)
        if field_id is None:
            return None

        method = getattr(question_bank, "get_questions_for_field", None)
        if callable(method):
            result = None
            try:
                result = method(
                    complaint,
                    field_id,
                    language=language,
                )
            except TypeError:
                try:
                    result = method(
                        complaint,
                        field_id,
                        language,
                    )
                except TypeError:
                    result = method(
                        complaint,
                        field_id,
                    )

            selected = self._pick_question(result, language)
            if selected is not None:
                return selected

        method = getattr(question_bank, "get_question_for_field", None)
        if callable(method):
            result = None
            try:
                result = method(
                    complaint,
                    field_id,
                    language=language,
                )
            except TypeError:
                try:
                    result = method(
                        complaint,
                        field_id,
                        language,
                    )
                except TypeError:
                    try:
                        result = method(
                            complaint,
                            field_id,
                        )
                    except (TypeError, ValueError):
                        result = None

            selected = self._pick_question(result, language)
            if selected is not None:
                return selected

        for method_name in (
            "get_questions_for_complaint",
            "get_questions",
        ):
            method = getattr(question_bank, method_name, None)
            if not callable(method):
                continue

            try:
                questions = method(
                    complaint,
                    language=language,
                ) or []
            except TypeError:
                questions = method(complaint) or []

            matching = [
                question
                for question in questions
                if self._question_field_id(question) == field_id
            ]

            selected = self._select_language_question(matching, language)
            if selected is not None:
                return selected

            for question in matching:
                if self._question_language(question) is None:
                    return question

        return None

    @classmethod
    def _pick_question(
        cls,
        result: Any,
        language: QuestionLanguage,
    ) -> Any | None:
        if result is None:
            return None

        if isinstance(result, (list, tuple)):
            selected = cls._select_language_question(result, language)
            if selected is not None:
                return selected

            for question in result:
                if cls._question_language(question) is None:
                    return question

            return result[0] if result else None

        question_language = cls._question_language(result)
        if question_language is None or question_language == language:
            return result

        return None

    # ------------------------------------------------------------------
    # Question helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _question_language(question: Any) -> QuestionLanguage | None:
        """Extract QuestionLanguage from a question."""

        if question is None:
            return None

        value = getattr(question, "language", None)

        if isinstance(value, QuestionLanguage):
            return value

        if isinstance(value, str):
            aliases = {
                "en": QuestionLanguage.ENGLISH,
                "english": QuestionLanguage.ENGLISH,
                "hi": QuestionLanguage.HINDI,
                "hindi": QuestionLanguage.HINDI,
                "bn": QuestionLanguage.BENGALI,
                "bengali": QuestionLanguage.BENGALI,
                "mr": QuestionLanguage.MARATHI,
                "marathi": QuestionLanguage.MARATHI,
            }
            return aliases.get(value.strip().lower())

        return None

    @classmethod
    def _select_language_question(
        cls,
        questions: Iterable[Any],
        language: QuestionLanguage,
    ) -> Any | None:
        """Select the first question matching the requested language."""

        for question in questions:
            if cls._question_language(question) == language:
                return question

        return None

    @staticmethod
    def _question_field_id(question: Any) -> str | None:
        """Extract the ontology field ID from a question."""

        if question is None:
            return None

        for attribute in (
            "field_id",
            "clinical_field",
            "ontology_field",
            "field",
        ):
            value = getattr(question, attribute, None)
            if value is None:
                continue

            if isinstance(value, str):
                return value

            for nested_attribute in (
                "field_id",
                "id",
                "identifier",
                "name",
                "value",
            ):
                nested = getattr(value, nested_attribute, None)
                if nested is not None:
                    return str(nested)

            return str(value)

        return None


__all__ = [
    "AdaptiveQuestioning",
    "BranchRule",
    "FieldDecision",
    "NextQuestionResult",
    "answer_establishes_persistent_duration",
]
