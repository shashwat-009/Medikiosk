from supabase import create_client

from app.config import settings


BUCKET_NAME = "medical-documents"


supabase = create_client(
    settings.supabase_url,
    settings.supabase_service_key,
)


def upload_document(
    file_bytes: bytes,
    storage_path: str,
    content_type: str,
):
    return supabase.storage.from_(
        BUCKET_NAME
    ).upload(
        storage_path,
        file_bytes,
        {
            "content-type": content_type,
            "upsert": "false",
        },
    )


def download_document(
    storage_path: str,
) -> bytes:

    return supabase.storage.from_(
        BUCKET_NAME
    ).download(
        storage_path
    )


def delete_document(
    storage_path: str,
):
    return supabase.storage.from_(
        BUCKET_NAME
    ).remove(
        [storage_path]
    )