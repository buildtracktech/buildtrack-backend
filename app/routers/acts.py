from typing import Annotated, Never

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.act_schemas import (
    AcceptanceActAuditLogResponse,
    AcceptanceActCreate,
    AcceptanceActResponse,
    AcceptanceActStatusUpdate,
)
from app.core.enums import AcceptanceActStatus, AcceptanceActType
from app.database import get_db
from app.services import act_service, auth_service


router = APIRouter(
    prefix="/acts",
    tags=["Технические акты"],
    dependencies=[Depends(auth_service.get_current_user)],
)


def _raise_http_error(exc: Exception) -> Never:
    if isinstance(exc, act_service.AcceptanceActNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, act_service.AcceptanceActAccessError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(
        exc,
        (
            act_service.AcceptanceActReferenceError,
            act_service.AcceptanceActTransitionError,
            act_service.AcceptanceActConflictError,
        ),
    ):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, act_service.AcceptanceActPersistenceError):
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    raise exc


@router.post(
    "/",
    response_model=AcceptanceActResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать технический акт",
)
def create_acceptance_act(
    data: AcceptanceActCreate,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> AcceptanceActResponse:
    try:
        check = act_service.get_completed_check(db, data.check_id)
        auth_service.ensure_project_roles(
            db,
            current_user,
            check.project_id,
        )
        data.created_by_user_id = auth_service.ensure_actor(
            current_user,
            data.created_by_user_id,
        )
        return act_service.create_acceptance_act(db, data)
    except (
        act_service.AcceptanceActReferenceError,
        act_service.AcceptanceActAccessError,
        act_service.AcceptanceActConflictError,
        act_service.AcceptanceActPersistenceError,
    ) as exc:
        _raise_http_error(exc)


@router.get("/", response_model=list[AcceptanceActResponse], summary="Получить акты")
def get_acceptance_acts(
    project_id: int | None = None,
    stage_id: int | None = None,
    check_id: int | None = None,
    act_status: Annotated[AcceptanceActStatus | None, Query(alias="status")] = None,
    act_type: AcceptanceActType | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> list[AcceptanceActResponse]:
    if project_id is not None:
        auth_service.ensure_project_roles(db, current_user, project_id)
    return act_service.list_acceptance_acts(
        db,
        project_id=project_id,
        stage_id=stage_id,
        check_id=check_id,
        status=act_status,
        act_type=act_type,
        accessible_project_ids=auth_service.accessible_project_ids(db, current_user),
        offset=offset,
        limit=limit,
    )


@router.get("/{act_id}", response_model=AcceptanceActResponse, summary="Получить акт")
def get_acceptance_act(
    act_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> AcceptanceActResponse:
    try:
        act = act_service.get_acceptance_act(db, act_id)
        auth_service.ensure_project_roles(db, current_user, act.project_id)
        return act
    except act_service.AcceptanceActNotFoundError as exc:
        _raise_http_error(exc)


@router.patch(
    "/{act_id}/status",
    response_model=AcceptanceActResponse,
    summary="Изменить статус акта",
)
def update_acceptance_act_status(
    act_id: int,
    data: AcceptanceActStatusUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> AcceptanceActResponse:
    try:
        act = act_service.get_acceptance_act(db, act_id)
        auth_service.ensure_project_roles(db, current_user, act.project_id)
        data.changed_by_user_id = auth_service.ensure_actor(
            current_user,
            data.changed_by_user_id,
        )
        return act_service.update_acceptance_act_status(db, act_id, data)
    except (
        act_service.AcceptanceActNotFoundError,
        act_service.AcceptanceActReferenceError,
        act_service.AcceptanceActAccessError,
        act_service.AcceptanceActTransitionError,
        act_service.AcceptanceActPersistenceError,
    ) as exc:
        _raise_http_error(exc)


@router.get(
    "/{act_id}/audit",
    response_model=list[AcceptanceActAuditLogResponse],
    summary="Получить историю акта",
)
def get_acceptance_act_audit(
    act_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> list[AcceptanceActAuditLogResponse]:
    try:
        act = act_service.get_acceptance_act(db, act_id)
        auth_service.ensure_project_roles(db, current_user, act.project_id)
        return act_service.list_acceptance_act_audit(db, act_id)
    except act_service.AcceptanceActNotFoundError as exc:
        _raise_http_error(exc)
