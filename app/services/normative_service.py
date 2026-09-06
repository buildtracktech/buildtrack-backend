from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.models import Normative, Stage
from app.normative_schemas import (
    NormativeCreate,
    NormativeUpdate,
    NormativeVersionCreate,
)


class NormativeNotFoundError(LookupError):
    pass


class NormativeVersionConflictError(ValueError):
    pass


class StageSelectionError(LookupError):
    def __init__(self, missing_stage_ids: list[int]) -> None:
        self.missing_stage_ids = missing_stage_ids
        super().__init__(f"Не найдены этапы: {missing_stage_ids}")


def _load_stages(db: Session, stage_ids: list[int]) -> list[Stage]:
    unique_stage_ids = sorted(set(stage_ids))
    stages = (
        db.query(Stage)
        .filter(Stage.id.in_(unique_stage_ids))
        .order_by(Stage.id)
        .all()
    )
    found_ids = {stage.id for stage in stages}
    missing_ids = [stage_id for stage_id in unique_stage_ids if stage_id not in found_ids]
    if missing_ids:
        raise StageSelectionError(missing_ids)
    return stages


def _get_normative_or_raise(db: Session, normative_id: int) -> Normative:
    normative = (
        db.query(Normative)
        .options(selectinload(Normative.stages))
        .filter(Normative.id == normative_id)
        .first()
    )
    if normative is None:
        raise NormativeNotFoundError(f"Нормативное правило {normative_id} не найдено")
    return normative


def _ensure_version_available(db: Session, family_key: str, version: str) -> None:
    exists = (
        db.query(Normative.id)
        .filter(
            Normative.family_key == family_key,
            Normative.version == version,
        )
        .first()
    )
    if exists:
        raise NormativeVersionConflictError(
            f"Версия {version} уже существует в серии правил {family_key}"
        )


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise NormativeVersionConflictError(
            "Такая версия уже существует в этой серии нормативных правил"
        ) from exc


def create_normative(db: Session, data: NormativeCreate) -> Normative:
    stages = _load_stages(db, data.stage_ids)
    family_key = uuid4().hex
    _ensure_version_available(db, family_key, data.version)

    normative = Normative(
        family_key=family_key,
        title=data.title,
        document_code=data.document_code,
        section=data.section,
        requirement_text=data.requirement_text,
        source=data.source,
        version=data.version,
        effective_date=data.effective_date,
        status=data.status,
        stages=stages,
        rule_type=data.rule_type.value,
        rule_config=data.rule_config,
        recommendation=data.recommendation,
        severity=data.severity.value,
        is_demo=data.is_demo,
        expert_validated=data.expert_validated,
    )
    db.add(normative)
    _commit(db)
    db.refresh(normative)
    return normative


def list_normatives(
    db: Session,
    *,
    stage_id: int | None,
    status: str | None,
    family_key: str | None,
    offset: int,
    limit: int,
) -> list[Normative]:
    query = db.query(Normative).options(selectinload(Normative.stages))
    if stage_id is not None:
        query = query.filter(Normative.stages.any(Stage.id == stage_id))
    if status is not None:
        query = query.filter(Normative.status == status)
    if family_key is not None:
        query = query.filter(Normative.family_key == family_key)
    return query.order_by(Normative.id.desc()).offset(offset).limit(limit).all()


def get_normative(db: Session, normative_id: int) -> Normative:
    return _get_normative_or_raise(db, normative_id)


def update_normative(
    db: Session,
    normative_id: int,
    data: NormativeUpdate,
) -> Normative:
    normative = _get_normative_or_raise(db, normative_id)
    changes = data.model_dump(exclude_unset=True)
    stage_ids = changes.pop("stage_ids", None)

    requested_status = changes.get("status")
    if requested_status == "active":
        active_versions = (
            db.query(Normative)
            .filter(
                Normative.family_key == normative.family_key,
                Normative.id != normative.id,
                Normative.status == "active",
            )
            .all()
        )
        for active_version in active_versions:
            active_version.status = "inactive"
            active_version.updated_at = utc_now()
        normative.status = "active"
    elif requested_status == "inactive":
        normative.status = "inactive"

    if stage_ids is not None:
        normative.stages = _load_stages(db, stage_ids)

    normative.updated_at = utc_now()
    _commit(db)
    db.refresh(normative)
    return normative


def create_normative_version(
    db: Session,
    normative_id: int,
    data: NormativeVersionCreate,
) -> Normative:
    previous = _get_normative_or_raise(db, normative_id)
    if previous.status != "active":
        raise NormativeVersionConflictError(
            "Новую версию можно создать только на основе активного нормативного правила"
        )
    _ensure_version_available(db, previous.family_key, data.version)
    changes = data.model_dump(exclude_unset=True)
    stage_ids = changes.pop("stage_ids", None)
    changes.pop("version", None)

    def inherited(field_name: str):
        value = changes.get(field_name, getattr(previous, field_name))
        if hasattr(value, "value"):
            value = value.value
        if field_name in {"title", "document_code", "requirement_text"} and value is None:
            return getattr(previous, field_name)
        return value

    stages = list(previous.stages) if stage_ids is None else _load_stages(db, stage_ids)
    normative = Normative(
        family_key=previous.family_key,
        supersedes_id=previous.id,
        title=inherited("title"),
        document_code=inherited("document_code"),
        section=inherited("section"),
        requirement_text=inherited("requirement_text"),
        source=inherited("source"),
        version=data.version,
        effective_date=inherited("effective_date"),
        status="active",
        stages=stages,
        rule_type=inherited("rule_type"),
        rule_config=inherited("rule_config"),
        recommendation=inherited("recommendation"),
        severity=inherited("severity"),
        is_demo=inherited("is_demo"),
        expert_validated=inherited("expert_validated"),
    )
    active_versions = (
        db.query(Normative)
        .filter(
            Normative.family_key == previous.family_key,
            Normative.status == "active",
        )
        .all()
    )
    for active_version in active_versions:
        active_version.status = "inactive"
        active_version.updated_at = utc_now()
    db.add(normative)
    _commit(db)
    db.refresh(normative)
    return normative


def deactivate_normative(db: Session, normative_id: int) -> None:
    normative = _get_normative_or_raise(db, normative_id)
    normative.status = "inactive"
    normative.updated_at = utc_now()
    _commit(db)
