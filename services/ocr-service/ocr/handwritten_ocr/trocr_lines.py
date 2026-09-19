
import json
import re
from pathlib import Path

import torch
from PIL import Image, ImageOps
from transformers import TrOCRProcessor, VisionEncoderDecoderModel


# ============================================================
# MEDIKIOSK - IMPROVED TrOCR LINE RECOGNITION
# ============================================================

MODEL_NAME = "microsoft/trocr-base-handwritten"

BASE_DIR = Path(__file__).resolve().parent

LINES_DIR = BASE_DIR / "processed" / "lines"

OUTPUT_JSON = (
    BASE_DIR /
    "processed" /
    "handwritten_text.json"
)

OUTPUT_TXT = (
    BASE_DIR /
    "processed" /
    "handwritten_text.txt"
)


# ============================================================
# CONFIGURATION
# ============================================================

# TrOCR expects reasonably sized line images.
# Small detected crops are enlarged before recognition.
UPSCALE_FACTOR = 3

# Minimum useful dimensions after resizing.
MIN_WIDTH = 384
MIN_HEIGHT = 64

# Maximum generation length.
MAX_NEW_TOKENS = 128

# Beam search improves stability compared with greedy decoding.
NUM_BEAMS = 5


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):
    """
    Basic OCR text cleanup.

    This does NOT attempt to guess medical words.
    It only removes formatting noise.
    """

    if not text:
        return ""

    text = str(text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# PREPARE LINE IMAGE
# ============================================================

def prepare_line_image(image):
    """
    Prepare a detected handwriting line for TrOCR.

    Operations:
    - RGB conversion
    - grayscale normalization
    - white background
    - proportional enlargement
    - minimum dimensions
    - padding
    """

    image = image.convert("L")

    # Make sure background is white.
    image = ImageOps.autocontrast(image)

    width, height = image.size

    # --------------------------------------------------------
    # Upscale
    # --------------------------------------------------------

    new_width = max(
        width * UPSCALE_FACTOR,
        MIN_WIDTH
    )

    new_height = max(
        height * UPSCALE_FACTOR,
        MIN_HEIGHT
    )

    # Preserve aspect ratio.
    scale = max(
        new_width / width,
        new_height / height
    )

    resized_width = max(
        1,
        int(width * scale)
    )

    resized_height = max(
        1,
        int(height * scale)
    )

    image = image.resize(
        (resized_width, resized_height),
        Image.Resampling.LANCZOS
    )

    # --------------------------------------------------------
    # Add white border
    # --------------------------------------------------------

    image = ImageOps.expand(
        image,
        border=(32, 32, 32, 32),
        fill=255
    )

    # Convert back to RGB.
    image = image.convert("RGB")

    return image


# ============================================================
# LOAD MODEL
# ============================================================

def load_model():

    print()
    print("Loading TrOCR model...")
    print(f"Model: {MODEL_NAME}")

    device = torch.device(
        "cuda" if torch.cuda.is_available()
        else "cpu"
    )

    print(f"Device: {device}")

    # --------------------------------------------------------
    # Processor
    # --------------------------------------------------------

    processor = TrOCRProcessor.from_pretrained(
        MODEL_NAME
    )

    # --------------------------------------------------------
    # Model
    # --------------------------------------------------------

    model = VisionEncoderDecoderModel.from_pretrained(
        MODEL_NAME
    )

    tokenizer = processor.tokenizer

    # --------------------------------------------------------
    # Validate tokenizer IDs
    # --------------------------------------------------------

    print()
    print("Tokenizer configuration:")

    print(
        "CLS:",
        tokenizer.cls_token_id
    )

    print(
        "PAD:",
        tokenizer.pad_token_id
    )

    print(
        "SEP:",
        tokenizer.sep_token_id
    )

    # --------------------------------------------------------
    # Configure generation only when IDs exist.
    # --------------------------------------------------------

    if tokenizer.cls_token_id is not None:

        model.config.decoder_start_token_id = (
            tokenizer.cls_token_id
        )

        model.generation_config.decoder_start_token_id = (
            tokenizer.cls_token_id
        )

    if tokenizer.pad_token_id is not None:

        model.config.pad_token_id = (
            tokenizer.pad_token_id
        )

        model.generation_config.pad_token_id = (
            tokenizer.pad_token_id
        )

    if tokenizer.sep_token_id is not None:

        model.config.eos_token_id = (
            tokenizer.sep_token_id
        )

        model.generation_config.eos_token_id = (
            tokenizer.sep_token_id
        )

    # --------------------------------------------------------
    # Device
    # --------------------------------------------------------

    model.to(device)

    model.eval()

    print()
    print("Generation configuration:")

    print(
        "decoder_start_token_id:",
        model.generation_config.decoder_start_token_id
    )

    print(
        "pad_token_id:",
        model.generation_config.pad_token_id
    )

    print(
        "eos_token_id:",
        model.generation_config.eos_token_id
    )

    print()
    print("TrOCR model loaded successfully.")

    return processor, model, device


# ============================================================
# RECOGNIZE ONE LINE
# ============================================================

def recognize_line(
    image_path,
    processor,
    model,
    device
):

    try:

        # ----------------------------------------------------
        # Open image
        # ----------------------------------------------------

        image = Image.open(
            image_path
        )

        # ----------------------------------------------------
        # Prepare image
        # ----------------------------------------------------

        image = prepare_line_image(
            image
        )

        # ----------------------------------------------------
        # Processor
        # ----------------------------------------------------

        inputs = processor(
            images=image,
            return_tensors="pt"
        )

        pixel_values = inputs.pixel_values.to(
            device
        )

        # ----------------------------------------------------
        # Generate
        # ----------------------------------------------------

        with torch.no_grad():

            generated_ids = model.generate(
                pixel_values=pixel_values,
                max_new_tokens=MAX_NEW_TOKENS,
                num_beams=NUM_BEAMS,
                early_stopping=True,
                no_repeat_ngram_size=2
            )

        # ----------------------------------------------------
        # Decode
        # ----------------------------------------------------

        text = processor.batch_decode(
            generated_ids,
            skip_special_tokens=True
        )[0]

        text = clean_text(
            text
        )

        return text

    except Exception as e:

        print(
            f"ERROR processing "
            f"{image_path.name}: {e}"
        )

        return ""


# ============================================================
# FIND LINE IMAGES
# ============================================================

def get_line_images():

    if not LINES_DIR.exists():

        raise FileNotFoundError(
            f"Lines directory not found: "
            f"{LINES_DIR}"
        )

    lines = sorted(
        LINES_DIR.glob("line_*.png")
    )

    if not lines:

        raise FileNotFoundError(
            f"No line images found in: "
            f"{LINES_DIR}"
        )

    return lines


# ============================================================
# SAVE JSON
# ============================================================

def save_json(results):

    OUTPUT_JSON.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output = {
        "module": "Handwritten OCR - TrOCR",
        "model": MODEL_NAME,
        "total_lines": len(results),
        "successful_lines": sum(
            1
            for item in results
            if item["text"]
        ),
        "lines": results
    }

    with open(
        OUTPUT_JSON,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            indent=4,
            ensure_ascii=False
        )


# ============================================================
# SAVE TEXT
# ============================================================

def save_text(results):

    OUTPUT_TXT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_TXT,
        "w",
        encoding="utf-8"
    ) as f:

        for item in results:

            text = item.get(
                "text",
                ""
            )

            if text:

                f.write(
                    text + "\n"
                )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print(
        "       MEDIKIOSK - TrOCR LINE RECOGNITION"
    )
    print("=" * 60)

    print()
    print("Lines directory:")
    print(LINES_DIR)

    # --------------------------------------------------------
    # Find lines
    # --------------------------------------------------------

    try:

        line_images = get_line_images()

    except Exception as e:

        print()
        print(f"ERROR: {e}")
        return

    print()
    print(
        f"Found {len(line_images)} "
        f"handwriting lines."
    )

    # --------------------------------------------------------
    # Load model
    # --------------------------------------------------------

    try:

        processor, model, device = load_model()

    except Exception as e:

        print()
        print(
            f"ERROR loading TrOCR model: {e}"
        )

        return

    # --------------------------------------------------------
    # Process lines
    # --------------------------------------------------------

    results = []

    print()
    print("=" * 60)
    print("             PROCESSING LINES")
    print("=" * 60)

    for index, image_path in enumerate(
        line_images,
        start=1
    ):

        print()
        print(
            f"Processing line "
            f"{index}/{len(line_images)}..."
        )

        text = recognize_line(
            image_path,
            processor,
            model,
            device
        )

        result = {
            "line_number": index,
            "image": image_path.name,
            "text": text,
            "status": (
                "SUCCESS"
                if text
                else "NO_TEXT"
            )
        }

        results.append(
            result
        )

        if text:

            print(
                f"Recognized: {text}"
            )

        else:

            print(
                "Recognized: "
                "[NO TEXT DETECTED]"
            )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    save_json(
        results
    )

    save_text(
        results
    )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("             TrOCR RESULT")
    print("=" * 60)

    print()

    for item in results:

        number = item["line_number"]
        text = item["text"]

        print(
            f"{number:02d}. {text}"
        )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("OUTPUT FILES")
    print("=" * 60)

    print()
    print(
        f"JSON: {OUTPUT_JSON}"
    )

    print(
        f"TEXT: {OUTPUT_TXT}"
    )

    successful = sum(
        1
        for item in results
        if item["text"]
    )

    print()
    print(
        f"Successful lines: "
        f"{successful}/{len(results)}"
    )

    print()
    print("=" * 60)
    print("STATUS: SUCCESS")
    print("=" * 60)


if __name__ == "__main__":
    main()

