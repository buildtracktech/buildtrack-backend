from typing import Annotated, Never

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.document_schemas import DocumentResponse, DocumentStatus
from app.core.enums import ProjectRole
from app.services import auth_service, document_service, storage_service


router = APIRouter(
    prefix="/documents",
    tags=["Документы"],
    dependencies=[Depends(auth_service.get_current_user)],
)


def _raise_http_error(exc: Exception) -> Never:
    if isinstance(
        exc,
        (
            document_service.DocumentNotFoundError,
            document_service.ProjectNotFoundError,
            document_service.UploaderNotFoundError,
        ),
    ):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, document_service.StageProjectMismatchError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, document_service.UploaderAccessError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, document_service.DocumentVersionConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, document_service.InvalidDocumentMetadataError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, storage_service.InvalidPdfError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, storage_service.PdfTooLargeError):
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    if isinstance(
        exc,
        (storage_service.StorageError, document_service.DocumentPersistenceError),
    ):
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    raise exc


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить PDF-документ",
)
def upload_document(
    project_id: Annotated[int, Form(gt=0)],
    stage_id: Annotated[int, Form(gt=0)],
    title: Annotated[str, Form(min_length=1, max_length=255)],
    version: Annotated[str, Form(min_length=1, max_length=50)],
    file: Annotated[UploadFile, File()],
    document_type: Annotated[
        str,
        Form(min_length=1, max_length=100),
    ] = "project_documentation",
    uploaded_by_user_id: Annotated[int | None, Form(gt=0)] = None,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> DocumentResponse:
    auth_service.ensure_project_roles(
        db,
        current_user,
        project_id,
        {
            ProjectRole.PROJECT_MANAGER,
            ProjectRole.INSPECTOR,
            ProjectRole.CONTRACTOR,
        },
    )
    effective_uploader_id = auth_service.ensure_actor(
        current_user,
        uploaded_by_user_id,
    )
    try:
        return document_service.create_document(
            db,
            project_id=project_id,
            stage_id=stage_id,
            title=title.strip(),
            document_type=document_type.strip(),
            version=version.strip(),
            uploader_id=effective_uploader_id,
            stream=file.file,
            original_filename=file.filename,
            content_type=file.content_type,
        )
    except (
        document_service.ProjectNotFoundError,
        document_service.StageProjectMismatchError,
        document_service.UploaderNotFoundError,
        document_service.UploaderAccessError,
        document_service.DocumentVersionConflictError,
        document_service.DocumentPersistenceError,
        document_service.InvalidDocumentMetadataError,
        storage_service.InvalidPdfError,
        storage_service.PdfTooLargeError,
        storage_service.StorageError,
    ) as exc:
        _raise_http_error(exc)


@router.get("/", response_model=list[DocumentResponse], summary="Получить документы")
def get_documents(
    project_id: int | None = None,
    stage_id: int | None = None,
    document_status: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    series_key: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> list[DocumentResponse]:
    if project_id is not None:
        auth_service.ensure_project_roles(db, current_user, project_id)
    return document_service.list_documents(
        db,
        project_id=project_id,
        stage_id=stage_id,
        status=document_status,
        series_key=series_key,
        accessible_project_ids=auth_service.accessible_project_ids(db, current_user),
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{document_id}/versions",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить новую версию документа",
)
def upload_document_version(
    document_id: int,
    version: Annotated[str, Form(min_length=1, max_length=50)],
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(min_length=1, max_length=255)] = None,
    document_type: Annotated[
        str | None,
        Form(min_length=1, max_length=100),
    ] = None,
    uploaded_by_user_id: Annotated[int | None, Form(gt=0)] = None,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> DocumentResponse:
    try:
        previous = document_service.get_document(db, document_id)
        auth_service.ensure_project_roles(
            db,
            current_user,
            previous.project_id,
            {
                ProjectRole.PROJECT_MANAGER,
                ProjectRole.INSPECTOR,
                ProjectRole.CONTRACTOR,
            },
        )
        effective_uploader_id = auth_service.ensure_actor(
            current_user,
            uploaded_by_user_id,
        )
        return document_service.create_document_version(
            db,
            document_id,
            version=version.strip(),
            title=title.strip() if title else None,
            document_type=document_type.strip() if document_type else None,
            uploader_id=effective_uploader_id,
            stream=file.file,
            original_filename=file.filename,
            content_type=file.content_type,
        )
    except (
        document_service.DocumentNotFoundError,
        document_service.UploaderNotFoundError,
        document_service.UploaderAccessError,
        document_service.DocumentVersionConflictError,
        document_service.DocumentPersistenceError,
        document_service.InvalidDocumentMetadataError,
        storage_service.InvalidPdfError,
        storage_service.PdfTooLargeError,
        storage_service.StorageError,
    ) as exc:
        _raise_http_error(exc)


@router.get(
    "/{document_id}/versions",
    response_model=list[DocumentResponse],
    summary="Получить версии документа",
)
def get_document_versions(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> list[DocumentResponse]:
    try:
        document = document_service.get_document(db, document_id)
        auth_service.ensure_project_roles(db, current_user, document.project_id)
        return document_service.list_document_versions(db, document_id)
    except document_service.DocumentNotFoundError as exc:
        _raise_http_error(exc)


@router.get("/{document_id}/download", summary="Скачать документ")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> FileResponse:
    try:
        document = document_service.get_document(db, document_id)
        auth_service.ensure_project_roles(db, current_user, document.project_id)
        path = storage_service.resolve_storage_key(document.storage_key)
    except document_service.DocumentNotFoundError as exc:
        _raise_http_error(exc)
    except storage_service.InvalidStorageKeyError as exc:
        raise HTTPException(
            status_code=500,
            detail="Некорректный ключ хранения документа",
        ) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Файл документа не найден в хранилище")
    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename=document.original_filename,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Получить документ",
)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> DocumentResponse:
    try:
        document = document_service.get_document(db, document_id)
        auth_service.ensure_project_roles(db, current_user, document.project_id)
        return document
    except document_service.DocumentNotFoundError as exc:
        _raise_http_error(exc)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Деактивировать документ",
)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> Response:
    try:
        document = document_service.get_document(db, document_id)
        auth_service.ensure_project_roles(
            db,
            current_user,
            document.project_id,
            {ProjectRole.PROJECT_MANAGER},
        )
        document_service.deactivate_document(db, document_id)
    except (
        document_service.DocumentNotFoundError,
        document_service.DocumentPersistenceError,
    ) as exc:
        _raise_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
