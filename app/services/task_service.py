from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.core.enums import ProjectRole, TASK_STATUS_TRANSITIONS, TaskStatus, UserStatus
from app.core.time import utc_now
from app.task_schemas import TaskCreate, TaskStatusUpdate, TaskUpdate


class TaskNotFoundError(ValueError):
    pass


class TaskReferenceError(ValueError):
    pass


class TaskTransitionError(ValueError):
    pass


def _get_user(db: Session, user_id: int, label: str) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise TaskReferenceError(f"Пользователь ({label}) {user_id} не найден")
    if user.status != UserStatus.ACTIVE.value:
        raise TaskReferenceError(f"Пользователь ({label}) {user_id} неактивен")
    return user


def _require_project_access(
    db: Session,
    project_id: int,
    user_id: int,
    label: str,
) -> models.User:
    user = _get_user(db, user_id, label)
    if user.is_system_admin:
        return user
    membership = (
        db.query(models.ProjectMembership.id)
        .filter(
            models.ProjectMembership.project_id == project_id,
            models.ProjectMembership.user_id == user_id,
        )
        .first()
    )
    if not membership:
        raise TaskReferenceError(
            f"Пользователь ({label}) {user_id} не является участником проекта"
        )
    return user


def _require_assignable_project_member(
    db: Session,
    project_id: int,
    user_id: int,
) -> models.User:
    user = _require_project_access(db, project_id, user_id, "исполнитель")
    if user.is_system_admin:
        return user
    assignable_roles = {
        ProjectRole.PROJECT_MANAGER.value,
        ProjectRole.INSPECTOR.value,
        ProjectRole.CONTRACTOR.value,
        ProjectRole.SERVICE_AGENT.value,
    }
    membership = (
        db.query(models.ProjectMembership.id)
        .filter(
            models.ProjectMembership.project_id == project_id,
            models.ProjectMembership.user_id == user_id,
            models.ProjectMembership.role.in_(assignable_roles),
        )
        .first()
    )
    if membership is None:
        raise TaskReferenceError(
            "Исполнителю нужна рабочая роль в проекте; роль инвестора доступна "
            "только для просмотра"
        )
    return user


def _validate_project_and_stage(
    db: Session,
    project_id: int,
    stage_id: int | None,
) -> None:
    project = db.query(models.Project.id).filter(models.Project.id == project_id).first()
    if not project:
        raise TaskReferenceError(f"Проект {project_id} не найден")
    if stage_id is None:
        return
    stage = db.query(models.Stage).filter(models.Stage.id == stage_id).first()
    if not stage:
        raise TaskReferenceError(f"Этап {stage_id} не найден")
    if stage.project_id != project_id:
        raise TaskReferenceError(
            f"Этап {stage_id} не относится к проекту {project_id}"
        )


def get_task(db: Session, task_id: int) -> models.Task:
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise TaskNotFoundError(f"Задача {task_id} не найдена")
    return task


def create_task(db: Session, data: TaskCreate) -> models.Task:
    _validate_project_and_stage(db, data.project_id, data.stage_id)
    if data.assigned_to_user_id is not None:
        _require_assignable_project_member(
            db, data.project_id, data.assigned_to_user_id
        )
    if data.created_by_user_id is not None:
        _require_project_access(
            db,
            data.project_id,
            data.created_by_user_id,
            "автор",
        )

    task = models.Task(
        project_id=data.project_id,
        stage_id=data.stage_id,
        title=data.title,
        description=data.description,
        status=TaskStatus.CREATED.value,
        priority=data.priority.value,
        assigned_to_user_id=data.assigned_to_user_id,
        created_by_user_id=data.created_by_user_id,
        due_at=data.due_at,
    )
    db.add(task)
    db.flush()
    db.add(
        models.TaskAuditLog(
            task_id=task.id,
            old_status=None,
            new_status=TaskStatus.CREATED.value,
            comment="Задача создана",
            changed_by_user_id=data.created_by_user_id,
        )
    )
    db.commit()
    db.refresh(task)
    return task


def list_tasks(
    db: Session,
    *,
    project_id: int | None,
    stage_id: int | None,
    status: TaskStatus | None,
    assigned_to_user_id: int | None,
    accessible_project_ids: set[int] | None,
    full_access_project_ids: set[int] | None,
    current_user_id: int | None,
    offset: int,
    limit: int,
) -> list[models.Task]:
    query = db.query(models.Task)
    if accessible_project_ids is not None:
        query = query.filter(models.Task.project_id.in_(accessible_project_ids))
        visibility = []
        if full_access_project_ids:
            visibility.append(models.Task.project_id.in_(full_access_project_ids))
        if current_user_id is not None:
            visibility.append(models.Task.assigned_to_user_id == current_user_id)
        if not visibility:
            return []
        query = query.filter(or_(*visibility))
    if project_id is not None:
        query = query.filter(models.Task.project_id == project_id)
    if stage_id is not None:
        query = query.filter(models.Task.stage_id == stage_id)
    if status is not None:
        query = query.filter(models.Task.status == status.value)
    if assigned_to_user_id is not None:
        query = query.filter(models.Task.assigned_to_user_id == assigned_to_user_id)
    return query.order_by(models.Task.id.desc()).offset(offset).limit(limit).all()


def update_task(db: Session, task_id: int, data: TaskUpdate) -> models.Task:
    task = get_task(db, task_id)
    updates = data.model_dump(exclude_unset=True)
    if "assigned_to_user_id" in updates and updates["assigned_to_user_id"] is not None:
        _require_assignable_project_member(
            db, task.project_id, updates["assigned_to_user_id"]
        )
    if "priority" in updates:
        updates["priority"] = updates["priority"].value
    for field, value in updates.items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


def update_task_status(
    db: Session,
    task_id: int,
    data: TaskStatusUpdate,
) -> models.Task:
    task = get_task(db, task_id)
    current_status = TaskStatus(task.status)
    target_status = data.status
    if target_status not in TASK_STATUS_TRANSITIONS[current_status]:
        raise TaskTransitionError(
            f"Статус задачи нельзя изменить с {current_status.value} "
            f"на {target_status.value}"
        )
    if data.changed_by_user_id is not None:
        _require_project_access(
            db,
            task.project_id,
            data.changed_by_user_id,
            "участник действия",
        )

    task.status = target_status.value
    task.completed_at = utc_now() if target_status == TaskStatus.VERIFIED else None
    db.add(
        models.TaskAuditLog(
            task_id=task.id,
            old_status=current_status.value,
            new_status=target_status.value,
            comment=data.comment,
            changed_by_user_id=data.changed_by_user_id,
        )
    )
    db.commit()
    db.refresh(task)
    return task


def list_task_audit(db: Session, task_id: int) -> list[models.TaskAuditLog]:
    get_task(db, task_id)
    return (
        db.query(models.TaskAuditLog)
        .filter(models.TaskAuditLog.task_id == task_id)
        .order_by(models.TaskAuditLog.id)
        .all()
    )
