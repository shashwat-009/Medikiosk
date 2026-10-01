from pathlib import Path


ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".pdf"
}

MAX_FILE_SIZE_MB = 20


def validate_file(file_path):
    path = Path(file_path)

    # Check file exists
    if not path.exists():
        return False, "File does not exist."

    # Check that it is actually a file
    if not path.is_file():
        return False, "Path is not a file."

    # Check extension
    extension = path.suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        return False, (
            f"Unsupported file type: {extension}. "
            f"Allowed: JPG, JPEG, PNG, PDF"
        )

    # Check file size
    size_mb = path.stat().st_size / (1024 * 1024)

    if size_mb > MAX_FILE_SIZE_MB:
        return False, (
            f"File is too large: {size_mb:.2f} MB. "
            f"Maximum allowed is {MAX_FILE_SIZE_MB} MB."
        )

    return True, {
        "file_name": path.name,
        "file_type": extension,
        "file_size_mb": round(size_mb, 2)
    }


if __name__ == "__main__":

    test_file = "test_images/prescription.png"

    valid, result = validate_file(test_file)

    print("=" * 60)
    print("             FILE VALIDATION")
    print("=" * 60)

    if valid:
        print("Status : VALID")
        print(f"Name   : {result['file_name']}")
        print(f"Type   : {result['file_type']}")
        print(f"Size   : {result['file_size_mb']} MB")
    else:
        print("Status : INVALID")
        print(f"Reason : {result}")

    print("=" * 60)