import cv2
from pathlib import Path


def preprocess_image(input_path, output_path):
    """
    Prepare a handwritten medical document for OCR.

    Processing:
    - grayscale conversion
    - upscaling
    - denoising
    - contrast enhancement
    - adaptive thresholding
    - morphological cleanup
    """

    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input image not found: {input_path}"
        )

    image = cv2.imread(str(input_path))

    if image is None:
        raise ValueError(
            f"Unable to read image: {input_path}"
        )

    # --------------------------------------------------------
    # 1. Convert to grayscale
    # --------------------------------------------------------

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    # --------------------------------------------------------
    # 2. Upscale
    # --------------------------------------------------------

    height, width = gray.shape

    gray = cv2.resize(
        gray,
        (width * 2, height * 2),
        interpolation=cv2.INTER_CUBIC
    )

    # --------------------------------------------------------
    # 3. Denoise
    # --------------------------------------------------------

    denoised = cv2.GaussianBlur(
        gray,
        (3, 3),
        0
    )

    # --------------------------------------------------------
    # 4. Contrast enhancement
    # --------------------------------------------------------

    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8)
    )

    enhanced = clahe.apply(denoised)

    # --------------------------------------------------------
    # 5. Adaptive threshold
    # --------------------------------------------------------

    binary = cv2.adaptiveThreshold(
        enhanced,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        11
    )

    # --------------------------------------------------------
    # 6. Morphological cleanup
    # --------------------------------------------------------

    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (2, 2)
    )

    cleaned = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        kernel
    )

    # --------------------------------------------------------
    # 7. Save processed image
    # --------------------------------------------------------

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if not cv2.imwrite(
        str(output_path),
        cleaned
    ):
        raise RuntimeError(
            f"Failed to save processed image: {output_path}"
        )

    return output_path


def main():

    print("=" * 60)
    print("       HANDWRITTEN OCR - PREPROCESSING")
    print("=" * 60)

    base_dir = Path(__file__).resolve().parent

    input_path = (
        base_dir /
        "input" /
        "handwritten.png"
    )

    output_path = (
        base_dir /
        "processed" /
        "cleaned.png"
    )

    print()
    print("Input image:")
    print(input_path)

    print()
    print("Processing image...")

    result = preprocess_image(
        input_path,
        output_path
    )

    print()
    print("Processed image:")
    print(result)

    print()
    print("=" * 60)
    print("STATUS: SUCCESS")
    print("=" * 60)


if __name__ == "__main__":
    main()