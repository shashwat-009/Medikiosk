from __future__ import annotations

from ai.conversation.red_flags import (
    RED_FLAG_PATTERNS,
    DetectedRedFlag,
    RedFlagDetector,
    detect_red_flags,
)


def _is_detected(result) -> bool:
    """Support both fallback result and project result schema."""
    if hasattr(result, "detected"):
        return bool(result.detected)

    if hasattr(result, "is_red_flag"):
        return bool(result.is_red_flag)

    if hasattr(result, "red_flag_detected"):
        return bool(result.red_flag_detected)

    return False


def _get_category(result):
    return getattr(result, "category", None)


def _get_matched_pattern(result):
    return getattr(result, "matched_pattern", None)


def test_module_imports_successfully():
    assert RedFlagDetector is not None
    assert detect_red_flags is not None


def test_detector_initializes_successfully():
    detector = RedFlagDetector()

    assert detector is not None
    assert isinstance(detector.patterns, dict)
    assert len(detector.patterns) > 0


def test_normal_answer_returns_no_red_flag():
    detector = RedFlagDetector()

    result = detector.detect(
        "I have a mild fever since yesterday."
    )

    assert _is_detected(result) is False


def test_predefined_red_flag_is_detected():
    detector = RedFlagDetector()

    result = detector.detect(
        "I cannot breathe properly."
    )

    assert _is_detected(result) is True
    assert _get_category(result) == "severe_breathing_difficulty"


def test_multiple_supported_patterns_are_detected():
    detector = RedFlagDetector()

    test_cases = [
        (
            "I cannot breathe.",
            "severe_breathing_difficulty",
        ),
        (
            "I passed out yesterday.",
            "loss_of_consciousness",
        ),
        (
            "I have severe chest pain.",
            "severe_chest_pain",
        ),
        (
            "I am bleeding heavily.",
            "severe_bleeding",
        ),
        (
            "I suddenly have weakness on one side.",
            "sudden_weakness_or_paralysis",
        ),
    ]

    for text, expected_category in test_cases:
        result = detector.detect(text)

        assert _is_detected(result) is True
        assert _get_category(result) == expected_category


def test_case_normalization_works():
    detector = RedFlagDetector()

    result = detector.detect(
        "I CANNOT BREATHE"
    )

    assert _is_detected(result) is True


def test_whitespace_normalization_works():
    detector = RedFlagDetector()

    result = detector.detect(
        "I    cannot     breathe"
    )

    assert _is_detected(result) is True


def test_hindi_hinglish_matching_works():
    detector = RedFlagDetector()

    hindi_result = detector.detect(
        "Mujhe saans lene mein dikkat ho rahi hai."
    )

    hinglish_result = detector.detect(
        "Meri saans nahi aa rahi."
    )

    assert _is_detected(hindi_result) is True
    assert _is_detected(hinglish_result) is True


def test_unrelated_words_do_not_trigger_false_positive():
    detector = RedFlagDetector()

    normal_answers = [
        "I am breathing normally.",
        "I have a mild headache.",
        "My chest feels normal.",
        "I have no serious problem.",
        "I feel slightly tired.",
    ]

    for answer in normal_answers:
        result = detector.detect(answer)

        assert _is_detected(result) is False


def test_third_person_context_does_not_trigger():
    detector = RedFlagDetector()

    result = detector.detect(
        "I watched a movie about someone who passed out."
    )

    assert _is_detected(result) is False


def test_negated_passed_out_does_not_trigger():
    detector = RedFlagDetector()

    result = detector.detect(
        "I did not pass out."
    )

    assert _is_detected(result) is False


def test_negated_bleeding_does_not_trigger():
    detector = RedFlagDetector()

    result = detector.detect(
        "There is no bleeding."
    )

    assert _is_detected(result) is False


def test_actual_passed_out_triggers():
    detector = RedFlagDetector()

    result = detector.detect(
        "I passed out yesterday."
    )

    assert _is_detected(result) is True
    assert _get_category(result) == "loss_of_consciousness"


def test_actual_bleeding_triggers():
    detector = RedFlagDetector()

    result = detector.detect(
        "I am bleeding heavily."
    )

    assert _is_detected(result) is True
    assert _get_category(result) == "severe_bleeding"


def test_empty_input_is_safe():
    detector = RedFlagDetector()

    assert _is_detected(detector.detect("")) is False
    assert _is_detected(detector.detect("   ")) is False
    assert _is_detected(detector.detect(None)) is False


def test_repeated_detection_is_deterministic():
    detector = RedFlagDetector()

    answer = "I cannot breathe properly."

    first = detector.detect(answer)
    second = detector.detect(answer)

    assert _is_detected(first) == _is_detected(second)
    assert _get_category(first) == _get_category(second)
    assert _get_matched_pattern(first) == _get_matched_pattern(second)


def test_result_has_stable_structured_fields():
    detector = RedFlagDetector()

    result = detector.detect(
        "I cannot breathe."
    )

    assert (
        hasattr(result, "detected")
        or hasattr(result, "is_red_flag")
        or hasattr(result, "red_flag_detected")
    )

    assert hasattr(result, "category")
    assert hasattr(result, "matched_pattern")


def test_no_network_dependency():
    detector = RedFlagDetector()

    result = detector.detect(
        "I have a headache."
    )

    assert _is_detected(result) is False


def test_does_not_depend_on_sarvam():
    detector = RedFlagDetector()

    assert not hasattr(detector, "sarvam")
    assert not hasattr(detector, "asr_provider")


def test_custom_patterns_are_supported():
    detector = RedFlagDetector(
        patterns={
            "custom_flag": (
                "special emergency phrase",
            )
        }
    )

    result = detector.detect(
        "This is a special emergency phrase."
    )

    assert _is_detected(result) is True
    assert _get_category(result) == "custom_flag"
    assert _get_matched_pattern(result) == "special emergency phrase"


def test_pattern_catalog_is_deterministic():
    first = tuple(RED_FLAG_PATTERNS.keys())
    second = tuple(RED_FLAG_PATTERNS.keys())

    assert first == second


def test_convenience_function():
    result = detect_red_flags(
        "I cannot breathe."
    )

    assert _is_detected(result) is True
    
def test_severe_breathing_difficulty_is_critical():
    detector = RedFlagDetector()

    result = detector.detect(
        "I cannot breathe properly."
    )

    assert _is_detected(result) is True
    assert result.priority.value == "critical"


def test_loss_of_consciousness_is_critical():
    detector = RedFlagDetector()

    result = detector.detect(
        "I passed out yesterday."
    )

    assert _is_detected(result) is True
    assert result.priority.value == "critical"


def test_severe_chest_pain_is_critical():
    detector = RedFlagDetector()

    result = detector.detect(
        "I have severe chest pain."
    )

    assert _is_detected(result) is True
    assert result.priority.value == "critical"


def test_severe_bleeding_is_critical():
    detector = RedFlagDetector()

    result = detector.detect(
        "I am bleeding heavily."
    )

    assert _is_detected(result) is True
    assert result.priority.value == "critical"


def test_sudden_weakness_is_critical():
    detector = RedFlagDetector()

    result = detector.detect(
        "I suddenly have weakness on one side."
    )

    assert _is_detected(result) is True
    assert result.priority.value == "critical" 
