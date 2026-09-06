import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_path(value: str, default: Path) -> Path:
    if not value:
        return default

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _resolve_database_url(value: str, default: Path) -> str:
    if not value:
        return f"sqlite:///{default}"

    sqlite_prefix = "sqlite:///"
    if not value.startswith(sqlite_prefix):
        return value

    database_path = value.removeprefix(sqlite_prefix)
    if database_path == ":memory:" or Path(database_path).is_absolute():
        return value

    resolved_path = (PROJECT_ROOT / database_path).resolve()
    return f"sqlite:///{resolved_path}"


@dataclass(frozen=True)
class Settings:
    database_url: str
    upload_dir: Path
    max_pdf_size_bytes: int
    jwt_secret: str
    access_token_expire_minutes: int


def get_settings() -> Settings:
    default_database_path = PROJECT_ROOT / "buildtrack.db"
    database_url = _resolve_database_url(
        os.getenv("BUILDTRACK_DATABASE_URL", ""),
        default_database_path,
    )
    upload_dir = _resolve_path(
        os.getenv("BUILDTRACK_UPLOAD_DIR", ""),
        PROJECT_ROOT / "uploads",
    )
    max_pdf_size_bytes = int(
        os.getenv("BUILDTRACK_MAX_PDF_SIZE_BYTES", str(25 * 1024 * 1024))
    )
    if max_pdf_size_bytes <= 0:
        raise ValueError("BUILDTRACK_MAX_PDF_SIZE_BYTES must be greater than zero")
    jwt_secret = os.getenv(
        "BUILDTRACK_JWT_SECRET",
        "development-only-change-before-deployment",
    )
    access_token_expire_minutes = int(
        os.getenv("BUILDTRACK_ACCESS_TOKEN_EXPIRE_MINUTES", "480")
    )
    if access_token_expire_minutes <= 0:
        raise ValueError(
            "BUILDTRACK_ACCESS_TOKEN_EXPIRE_MINUTES must be greater than zero"
        )
    return Settings(
        database_url=database_url,
        upload_dir=upload_dir,
        max_pdf_size_bytes=max_pdf_size_bytes,
        jwt_secret=jwt_secret,
        access_token_expire_minutes=access_token_expire_minutes,
    )


settings = get_settings()
