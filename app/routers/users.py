from typing import Annotated, Never

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.enums import ProjectRole, UserStatus
from app.database import get_db
from app.services import user_service
from app.services import auth_service
from app.user_schemas import (
    ProjectMembershipCreate,
    ProjectMembershipResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)


router = APIRouter(
    tags=["Пользователи и роли"],
    dependencies=[Depends(auth_service.get_current_user)],
)


def _raise_http_error(exc: Exception) -> Never:
    if isinstance(
        exc,
        (
            user_service.UserNotFoundError,
            user_service.ProjectNotFoundError,
            user_service.MembershipNotFoundError,
        ),
    ):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, user_service.UserConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise exc


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать пользователя",
)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    _current_user=Depends(auth_service.require_system_admin),
) -> UserResponse:
    try:
        return user_service.create_user(db, data)
    except user_service.UserConflictError as exc:
        _raise_http_error(exc)


@router.get("/users", response_model=list[UserResponse], summary="Получить пользователей")
def get_users(
    user_status: Annotated[UserStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
    _current_user=Depends(auth_service.require_system_admin),
) -> list[UserResponse]:
    return user_service.list_users(
        db,
        status=user_status,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/users/{user_id}",
    response_model=UserResponse,
    summary="Получить пользователя",
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> UserResponse:
    if not current_user.is_system_admin and current_user.id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Пользователь может просматривать только свой профиль",
        )
    try:
        return user_service.get_user(db, user_id)
    except user_service.UserNotFoundError as exc:
        _raise_http_error(exc)


@router.patch(
    "/users/{user_id}",
    response_model=UserResponse,
    summary="Изменить пользователя",
)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    _current_user=Depends(auth_service.require_system_admin),
) -> UserResponse:
    try:
        return user_service.update_user(db, user_id, data)
    except (user_service.UserNotFoundError, user_service.UserConflictError) as exc:
        _raise_http_error(exc)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Деактивировать пользователя",
)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.require_system_admin),
) -> Response:
    if current_user.id == user_id:
        raise HTTPException(
            status_code=409,
            detail="Активный администратор не может деактивировать сам себя",
        )
    try:
        user_service.deactivate_user(db, user_id)
    except user_service.UserNotFoundError as exc:
        _raise_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project_id}/members",
    response_model=ProjectMembershipResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить участника проекта",
)
def add_project_member(
    project_id: int,
    data: ProjectMembershipCreate,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> ProjectMembershipResponse:
    auth_service.ensure_project_roles(
        db,
        current_user,
        project_id,
        {ProjectRole.PROJECT_MANAGER},
    )
    try:
        return user_service.add_project_member(db, project_id, data)
    except (
        user_service.UserNotFoundError,
        user_service.ProjectNotFoundError,
        user_service.UserConflictError,
    ) as exc:
        _raise_http_error(exc)


@router.get(
    "/projects/{project_id}/members",
    response_model=list[ProjectMembershipResponse],
    summary="Получить участников проекта",
)
def get_project_members(
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> list[ProjectMembershipResponse]:
    auth_service.ensure_project_roles(db, current_user, project_id)
    try:
        return user_service.list_project_members(db, project_id)
    except user_service.ProjectNotFoundError as exc:
        _raise_http_error(exc)


@router.delete(
    "/projects/{project_id}/members/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить участника из проекта",
)
def remove_project_member(
    project_id: int,
    membership_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> Response:
    auth_service.ensure_project_roles(
        db,
        current_user,
        project_id,
        {ProjectRole.PROJECT_MANAGER},
    )
    try:
        user_service.remove_project_member(db, project_id, membership_id)
    except user_service.MembershipNotFoundError as exc:
        _raise_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
