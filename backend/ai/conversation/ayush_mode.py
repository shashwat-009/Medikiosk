"""
AYUSH-specific history-taking layer for MediKiosk.

This module is intentionally a thin domain layer over the existing
conversation engine.

Responsibilities:
    - Identify AYUSH mode.
    - Define AYUSH history-taking sections.
    - Provide deterministic multilingual AYUSH question specifications.
    - Track AYUSH-specific collected information.
    - Report deterministic progress/completion.
    - Validate AYUSH field identifiers.

Non-responsibilities:
    - ASR
    - OCR
    - LLM calls
    - diagnosis
    - treatment recommendations
    - red-flag detection
    - independent dialogue management
    - adaptive question selection

The existing conversation engine should remain responsible for:
    - DialogueState
    - adaptive questioning
    - conversation history
    - red flags
    - structured clinical output

Supported languages:
    - en: English
    - hi: Hindi
    - bn: Bengali
    - mr: Marathi
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Final, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AyushSection(StrEnum):
    """Sections of AYUSH history collection."""

    DASHAVIDHA_PARIKSHA = "dashavidha_pariksha"
    AHARA = "ahara"
    VIHARA = "vihara"
    GENERAL_HISTORY = "general_history"


class DashavidhaField(StrEnum):
    """The ten components of Dashavidha Pariksha."""

    PRAKRITI = "prakriti"
    VIKRITI = "vikriti"
    SARA = "sara"
    SAMHANANA = "samhanana"
    PRAMANA = "pramana"
    SATMYA = "satmya"
    SATTVA = "sattva"
    AHARA_SHAKTI = "ahara_shakti"
    VYAYAMA_SHAKTI = "vyayama_shakti"
    VAYA = "vaya"


class AyushField(StrEnum):
    """All AYUSH-specific structured history fields."""

    PRAKRITI = "prakriti"
    VIKRITI = "vikriti"
    SARA = "sara"
    SAMHANANA = "samhanana"
    PRAMANA = "pramana"
    SATMYA = "satmya"
    SATTVA = "sattva"
    AHARA_SHAKTI = "ahara_shakti"
    VYAYAMA_SHAKTI = "vyayama_shakti"
    VAYA = "vaya"

    AHARA_PATTERN = "ahara_pattern"
    AHARA_TIMING = "ahara_timing"
    AHARA_APPETITE = "ahara_appetite"
    AHARA_TOLERANCE = "ahara_tolerance"
    AHARA_PREFERENCES = "ahara_preferences"

    VIHARA_SLEEP = "vihara_sleep"
    VIHARA_ACTIVITY = "vihara_activity"
    VIHARA_EXERCISE = "vihara_exercise"
    VIHARA_DAILY_ROUTINE = "vihara_daily_routine"
    VIHARA_STRESS = "vihara_stress"

    GENERAL_CHIEF_COMPLAINT = "general_chief_complaint"
    GENERAL_DURATION = "general_duration"
    GENERAL_MEDICAL_HISTORY = "general_medical_history"
    GENERAL_MEDICATIONS = "general_medications"
    GENERAL_ALLERGIES = "general_allergies"


SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = (
    "en",
    "hi",
    "bn",
    "mr",
)


class AyushQuestion(BaseModel):
    """
    Deterministic multilingual question specification consumed by the
    existing question/adaptive-questioning layer.

    The canonical English question is stored in ``text``.
    Additional supported-language translations are stored in
    ``translations``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    field_id: str
    section: AyushSection
    text: str
    translations: Mapping[str, str] = Field(default_factory=dict)
    required: bool = True
    order: int = Field(ge=0)

    @field_validator("id", "field_id", "text")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question values cannot be empty.")
        return value

    @field_validator("translations")
    @classmethod
    def validate_translations(
        cls,
        value: Mapping[str, str],
    ) -> Mapping[str, str]:
        for language, text in value.items():
            if language not in SUPPORTED_LANGUAGES:
                raise ValueError(
                    f"Unsupported AYUSH question language: {language!r}"
                )

            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    f"Translation for {language!r} cannot be empty."
                )

        return dict(value)

    def text_for(self, language: str) -> str:
        """
        Return the question text for the requested language.

        English is the canonical fallback when a translation is unavailable.
        """
        language = language.strip().lower()

        if language == "en":
            return self.text

        return self.translations.get(language, self.text)


class AyushFieldValue(BaseModel):
    """A collected AYUSH history value."""

    model_config = ConfigDict(extra="forbid")

    field_id: str
    value: Any

    @field_validator("field_id")
    @classmethod
    def validate_field_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field_id cannot be empty.")
        return value


class AyushProgress(BaseModel):
    """Deterministic AYUSH collection progress."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_fields: int = Field(ge=0)
    collected_fields: int = Field(ge=0)
    remaining_fields: int = Field(ge=0)
    percentage: float = Field(ge=0.0, le=100.0)
    completed: bool


class AyushModeState(BaseModel):
    """Serializable AYUSH-specific state."""

    model_config = ConfigDict(extra="forbid")

    mode: str = "ayush"
    values: dict[str, Any] = Field(default_factory=dict)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value != "ayush":
            raise ValueError("AyushModeState mode must be 'ayush'.")
        return value


# ---------------------------------------------------------------------------
# Deterministic domain definitions
# ---------------------------------------------------------------------------

DASHAVIDHA_FIELDS: Final[tuple[str, ...]] = tuple(
    field.value for field in DashavidhaField
)

AHARA_FIELDS: Final[tuple[str, ...]] = (
    AyushField.AHARA_PATTERN.value,
    AyushField.AHARA_TIMING.value,
    AyushField.AHARA_APPETITE.value,
    AyushField.AHARA_TOLERANCE.value,
    AyushField.AHARA_PREFERENCES.value,
)

VIHARA_FIELDS: Final[tuple[str, ...]] = (
    AyushField.VIHARA_SLEEP.value,
    AyushField.VIHARA_ACTIVITY.value,
    AyushField.VIHARA_EXERCISE.value,
    AyushField.VIHARA_DAILY_ROUTINE.value,
    AyushField.VIHARA_STRESS.value,
)

GENERAL_FIELDS: Final[tuple[str, ...]] = (
    AyushField.GENERAL_CHIEF_COMPLAINT.value,
    AyushField.GENERAL_DURATION.value,
    AyushField.GENERAL_MEDICAL_HISTORY.value,
    AyushField.GENERAL_MEDICATIONS.value,
    AyushField.GENERAL_ALLERGIES.value,
)

AYUSH_FIELDS: Final[tuple[str, ...]] = (
    DASHAVIDHA_FIELDS + AHARA_FIELDS + VIHARA_FIELDS
)


def _question(
    number: int,
    field_id: str,
    section: AyushSection,
    text: str,
    *,
    hi: str,
    bn: str,
    mr: str,
) -> AyushQuestion:
    """Create a multilingual deterministic question specification."""
    return AyushQuestion(
        id=f"ayush.{section.value}.{number}",
        field_id=field_id,
        section=section,
        text=text,
        translations={
            "hi": hi,
            "bn": bn,
            "mr": mr,
        },
        order=number,
    )


# ---------------------------------------------------------------------------
# Multilingual AYUSH question bank
# ---------------------------------------------------------------------------
#
# English is the canonical source text.
# Hindi, Bengali and Marathi translations preserve AYUSH terminology where
# appropriate so that clinical/domain terms remain recognizable.
#
# The questions deliberately ask for history rather than making clinical
# interpretations. The existing adaptive-questioning module decides when
# an available question should actually be presented.
# ---------------------------------------------------------------------------

AYUSH_QUESTIONS: Final[tuple[AyushQuestion, ...]] = (
    _question(
        1,
        AyushField.PRAKRITI.value,
        AyushSection.DASHAVIDHA_PARIKSHA,
        "Please describe the person's usual body constitution or Prakriti, "
        "if this has previously been assessed.",
        hi=(
            "कृपया व्यक्ति की सामान्य शारीरिक प्रकृति या प्रकृति "
            "(Prakriti) का वर्णन करें, यदि इसका पहले आकलन किया गया है।"
        ),
        bn=(
            "ব্যক্তির স্বাভাবিক শারীরিক গঠন বা প্রকৃতি (Prakriti) সম্পর্কে "
            "বর্ণনা করুন, যদি এটি আগে মূল্যায়ন করা হয়ে থাকে।"
        ),
        mr=(
            "व्यक्तीची नेहमीची शारीरिक प्रकृती (Prakriti) कशी आहे ते "
            "सांगा, जर तिचे यापूर्वी मूल्यांकन केले गेले असेल."
        ),
    ),
    _question(
        2,
        AyushField.VIKRITI.value,
        AyushSection.DASHAVIDHA_PARIKSHA,
        "Please describe any current changes from the person's usual state "
        "that have been observed or previously assessed.",
        hi=(
            "व्यक्ति की सामान्य स्थिति में वर्तमान में देखे गए या पहले "
            "आकलन किए गए किसी भी बदलाव का वर्णन करें।"
        ),
        bn=(
            "ব্যক্তির স্বাভাবিক অবস্থার তুলনায় বর্তমানে দেখা দেওয়া বা আগে "
            "মূল্যায়ন করা হয়েছে এমন কোনো পরিবর্তন সম্পর্কে বর্ণনা করুন।"
        ),
        mr=(
            "व्यक्तीच्या नेहमीच्या स्थितीपेक्षा सध्या दिसून येणारे किंवा "
            "पूर्वी मूल्यांकन केलेले कोणतेही बदल सांगा."
        ),
    ),
    _question(
        3,
        AyushField.SARA.value,
        AyushSection.DASHAVIDHA_PARIKSHA,
        "Please provide the available assessment of Sara or tissue quality, "
        "if previously assessed.",
        hi=(
            "यदि पहले आकलन किया गया है, तो सारा (Sara) या ऊतक की गुणवत्ता "
            "से संबंधित उपलब्ध आकलन बताएं।"
        ),
        bn=(
            "যদি আগে মূল্যায়ন করা হয়ে থাকে, তাহলে সারা (Sara) বা "
            "টিস্যুর গুণমান সম্পর্কে উপলব্ধ মূল্যায়ন জানান।"
        ),
        mr=(
            "यापूर्वी मूल्यांकन केले असल्यास, सारा (Sara) किंवा ऊतकांच्या "
            "गुणवत्तेबाबत उपलब्ध मूल्यांकन सांगा."
        ),
    ),
    _question(
        4,
        AyushField.SAMHANANA.value,
        AyushSection.DASHAVIDHA_PARIKSHA,
        "Please provide the available assessment of Samhanana or body "
        "compactness, if previously assessed.",
        hi=(
            "यदि पहले आकलन किया गया है, तो संहनन (Samhanana) या शरीर की "
            "संघटनात्मक दृढ़ता से संबंधित उपलब्ध आकलन बताएं।"
        ),
        bn=(
            "যদি আগে মূল্যায়ন করা হয়ে থাকে, তাহলে সংহনন (Samhanana) বা "
            "শরীরের গঠনগত দৃঢ়তা সম্পর্কে উপলব্ধ মূল্যায়ন জানান।"
        ),
        mr=(
            "यापूर्वी मूल्यांकन केले असल्यास, संहनन (Samhanana) किंवा "
            "शरीराच्या बांध्याच्या घट्टपणाबाबत उपलब्ध मूल्यांकन सांगा."
        ),
    ),
    _question(
        5,
        AyushField.PRAMANA.value,
        AyushSection.DASHAVIDHA_PARIKSHA,
        "Please provide the available Pramana or body measurement "
        "information, if previously assessed.",
        hi=(
            "यदि पहले आकलन किया गया है, तो प्रमाण (Pramana) या शरीर के "
            "माप से संबंधित उपलब्ध जानकारी बताएं।"
        ),
        bn=(
            "যদি আগে মূল্যায়ন করা হয়ে থাকে, তাহলে প্রমাণ (Pramana) বা "
            "শরীরের পরিমাপ সম্পর্কিত উপলব্ধ তথ্য জানান।"
        ),
        mr=(
            "यापूर्वी मूल्यांकन केले असल्यास, प्रमाण (Pramana) किंवा "
            "शरीराच्या मोजमापाबाबत उपलब्ध माहिती सांगा."
        ),
    ),
    _question(
        6,
        AyushField.SATMYA.value,
        AyushSection.DASHAVIDHA_PARIKSHA,
        "Please describe Satmya, including substances, foods, or routines "
        "that the person is accustomed to or tolerates well.",
        hi=(
            "सात्म्य (Satmya) का वर्णन करें, जिसमें वे पदार्थ, खाद्य पदार्थ "
            "या दिनचर्याएं शामिल हों जिनका व्यक्ति अभ्यस्त है या जिन्हें "
            "वह अच्छी तरह सहन करता है।"
        ),
        bn=(
            "সাত্ম্য (Satmya) সম্পর্কে বর্ণনা করুন। ব্যক্তি যে উপাদান, "
            "খাবার বা দৈনন্দিন অভ্যাসে অভ্যস্ত বা যেগুলো ভালোভাবে সহ্য করেন, "
            "সেগুলো উল্লেখ করুন।"
        ),
        mr=(
            "सात्म्य (Satmya) बद्दल सांगा. व्यक्तीला सवयीचे असलेले किंवा "
            "ज्यांचे तो/ती चांगल्या प्रकारे सहन करते असे पदार्थ, अन्न किंवा "
            "दिनचर्या यांचा समावेश करा."
        ),
    ),
    _question(
        7,
        AyushField.SATTVA.value,
        AyushSection.DASHAVIDHA_PARIKSHA,
        "Please describe the available assessment of Sattva or mental "
        "strength, if previously assessed.",
        hi=(
            "यदि पहले आकलन किया गया है, तो सत्त्व (Sattva) या मानसिक "
            "सामर्थ्य से संबंधित उपलब्ध आकलन बताएं।"
        ),
        bn=(
            "যদি আগে মূল্যায়ন করা হয়ে থাকে, তাহলে সত্ত্ব (Sattva) বা "
            "মানসিক শক্তি সম্পর্কে উপলব্ধ মূল্যায়ন জানান।"
        ),
        mr=(
            "यापूर्वी मूल्यांकन केले असल्यास, सत्त्व (Sattva) किंवा "
            "मानसिक सामर्थ्याबाबत उपलब्ध मूल्यांकन सांगा."
        ),
    ),
    _question(
        8,
        AyushField.AHARA_SHAKTI.value,
        AyushSection.DASHAVIDHA_PARIKSHA,
        "Please describe the person's usual Ahara Shakti or capacity "
        "related to food intake and digestion, based on history.",
        hi=(
            "इतिहास के आधार पर व्यक्ति की सामान्य आहार शक्ति (Ahara Shakti) "
            "या भोजन ग्रहण और पाचन से संबंधित क्षमता का वर्णन करें।"
        ),
        bn=(
            "ইতিহাসের ভিত্তিতে ব্যক্তির স্বাভাবিক আহার শক্তি (Ahara Shakti) "
            "বা খাদ্য গ্রহণ ও হজমের সঙ্গে সম্পর্কিত সক্ষমতা সম্পর্কে বলুন।"
        ),
        mr=(
            "इतिहासाच्या आधारे व्यक्तीची नेहमीची आहार शक्ती (Ahara Shakti) "
            "किंवा अन्न सेवन व पचनाशी संबंधित क्षमता सांगा."
        ),
    ),
    _question(
        9,
        AyushField.VYAYAMA_SHAKTI.value,
        AyushSection.DASHAVIDHA_PARIKSHA,
        "Please describe the person's usual Vyayama Shakti or exercise "
        "capacity.",
        hi=(
            "कृपया व्यक्ति की सामान्य व्यायाम शक्ति (Vyayama Shakti) या "
            "व्यायाम करने की क्षमता का वर्णन करें।"
        ),
        bn=(
            "ব্যক্তির স্বাভাবিক ব্যায়াম শক্তি (Vyayama Shakti) বা "
            "ব্যায়াম করার সক্ষমতা সম্পর্কে বর্ণনা করুন।"
        ),
        mr=(
            "व्यक्तीची नेहमीची व्यायाम शक्ती (Vyayama Shakti) किंवा "
            "व्यायाम करण्याची क्षमता सांगा."
        ),
    ),
    _question(
        10,
        AyushField.VAYA.value,
        AyushSection.DASHAVIDHA_PARIKSHA,
        "What is the person's age or Vaya?",
        hi="व्यक्ति की आयु या वय (Vaya) क्या है?",
        bn="ব্যক্তির বয়স বা বয় (Vaya) কত?",
        mr="व्यक्तीचे वय किंवा वय (Vaya) किती आहे?",
    ),
    _question(
        11,
        AyushField.AHARA_PATTERN.value,
        AyushSection.AHARA,
        "Please describe the person's usual food and eating pattern.",
        hi="कृपया व्यक्ति के सामान्य भोजन और खाने के तरीके का वर्णन करें।",
        bn="ব্যক্তির স্বাভাবিক খাবার এবং খাওয়ার ধরন সম্পর্কে বর্ণনা করুন।",
        mr="कृपया व्यक्तीच्या नेहमीच्या आहार आणि खाण्याच्या पद्धतीचे वर्णन करा.",
    ),
    _question(
        12,
        AyushField.AHARA_TIMING.value,
        AyushSection.AHARA,
        "What is the usual timing and regularity of meals?",
        hi="भोजन का सामान्य समय और नियमितता कैसी है?",
        bn="সাধারণত খাবারের সময় এবং নিয়মিততা কেমন?",
        mr="जेवणाची नेहमीची वेळ आणि नियमितता कशी आहे?",
    ),
    _question(
        13,
        AyushField.AHARA_APPETITE.value,
        AyushSection.AHARA,
        "How would you describe the person's usual appetite?",
        hi="आप व्यक्ति की सामान्य भूख का वर्णन कैसे करेंगे?",
        bn="ব্যক্তির স্বাভাবিক ক্ষুধা কীভাবে বর্ণনা করবেন?",
        mr="व्यक्तीची नेहमीची भूक तुम्ही कशी वर्णन कराल?",
    ),
    _question(
        14,
        AyushField.AHARA_TOLERANCE.value,
        AyushSection.AHARA,
        "Are there foods that the person does not tolerate or that commonly "
        "cause discomfort?",
        hi=(
            "क्या ऐसे खाद्य पदार्थ हैं जिन्हें व्यक्ति सहन नहीं करता या "
            "जिनसे आमतौर पर असुविधा होती है?"
        ),
        bn=(
            "এমন কোনো খাবার আছে কি যা ব্যক্তি সহ্য করতে পারেন না বা যা "
            "সাধারণত অস্বস্তি সৃষ্টি করে?"
        ),
        mr=(
            "अशी काही अन्नपदार्थ आहेत का जे व्यक्तीला सहन होत नाहीत किंवा "
            "ज्यामुळे नेहमी त्रास होतो?"
        ),
    ),
    _question(
        15,
        AyushField.AHARA_PREFERENCES.value,
        AyushSection.AHARA,
        "Are there any important dietary preferences, restrictions, or "
        "usual food choices to record?",
        hi=(
            "क्या कोई महत्वपूर्ण आहार संबंधी पसंद, प्रतिबंध या सामान्य "
            "खाद्य विकल्प दर्ज करने हैं?"
        ),
        bn=(
            "কোনো গুরুত্বপূর্ণ খাদ্য পছন্দ, বিধিনিষেধ বা সাধারণ খাবারের "
            "পছন্দ কি নথিভুক্ত করা দরকার?"
        ),
        mr=(
            "नोंद करण्यासारख्या काही महत्त्वाच्या आहारविषयक आवडी, "
            "मर्यादा किंवा नेहमीच्या खाद्य निवडी आहेत का?"
        ),
    ),
    _question(
        16,
        AyushField.VIHARA_SLEEP.value,
        AyushSection.VIHARA,
        "Please describe the person's usual sleep pattern and sleep quality.",
        hi="कृपया व्यक्ति की सामान्य नींद की दिनचर्या और नींद की गुणवत्ता का वर्णन करें।",
        bn="ব্যক্তির স্বাভাবিক ঘুমের ধরন এবং ঘুমের মান সম্পর্কে বর্ণনা করুন।",
        mr="कृपया व्यक्तीच्या नेहमीच्या झोपेची पद्धत आणि झोपेची गुणवत्ता सांगा.",
    ),
    _question(
        17,
        AyushField.VIHARA_ACTIVITY.value,
        AyushSection.VIHARA,
        "Please describe the person's usual daily physical activity.",
        hi="कृपया व्यक्ति की सामान्य दैनिक शारीरिक गतिविधि का वर्णन करें।",
        bn="ব্যক্তির স্বাভাবিক দৈনিক শারীরিক কার্যকলাপ সম্পর্কে বর্ণনা করুন।",
        mr="कृपया व्यक्तीच्या नेहमीच्या दैनंदिन शारीरिक हालचालींचे वर्णन करा.",
    ),
    _question(
        18,
        AyushField.VIHARA_EXERCISE.value,
        AyushSection.VIHARA,
        "Please describe the person's usual exercise or physical activity "
        "routine.",
        hi=(
            "कृपया व्यक्ति की सामान्य व्यायाम या शारीरिक गतिविधि की "
            "दिनचर्या का वर्णन करें।"
        ),
        bn=(
            "ব্যক্তির স্বাভাবিক ব্যায়াম বা শারীরিক কার্যকলাপের রুটিন "
            "সম্পর্কে বর্ণনা করুন।"
        ),
        mr=(
            "कृपया व्यक्तीच्या नेहमीच्या व्यायाम किंवा शारीरिक "
            "हालचालींच्या दिनचर्येचे वर्णन करा."
        ),
    ),
    _question(
        19,
        AyushField.VIHARA_DAILY_ROUTINE.value,
        AyushSection.VIHARA,
        "Please describe the person's usual daily routine.",
        hi="कृपया व्यक्ति की सामान्य दैनिक दिनचर्या का वर्णन करें।",
        bn="ব্যক্তির স্বাভাবিক দৈনন্দিন রুটিন সম্পর্কে বর্ণনা করুন।",
        mr="कृपया व्यक्तीच्या नेहमीच्या दैनंदिन दिनचर्येचे वर्णन करा.",
    ),
    _question(
        20,
        AyushField.VIHARA_STRESS.value,
        AyushSection.VIHARA,
        "Please describe any relevant stress, workload, or routine-related "
        "factors.",
        hi=(
            "कृपया किसी भी प्रासंगिक तनाव, कार्यभार या दिनचर्या से संबंधित "
            "कारकों का वर्णन करें।"
        ),
        bn=(
            "প্রাসঙ্গিক মানসিক চাপ, কাজের চাপ বা দৈনন্দিন রুটিন সম্পর্কিত "
            "কোনো বিষয় সম্পর্কে বর্ণনা করুন।"
        ),
        mr=(
            "कृपया संबंधित ताण, कामाचा भार किंवा दिनचर्येशी संबंधित "
            "घटकांबद्दल सांगा."
        ),
    ),
)


class AyushMode:
    """
    Thin AYUSH domain adapter for the existing conversation system.

    This class does not own dialogue management. It exposes AYUSH fields
    and deterministic question specifications so that the existing
    Question Bank, Dialogue State, and Adaptive Questioning components
    can continue to own conversation behavior.
    """

    mode: Final[str] = "ayush"

    def __init__(
        self,
        *,
        include_general_history: bool = True,
    ) -> None:
        self.include_general_history = include_general_history
        self._values: dict[str, Any] = {}

    @property
    def fields(self) -> tuple[str, ...]:
        """Return the AYUSH fields collected by this mode."""
        fields = AYUSH_FIELDS

        if self.include_general_history:
            return fields + GENERAL_FIELDS

        return fields

    @property
    def dashavidha_fields(self) -> tuple[str, ...]:
        """Return the ten Dashavidha Pariksha fields."""
        return DASHAVIDHA_FIELDS

    @property
    def ahara_fields(self) -> tuple[str, ...]:
        """Return AYUSH Ahara fields."""
        return AHARA_FIELDS

    @property
    def vihara_fields(self) -> tuple[str, ...]:
        """Return AYUSH Vihara fields."""
        return VIHARA_FIELDS

    @property
    def general_history_fields(self) -> tuple[str, ...]:
        """Return general history fields included in AYUSH mode."""
        return GENERAL_FIELDS if self.include_general_history else ()

    def is_ayush(self) -> bool:
        """Return True when this mode represents AYUSH consultation."""
        return self.mode == "ayush"

    def questions(
        self,
        *,
        section: AyushSection | None = None,
    ) -> tuple[AyushQuestion, ...]:
        """
        Return deterministic AYUSH question specifications.

        This does not select the next question. The existing adaptive
        questioning component should perform that responsibility.
        """
        questions = AYUSH_QUESTIONS

        if section is None:
            return questions

        return tuple(
            question
            for question in questions
            if question.section == section
        )

    def get_question(self, question_id: str) -> AyushQuestion:
        """Return a question by ID or raise ValueError."""
        for question in AYUSH_QUESTIONS:
            if question.id == question_id:
                return question

        raise ValueError(f"Unknown AYUSH question: {question_id!r}")

    def get_question_text(
        self,
        question_id: str,
        language: str = "en",
    ) -> str:
        """
        Return a localized question text by question ID.

        Falls back to English when the requested language is unsupported
        or when a translation is unavailable.
        """
        question = self.get_question(question_id)
        return question.text_for(language)

    def validate_field(self, field_id: str) -> str:
        """
        Validate and return an AYUSH field identifier.

        Raises:
            ValueError: if the field is not part of this mode.
        """
        if field_id not in self.fields:
            raise ValueError(f"Unknown AYUSH field: {field_id!r}")

        return field_id

    def update_field(self, field_id: str, value: Any) -> None:
        """
        Store a structured AYUSH field value.

        The latest valid structured value replaces the previous value.
        No inference is performed.
        """
        self.validate_field(field_id)

        if value is None:
            raise ValueError("AYUSH field value cannot be None.")

        if isinstance(value, str) and not value.strip():
            raise ValueError("AYUSH field value cannot be empty.")

        self._values[field_id] = value

    def update(self, field: AyushFieldValue) -> None:
        """Update state using a validated AYUSH field-value object."""
        self.update_field(field.field_id, field.value)

    def get_field(self, field_id: str) -> Any | None:
        """Return a collected field value, or None when not collected."""
        self.validate_field(field_id)
        return self._values.get(field_id)

    def has_field(self, field_id: str) -> bool:
        """Return whether a valid field has been collected."""
        self.validate_field(field_id)
        return field_id in self._values

    def collected_fields(self) -> tuple[str, ...]:
        """Return collected field IDs in deterministic schema order."""
        return tuple(
            field_id
            for field_id in self.fields
            if field_id in self._values
        )

    def missing_fields(self) -> tuple[str, ...]:
        """Return missing field IDs in deterministic schema order."""
        return tuple(
            field_id
            for field_id in self.fields
            if field_id not in self._values
        )

    def progress(self) -> AyushProgress:
        """Calculate deterministic AYUSH collection progress."""
        total = len(self.fields)
        collected = len(self.collected_fields())
        remaining = total - collected

        percentage = (
            0.0
            if total == 0
            else (collected / total) * 100.0
        )

        return AyushProgress(
            total_fields=total,
            collected_fields=collected,
            remaining_fields=remaining,
            percentage=round(percentage, 2),
            completed=remaining == 0,
        )

    def is_complete(self) -> bool:
        """Return True when every configured field has been collected."""
        return self.progress().completed

    def state(self) -> AyushModeState:
        """Return a serializable snapshot of the AYUSH state."""
        return AyushModeState(
            mode=self.mode,
            values=dict(self._values),
        )

    def collected_information(self) -> Mapping[str, Any]:
        """Return collected information without exposing mutable state."""
        return dict(self._values)

    def reset(self) -> None:
        """Clear collected AYUSH information."""
        self._values.clear()


def create_ayush_mode(
    *,
    include_general_history: bool = True,
) -> AyushMode:
    """
    Create an AYUSH mode instance.

    Backend integration can use this as the explicit mode factory:

        mode = create_ayush_mode()

    The returned object is then passed through the existing conversation
    infrastructure.
    """
    return AyushMode(
        include_general_history=include_general_history,
    )


def is_ayush_mode(mode: str) -> bool:
    """Return True when a backend mode value requests AYUSH."""
    return mode.strip().lower() == "ayush"