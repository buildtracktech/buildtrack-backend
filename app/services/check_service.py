from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app import models
from app.check_schemas import FindingStatusUpdate
from app.core.enums import (
    CheckStatus,
    CheckVerdict,
    FINDING_STATUS_TRANSITIONS,
    FindingKind,
    FindingSeverity,
    FindingStatus,
    UserStatus,
)
from app.core.time import utc_now
from app.services import check_engine, storage_service


ENGINE_CODE = "deterministic_text_rules_v1"
TRAINING_DISCLAIMER = (
    "Результат приёмочного сценария. Он не является заключением строительной экспертизы, "
    "юридическим актом приёмки или разрешением на выполнение строительных работ."
)


class CheckNotFoundError(LookupError):
    pass


class FindingNotFoundError(LookupError):
    pass


class CheckReferenceError(ValueError):
    pass


class CheckConfigurationError(ValueError):
    pass


class FindingTransitionError(ValueError):
    pass


class CheckPersistenceError(RuntimeError):
    pass


def _require_project_access(
    db: Session,
    project_id: int,
    user_id: int | None,
) -> None:
    if user_id is None:
        return
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise CheckReferenceError(f"Пользователь {user_id} не найден")
    if user.status != UserStatus.ACTIVE.value:
        raise CheckReferenceError(f"Пользователь {user_id} неактивен")
    if user.is_system_admin:
        return
    membership = (
        db.query(models.ProjectMembership.id)
        .filter(
            models.ProjectMembership.project_id == project_id,
            models.ProjectMembership.user_id == user_id,
        )
        .first()
    )
    if membership is None:
        raise CheckReferenceError(
            f"Пользователь {user_id} не является участником проекта {project_id}"
        )


def _check_query(db: Session):
    return db.query(models.Check).options(
        selectinload(models.Check.normative_snapshots),
        selectinload(models.Check.findings),
    )


def get_check(db: Session, check_id: int) -> models.Check:
    check = _check_query(db).filter(models.Check.id == check_id).first()
    if check is None:
        raise CheckNotFoundError(f"Проверка {check_id} не найдена")
    return check


def _snapshot_normative(
    check: models.Check,
    normative: models.Normative,
) -> models.CheckNormativeSnapshot:
    return models.CheckNormativeSnapshot(
        check=check,
        normative_id=normative.id,
        family_key=normative.family_key,
        title=normative.title,
        document_code=normative.document_code,
        section=normative.section,
        requirement_text=normative.requirement_text,
        source=normative.source,
        version=normative.version,
        rule_type=normative.rule_type,
        rule_config=normative.rule_config,
        recommendation=normative.recommendation,
        severity=normative.severity,
        is_demo=normative.is_demo,
        expert_validated=normative.expert_validated,
    )


def _add_finding(
    db: Session,
    check: models.Check,
    candidate: check_engine.FindingCandidate,
) -> models.Finding:
    finding = models.Finding(
        check=check,
        normative_snapshot_id=candidate.normative_snapshot_id,
        kind=candidate.kind.value,
        severity=candidate.severity.value,
        status=FindingStatus.OPEN.value,
        title=candidate.title,
        description=candidate.description,
        recommendation=candidate.recommendation,
        page_number=candidate.page_number,
        evidence_text=candidate.evidence_text,
    )
    db.add(finding)
    db.flush()
    db.add(
        models.FindingAuditLog(
            finding_id=finding.id,
            old_status=None,
            new_status=FindingStatus.OPEN.value,
            comment="Замечание создано движком проверки",
        )
    )
    return finding


def _commit(db: Session, message: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise CheckPersistenceError(message) from exc


def create_and_run_check(
    db: Session,
    *,
    document_id: int,
    initiated_by_user_id: int | None,
) -> models.Check:
    document = (
        db.query(models.Document)
        .filter(models.Document.id == document_id)
        .first()
    )
    if document is None:
        raise CheckReferenceError(f"Документ {document_id} не найден")
    if document.status != "active":
        raise CheckReferenceError("Проверять можно только активную версию документа")
    _require_project_access(db, document.project_id, initiated_by_user_id)

    normatives = (
        db.query(models.Normative)
        .filter(
            models.Normative.status == "active",
            models.Normative.stages.any(models.Stage.id == document.stage_id),
        )
        .order_by(models.Normative.id)
        .all()
    )
    if not normatives:
        raise CheckConfigurationError(
            f"Для этапа {document.stage_id} не назначены активные нормативные правила"
        )

    check = models.Check(
        project_id=document.project_id,
        stage_id=document.stage_id,
        document_id=document.id,
        initiated_by_user_id=initiated_by_user_id,
        status=CheckStatus.PROCESSING.value,
        engine_code=ENGINE_CODE,
        document_hash_snapshot=document.file_hash,
        started_at=utc_now(),
    )
    check.normative_snapshots = [
        _snapshot_normative(check, normative) for normative in normatives
    ]
    db.add(check)
    _commit(db, "Не удалось создать проверку")
    db.refresh(check)

    try:
        document_path = storage_service.resolve_storage_key(document.storage_key)
        pages = check_engine.extract_pdf_pages(document_path)
    except (
        check_engine.CheckExecutionError,
        storage_service.InvalidStorageKeyError,
    ) as exc:
        check.status = CheckStatus.FAILED.value
        check.error_message = str(exc)
        check.completed_at = utc_now()
        _commit(db, "Не удалось сохранить сведения об ошибке проверки")
        return get_check(db, check.id)

    check.pages_count = len(pages)
    check.extracted_text_hash = check_engine.extracted_text_hash(pages)
    if any(page.strip() for page in pages):
        candidates = [
            candidate
            for snapshot in check.normative_snapshots
            if (candidate := check_engine.evaluate_rule(snapshot, pages)) is not None
        ]
    else:
        candidates = [
            check_engine.FindingCandidate(
                normative_snapshot_id=None,
                kind=FindingKind.MANUAL_REVIEW,
                severity=FindingSeverity.INFO,
                title="В PDF не найден машиночитаемый текст",
                description=(
                    "Документ может состоять из сканированных изображений и не может "
                    "быть проверен текстовыми правилами без распознавания."
                ),
                recommendation=(
                    "Выполнить OCR-распознавание или загрузить PDF с текстовым слоем."
                ),
                page_number=None,
                evidence_text=None,
            )
        ]
    for candidate in candidates:
        _add_finding(db, check, candidate)

    requires_expert_confirmation = any(
        snapshot.is_demo or not snapshot.expert_validated
        for snapshot in check.normative_snapshots
    )
    if requires_expert_confirmation:
        _add_finding(
            db,
            check,
            check_engine.FindingCandidate(
                normative_snapshot_id=None,
                kind=FindingKind.MANUAL_REVIEW,
                severity=FindingSeverity.INFO,
                title="Требуется подтверждение эксперта",
                description=(
                    "В проверке использованы контрольные или ещё не подтверждённые "
                    "экспертом правила."
                ),
                recommendation=(
                    "Перед использованием результата получить подтверждение "
                    "квалифицированного специалиста."
                ),
                page_number=None,
                evidence_text=None,
            ),
        )

    if any(candidate.kind == FindingKind.NON_COMPLIANCE for candidate in candidates):
        check.verdict = CheckVerdict.INVALID.value
    elif any(candidate.kind == FindingKind.MANUAL_REVIEW for candidate in candidates):
        check.verdict = CheckVerdict.MANUAL_REVIEW.value
    elif requires_expert_confirmation:
        check.verdict = CheckVerdict.MANUAL_REVIEW.value
    else:
        check.verdict = CheckVerdict.VALID.value
    check.status = CheckStatus.COMPLETED.value
    check.completed_at = utc_now()
    _commit(db, "Не удалось сохранить результат проверки")
    return get_check(db, check.id)


def list_checks(
    db: Session,
    *,
    project_id: int | None,
    stage_id: int | None,
    document_id: int | None,
    status: CheckStatus | None,
    verdict: CheckVerdict | None,
    accessible_project_ids: set[int] | None,
    offset: int,
    limit: int,
) -> list[models.Check]:
    query = _check_query(db)
    if accessible_project_ids is not None:
        query = query.filter(models.Check.project_id.in_(accessible_project_ids))
    if project_id is not None:
        query = query.filter(models.Check.project_id == project_id)
    if stage_id is not None:
        query = query.filter(models.Check.stage_id == stage_id)
    if document_id is not None:
        query = query.filter(models.Check.document_id == document_id)
    if status is not None:
        query = query.filter(models.Check.status == status.value)
    if verdict is not None:
        query = query.filter(models.Check.verdict == verdict.value)
    return query.order_by(models.Check.id.desc()).offset(offset).limit(limit).all()


def get_finding(db: Session, finding_id: int) -> models.Finding:
    finding = db.query(models.Finding).filter(models.Finding.id == finding_id).first()
    if finding is None:
        raise FindingNotFoundError(f"Замечание {finding_id} не найдено")
    return finding


def update_finding_status(
    db: Session,
    finding_id: int,
    data: FindingStatusUpdate,
) -> models.Finding:
    finding = get_finding(db, finding_id)
    current = FindingStatus(finding.status)
    if data.status not in FINDING_STATUS_TRANSITIONS[current]:
        raise FindingTransitionError(
            f"Статус замечания нельзя изменить с {current.value} на {data.status.value}"
        )
    _require_project_access(
        db,
        finding.check.project_id,
        data.changed_by_user_id,
    )
    finding.status = data.status.value
    finding.reviewed_by_user_id = data.changed_by_user_id
    finding.review_comment = data.comment
    finding.reviewed_at = utc_now()
    finding.updated_at = utc_now()
    db.add(
        models.FindingAuditLog(
            finding_id=finding.id,
            old_status=current.value,
            new_status=data.status.value,
            comment=data.comment,
            changed_by_user_id=data.changed_by_user_id,
        )
    )
    _commit(db, "Не удалось обновить замечание")
    db.refresh(finding)
    return finding


def list_finding_audit(
    db: Session,
    finding_id: int,
) -> list[models.FindingAuditLog]:
    get_finding(db, finding_id)
    return (
        db.query(models.FindingAuditLog)
        .filter(models.FindingAuditLog.finding_id == finding_id)
        .order_by(models.FindingAuditLog.id)
        .all()
    )


def build_check_report(db: Session, check_id: int) -> dict:
    check = get_check(db, check_id)
    findings = check.findings
    return {
        "check": check,
        "summary": {
            "total_normatives": len(check.normative_snapshots),
            "total_findings": len(findings),
            "non_compliance_findings": sum(
                finding.kind == FindingKind.NON_COMPLIANCE.value
                for finding in findings
            ),
            "manual_review_findings": sum(
                finding.kind == FindingKind.MANUAL_REVIEW.value
                for finding in findings
            ),
            "open_findings": sum(
                finding.status == FindingStatus.OPEN.value for finding in findings
            ),
            "confirmed_findings": sum(
                finding.status == FindingStatus.CONFIRMED.value
                for finding in findings
            ),
            "dismissed_findings": sum(
                finding.status == FindingStatus.DISMISSED.value
                for finding in findings
            ),
            "resolved_findings": sum(
                finding.status == FindingStatus.RESOLVED.value for finding in findings
            ),
        },
        "disclaimer": TRAINING_DISCLAIMER,
    }
