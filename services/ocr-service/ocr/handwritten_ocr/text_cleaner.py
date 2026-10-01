import json
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

INPUT_JSON = BASE_DIR / "processed" / "handwritten_text.json"
OUTPUT_JSON = BASE_DIR / "processed" / "cleaned_handwritten_text.json"
OUTPUT_TXT = BASE_DIR / "processed" / "cleaned_handwritten_text.txt"


def clean_text(text):
    if not text:
        return ""

    text = str(text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    # Remove unwanted control characters
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)

    return text.strip()


def clean_results(data):

    cleaned_lines = []

    for item in data.get("lines", []):

        text = clean_text(
            item.get("text", "")
        )

        cleaned_lines.append({
            "line_number": item.get("line_number"),
            "image": item.get("image"),
            "original_text": item.get("text", ""),
            "cleaned_text": text
        })

    return {
        "module": "Handwritten OCR - Text Cleaning",
        "model": data.get("model"),
        "total_lines": len(cleaned_lines),
        "lines": cleaned_lines
    }


def main():

    print("=" * 60)
    print("       HANDWRITTEN OCR - TEXT CLEANING")
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

    result = clean_results(data)

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

    with open(
        OUTPUT_TXT,
        "w",
        encoding="utf-8"
    ) as f:

        for item in result["lines"]:

            text = item["cleaned_text"]

            if text:
                f.write(text + "\n")

    print()
    print(f"Input:  {INPUT_JSON}")
    print(f"JSON:   {OUTPUT_JSON}")
    print(f"TXT:    {OUTPUT_TXT}")

    print()
    print("=" * 60)
    print("STATUS: SUCCESS")
    print("=" * 60)


if __name__ == "__main__":
    main()