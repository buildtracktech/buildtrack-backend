from typing import BinaryIO
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import Document, Project, ProjectMembership, Stage, User
from app.services import storage_service


class DocumentNotFoundError(LookupError):
    pass


class ProjectNotFoundError(LookupError):
    pass


class StageProjectMismatchError(ValueError):
    pass


class UploaderNotFoundError(LookupError):
    pass


class UploaderAccessError(PermissionError):
    pass


class DocumentVersionConflictError(ValueError):
    pass


class DocumentPersistenceError(RuntimeError):
    pass


class InvalidDocumentMetadataError(ValueError):
    pass


def _required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        field_labels = {
            "title": "Название",
            "document_type": "Тип документа",
            "version": "Версия",
        }
        raise InvalidDocumentMetadataError(
            f"Поле «{field_labels.get(field_name, field_name)}» не может быть пустым"
        )
    return cleaned


def _optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _get_document_or_raise(db: Session, document_id: int) -> Document:
    document = db.query(Document).filter(Document.id == document_id).first()
    if document is None:
        raise DocumentNotFoundError(f"Документ {document_id} не найден")
    return document


def _validate_project_stage(db: Session, project_id: int, stage_id: int) -> None:
    if db.query(Project.id).filter(Project.id == project_id).first() is None:
        raise ProjectNotFoundError(f"Проект {project_id} не найден")
    stage = db.query(Stage.id, Stage.project_id).filter(Stage.id == stage_id).first()
    if stage is None:
        raise StageProjectMismatchError(f"Этап {stage_id} не найден")
    if stage.project_id != project_id:
        raise StageProjectMismatchError(
            f"Этап {stage_id} не относится к проекту {project_id}"
        )


def _validate_uploader(
    db: Session,
    uploader_id: int | None,
    project_id: int,
) -> None:
    if uploader_id is None:
        return
    user = db.query(User).filter(User.id == uploader_id).first()
    if user is None:
        raise UploaderNotFoundError(f"Пользователь {uploader_id} не найден")
    if user.status != "active":
        raise UploaderAccessError("Неактивный пользователь не может загружать документы")
    if user.is_system_admin:
        return
    membership_exists = (
        db.query(ProjectMembership.id)
        .filter(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == uploader_id,
        )
        .first()
    )
    if membership_exists is None:
        raise UploaderAccessError(
            f"Пользователь {uploader_id} не является участником проекта {project_id}"
        )


def _ensure_version_available(db: Session, series_key: str, version: str) -> None:
    exists = (
        db.query(Document.id)
        .filter(Document.series_key == series_key, Document.version == version)
        .first()
    )
    if exists:
        raise DocumentVersionConflictError(
            f"Версия {version} уже существует в серии документов {series_key}"
        )


def _commit_document(
    db: Session,
    document: Document,
    storage_key: str,
) -> Document:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        storage_service.delete_stored_file(storage_key)
        raise DocumentVersionConflictError(
            "Такая версия уже существует в этой серии документов"
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        storage_service.delete_stored_file(storage_key)
        raise DocumentPersistenceError("Не удалось сохранить сведения о документе") from exc
    db.refresh(document)
    return document


def create_document(
    db: Session,
    *,
    project_id: int,
    stage_id: int,
    title: str,
    document_type: str,
    version: str,
    uploader_id: int | None,
    stream: BinaryIO,
    original_filename: str | None,
    content_type: str | None,
) -> Document:
    title = _required_text(title, "title")
    document_type = _required_text(document_type, "document_type")
    version = _required_text(version, "version")
    _validate_project_stage(db, project_id, stage_id)
    _validate_uploader(db, uploader_id, project_id)
    series_key = uuid4().hex
    stored = storage_service.store_pdf(
        stream,
        series_key=series_key,
        original_filename=original_filename,
        content_type=content_type,
    )
    document = Document(
        series_key=series_key,
        project_id=project_id,
        stage_id=stage_id,
        uploaded_by_user_id=uploader_id,
        title=title,
        document_type=document_type,
        version=version,
        original_filename=stored.original_filename,
        storage_key=stored.storage_key,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        file_hash=stored.file_hash,
        status="active",
    )
    db.add(document)
    return _commit_document(db, document, stored.storage_key)


def create_document_version(
    db: Session,
    document_id: int,
    *,
    version: str,
    title: str | None,
    document_type: str | None,
    uploader_id: int | None,
    stream: BinaryIO,
    original_filename: str | None,
    content_type: str | None,
) -> Document:
    version = _required_text(version, "version")
    title = _optional_text(title, "title")
    document_type = _optional_text(document_type, "document_type")
    previous = _get_document_or_raise(db, document_id)
    if previous.status != "active":
        raise DocumentVersionConflictError(
            "Новую версию можно создать только на основе активной версии документа"
        )
    _ensure_version_available(db, previous.series_key, version)
    _validate_uploader(db, uploader_id, previous.project_id)
    stored = storage_service.store_pdf(
        stream,
        series_key=previous.series_key,
        original_filename=original_filename,
        content_type=content_type,
    )

    active_versions = (
        db.query(Document)
        .filter(
            Document.series_key == previous.series_key,
            Document.status == "active",
        )
        .all()
    )
    for active_version in active_versions:
        active_version.status = "inactive"
        active_version.updated_at = utc_now()

    document = Document(
        series_key=previous.series_key,
        supersedes_id=previous.id,
        project_id=previous.project_id,
        stage_id=previous.stage_id,
        uploaded_by_user_id=uploader_id,
        title=title or previous.title,
        document_type=document_type or previous.document_type,
        version=version,
        original_filename=stored.original_filename,
        storage_key=stored.storage_key,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        file_hash=stored.file_hash,
        status="active",
    )
    db.add(document)
    return _commit_document(db, document, stored.storage_key)


def list_documents(
    db: Session,
    *,
    project_id: int | None,
    stage_id: int | None,
    status: str | None,
    series_key: str | None,
    accessible_project_ids: set[int] | None,
    offset: int,
    limit: int,
) -> list[Document]:
    query = db.query(Document)
    if accessible_project_ids is not None:
        query = query.filter(Document.project_id.in_(accessible_project_ids))
    if project_id is not None:
        query = query.filter(Document.project_id == project_id)
    if stage_id is not None:
        query = query.filter(Document.stage_id == stage_id)
    if status is not None:
        query = query.filter(Document.status == status)
    if series_key is not None:
        query = query.filter(Document.series_key == series_key)
    return query.order_by(Document.id.desc()).offset(offset).limit(limit).all()


def list_document_versions(db: Session, document_id: int) -> list[Document]:
    document = _get_document_or_raise(db, document_id)
    return (
        db.query(Document)
        .filter(Document.series_key == document.series_key)
        .order_by(Document.id.desc())
        .all()
    )


def get_document(db: Session, document_id: int) -> Document:
    return _get_document_or_raise(db, document_id)


def deactivate_document(db: Session, document_id: int) -> None:
    document = _get_document_or_raise(db, document_id)
    document.status = "inactive"
    document.updated_at = utc_now()
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise DocumentPersistenceError("Не удалось деактивировать документ") from exc
