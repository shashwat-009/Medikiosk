import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

INPUT_JSON = (
    BASE_DIR /
    "processed" /
    "cleaned_handwritten_text.json"
)

OUTPUT_JSON = (
    BASE_DIR /
    "output" /
    "handwritten_quality.json"
)


def check_line(text):

    text = text.strip()

    if not text:
        return {
            "status": "FAILED",
            "reason": "EMPTY_OCR"
        }

    if len(text) < 2:
        return {
            "status": "REVIEW",
            "reason": "VERY_SHORT_TEXT"
        }

    # Detect suspicious repeated characters
    if len(set(text.replace(" ", ""))) <= 1:
        return {
            "status": "REVIEW",
            "reason": "REPEATED_CHARACTER"
        }

    return {
        "status": "PASS",
        "reason": "OK"
    }


def main():

    print("=" * 60)
    print("      HANDWRITTEN OCR - QUALITY CHECKER")
    print("=" * 60)

    if not INPUT_JSON.exists():
        raise FileNotFoundError(
            f"Input JSON not found: {INPUT_JSON}"
        )

    with open(
        INPUT_JSON,
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    checked_lines = []

    passed = 0
    review = 0
    failed = 0

    for item in data.get("lines", []):

        text = item.get(
            "cleaned_text",
            ""
        )

        quality = check_line(text)

        checked_item = {
            "line_number": item.get("line_number"),
            "image": item.get("image"),
            "text": text,
            "quality": quality
        }

        checked_lines.append(
            checked_item
        )

        if quality["status"] == "PASS":
            passed += 1

        elif quality["status"] == "REVIEW":
            review += 1

        else:
            failed += 1

    total = len(checked_lines)

    if total == 0:
        overall_status = "FAILED"

    elif failed > 0:
        overall_status = "REVIEW"

    elif review > 0:
        overall_status = "REVIEW"

    else:
        overall_status = "PASS"

    result = {
        "module": "Handwritten OCR - Quality Checker",
        "total_lines": total,
        "passed": passed,
        "review_required": review,
        "failed": failed,
        "overall_status": overall_status,
        "lines": checked_lines
    }

    OUTPUT_JSON.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_JSON,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            indent=4,
            ensure_ascii=False
        )

    print()
    print(f"Total lines:     {total}")
    print(f"Passed:          {passed}")
    print(f"Review required: {review}")
    print(f"Failed:          {failed}")
    print(f"Overall status:  {overall_status}")

    print()
    print(f"Output: {OUTPUT_JSON}")

    print()
    print("=" * 60)
    print("STATUS: SUCCESS")
    print("=" * 60)


if __name__ == "__main__":
    main()