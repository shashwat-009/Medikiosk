from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Project structure:
#
# medikiosk/
# ├── ai/
# ├── backend/
# │   ├── .env
# │   └── app/
# │       └── config.py
# └── frontend/
#
# config.py is therefore:
# backend/app/config.py
#
# parents[0] = app/
# parents[1] = backend/
# parents[2] = medikiosk/

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    app_name: str
    app_version: str
    database_url: str
    sarvam_api_key: str
    supabase_url: str
    supabase_service_key: str

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()