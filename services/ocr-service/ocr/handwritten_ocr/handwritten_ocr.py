import json
from pathlib import Path

import torch
from PIL import Image
from transformers import TrOCRProcessor, VisionEncoderDecoderModel


# ============================================================
# HANDWRITTEN OCR USING TrOCR
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

MODEL_NAME = "microsoft/trocr-base-handwritten"


# ------------------------------------------------------------
# LOAD MODEL
# ------------------------------------------------------------

def load_model():

    print("=" * 60)
    print("              HANDWRITTEN OCR - TrOCR")
    print("=" * 60)

    print("\nLoading TrOCR model...")
    print(f"Model: {MODEL_NAME}")

    processor = TrOCRProcessor.from_pretrained(
        MODEL_NAME
    )

    model = VisionEncoderDecoderModel.from_pretrained(
        MODEL_NAME
    )

    device = torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )

    model.to(device)
    model.eval()

    print(f"Device: {device}")
    print("TrOCR model loaded successfully.")

    return processor, model, device


# ------------------------------------------------------------
# OCR SINGLE IMAGE
# ------------------------------------------------------------

def recognize_handwriting(
    image_path,
    processor,
    model,
    device
):

    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(
            f"Image not found: {image_path}"
        )

    print("\n" + "=" * 60)
    print("              HANDWRITTEN OCR PROCESS")
    print("=" * 60)

    print(f"\nInput image: {image_path}")

    image = Image.open(image_path).convert("RGB")

    print(
        f"Image size: {image.width} x {image.height}"
    )

    # --------------------------------------------------------
    # Prepare image
    # --------------------------------------------------------

    pixel_values = processor(
        images=image,
        return_tensors="pt"
    ).pixel_values

    pixel_values = pixel_values.to(device)

    # --------------------------------------------------------
    # Generate text
    # --------------------------------------------------------

    print("\nRunning TrOCR...")

    with torch.no_grad():

        generated_ids = model.generate(
            pixel_values,
            max_new_tokens=128
        )

    generated_text = processor.batch_decode(
        generated_ids,
        skip_special_tokens=True
    )[0]

    generated_text = generated_text.strip()

    return generated_text


# ------------------------------------------------------------
# SAVE RESULT
# ------------------------------------------------------------

def save_result(
    image_path,
    text
):

    output = {
        "module": "Handwritten OCR",
        "document_type": "HANDWRITTEN_DOCUMENT",
        "source_image": str(image_path),
        "ocr_engine": "TrOCR",
        "model": MODEL_NAME,
        "text": text,
        "status": "SUCCESS"
    }

    output_file = BASE_DIR / "handwritten_ocr_result.json"

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            indent=4,
            ensure_ascii=False
        )

    return output_file


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    print("=" * 60)
    print("          MEDIKIOSK HANDWRITTEN OCR")
    print("=" * 60)

    # --------------------------------------------------------
    # INPUT IMAGE
    # --------------------------------------------------------

    image_path = BASE_DIR / "test_images" / "handwritten.png"

    if not image_path.exists():

        print("\nERROR:")
        print(
            f"Handwritten image not found:\n{image_path}"
        )

        print("\nPlease place your handwritten image here:")
        print(
            "test_images\\handwritten.jpg"
        )

        return

    # --------------------------------------------------------
    # LOAD MODEL
    # --------------------------------------------------------

    processor, model, device = load_model()

    # --------------------------------------------------------
    # OCR
    # --------------------------------------------------------

    text = recognize_handwriting(
        image_path,
        processor,
        model,
        device
    )

    # --------------------------------------------------------
    # DISPLAY
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("              HANDWRITTEN OCR RESULT")
    print("=" * 60)

    print("\nRecognized Text:")
    print("-" * 60)

    if text:
        print(text)
    else:
        print("[NO TEXT DETECTED]")

    print("-" * 60)

    # --------------------------------------------------------
    # SAVE JSON
    # --------------------------------------------------------

    output_file = save_result(
        image_path,
        text
    )

    print(
        f"\nJSON saved to: {output_file.name}"
    )

    print("\n" + "=" * 60)
    print("STATUS: SUCCESS")
    print("=" * 60)


if __name__ == "__main__":
    main()