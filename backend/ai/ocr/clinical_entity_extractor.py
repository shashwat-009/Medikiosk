"""
MediSetu Clinical Entity Extractor

Consumes REAL OCR output from PaddleOCR.

The extractor is layout-aware and uses OCR coordinates to reconstruct
clinical tables such as medication and laboratory tables.

Expected OCR item:
{
    "text": "...",
    "confidence": 0.99,
    "bbox": {
        "x": 100,
        "y": 200,
        "width": 100,
        "height": 20
    },
    "x": 100,
    "y": 200,
    "width": 100,
    "height": 20
}
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# ============================================================================
# PATTERNS
# ============================================================================

DATE_PATTERN = re.compile(
    r"\b\d{1,2}\s+"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{4}\b",
    re.IGNORECASE,
)

DOSAGE_PATTERN = re.compile(
    r"^\s*\d+(?:\.\d+)?\s*"
    r"(?:mg|mcg|g|kg|ml|mL|IU|units?|sachet|tablet|tablets|"
    r"capsule|capsules)\s*$",
    re.IGNORECASE,
)

DURATION_PATTERN = re.compile(
    r"^\s*\d+(?:\.\d+)?\s*"
    r"(?:day|days|week|weeks|month|months|hour|hours)\s*$",
    re.IGNORECASE,
)

REFERENCE_RANGE_PATTERN = re.compile(
    r"^\s*\d[\d,]*(?:\.\d+)?\s*[-–—]\s*\d[\d,]*(?:\.\d+)?\s*$"
)

NUMERIC_PATTERN = re.compile(
    r"^\s*\d[\d,]*(?:\.\d+)?\s*$"
)

UNIT_PATTERN = re.compile(
    r"^\s*(?:"
    r"g/dl|mg/dl|mg/l|g/l|u/l|iu/l|"
    r"/μl|/ul|%|mmol/l|meq/l|ng/ml|pg/ml|fl|"
    r"bpm|mmhg|cm|kg|ml|mg|g"
    r")\s*$",
    re.IGNORECASE,
)


# ============================================================================
# MEDICATION VALUES
# ============================================================================

ROUTE_VALUES = {
    "oral",
    "intravenous",
    "iv",
    "intramuscular",
    "im",
    "subcutaneous",
    "sc",
    "topical",
    "sublingual",
    "inhaled",
    "rectal",
    "nasal",
    "ophthalmic",
    "otic",
}

FREQUENCY_PATTERNS = (
    "once daily",
    "twice daily",
    "three times daily",
    "four times daily",
    "thrice daily",
    "once a day",
    "twice a day",
    "three times a day",
    "every morning",
    "every night",
    "at night",
    "as needed",
    "prn",
)


# ============================================================================
# NON-MEDICATION CLINICAL HEADERS
# ============================================================================

MEDICATION_STOP_HEADERS = {
    "allergies",
    "drug allergies",
    "allergy",
    "advice",
    "discharge advice",
    "follow-up",
    "follow up",
    "red-flag advice",
    "red flag advice",
    "red flags",
    "doctor",
    "hospital",
    "laboratory",
    "laboratory comment",
    "important",
}


MEDICATION_TABLE_HEADERS = {
    "medicine",
    "medication",
    "medications",
    "dose",
    "dosage",
    "route",
    "frequency",
    "duration",
}


# ============================================================================
# LAB NAME NORMALIZATION
# ============================================================================

LAB_ALIASES = {
    "hemoglobin": "Hemoglobin",
    "haemoglobin": "Hemoglobin",
    "hb": "Hemoglobin",
    "wbc count": "WBC Count",
    "wbc": "WBC Count",
    "white blood cell count": "WBC Count",
    "white blood cells": "WBC Count",
    "platelet count": "Platelet Count",
    "platelets": "Platelet Count",
    "neutrophils": "Neutrophils",
    "lymphocytes": "Lymphocytes",
    "crp": "CRP",
    "creatinine": "Creatinine",
    "alt": "ALT",
    "ast": "AST",
    "bilirubin": "Bilirubin",
    "glucose": "Glucose",
    "hba1c": "HbA1c",
    "sodium": "Sodium",
    "potassium": "Potassium",
    "urea": "Urea",
    "tsh": "TSH",
    "t3": "T3",
    "t4": "T4",
}


# ============================================================================
# BASIC HELPERS
# ============================================================================

def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip()

    replacements = {
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return re.sub(r"\s+", " ", text).strip()


def clean_value(value: Optional[str]) -> Optional[str]:
    value = normalize_text(value)

    if not value:
        return None

    return value


# ============================================================================
# OCR NORMALIZATION
# ============================================================================

def normalize_ocr_results(
    ocr_results: Any,
) -> List[Dict[str, Any]]:
    """
    Normalize actual PaddleOCR output.

    Preferred input:
        page["ocr_text"]

    Also accepts:
        {"ocr_text": [...]}
        {"results": [...]}
        plain text as a fallback.

    IMPORTANT:
    When structured OCR items are supplied, their coordinates are preserved.
    """

    if isinstance(ocr_results, dict):

        if isinstance(ocr_results.get("ocr_text"), list):
            ocr_results = ocr_results["ocr_text"]

        elif isinstance(ocr_results.get("results"), list):
            ocr_results = ocr_results["results"]

        elif isinstance(ocr_results.get("text"), str):
            ocr_results = ocr_results["text"]

    # ------------------------------------------------------------------------
    # Plain-text fallback
    # ------------------------------------------------------------------------

    if isinstance(ocr_results, str):

        output = []

        for index, line in enumerate(
            ocr_results.splitlines()
        ):

            text = normalize_text(line)

            if not text:
                continue

            output.append(
                {
                    "text": text,
                    "confidence": 1.0,
                    "x": 0.0,
                    "y": float(index * 30),
                    "width": float(
                        max(len(text) * 8, 1)
                    ),
                    "height": 20.0,
                }
            )

        return output

    if not isinstance(ocr_results, list):
        return []

    output = []

    for item in ocr_results:

        if not isinstance(item, dict):
            continue

        text = normalize_text(
            item.get("text")
        )

        if not text:
            continue

        bbox = item.get("bbox") or {}

        def number(
            direct_key: str,
            bbox_key: str,
            default: float = 0.0,
        ) -> float:

            value = item.get(
                direct_key,
                bbox.get(
                    bbox_key,
                    default,
                ),
            )

            try:
                return float(value)
            except (
                TypeError,
                ValueError,
            ):
                return default

        output.append(
            {
                "text": text,
                "confidence": number(
                    "confidence",
                    "confidence",
                    1.0,
                ),
                "x": number("x", "x"),
                "y": number("y", "y"),
                "width": number(
                    "width",
                    "width",
                ),
                "height": number(
                    "height",
                    "height",
                ),
            }
        )

    return output


def ocr_to_text(
    ocr_results: Any,
) -> str:

    items = normalize_ocr_results(
        ocr_results
    )

    return "\n".join(
        item["text"]
        for item in items
    )


# ============================================================================
# HEADER NORMALIZATION
# ============================================================================

def normalize_header(
    text: str,
) -> str:
    """
    Normalize a clinical section/header.

    Examples:
        "Allergies" -> "allergies"
        "Allergies: No known drug allergies" -> "allergies"
        "Follow-up: Review after 5 days." -> "follow-up"
    """

    text = normalize_text(
        text
    ).lower()

    if ":" in text:
        text = text.split(
            ":",
            1,
        )[0]

    text = text.strip()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.rstrip(":")


# ============================================================================
# PATIENT
# ============================================================================

def extract_patient(
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:

    patient = {
        "name": None,
        "patient_id": None,
        "hospital_id": None,
        "age": None,
        "sex": None,
    }

    for item in items:

        text = item["text"]

        match = re.search(
            r"Patient\s+Name\s*:\s*(.+)",
            text,
            re.IGNORECASE,
        )

        if match:
            patient["name"] = normalize_text(
                match.group(1)
            )

        match = re.search(
            r"Patient\s+ID\s*:\s*(.+)",
            text,
            re.IGNORECASE,
        )

        if match:
            patient["patient_id"] = normalize_text(
                match.group(1)
            )

        match = re.search(
            r"Hospital\s+ID\s*:\s*(.+)",
            text,
            re.IGNORECASE,
        )

        if match:
            patient["hospital_id"] = normalize_text(
                match.group(1)
            )

        match = re.search(
            r"Age\s*/\s*Sex\s*:\s*"
            r"(\d+)\s*(?:years?|yrs?)?\s*/\s*"
            r"([A-Za-z]+)",
            text,
            re.IGNORECASE,
        )

        if match:
            patient["age"] = int(
                match.group(1)
            )

            patient["sex"] = normalize_text(
                match.group(2)
            )

    return patient


# ============================================================================
# DIAGNOSIS
# ============================================================================

def extract_diagnoses(
    items: List[Dict[str, Any]],
) -> List[str]:

    diagnoses = []

    headers = {
        "diagnosis",
        "diagnoses",
        "final diagnosis",
        "impression",
        "clinical impression",
    }

    stop_headers = {
        "medications",
        "medication",
        "discharge medications",
        "procedures",
        "procedure",
        "hospital course",
        "discharge advice",
        "follow-up",
        "follow up",
        "drug allergies",
    }

    for index, item in enumerate(items):

        text = item["text"]

        inline = re.match(
            r"^(?:Diagnosis|Final Diagnosis|Impression|"
            r"Clinical Impression)\s*:\s*(.+)$",
            text,
            re.IGNORECASE,
        )

        if inline:

            diagnosis = normalize_text(
                inline.group(1)
            ).rstrip(".")

            if (
                diagnosis
                and diagnosis not in diagnoses
            ):
                diagnoses.append(
                    diagnosis
                )

            continue

        normalized = normalize_header(
            text
        )

        if normalized not in headers:
            continue

        header_y = item["y"]

        for candidate in items[index + 1:]:

            if candidate["y"] <= header_y:
                continue

            if (
                candidate["y"] - header_y
                > 100
            ):
                break

            candidate_header = normalize_header(
                candidate["text"]
            )

            if candidate_header in headers:
                continue

            if candidate_header in stop_headers:
                break

            diagnosis = normalize_text(
                candidate["text"]
            ).rstrip(".")

            if (
                diagnosis
                and diagnosis not in diagnoses
            ):
                diagnoses.append(
                    diagnosis
                )

            break

    return diagnoses


# ============================================================================
# ROW GROUPING
# ============================================================================

def group_rows(
    items: List[Dict[str, Any]],
    tolerance: float = 14.0,
) -> List[List[Dict[str, Any]]]:
    """
    Group OCR boxes into visual rows using their Y coordinates.
    """

    sorted_items = sorted(
        items,
        key=lambda item: (
            item["y"],
            item["x"],
        ),
    )

    rows: List[List[Dict[str, Any]]] = []

    for item in sorted_items:

        center_y = (
            item["y"]
            + item["height"] / 2
        )

        matched = False

        for row in rows:

            row_center = sum(
                current["y"]
                + current["height"] / 2
                for current in row
            ) / len(row)

            if (
                abs(
                    center_y
                    - row_center
                )
                <= tolerance
            ):
                row.append(item)
                matched = True
                break

        if not matched:
            rows.append([item])

    for row in rows:
        row.sort(
            key=lambda item: item["x"]
        )

    return rows


# ============================================================================
# MEDICATION HELPERS
# ============================================================================

def is_dosage(
    text: str,
) -> bool:

    return bool(
        DOSAGE_PATTERN.match(
            normalize_text(text)
        )
    )


def is_duration(
    text: str,
) -> bool:

    return bool(
        DURATION_PATTERN.match(
            normalize_text(text)
        )
    )


def is_route(
    text: str,
) -> bool:

    return (
        normalize_text(text).lower()
        in ROUTE_VALUES
    )


def is_frequency(
    text: str,
) -> bool:

    lowered = normalize_text(
        text
    ).lower()

    return any(
        pattern in lowered
        for pattern in FREQUENCY_PATTERNS
    )


def looks_like_medication_name(
    text: str,
) -> bool:
    """
    Reject obvious non-medication content.

    This is deliberately conservative so that prose such as:
        Allergies: No known drug allergies
        Advice: Adequate oral fluids...
        Follow-up: Review after 5 days
    is never treated as a medicine.
    """

    text = normalize_text(
        text
    )

    if not text:
        return False

    lowered = text.lower()

    # ------------------------------------------------------------------------
    # Explicit exclusions
    # ------------------------------------------------------------------------

    excluded_exact = (
        MEDICATION_TABLE_HEADERS
        | MEDICATION_STOP_HEADERS
        | {
            "oral",
            "intravenous",
            "iv",
            "normal",
            "high",
            "low",
            "status",
            "result",
            "reference range",
            "investigation",
        }
    )

    if lowered in excluded_exact:
        return False

    # ------------------------------------------------------------------------
    # Clinical prose / section labels
    # ------------------------------------------------------------------------

    clinical_prefixes = (
        "allergies:",
        "drug allergies:",
        "advice:",
        "discharge advice:",
        "follow-up:",
        "follow up:",
        "red-flag advice:",
        "red flag advice:",
        "important:",
        "laboratory comment:",
        "doctor:",
        "hospital:",
    )

    if lowered.startswith(
        clinical_prefixes
    ):
        return False

    # ------------------------------------------------------------------------
    # Punctuation-heavy prose is unlikely to be a medicine name.
    # ------------------------------------------------------------------------

    if ":" in text:
        return False

    if text.endswith("."):
        return False

    # ------------------------------------------------------------------------
    # Structured non-name values
    # ------------------------------------------------------------------------

    if is_dosage(text):
        return False

    if is_duration(text):
        return False

    if is_route(text):
        return False

    if is_frequency(text):
        return False

    if NUMERIC_PATTERN.match(text):
        return False

    if REFERENCE_RANGE_PATTERN.match(text):
        return False

    if UNIT_PATTERN.match(text):
        return False

    # ------------------------------------------------------------------------
    # Sentence-like prose
    # ------------------------------------------------------------------------

    words = text.split()

    if len(words) > 4:
        return False

    # Medication names can contain letters, digits, hyphens, etc.
    return bool(
        re.search(
            r"[A-Za-z]",
            text,
        )
    )


# ============================================================================
# SECTION FINDER
# ============================================================================

def find_section(
    items: List[Dict[str, Any]],
    start_headers: List[str],
    end_headers: List[str],
) -> List[Dict[str, Any]]:
    """
    Find a section using normalized header matching.

    Handles both:
        "Allergies"
        "Allergies: No known drug allergies."

    The latter is normalized to:
        "allergies"
    """

    normalized_start = {
        normalize_header(header)
        for header in start_headers
    }

    normalized_end = {
        normalize_header(header)
        for header in end_headers
    }

    start_index = -1

    for index, item in enumerate(items):

        header = normalize_header(
            item["text"]
        )

        if header in normalized_start:
            start_index = index
            break

    if start_index == -1:
        return []

    end_index = len(items)

    for index in range(
        start_index + 1,
        len(items),
    ):

        header = normalize_header(
            items[index]["text"]
        )

        if header in normalized_end:
            end_index = index
            break

    return items[
        start_index:end_index
    ]


# ============================================================================
# MEDICATION EXTRACTION
# ============================================================================

def extract_medications(
    items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Extract medication tables using OCR coordinates.

    Supports layouts such as:

        Medicine | Dosage | Route | Frequency | Duration

    and:

        Medication | Dose | Frequency | Duration
    """

    section = find_section(
        items,
        start_headers=[
            "Medications",
            "Discharge Medications",
        ],
        end_headers=[
            "Allergies",
            "Drug Allergies",
            "Advice",
            "Discharge Advice",
            "Follow-up",
            "Follow Up",
            "Red-flag advice",
            "Red Flag Advice",
        ],
    )

    if not section:
        return []

    # ------------------------------------------------------------------------
    # Locate table headers.
    # ------------------------------------------------------------------------

    headers: Dict[str, float] = {}

    for item in section:

        header = normalize_header(
            item["text"]
        )

        if header in {
            "medicine",
            "medication",
        }:
            headers["name"] = item["x"]

        elif header in {
            "dosage",
            "dose",
        }:
            headers["dosage"] = item["x"]

        elif header == "route":
            headers["route"] = item["x"]

        elif header == "frequency":
            headers["frequency"] = item["x"]

        elif header == "duration":
            headers["duration"] = item["x"]

    if "name" not in headers:
        return []

    # ------------------------------------------------------------------------
    # Find the table header Y coordinate.
    # ------------------------------------------------------------------------

    header_y = None

    for item in section:

        header = normalize_header(
            item["text"]
        )

        if header in {
            "medicine",
            "medication",
        }:
            header_y = (
                item["y"]
                + item["height"] / 2
            )
            break

    if header_y is None:
        return []

    # ------------------------------------------------------------------------
    # Only process items below the table header.
    # ------------------------------------------------------------------------

    data = []

    for item in section:

        item_center_y = (
            item["y"]
            + item["height"] / 2
        )

        if item_center_y > header_y + 8:
            data.append(item)

    rows = group_rows(
        data,
        tolerance=16.0,
    )

    # ------------------------------------------------------------------------
    # Build column boundaries from header positions.
    #
    # We use midpoint boundaries between adjacent headers instead of simply
    # assigning every item to the nearest header. This prevents a long text
    # item from jumping into a neighboring column.
    # ------------------------------------------------------------------------

    ordered_columns = sorted(
        headers.items(),
        key=lambda pair: pair[1],
    )

    boundaries = []

    for index, (
        column_name,
        x_position,
    ) in enumerate(
        ordered_columns
    ):

        if index == 0:
            left = float("-inf")
        else:
            previous_x = ordered_columns[
                index - 1
            ][1]

            left = (
                previous_x
                + x_position
            ) / 2

        if index == len(
            ordered_columns
        ) - 1:
            right = float("inf")
        else:
            next_x = ordered_columns[
                index + 1
            ][1]

            right = (
                x_position
                + next_x
            ) / 2

        boundaries.append(
            (
                column_name,
                left,
                right,
            )
        )

    def get_column(
        x: float,
    ) -> Optional[str]:

        for (
            column_name,
            left,
            right,
        ) in boundaries:

            if left <= x < right:
                return column_name

        return None

    medications = []

    for row in rows:

        cells: Dict[str, str] = {}

        for item in row:

            column = get_column(
                item["x"]
            )

            if column is None:
                continue

            text = normalize_text(
                item["text"]
            )

            if not text:
                continue

            if column in cells:
                cells[column] = (
                    cells[column]
                    + " "
                    + text
                )
            else:
                cells[column] = text

        name = clean_value(
            cells.get("name")
        )

        if not name:
            continue

        if not looks_like_medication_name(
            name
        ):
            continue

        medication = {
            "name": name,
            "dosage": clean_value(
                cells.get("dosage")
            ),
            "route": clean_value(
                cells.get("route")
            ),
            "frequency": clean_value(
                cells.get("frequency")
            ),
            "duration": clean_value(
                cells.get("duration")
            ),
        }

        medications.append(
            medication
        )

    return deduplicate_medications(
        medications
    )


def deduplicate_medications(
    medications: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:

    output = []
    seen = set()

    for medication in medications:

        name = normalize_text(
            medication.get("name")
        )

        if not name:
            continue

        key = (
            name.lower(),
            normalize_text(
                medication.get("dosage")
            ).lower(),
            normalize_text(
                medication.get("frequency")
            ).lower(),
            normalize_text(
                medication.get("duration")
            ).lower(),
        )

        if key in seen:
            continue

        seen.add(key)
        output.append(
            medication
        )

    return output


# ============================================================================
# LAB HELPERS
# ============================================================================

def canonical_lab_name(
    text: str,
) -> Optional[str]:

    normalized = normalize_text(
        text
    ).lower()

    return LAB_ALIASES.get(
        normalized
    )


def extract_reference_numbers(
    reference_range: Optional[str],
) -> Optional[tuple[float, float]]:

    if not reference_range:
        return None

    match = re.match(
        r"^\s*"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*-\s*"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*$",
        reference_range,
    )

    if not match:
        return None

    try:
        return (
            float(match.group(1)),
            float(match.group(2)),
        )
    except ValueError:
        return None


def infer_lab_status(
    value: str,
    reference_range: Optional[str],
) -> Optional[str]:

    bounds = extract_reference_numbers(
        reference_range
    )

    if bounds is None:
        return None

    try:
        numeric_value = float(
            value.replace(",", "")
        )
    except (
        ValueError,
        TypeError,
    ):
        return None

    lower, upper = bounds

    if numeric_value > upper:
        return "high"

    if numeric_value < lower:
        return "low"

    return "normal"


def extract_laboratory_results(
    items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Extract laboratory rows using OCR coordinates.

    IMPORTANT:
    Lab names are on the LEFT side of the table.
    Result/unit/reference/status are on the RIGHT.

    Therefore candidates must NOT be restricted to:
        item["x"] < lab_x

    Instead, we examine the full horizontal row and classify the cells.
    """

    results = []

    lab_items = []

    for item in items:

        lab_name = canonical_lab_name(
            item["text"]
        )

        if lab_name:
            lab_items.append(
                (
                    item,
                    lab_name,
                )
            )

    # ------------------------------------------------------------------------
    # Process every recognized investigation.
    # ------------------------------------------------------------------------

    for lab_item, lab_name in lab_items:

        center_y = (
            lab_item["y"]
            + lab_item["height"] / 2
        )

        lab_x = lab_item["x"]

        candidates = []

        for item in items:

            if item is lab_item:
                continue

            item_center_y = (
                item["y"]
                + item["height"] / 2
            )

            # Same visual row.
            if abs(
                item_center_y
                - center_y
            ) <= 24:

                # IMPORTANT:
                # Include the full row, not x < lab_x.
                #
                # We only exclude OCR items that are clearly to the LEFT
                # of the investigation name. The actual result fields are
                # expected to be at or to the RIGHT of the lab name.
                if item["x"] >= lab_x:
                    candidates.append(
                        item
                    )

        candidates.sort(
            key=lambda item: item["x"]
        )

        value = None
        unit = None
        reference_range = None
        status = None

        # --------------------------------------------------------------------
        # Classify cells by content.
        # --------------------------------------------------------------------

        for item in candidates:

            text = normalize_text(
                item["text"]
            )

            lowered = text.lower()

            if lowered in {
                "high",
                "low",
                "normal",
            }:
                status = lowered
                continue

            if REFERENCE_RANGE_PATTERN.match(
                text
            ):
                reference_range = text
                continue

            if UNIT_PATTERN.match(
                text
            ):
                unit = text
                continue

            if NUMERIC_PATTERN.match(
                text
            ):

                if value is None:
                    value = text

        if value is None:
            continue

        if status is None:
            status = infer_lab_status(
                value,
                reference_range,
            )

        abnormal = status in {
            "high",
            "low",
        }

        results.append(
            {
                "name": lab_name,
                "value": value,
                "unit": unit,
                "reference_range": (
                    reference_range
                ),
                "status": status,
                "abnormal": abnormal,
                "risk_flag": (
                    "review_required"
                    if abnormal
                    else None
                ),
            }
        )

    return deduplicate_labs(
        results
    )


def deduplicate_labs(
    results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:

    output = []
    seen = set()

    for result in results:

        key = (
            normalize_text(
                result.get("name")
            ).lower(),
            normalize_text(
                result.get("value")
            ),
        )

        if key in seen:
            continue

        seen.add(key)
        output.append(
            result
        )

    return output


# ============================================================================
# PROCEDURES
# ============================================================================

def extract_procedures(
    items: List[Dict[str, Any]],
) -> List[str]:

    procedures = []

    for index, item in enumerate(items):

        header = normalize_header(
            item["text"]
        )

        if header not in {
            "procedure",
            "procedures",
        }:
            continue

        header_y = item["y"]

        for candidate in items[index + 1:]:

            if candidate["y"] <= header_y:
                continue

            if (
                candidate["y"] - header_y
                > 100
            ):
                break

            candidate_header = normalize_header(
                candidate["text"]
            )

            if candidate_header in {
                "discharge medications",
                "drug allergies",
                "discharge advice",
                "follow-up",
                "follow up",
            }:
                break

            procedure = normalize_text(
                candidate["text"]
            ).rstrip(".")

            if procedure:
                procedures.append(
                    procedure
                )

            break

    return list(
        dict.fromkeys(
            procedures
        )
    )


# ============================================================================
# DATES
# ============================================================================

def extract_dates(
    items: List[Dict[str, Any]],
) -> List[Dict[str, str]]:

    dates = []

    for item in items:

        text = item["text"]

        matches = DATE_PATTERN.findall(
            text
        )

        for date in matches:

            lowered = text.lower()

            if "sample date" in lowered:
                date_type = "sample_date"

            elif "report date" in lowered:
                date_type = "report_date"

            elif "admission date" in lowered:
                date_type = "admission_date"

            elif "discharge date" in lowered:
                date_type = "discharge_date"

            else:
                date_type = "date"

            entry = {
                "date": normalize_text(
                    date
                ),
                "type": date_type,
            }

            if entry not in dates:
                dates.append(
                    entry
                )

    return dates


# ============================================================================
# MAIN PUBLIC FUNCTION
# ============================================================================

def extract_clinical_entities(
    ocr_results: Any,
    document_type: str = "unknown",
) -> Dict[str, Any]:
    """
    Extract clinical entities from REAL OCR results.

    Preferred input:
        page["ocr_text"]

    Parameters
    ----------
    ocr_results:
        Structured OCR items containing text and coordinates.

    document_type:
        Output of document_classifier.py.
    """

    items = normalize_ocr_results(
        ocr_results
    )

    patient = extract_patient(
        items
    )

    diagnoses = extract_diagnoses(
        items
    )

    medications = extract_medications(
        items
    )

    laboratory_results = (
        extract_laboratory_results(
            items
        )
    )

    procedures = extract_procedures(
        items
    )

    dates = extract_dates(
        items
    )

    return {
        "document_type": document_type,
        "patient": patient,
        "diagnoses": diagnoses,
        "medications": medications,
        "laboratory_results": laboratory_results,
        "procedures": procedures,
        "dates": dates,
        "source": {
            "ocr_line_count": len(items),
        },
    }