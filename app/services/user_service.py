from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app import models
from app.core.enums import UserStatus
from app.user_schemas import ProjectMembershipCreate, UserCreate, UserUpdate
from app.services import auth_service


class UserNotFoundError(ValueError):
    pass


class ProjectNotFoundError(ValueError):
    pass


class MembershipNotFoundError(ValueError):
    pass


class UserConflictError(ValueError):
    pass


def create_user(db: Session, data: UserCreate) -> models.User:
    user = models.User(
        email=data.email,
        full_name=data.full_name,
        status=UserStatus.ACTIVE.value,
        is_system_admin=data.is_system_admin,
        password_hash=(
            auth_service.hash_password(data.password) if data.password is not None else None
        ),
        token_version=0,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise UserConflictError(
            f"Пользователь с адресом {data.email} уже существует"
        ) from exc
    db.refresh(user)
    return user


def get_user(db: Session, user_id: int) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise UserNotFoundError(f"Пользователь {user_id} не найден")
    return user


def list_users(
    db: Session,
    *,
    status: UserStatus | None,
    offset: int,
    limit: int,
) -> list[models.User]:
    query = db.query(models.User)
    if status is not None:
        query = query.filter(models.User.status == status.value)
    return query.order_by(models.User.id.desc()).offset(offset).limit(limit).all()


def update_user(db: Session, user_id: int, data: UserUpdate) -> models.User:
    user = get_user(db, user_id)
    updates = data.model_dump(exclude_unset=True)
    password = updates.pop("password", None)
    if updates.get("email") is None:
        updates.pop("email", None)
    if "status" in updates:
        updates["status"] = updates["status"].value
        if updates["status"] == UserStatus.INACTIVE.value:
            user.token_version += 1
    if password is not None:
        user.password_hash = auth_service.hash_password(password)
        user.token_version += 1
    for field, value in updates.items():
        setattr(user, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise UserConflictError(
            f"Пользователь с адресом {updates.get('email')} уже существует"
        ) from exc
    db.refresh(user)
    return user


def deactivate_user(db: Session, user_id: int) -> None:
    user = get_user(db, user_id)
    user.status = UserStatus.INACTIVE.value
    user.token_version += 1
    db.commit()


def add_project_member(
    db: Session,
    project_id: int,
    data: ProjectMembershipCreate,
) -> models.ProjectMembership:
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise ProjectNotFoundError(f"Проект {project_id} не найден")

    user = get_user(db, data.user_id)
    if user.status != UserStatus.ACTIVE.value:
        raise UserConflictError("Неактивного пользователя нельзя добавить в проект")

    membership = models.ProjectMembership(
        project_id=project_id,
        user_id=data.user_id,
        role=data.role.value,
    )
    db.add(membership)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise UserConflictError("У пользователя уже есть эта роль в проекте") from exc
    return get_project_membership(db, project_id, membership.id)


def get_project_membership(
    db: Session,
    project_id: int,
    membership_id: int,
) -> models.ProjectMembership:
    membership = (
        db.query(models.ProjectMembership)
        .options(joinedload(models.ProjectMembership.user))
        .filter(
            models.ProjectMembership.id == membership_id,
            models.ProjectMembership.project_id == project_id,
        )
        .first()
    )
    if not membership:
        raise MembershipNotFoundError(
            f"Участие {membership_id} не найдено в проекте {project_id}"
        )
    return membership


def list_project_members(
    db: Session,
    project_id: int,
) -> list[models.ProjectMembership]:
    project_exists = db.query(models.Project.id).filter(models.Project.id == project_id).first()
    if not project_exists:
        raise ProjectNotFoundError(f"Проект {project_id} не найден")
    return (
        db.query(models.ProjectMembership)
        .options(joinedload(models.ProjectMembership.user))
        .filter(models.ProjectMembership.project_id == project_id)
        .order_by(models.ProjectMembership.id)
        .all()
    )


def remove_project_member(db: Session, project_id: int, membership_id: int) -> None:
    membership = get_project_membership(db, project_id, membership_id)
    db.delete(membership)
    db.commit()
