from pathlib import Path
from typing import Any

import cv2
try:
    from paddleocr import PaddleOCR
except ImportError:
    PaddleOCR = None



# ============================================================
# CONFIGURATION
# ============================================================

MIN_CONFIDENCE = 0.30

# Maximum image size sent to OCR.
MAX_INPUT_SIDE = 1600

# Text detection configuration.
# Slightly more permissive than the previous configuration so
# that characters near the beginning/end of a line are retained.
TEXT_DET_LIMIT_SIDE_LEN = 1280
TEXT_DET_LIMIT_TYPE = "max"

TEXT_DET_THRESH = 0.20
TEXT_DET_BOX_THRESH = 0.35
TEXT_DET_UNCLIP_RATIO = 1.8

TEXT_RECOGNITION_BATCH_SIZE = 1


# ============================================================
# OCR ENGINE
# ============================================================

class OCREngine:

    def __init__(self):
        print("=" * 60)
        print("                  OCR ENGINE")
        print("=" * 60)

        if PaddleOCR is None:
            raise RuntimeError(
                "PaddleOCR is not installed. Please install PaddleOCR to perform OCR."
            )

        print("Initializing PaddleOCR...")

        self.ocr = PaddleOCR(
            lang="en",

            # Required for the current Windows CPU setup.
            enable_mkldnn=False,

            # Detection configuration.
            text_det_limit_side_len=TEXT_DET_LIMIT_SIDE_LEN,
            text_det_limit_type=TEXT_DET_LIMIT_TYPE,
            text_det_thresh=TEXT_DET_THRESH,
            text_det_box_thresh=TEXT_DET_BOX_THRESH,
            text_det_unclip_ratio=TEXT_DET_UNCLIP_RATIO,

            # Keep recognition lightweight.
            text_recognition_batch_size=TEXT_RECOGNITION_BATCH_SIZE,
        )

        print("PaddleOCR initialized.")
        print("=" * 60)


    # ========================================================
    # IMAGE PREPARATION
    # ========================================================

    def _prepare_input(
        self,
        image_path: str
    ) -> tuple[str, bool]:

        path = Path(image_path)

        image = cv2.imread(
            str(path),
            cv2.IMREAD_COLOR
        )

        if image is None:
            raise ValueError(
                f"Could not read image: {image_path}"
            )

        height, width = image.shape[:2]

        largest_side = max(
            width,
            height
        )

        # Keep original image if it is already within limits.
        if largest_side <= MAX_INPUT_SIDE:
            return str(path), False

        scale = (
            MAX_INPUT_SIDE
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

        resized = cv2.resize(
            image,
            (
                new_width,
                new_height
            ),
            interpolation=cv2.INTER_AREA
        )

        resized_path = (
            path.parent
            / f".ocr_resized_{path.name}"
        )

        success = cv2.imwrite(
            str(resized_path),
            resized
        )

        if not success:
            raise RuntimeError(
                "Failed to create resized OCR image."
            )

        print(
            f"OCR input resized to: {resized_path}"
        )

        return str(resized_path), True


    # ========================================================
    # POLYGON → BOUNDING BOX
    # ========================================================

    @staticmethod
    def _polygon_to_bbox(
        polygon: Any
    ) -> dict:

        try:

            points = [
                (
                    float(point[0]),
                    float(point[1])
                )
                for point in polygon
            ]

            if not points:
                return {
                    "x": 0,
                    "y": 0,
                    "width": 0,
                    "height": 0,
                }

            xs = [
                point[0]
                for point in points
            ]

            ys = [
                point[1]
                for point in points
            ]

            min_x = min(xs)
            max_x = max(xs)
            min_y = min(ys)
            max_y = max(ys)

            return {
                "x": int(min_x),
                "y": int(min_y),
                "width": int(
                    max_x - min_x
                ),
                "height": int(
                    max_y - min_y
                ),
            }

        except Exception:

            return {
                "x": 0,
                "y": 0,
                "width": 0,
                "height": 0,
            }


    # ========================================================
    # RESULT EXTRACTION
    # ========================================================

    def _extract_results(
        self,
        result
    ) -> list[dict]:

        extracted = []

        if result is None:
            return extracted

        # PaddleOCR 3.x returns a list-like result.
        if not isinstance(
            result,
            (list, tuple)
        ):
            result = [result]

        for page_result in result:

            if page_result is None:
                continue

            # PaddleOCR 3.x result object behaves like a
            # dictionary for these fields.
            try:
                texts = page_result.get(
                    "rec_texts",
                    []
                )

                scores = page_result.get(
                    "rec_scores",
                    []
                )

                polygons = page_result.get(
                    "rec_polys",
                    []
                )

            except AttributeError:
                continue

            for index, text in enumerate(texts):

                if text is None:
                    continue

                text = str(text).strip()

                if not text:
                    continue

                try:
                    confidence = float(
                        scores[index]
                    )
                except (
                    IndexError,
                    TypeError,
                    ValueError
                ):
                    confidence = 0.0

                if confidence < MIN_CONFIDENCE:
                    continue

                try:
                    polygon = polygons[index]
                except IndexError:
                    polygon = []

                bbox = self._polygon_to_bbox(
                    polygon
                )

                extracted.append(
                    {
                        "text": text,
                        "confidence": round(
                            confidence,
                            4
                        ),
                        "bbox": bbox,
                        "x": bbox["x"],
                        "y": bbox["y"],
                        "width": bbox["width"],
                        "height": bbox["height"],
                    }
                )

        # ====================================================
        # SORT TOP → BOTTOM, LEFT → RIGHT
        # ====================================================

        extracted.sort(
            key=lambda item: (
                item["y"],
                item["x"]
            )
        )

        return extracted


    # ========================================================
    # RUN OCR
    # ========================================================

    def run(
        self,
        image_path: str
    ) -> list[dict]:

        print("=" * 60)
        print("                  OCR PROCESS")
        print("=" * 60)

        print(
            f"Input: {image_path}"
        )

        prepared_path = None
        temporary_file = False

        try:

            prepared_path, temporary_file = (
                self._prepare_input(
                    image_path
                )
            )

            print(
                "Running PaddleOCR..."
            )

            result = self.ocr.predict(
                prepared_path
            )

            extracted = (
                self._extract_results(
                    result
                )
            )

            print()

            print(
                f"Detected text lines: "
                f"{len(extracted)}"
            )

            for item in extracted:

                print(
                    f'{item["text"]} '
                    f'[{item["confidence"]:.2f}]'
                )

            return extracted

        finally:

            # Remove temporary resized image.
            if (
                temporary_file
                and prepared_path
            ):

                try:
                    Path(
                        prepared_path
                    ).unlink(
                        missing_ok=True
                    )

                except Exception:
                    pass


# ============================================================
# SINGLETON ENGINE
# ============================================================

_engine = None


def get_ocr_engine() -> OCREngine:

    global _engine

    if _engine is None:
        _engine = OCREngine()

    return _engine


# ============================================================
# PUBLIC FUNCTION
# ============================================================

def run_ocr(
    image_path: str
) -> list[dict]:

    engine = get_ocr_engine()

    return engine.run(
        image_path
    )


# ============================================================
# CLI TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("             MEDISETU OCR TEST")
    print("=" * 60)

    test_image = Path(
        "processed/enhanced_ocr_test.png"
    )

    if not test_image.exists():

        print(
            f"Test image not found: "
            f"{test_image}"
        )

    else:

        results = run_ocr(
            str(test_image)
        )

        print()
        print("=" * 60)
        print("OCR RESULT")
        print("=" * 60)

        for item in results:

            print(
                f'{item["text"]} '
                f'[{item["confidence"]:.2f}]'
            )

    print("=" * 60)