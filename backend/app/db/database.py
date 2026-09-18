from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import BASE_DIR, settings


def _resolve_database_url(url: str) -> str:
    """Ensure relative SQLite database paths resolve relative to backend BASE_DIR,
    not the current working directory from which a command happens to be run."""
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        raw_path = url[len("sqlite:///"):]
        p = Path(raw_path)
        if not p.is_absolute():
            clean_rel = raw_path[2:] if raw_path.startswith("./") else raw_path
            abs_path = (BASE_DIR / clean_rel).resolve()
            return f"sqlite:///{abs_path.as_posix()}"
    return url


engine = create_engine(
    _resolve_database_url(settings.database_url),
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()