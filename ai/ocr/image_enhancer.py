from pathlib import Path
from typing import Optional

import cv2
import numpy as np


# ============================================================
# CONFIGURATION
# ============================================================

MAX_SIDE = 1600
MIN_SIDE = 800

# Padding added around detected document content.
CONTENT_PADDING = 80

OUTPUT_DIR = "processed"


# ============================================================
# CONTENT CROP
# ============================================================

def crop_to_content(
    image: np.ndarray
) -> np.ndarray:
    """
    Remove large blank margins around document content.

    This is especially useful for scanned documents where
    the actual text occupies only a small portion of the page.
    """

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    # Small blur removes isolated noise.
    blurred = cv2.GaussianBlur(
        gray,
        (3, 3),
        0
    )

    # Detect pixels that are meaningfully darker than white.
    threshold = cv2.threshold(
        blurred,
        245,
        255,
        cv2.THRESH_BINARY_INV
    )[1]

    # Remove tiny noise.
    kernel = np.ones(
        (3, 3),
        np.uint8
    )

    threshold = cv2.morphologyEx(
        threshold,
        cv2.MORPH_OPEN,
        kernel
    )

    # Find all content.
    contours, _ = cv2.findContours(
        threshold,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    if not contours:
        return image

    height, width = image.shape[:2]

    boxes = []

    for contour in contours:

        x, y, w, h = cv2.boundingRect(
            contour
        )

        # Ignore extremely tiny noise.
        if w < 3 or h < 3:
            continue

        boxes.append(
            (x, y, w, h)
        )

    if not boxes:
        return image

    # Combined bounding rectangle.
    min_x = min(
        box[0]
        for box in boxes
    )

    min_y = min(
        box[1]
        for box in boxes
    )

    max_x = max(
        box[0] + box[2]
        for box in boxes
    )

    max_y = max(
        box[1] + box[3]
        for box in boxes
    )

    # Add safe padding.
    min_x = max(
        0,
        min_x - CONTENT_PADDING
    )

    min_y = max(
        0,
        min_y - CONTENT_PADDING
    )

    max_x = min(
        width,
        max_x + CONTENT_PADDING
    )

    max_y = min(
        height,
        max_y + CONTENT_PADDING
    )

    cropped = image[
        min_y:max_y,
        min_x:max_x
    ]

    # Only use the crop if it is actually meaningful.
    crop_area = (
        (max_x - min_x)
        * (max_y - min_y)
    )

    original_area = (
        width * height
    )

    # If almost the entire page is content already,
    # don't unnecessarily crop it.
    if (
        crop_area
        >= original_area * 0.90
    ):
        return image

    print(
        "Content area detected:"
        f" ({min_x}, {min_y}) →"
        f" ({max_x}, {max_y})"
    )

    return cropped


# ============================================================
# RESIZE
# ============================================================

def resize_for_ocr(
    image: np.ndarray
) -> np.ndarray:

    height, width = image.shape[:2]

    largest_side = max(
        width,
        height
    )

    # Large image.
    if largest_side > MAX_SIDE:

        scale = (
            MAX_SIDE
            / largest_side
        )

        new_width = max(
            1,
            int(width * scale)
        )

        new_height = max(
            1,
            int(height * scale)
        )

        return cv2.resize(
            image,
            (
                new_width,
                new_height
            ),
            interpolation=cv2.INTER_AREA
        )

    # Small image.
    smallest_side = min(
        width,
        height
    )

    if smallest_side < MIN_SIDE:

        scale = (
            MIN_SIDE
            / smallest_side
        )

        # Don't enlarge more than 2x.
        scale = min(
            scale,
            2.0
        )

        new_width = max(
            1,
            int(width * scale)
        )

        new_height = max(
            1,
            int(height * scale)
        )

        return cv2.resize(
            image,
            (
                new_width,
                new_height
            ),
            interpolation=cv2.INTER_CUBIC
        )

    return image


# ============================================================
# BORDER
# ============================================================

def add_safe_border(
    image: np.ndarray
) -> np.ndarray:

    return cv2.copyMakeBorder(
        image,
        CONTENT_PADDING,
        CONTENT_PADDING,
        CONTENT_PADDING,
        CONTENT_PADDING,
        borderType=cv2.BORDER_CONSTANT,
        value=(255, 255, 255)
    )


# ============================================================
# LIGHT ENHANCEMENT
# ============================================================

def enhance_contrast(
    image: np.ndarray
) -> np.ndarray:

    lab = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2LAB
    )

    l_channel, a_channel, b_channel = (
        cv2.split(lab)
    )

    clahe = cv2.createCLAHE(
        clipLimit=1.5,
        tileGridSize=(8, 8)
    )

    l_channel = clahe.apply(
        l_channel
    )

    enhanced = cv2.merge(
        (
            l_channel,
            a_channel,
            b_channel
        )
    )

    enhanced = cv2.cvtColor(
        enhanced,
        cv2.COLOR_LAB2BGR
    )

    return enhanced


# ============================================================
# MAIN ENHANCER
# ============================================================

def enhance_image(
    image_path: str,
    output_dir: str = OUTPUT_DIR
) -> Optional[str]:

    path = Path(
        image_path
    )

    if not path.exists():

        print(
            f"Image not found: {path}"
        )

        return None

    if not path.is_file():

        print(
            f"Path is not a file: {path}"
        )

        return None

    # ========================================================
    # READ
    # ========================================================

    image = cv2.imread(
        str(path),
        cv2.IMREAD_COLOR
    )

    if image is None:

        print(
            f"Could not read image: {path}"
        )

        return None

    original_height, original_width = (
        image.shape[:2]
    )

    print(
        f"Original size: "
        f"{original_width}x{original_height}"
    )

    # ========================================================
    # CROP LARGE WHITE MARGINS
    # ========================================================

    image = crop_to_content(
        image
    )

    cropped_height, cropped_width = (
        image.shape[:2]
    )

    print(
        f"Content size: "
        f"{cropped_width}x{cropped_height}"
    )

    # ========================================================
    # RESIZE
    # ========================================================

    image = resize_for_ocr(
        image
    )

    resized_height, resized_width = (
        image.shape[:2]
    )

    print(
        f"OCR image size: "
        f"{resized_width}x{resized_height}"
    )

    # ========================================================
    # SAFE BORDER
    # ========================================================

    image = add_safe_border(
        image
    )

    # ========================================================
    # LIGHT CONTRAST ENHANCEMENT
    # ========================================================

    image = enhance_contrast(
        image
    )

    # ========================================================
    # LIGHT DENOISING
    # ========================================================

    image = cv2.fastNlMeansDenoisingColored(
        image,
        None,
        2,
        2,
        7,
        21
    )

    # ========================================================
    # SAVE
    # ========================================================

    output = Path(
        output_dir
    )

    output.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path = (
        output
        / f"enhanced_{path.stem}.png"
    )

    success = cv2.imwrite(
        str(output_path),
        image
    )

    if not success:

        print(
            f"Failed to save: {output_path}"
        )

        return None

    print(
        f"Enhanced image: {output_path}"
    )

    return str(output_path)


# ============================================================
# CLI TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("             IMAGE ENHANCEMENT TEST")
    print("=" * 60)

    input_path = Path(
        "test_images/ocr_test.png"
    )

    if not input_path.exists():

        print(
            f"Test image not found: {input_path}"
        )

    else:

        result = enhance_image(
            str(input_path)
        )

        print()

        if result:

            print(
                "STATUS: SUCCESS"
            )

            print(
                f"Output: {result}"
            )

        else:

            print(
                "STATUS: FAILED"
            )

    print("=" * 60)