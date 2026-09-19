import cv2
import numpy as np
from pathlib import Path


# ============================================================
# MEDIKIOSK - HANDWRITTEN LINE DETECTION
# Mixed document:
# Printed heading + handwritten content
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_IMAGE = BASE_DIR / "input" / "handwritten.png"
OUTPUT_DIR = BASE_DIR / "processed" / "lines"


# ============================================================
# DETECT HANDWRITTEN LINES
# ============================================================

def detect_lines(input_path, output_dir):

    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input image not found: {input_path}"
        )

    image = cv2.imread(
        str(input_path),
        cv2.IMREAD_GRAYSCALE
    )

    if image is None:
        raise ValueError(
            f"Could not read image: {input_path}"
        )

    height, width = image.shape

    print(f"Image size: {width} x {height}")

    # --------------------------------------------------------
    # 1. Remove printed top heading
    #
    # We assume handwritten content starts below
    # approximately 15% of the document.
    # --------------------------------------------------------

    handwriting_start = int(height * 0.15)

    roi = image[handwriting_start:, :]

    print(
        f"Handwriting search region: "
        f"y={handwriting_start} to {height}"
    )

    # --------------------------------------------------------
    # 2. Threshold
    # --------------------------------------------------------

    binary = cv2.adaptiveThreshold(
        roi,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        15
    )

    # --------------------------------------------------------
    # 3. Remove tiny noise
    # --------------------------------------------------------

    small_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (2, 2)
    )

    binary = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        small_kernel
    )

    # --------------------------------------------------------
    # 4. Connect characters belonging to same line
    # --------------------------------------------------------

    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (25, 3)
    )

    connected = cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        horizontal_kernel
    )

    # --------------------------------------------------------
    # 5. Find contours
    # --------------------------------------------------------

    contours, _ = cv2.findContours(
        connected,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    candidates = []

    roi_height, roi_width = roi.shape

    for contour in contours:

        x, y, w, h = cv2.boundingRect(contour)

        # Ignore tiny regions
        if w < 25:
            continue

        if h < 8:
            continue

        # Ignore huge page/background regions
        if w > roi_width * 0.98 and h > roi_height * 0.40:
            continue

        # Handwritten line should be reasonably thin
        if h > roi_height * 0.20:
            continue

        # Ignore extremely narrow blobs
        if w / max(h, 1) < 1.2:
            continue

        # Convert ROI coordinate to original image coordinate
        original_y = y + handwriting_start

        candidates.append(
            (x, original_y, w, h)
        )

    print(
        f"Candidate regions: {len(candidates)}"
    )

    # --------------------------------------------------------
    # 6. Sort top-to-bottom
    # --------------------------------------------------------

    candidates.sort(
        key=lambda box: box[1]
    )

    # --------------------------------------------------------
    # 7. Merge overlapping / nearby regions
    #
    # Handwriting may produce multiple contours
    # belonging to one line.
    # --------------------------------------------------------

    merged = []

    for box in candidates:

        x, y, w, h = box

        if not merged:

            merged.append(
                [x, y, x + w, y + h]
            )

            continue

        last = merged[-1]

        lx1, ly1, lx2, ly2 = last

        # Vertical distance between regions
        gap = y - ly2

        # Horizontal overlap
        overlap = min(x + w, lx2) - max(x, lx1)

        if (
            gap <= max(15, int(h * 0.8))
            and overlap > 0
        ):

            last[0] = min(lx1, x)
            last[1] = min(ly1, y)
            last[2] = max(lx2, x + w)
            last[3] = max(ly2, y + h)

        else:

            merged.append(
                [x, y, x + w, y + h]
            )

    print(
        f"Merged line regions: {len(merged)}"
    )

    # --------------------------------------------------------
    # 8. Prepare output directory
    # --------------------------------------------------------

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # Delete old line images
    for old_file in output_dir.glob("line_*.png"):

        try:
            old_file.unlink()
        except OSError:
            pass

    # --------------------------------------------------------
    # 9. Crop lines
    # --------------------------------------------------------

    line_paths = []

    padding_x = 15
    padding_y = 12

    for index, box in enumerate(
        merged,
        start=1
    ):

        x1, y1, x2, y2 = box

        x1 = max(
            0,
            x1 - padding_x
        )

        y1 = max(
            handwriting_start,
            y1 - padding_y
        )

        x2 = min(
            width,
            x2 + padding_x
        )

        y2 = min(
            height,
            y2 + padding_y
        )

        crop = image[
            y1:y2,
            x1:x2
        ]

        if crop.size == 0:
            continue

        # ----------------------------------------------------
        # Add white border
        # ----------------------------------------------------

        crop = cv2.copyMakeBorder(
            crop,
            20,
            20,
            20,
            20,
            cv2.BORDER_CONSTANT,
            value=255
        )

        output_file = (
            output_dir /
            f"line_{index:03d}.png"
        )

        success = cv2.imwrite(
            str(output_file),
            crop
        )

        if success:
            line_paths.append(
                output_file
            )

    return line_paths


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("      MEDIKIOSK - HANDWRITTEN LINE DETECTION")
    print("=" * 60)

    print()
    print("Input:")
    print(INPUT_IMAGE)

    print()
    print("Output:")
    print(OUTPUT_DIR)

    print()
    print("Detecting handwritten region...")

    try:

        lines = detect_lines(
            INPUT_IMAGE,
            OUTPUT_DIR
        )

    except Exception as e:

        print()
        print(f"ERROR: {e}")

        print()
        print("=" * 60)
        print("STATUS: FAILED")
        print("=" * 60)

        return

    print()
    print("=" * 60)
    print("LINE DETECTION RESULT")
    print("=" * 60)

    print()
    print(
        f"Lines detected: {len(lines)}"
    )

    if not lines:

        print()
        print(
            "No handwriting lines detected."
        )

        print()
        print("=" * 60)
        print("STATUS: FAILED")
        print("=" * 60)

        return

    print()

    for line in lines:

        print(
            f" - {line.name}"
        )

    print()
    print("=" * 60)
    print("STATUS: SUCCESS")
    print("=" * 60)


if __name__ == "__main__":
    main()