from pathlib import Path
from typing import List

import pymupdf


SUPPORTED_IMAGES = {
    ".jpg",
    ".jpeg",
    ".png",
}

SUPPORTED_PDFS = {
    ".pdf",
}

# Render PDFs at a controlled resolution.
# This prevents huge page images from being created unnecessarily.
PDF_RENDER_SCALE = 1.5


def prepare_document(
    file_path: str,
    output_dir: str = "prepared"
) -> List[str]:
    """
    Prepare a medical document for OCR.

    Supported:
        JPG
        JPEG
        PNG
        PDF

    Images:
        Returned directly.

    PDFs:
        Each page is rendered into a PNG image.

    Returns:
        List of image paths ready for OCR.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Document not found: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Path is not a file: {path}"
        )

    extension = path.suffix.lower()

    # =========================================================
    # IMAGE
    # =========================================================

    if extension in SUPPORTED_IMAGES:
        return [
            str(path)
        ]

    # =========================================================
    # PDF
    # =========================================================

    if extension in SUPPORTED_PDFS:

        output = Path(output_dir)

        output.mkdir(
            parents=True,
            exist_ok=True
        )

        image_paths = []

        pdf = pymupdf.open(
            str(path)
        )

        try:

            for page_number, page in enumerate(
                pdf
            ):

                matrix = pymupdf.Matrix(
                    PDF_RENDER_SCALE,
                    PDF_RENDER_SCALE
                )

                pixmap = page.get_pixmap(
                    matrix=matrix,
                    alpha=False
                )

                image_path = (
                    output
                    / f"{path.stem}_page_{page_number + 1}.png"
                )

                pixmap.save(
                    str(image_path)
                )

                image_paths.append(
                    str(image_path)
                )

        finally:

            pdf.close()

        if not image_paths:
            raise ValueError(
                "PDF contains no readable pages."
            )

        return image_paths

    raise ValueError(
        f"Unsupported file type: {extension}. "
        "Allowed: JPG, JPEG, PNG, PDF"
    )


if __name__ == "__main__":

    print("=" * 60)
    print("             DOCUMENT PREPROCESSOR")
    print("=" * 60)

    test_file = Path(
        "test_images/ocr_test.png"
    )

    if not test_file.exists():

        print(
            f"Test file not found: {test_file}"
        )

    else:

        try:

            pages = prepare_document(
                test_file
            )

            print()
            print(
                f"Prepared pages: {len(pages)}"
            )

            for page in pages:
                print(
                    f" - {page}"
                )

            print()
            print("STATUS: SUCCESS")

        except Exception as exc:

            print()
            print("STATUS: FAILED")
            print(f"Reason: {exc}")

    print("=" * 60)