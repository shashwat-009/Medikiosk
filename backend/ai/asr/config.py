"""Configuration helpers for the ASR subsystem."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOTENV_PATH = PROJECT_ROOT / ".env"


def load_project_environment() -> bool:
    """Load the root ``.env`` without overriding existing environment values.

    The function returns whether python-dotenv found at least one variable to
    load. It never reads, logs, or returns individual secret values.
    """
    return load_dotenv(dotenv_path=DOTENV_PATH, override=False)
