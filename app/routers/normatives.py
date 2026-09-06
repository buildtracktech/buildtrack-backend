from typing import Annotated, Never

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.normative_schemas import (
    NormativeCreate,
    NormativeResponse,
    NormativeStatus,
    NormativeUpdate,
    NormativeVersionCreate,
)
from app.services import normative_service
from app.services import auth_service


router = APIRouter(
    prefix="/normatives",
    tags=["Нормативные правила"],
    dependencies=[Depends(auth_service.get_current_user)],
)


def _raise_http_error(exc: Exception) -> Never:
    if isinstance(exc, normative_service.NormativeNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, normative_service.StageSelectionError):
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Один или несколько этапов не найдены",
                "missing_stage_ids": exc.missing_stage_ids,
            },
        ) from exc
    if isinstance(exc, normative_service.NormativeVersionConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise exc


@router.post(
    "/",
    response_model=NormativeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать нормативное правило",
)
def create_normative(
    data: NormativeCreate,
    db: Session = Depends(get_db),
    _current_user=Depends(auth_service.require_system_admin),
) -> NormativeResponse:
    try:
        return normative_service.create_normative(db, data)
    except (
        normative_service.StageSelectionError,
        normative_service.NormativeVersionConflictError,
    ) as exc:
        _raise_http_error(exc)


@router.get(
    "/",
    response_model=list[NormativeResponse],
    summary="Получить нормативные правила",
)
def get_normatives(
    stage_id: int | None = None,
    normative_status: Annotated[NormativeStatus | None, Query(alias="status")] = None,
    family_key: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
) -> list[NormativeResponse]:
    return normative_service.list_normatives(
        db,
        stage_id=stage_id,
        status=normative_status,
        family_key=family_key,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{normative_id}/versions",
    response_model=NormativeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новую версию правила",
)
def create_normative_version(
    normative_id: int,
    data: NormativeVersionCreate,
    db: Session = Depends(get_db),
    _current_user=Depends(auth_service.require_system_admin),
) -> NormativeResponse:
    try:
        return normative_service.create_normative_version(db, normative_id, data)
    except (
        normative_service.NormativeNotFoundError,
        normative_service.StageSelectionError,
        normative_service.NormativeVersionConflictError,
    ) as exc:
        _raise_http_error(exc)


@router.get(
    "/{normative_id}",
    response_model=NormativeResponse,
    summary="Получить нормативное правило",
)
def get_normative(
    normative_id: int,
    db: Session = Depends(get_db),
) -> NormativeResponse:
    try:
        return normative_service.get_normative(db, normative_id)
    except normative_service.NormativeNotFoundError as exc:
        _raise_http_error(exc)


@router.patch(
    "/{normative_id}",
    response_model=NormativeResponse,
    summary="Изменить нормативное правило",
)
def update_normative(
    normative_id: int,
    data: NormativeUpdate,
    db: Session = Depends(get_db),
    _current_user=Depends(auth_service.require_system_admin),
) -> NormativeResponse:
    try:
        return normative_service.update_normative(db, normative_id, data)
    except (
        normative_service.NormativeNotFoundError,
        normative_service.StageSelectionError,
    ) as exc:
        _raise_http_error(exc)


@router.delete(
    "/{normative_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Деактивировать нормативное правило",
)
def delete_normative(
    normative_id: int,
    db: Session = Depends(get_db),
    _current_user=Depends(auth_service.require_system_admin),
) -> Response:
    try:
        normative_service.deactivate_normative(db, normative_id)
    except normative_service.NormativeNotFoundError as exc:
        _raise_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
