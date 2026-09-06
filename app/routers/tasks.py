from typing import Annotated, Never

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.enums import ProjectRole, TaskStatus
from app.database import get_db
from app.services import auth_service, task_service
from app.task_schemas import (
    TaskAuditLogResponse,
    TaskCreate,
    TaskResponse,
    TaskStatusUpdate,
    TaskUpdate,
)


router = APIRouter(
    prefix="/tasks",
    tags=["Задачи"],
    dependencies=[Depends(auth_service.get_current_user)],
)


TASK_FULL_VIEW_ROLES = {
    ProjectRole.INVESTOR,
    ProjectRole.PROJECT_MANAGER,
    ProjectRole.INSPECTOR,
}
TASK_EXECUTOR_ROLES = {
    ProjectRole.CONTRACTOR,
    ProjectRole.SERVICE_AGENT,
}


def _ensure_task_visible(db: Session, current_user, task) -> set[ProjectRole]:
    roles = auth_service.ensure_project_roles(
        db,
        current_user,
        task.project_id,
    )
    if current_user.is_system_admin or not roles.isdisjoint(TASK_FULL_VIEW_ROLES):
        return roles
    if (
        task.assigned_to_user_id == current_user.id
        and not roles.isdisjoint(TASK_EXECUTOR_ROLES)
    ):
        return roles
    raise HTTPException(
        status_code=403,
        detail="Исполнитель может просматривать только назначенные ему задачи",
    )


def _ensure_status_transition_allowed(
    current_user,
    task,
    roles: set[ProjectRole],
    target_status: TaskStatus,
) -> None:
    if current_user.is_system_admin or ProjectRole.PROJECT_MANAGER in roles:
        return
    if ProjectRole.INSPECTOR in roles and target_status in {
        TaskStatus.VERIFIED,
        TaskStatus.REJECTED,
    }:
        return
    if (
        not roles.isdisjoint(TASK_EXECUTOR_ROLES)
        and task.assigned_to_user_id == current_user.id
        and target_status
        in {
            TaskStatus.ACTIVE,
            TaskStatus.PENDING_VERIFICATION,
        }
    ):
        return
    raise HTTPException(
        status_code=403,
        detail="Текущая роль в проекте не может выполнить этот переход задачи",
    )


def _raise_http_error(exc: Exception) -> Never:
    if isinstance(exc, task_service.TaskNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, task_service.TaskReferenceError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, task_service.TaskTransitionError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise exc


@router.post(
    "/",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать задачу",
)
def create_task(
    data: TaskCreate,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> TaskResponse:
    try:
        auth_service.ensure_project_roles(
            db,
            current_user,
            data.project_id,
            {ProjectRole.PROJECT_MANAGER, ProjectRole.INSPECTOR},
        )
        data.created_by_user_id = auth_service.ensure_actor(
            current_user,
            data.created_by_user_id,
        )
        return task_service.create_task(db, data)
    except task_service.TaskReferenceError as exc:
        _raise_http_error(exc)


@router.get("/", response_model=list[TaskResponse], summary="Получить задачи")
def get_tasks(
    project_id: int | None = None,
    stage_id: int | None = None,
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
    assigned_to_user_id: int | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> list[TaskResponse]:
    if project_id is not None:
        auth_service.ensure_project_roles(db, current_user, project_id)
    full_access_project_ids = auth_service.project_ids_for_roles(
        db,
        current_user,
        TASK_FULL_VIEW_ROLES,
    )
    return task_service.list_tasks(
        db,
        project_id=project_id,
        stage_id=stage_id,
        status=task_status,
        assigned_to_user_id=assigned_to_user_id,
        accessible_project_ids=auth_service.accessible_project_ids(db, current_user),
        full_access_project_ids=full_access_project_ids,
        current_user_id=None if current_user.is_system_admin else current_user.id,
        offset=offset,
        limit=limit,
    )


@router.get("/{task_id}", response_model=TaskResponse, summary="Получить задачу")
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> TaskResponse:
    try:
        task = task_service.get_task(db, task_id)
        _ensure_task_visible(db, current_user, task)
        return task
    except task_service.TaskNotFoundError as exc:
        _raise_http_error(exc)


@router.patch("/{task_id}", response_model=TaskResponse, summary="Изменить задачу")
def update_task(
    task_id: int,
    data: TaskUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> TaskResponse:
    try:
        task = task_service.get_task(db, task_id)
        auth_service.ensure_project_roles(
            db,
            current_user,
            task.project_id,
            {ProjectRole.PROJECT_MANAGER, ProjectRole.INSPECTOR},
        )
        return task_service.update_task(db, task_id, data)
    except (
        task_service.TaskNotFoundError,
        task_service.TaskReferenceError,
    ) as exc:
        _raise_http_error(exc)


@router.patch(
    "/{task_id}/status",
    response_model=TaskResponse,
    summary="Изменить статус задачи",
)
def update_task_status(
    task_id: int,
    data: TaskStatusUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> TaskResponse:
    try:
        task = task_service.get_task(db, task_id)
        roles = _ensure_task_visible(db, current_user, task)
        _ensure_status_transition_allowed(current_user, task, roles, data.status)
        data.changed_by_user_id = auth_service.ensure_actor(
            current_user,
            data.changed_by_user_id,
        )
        return task_service.update_task_status(db, task_id, data)
    except (
        task_service.TaskNotFoundError,
        task_service.TaskReferenceError,
        task_service.TaskTransitionError,
    ) as exc:
        _raise_http_error(exc)


@router.get(
    "/{task_id}/audit",
    response_model=list[TaskAuditLogResponse],
    summary="Получить историю задачи",
)
def get_task_audit(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
) -> list[TaskAuditLogResponse]:
    try:
        task = task_service.get_task(db, task_id)
        _ensure_task_visible(db, current_user, task)
        return task_service.list_task_audit(db, task_id)
    except task_service.TaskNotFoundError as exc:
        _raise_http_error(exc)
