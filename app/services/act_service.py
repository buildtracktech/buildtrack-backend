import hashlib
import json
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app import models
from app.act_schemas import AcceptanceActCreate, AcceptanceActStatusUpdate
from app.core.enums import (
    ACCEPTANCE_ACT_STATUS_TRANSITIONS,
    AcceptanceActStatus,
    AcceptanceActType,
    CheckStatus,
    FindingStatus,
    ProjectRole,
    UserStatus,
)
from app.core.time import utc_now


ACT_CREATOR_ROLES = {ProjectRole.PROJECT_MANAGER.value, ProjectRole.INSPECTOR.value}
ACT_APPROVER_ROLES = {
    ProjectRole.PROJECT_MANAGER.value,
    ProjectRole.INSPECTOR.value,
}


class AcceptanceActNotFoundError(LookupError):
    pass


class AcceptanceActReferenceError(ValueError):
    pass


class AcceptanceActAccessError(PermissionError):
    pass


class AcceptanceActTransitionError(ValueError):
    pass


class AcceptanceActConflictError(ValueError):
    pass


class AcceptanceActPersistenceError(RuntimeError):
    pass


def _require_role(
    db: Session,
    project_id: int,
    user_id: int,
    allowed_roles: set[str],
) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise AcceptanceActReferenceError(f"Пользователь {user_id} не найден")
    if user.status != UserStatus.ACTIVE.value:
        raise AcceptanceActAccessError(f"Пользователь {user_id} неактивен")
    if user.is_system_admin:
        return user
    membership = (
        db.query(models.ProjectMembership.id)
        .filter(
            models.ProjectMembership.project_id == project_id,
            models.ProjectMembership.user_id == user_id,
            models.ProjectMembership.role.in_(allowed_roles),
        )
        .first()
    )
    if membership is None:
        allowed = ", ".join(sorted(allowed_roles))
        raise AcceptanceActAccessError(
            f"Пользователю {user_id} требуется одна из ролей проекта: {allowed}"
        )
    return user


def _participant_snapshot(db: Session, project_id: int) -> list[dict]:
    memberships = (
        db.query(models.ProjectMembership)
        .options(joinedload(models.ProjectMembership.user))
        .filter(models.ProjectMembership.project_id == project_id)
        .order_by(models.ProjectMembership.id)
        .all()
    )
    return [
        {
            "membership_id": membership.id,
            "user_id": membership.user_id,
            "full_name": membership.user.full_name,
            "email": membership.user.email,
            "role": membership.role,
        }
        for membership in memberships
    ]


def _finding_snapshot(check: models.Check) -> list[dict]:
    return [
        {
            "finding_id": finding.id,
            "normative_snapshot_id": finding.normative_snapshot_id,
            "kind": finding.kind,
            "severity": finding.severity,
            "status": finding.status,
            "title": finding.title,
            "description": finding.description,
            "recommendation": finding.recommendation,
            "page_number": finding.page_number,
            "evidence_text": finding.evidence_text,
        }
        for finding in check.findings
    ]


def _report_hash(
    check: models.Check,
    participants: list[dict],
    findings: list[dict],
) -> str:
    canonical = json.dumps(
        {
            "check_id": check.id,
            "document_id": check.document_id,
            "document_hash": check.document_hash_snapshot,
            "verdict": check.verdict,
            "participants": participants,
            "findings": findings,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _act_query(db: Session):
    return db.query(models.AcceptanceAct)


def get_acceptance_act(db: Session, act_id: int) -> models.AcceptanceAct:
    act = _act_query(db).filter(models.AcceptanceAct.id == act_id).first()
    if act is None:
        raise AcceptanceActNotFoundError(f"Акт {act_id} не найден")
    return act


def get_completed_check(db: Session, check_id: int) -> models.Check:
    check = (
        db.query(models.Check)
        .options(joinedload(models.Check.findings))
        .filter(models.Check.id == check_id)
        .first()
    )
    if check is None:
        raise AcceptanceActReferenceError(f"Проверка {check_id} не найдена")
    if check.status != CheckStatus.COMPLETED.value or check.verdict is None:
        raise AcceptanceActReferenceError(
            "Для создания акта требуется завершённая проверка"
        )
    return check


def create_acceptance_act(
    db: Session,
    data: AcceptanceActCreate,
) -> models.AcceptanceAct:
    check = get_completed_check(db, data.check_id)
    _require_role(
        db,
        check.project_id,
        data.created_by_user_id,
        ACT_CREATOR_ROLES,
    )
    participants = _participant_snapshot(db, check.project_id)
    findings = _finding_snapshot(check)
    act_number = data.act_number or f"BT-ACT-{check.project_id}-{uuid4().hex[:8].upper()}"
    act = models.AcceptanceAct(
        act_number=act_number,
        version=data.version,
        project_id=check.project_id,
        stage_id=check.stage_id,
        check_id=check.id,
        document_id=check.document_id,
        act_type=data.act_type.value,
        status=AcceptanceActStatus.DRAFT.value,
        work_description=data.work_description,
        period_start=data.period_start,
        period_end=data.period_end,
        participant_snapshot=participants,
        finding_snapshot=findings,
        verification_verdict=check.verdict,
        document_hash=check.document_hash_snapshot,
        report_hash=_report_hash(check, participants, findings),
        created_by_user_id=data.created_by_user_id,
    )
    db.add(act)
    try:
        db.flush()
        db.add(
            models.AcceptanceActAuditLog(
                act_id=act.id,
                old_status=None,
                new_status=AcceptanceActStatus.DRAFT.value,
                comment="Технический акт создан",
                changed_by_user_id=data.created_by_user_id,
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AcceptanceActConflictError(
            f"Акт {act_number} версии {data.version} уже существует"
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise AcceptanceActPersistenceError(
            "Не удалось создать технический акт"
        ) from exc
    db.refresh(act)
    return act


def list_acceptance_acts(
    db: Session,
    *,
    project_id: int | None,
    stage_id: int | None,
    check_id: int | None,
    status: AcceptanceActStatus | None,
    act_type: AcceptanceActType | None,
    accessible_project_ids: set[int] | None,
    offset: int,
    limit: int,
) -> list[models.AcceptanceAct]:
    query = _act_query(db)
    if accessible_project_ids is not None:
        query = query.filter(models.AcceptanceAct.project_id.in_(accessible_project_ids))
    if project_id is not None:
        query = query.filter(models.AcceptanceAct.project_id == project_id)
    if stage_id is not None:
        query = query.filter(models.AcceptanceAct.stage_id == stage_id)
    if check_id is not None:
        query = query.filter(models.AcceptanceAct.check_id == check_id)
    if status is not None:
        query = query.filter(models.AcceptanceAct.status == status.value)
    if act_type is not None:
        query = query.filter(models.AcceptanceAct.act_type == act_type.value)
    return query.order_by(models.AcceptanceAct.id.desc()).offset(offset).limit(limit).all()


def _refresh_draft_snapshot(db: Session, act: models.AcceptanceAct) -> None:
    check = get_completed_check(db, act.check_id)
    participants = _participant_snapshot(db, act.project_id)
    findings = _finding_snapshot(check)
    act.participant_snapshot = participants
    act.finding_snapshot = findings
    act.verification_verdict = check.verdict
    act.document_hash = check.document_hash_snapshot
    act.report_hash = _report_hash(check, participants, findings)


def update_acceptance_act_status(
    db: Session,
    act_id: int,
    data: AcceptanceActStatusUpdate,
) -> models.AcceptanceAct:
    act = get_acceptance_act(db, act_id)
    current = AcceptanceActStatus(act.status)
    target = data.status
    if target not in ACCEPTANCE_ACT_STATUS_TRANSITIONS[current]:
        raise AcceptanceActTransitionError(
            f"Статус акта нельзя изменить с {current.value} на {target.value}"
        )

    allowed_roles = (
        ACT_APPROVER_ROLES
        if target == AcceptanceActStatus.APPROVED
        else ACT_CREATOR_ROLES
    )
    _require_role(db, act.project_id, data.changed_by_user_id, allowed_roles)

    if target == AcceptanceActStatus.READY:
        _refresh_draft_snapshot(db, act)
        blocking = [
            finding
            for finding in act.finding_snapshot
            if finding["status"]
            in {FindingStatus.OPEN.value, FindingStatus.CONFIRMED.value}
        ]
        if act.act_type == AcceptanceActType.STAGE_ACCEPTANCE.value and blocking:
            raise AcceptanceActTransitionError(
                "Акт приёмки этапа нельзя подготовить, пока замечания требуют рассмотрения"
            )
    if target == AcceptanceActStatus.CANCELLED and not data.comment:
        raise AcceptanceActTransitionError("Для отмены необходимо указать причину")

    act.status = target.value
    act.updated_at = utc_now()
    if target == AcceptanceActStatus.APPROVED:
        act.approved_by_user_id = data.changed_by_user_id
        act.approved_at = utc_now()
    if target == AcceptanceActStatus.CANCELLED:
        act.cancellation_reason = data.comment
    db.add(
        models.AcceptanceActAuditLog(
            act_id=act.id,
            old_status=current.value,
            new_status=target.value,
            comment=data.comment,
            changed_by_user_id=data.changed_by_user_id,
        )
    )
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise AcceptanceActPersistenceError(
            "Не удалось обновить технический акт"
        ) from exc
    db.refresh(act)
    return act


def list_acceptance_act_audit(
    db: Session,
    act_id: int,
) -> list[models.AcceptanceActAuditLog]:
    get_acceptance_act(db, act_id)
    return (
        db.query(models.AcceptanceActAuditLog)
        .filter(models.AcceptanceActAuditLog.act_id == act_id)
        .order_by(models.AcceptanceActAuditLog.id)
        .all()
    )
