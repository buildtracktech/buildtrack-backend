import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.core.config import settings


PDF_MIME_TYPES = {"application/pdf", "application/octet-stream"}
CHUNK_SIZE = 1024 * 1024


class InvalidPdfError(ValueError):
    pass


class PdfTooLargeError(ValueError):
    pass


class StorageError(OSError):
    pass


class InvalidStorageKeyError(ValueError):
    pass


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    original_filename: str
    size_bytes: int
    file_hash: str
    mime_type: str


def _safe_original_filename(filename: str | None) -> str:
    if not filename:
        raise InvalidPdfError("Не указано имя файла")
    normalized = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip()
    if not normalized or len(normalized) > 255:
        raise InvalidPdfError("Имя файла должно содержать от 1 до 255 символов")
    if Path(normalized).suffix.lower() != ".pdf":
        raise InvalidPdfError("Разрешены только файлы с расширением .pdf")
    return normalized


def store_pdf(
    stream: BinaryIO,
    *,
    series_key: str,
    original_filename: str | None,
    content_type: str | None,
) -> StoredFile:
    safe_original_filename = _safe_original_filename(original_filename)
    normalized_content_type = (content_type or "").split(";", maxsplit=1)[0].lower()
    if normalized_content_type and normalized_content_type not in PDF_MIME_TYPES:
        raise InvalidPdfError("Загружаемый файл должен иметь тип PDF")

    stored_filename = f"{uuid4().hex}.pdf"
    storage_key = (Path("documents") / series_key / stored_filename).as_posix()
    destination = resolve_storage_key(storage_key)
    temporary = destination.with_suffix(".pdf.part")
    destination.parent.mkdir(parents=True, exist_ok=True)

    size_bytes = 0
    header = bytearray()
    digest = hashlib.sha256()
    try:
        with temporary.open("xb") as output:
            while chunk := stream.read(CHUNK_SIZE):
                size_bytes += len(chunk)
                if size_bytes > settings.max_pdf_size_bytes:
                    raise PdfTooLargeError(
                        f"Размер PDF превышает ограничение {settings.max_pdf_size_bytes} байт"
                    )
                if len(header) < 5:
                    header.extend(chunk[: 5 - len(header)])
                digest.update(chunk)
                output.write(chunk)

        if bytes(header) != b"%PDF-":
            raise InvalidPdfError("Содержимое файла не соответствует формату PDF")
        temporary.replace(destination)
    except (InvalidPdfError, PdfTooLargeError):
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise StorageError("Не удалось сохранить загруженный PDF") from exc

    return StoredFile(
        storage_key=storage_key,
        original_filename=safe_original_filename,
        size_bytes=size_bytes,
        file_hash=digest.hexdigest(),
        mime_type="application/pdf",
    )


def resolve_storage_key(storage_key: str) -> Path:
    root = settings.upload_dir.resolve()
    path = (root / storage_key).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise InvalidStorageKeyError(
            "Ключ хранения указывает за пределы каталога загрузок"
        ) from exc
    return path


def delete_stored_file(storage_key: str) -> None:
    try:
        resolve_storage_key(storage_key).unlink(missing_ok=True)
    except (InvalidStorageKeyError, OSError):
        return
