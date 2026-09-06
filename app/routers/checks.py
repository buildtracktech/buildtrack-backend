from typing import Annotated, Never

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.check_schemas import (
    CheckCreate,
    CheckReportResponse,
    CheckResponse,
    FindingAuditLogResponse,
    FindingResponse,
    FindingStatusUpdate,
)
from app.core.enums import CheckStatus, CheckVerdict, ProjectRole
from app import models
from app.database import get_db
from app.services import auth_service, check_service, report_service


router = APIRouter(
    tags=["Проверки и замечания"],
    dependencies=[Depends(auth_service.get_current_user)],
)


def _raise_http_error(exc: Exception) -> Never:
    if isinstance(
        exc,
        (check_service.CheckNotFoundError, check_service.FindingNotFoundError),
    ):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(
        exc,
        (
            check_service.CheckReferenceError,
            check_service.CheckConfigurationError,
            check_service.FindingTransitionError,
        ),
    ):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, check_service.CheckPersistenceError):
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    raise exc


@router.post(
    "/checks/",
    response_model=CheckResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Запустить проверку документа",
)
def create_check(
    data: CheckCreate,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> CheckResponse:
    try:
        document = (
            db.query(models.Document)
            .filter(models.Document.id == data.document_id)
            .first()
        )
        if document is None:
            raise check_service.CheckReferenceError(
                f"Документ {data.document_id} не найден"
            )
        auth_service.ensure_project_roles(
            db,
            current_user,
            document.project_id,
            {ProjectRole.PROJECT_MANAGER, ProjectRole.INSPECTOR},
        )
        effective_actor_id = auth_service.ensure_actor(
            current_user,
            data.initiated_by_user_id,
        )
        return check_service.create_and_run_check(
            db,
            document_id=data.document_id,
            initiated_by_user_id=effective_actor_id,
        )
    except (
        check_service.CheckReferenceError,
        check_service.CheckConfigurationError,
        check_service.CheckPersistenceError,
    ) as exc:
        _raise_http_error(exc)


@router.get("/checks/", response_model=list[CheckResponse], summary="Получить проверки")
def get_checks(
    project_id: int | None = None,
    stage_id: int | None = None,
    document_id: int | None = None,
    check_status: Annotated[CheckStatus | None, Query(alias="status")] = None,
    verdict: CheckVerdict | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> list[CheckResponse]:
    if project_id is not None:
        auth_service.ensure_project_roles(db, current_user, project_id)
    return check_service.list_checks(
        db,
        project_id=project_id,
        stage_id=stage_id,
        document_id=document_id,
        status=check_status,
        verdict=verdict,
        accessible_project_ids=auth_service.accessible_project_ids(db, current_user),
        offset=offset,
        limit=limit,
    )


@router.get(
    "/checks/{check_id}",
    response_model=CheckResponse,
    summary="Получить проверку",
)
def get_check(
    check_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> CheckResponse:
    try:
        check = check_service.get_check(db, check_id)
        auth_service.ensure_project_roles(db, current_user, check.project_id)
        return check
    except check_service.CheckNotFoundError as exc:
        _raise_http_error(exc)


@router.get(
    "/checks/{check_id}/report",
    response_model=CheckReportResponse,
    summary="Получить отчёт проверки в JSON",
)
def get_check_report(
    check_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> CheckReportResponse:
    try:
        check = check_service.get_check(db, check_id)
        auth_service.ensure_project_roles(db, current_user, check.project_id)
        return check_service.build_check_report(db, check_id)
    except check_service.CheckNotFoundError as exc:
        _raise_http_error(exc)


@router.get(
    "/checks/{check_id}/report.pdf",
    summary="Скачать отчёт проверки в PDF",
)
def download_check_report(
    check_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> Response:
    try:
        check = check_service.get_check(db, check_id)
        auth_service.ensure_project_roles(db, current_user, check.project_id)
    except check_service.CheckNotFoundError as exc:
        _raise_http_error(exc)
    if check.status != CheckStatus.COMPLETED.value:
        raise HTTPException(
            status_code=409,
            detail="PDF-отчёт доступен только для завершённой проверки",
        )
    content = report_service.generate_check_report_pdf(check)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="buildtrack-check-{check.id}-report.pdf"'
            )
        },
    )


@router.patch(
    "/findings/{finding_id}",
    response_model=FindingResponse,
    summary="Рассмотреть замечание",
)
def update_finding(
    finding_id: int,
    data: FindingStatusUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> FindingResponse:
    try:
        finding = check_service.get_finding(db, finding_id)
        auth_service.ensure_project_roles(
            db,
            current_user,
            finding.check.project_id,
            {ProjectRole.INSPECTOR},
        )
        data.changed_by_user_id = auth_service.ensure_actor(
            current_user,
            data.changed_by_user_id,
        )
        return check_service.update_finding_status(db, finding_id, data)
    except (
        check_service.FindingNotFoundError,
        check_service.CheckReferenceError,
        check_service.FindingTransitionError,
        check_service.CheckPersistenceError,
    ) as exc:
        _raise_http_error(exc)


@router.get(
    "/findings/{finding_id}/audit",
    response_model=list[FindingAuditLogResponse],
    summary="Получить историю замечания",
)
def get_finding_audit(
    finding_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> list[FindingAuditLogResponse]:
    try:
        finding = check_service.get_finding(db, finding_id)
        auth_service.ensure_project_roles(db, current_user, finding.check.project_id)
        return check_service.list_finding_audit(db, finding_id)
    except check_service.FindingNotFoundError as exc:
        _raise_http_error(exc)
