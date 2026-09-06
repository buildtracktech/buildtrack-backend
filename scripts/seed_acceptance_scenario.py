"""Создать полный приёмочный сценарий BuildTrack Backend одной командой."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import sys
from datetime import date
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402
from app.act_schemas import AcceptanceActCreate, AcceptanceActStatusUpdate  # noqa: E402
from app.check_schemas import FindingStatusUpdate  # noqa: E402
from app.core.enums import (  # noqa: E402
    AcceptanceActStatus,
    AcceptanceActType,
    FindingKind,
    FindingStatus,
    ProjectRole,
    TaskPriority,
    TaskStatus,
)
from app.database import SessionLocal  # noqa: E402
from app.normative_schemas import NormativeCreate  # noqa: E402
from app.services import (  # noqa: E402
    act_service,
    check_service,
    document_service,
    normative_service,
    report_service,
    task_service,
    user_service,
)
from app.task_schemas import TaskCreate, TaskStatusUpdate  # noqa: E402
from app.user_schemas import ProjectMembershipCreate, UserCreate  # noqa: E402
from scripts.generate_demo_pdf import generate_demo_pdf  # noqa: E402


DEFAULT_PROJECT_NAME = "Приёмка BuildTrack Backend: фундамент"
DEFAULT_SOURCE_PDF = REPOSITORY_ROOT / "output/pdf/buildtrack-primer-fundament.pdf"
DEFAULT_REPORT_PDF = (
    REPOSITORY_ROOT / "output/pdf/buildtrack-otchet-priemka-fundament.pdf"
)
DEFAULT_SUMMARY = REPOSITORY_ROOT / "output/acceptance/scenario-summary.json"
DEFAULT_CREDENTIALS = REPOSITORY_ROOT / "output/acceptance/access.txt"
DEFAULT_GUIDE = REPOSITORY_ROOT / "output/acceptance/how-to-check.txt"
NORMATIVES_PATH = REPOSITORY_ROOT / "scripts/fixtures/acceptance_normatives.json"

USER_BLUEPRINTS = {
    "project_manager": {
        "email": "prorab@buildtrack.local",
        "full_name": "Прораб BuildTrack",
        "role": ProjectRole.PROJECT_MANAGER,
    },
    "inspector": {
        "email": "inspektor@buildtrack.local",
        "full_name": "Инспектор BuildTrack",
        "role": ProjectRole.INSPECTOR,
    },
    "contractor": {
        "email": "rabochiy@buildtrack.local",
        "full_name": "Рабочий BuildTrack",
        "role": ProjectRole.CONTRACTOR,
    },
    "investor": {
        "email": "investor@buildtrack.local",
        "full_name": "Инвестор BuildTrack",
        "role": ProjectRole.INVESTOR,
    },
}


class ScenarioConflictError(ValueError):
    """Приёмочный сценарий конфликтует с уже существующими данными."""


def _preflight(db: Session, project_name: str) -> None:
    if db.query(models.Project.id).filter(models.Project.name == project_name).first():
        raise ScenarioConflictError(
            f"Проект «{project_name}» уже существует. "
            "Укажите другое имя через --project-name."
        )

    emails = [blueprint["email"] for blueprint in USER_BLUEPRINTS.values()]
    occupied = [
        email
        for (email,) in db.query(models.User.email)
        .filter(models.User.email.in_(emails))
        .order_by(models.User.email)
        .all()
    ]
    if occupied:
        raise ScenarioConflictError(
            "Уже существуют учётные записи: " + ", ".join(occupied)
        )


def _create_project_and_stage(
    db: Session,
    project_name: str,
) -> tuple[models.Project, models.Stage]:
    project = models.Project(
        name=project_name,
        description=(
            "Сквозная приёмка серверного этапа: документация, проверка, "
            "задача и технический акт."
        ),
        location="Контрольная площадка BuildTrack",
    )
    db.add(project)
    db.flush()
    stage = models.Stage(
        project_id=project.id,
        name="Фундамент",
        description="Контроль документации этапа фундамента",
        status="active",
    )
    db.add(stage)
    db.commit()
    db.refresh(project)
    db.refresh(stage)
    return project, stage


def _create_users_and_memberships(
    db: Session,
    project_id: int,
    password: str,
) -> dict[str, models.User]:
    users: dict[str, models.User] = {}
    for key, blueprint in USER_BLUEPRINTS.items():
        user = user_service.create_user(
            db,
            UserCreate(
                email=str(blueprint["email"]),
                full_name=str(blueprint["full_name"]),
                password=password,
            ),
        )
        user_service.add_project_member(
            db,
            project_id,
            ProjectMembershipCreate(
                user_id=user.id,
                role=blueprint["role"],
            ),
        )
        users[key] = user
    return users


def _create_normatives(db: Session, stage_id: int) -> list[models.Normative]:
    payloads = json.loads(NORMATIVES_PATH.read_text(encoding="utf-8"))
    return [
        normative_service.create_normative(
            db,
            NormativeCreate.model_validate({**payload, "stage_ids": [stage_id]}),
        )
        for payload in payloads
    ]


def _review_findings(
    db: Session,
    check: models.Check,
    inspector_id: int,
) -> models.Check:
    for finding in list(check.findings):
        if finding.kind == FindingKind.NON_COMPLIANCE.value:
            check_service.update_finding_status(
                db,
                finding.id,
                FindingStatusUpdate(
                    status=FindingStatus.CONFIRMED,
                    changed_by_user_id=inspector_id,
                    comment="Несоответствие подтверждено инспектором",
                ),
            )
            check_service.update_finding_status(
                db,
                finding.id,
                FindingStatusUpdate(
                    status=FindingStatus.RESOLVED,
                    changed_by_user_id=inspector_id,
                    comment="Замечание устранено и проверено инспектором",
                ),
            )
        elif finding.kind == FindingKind.MANUAL_REVIEW.value:
            check_service.update_finding_status(
                db,
                finding.id,
                FindingStatusUpdate(
                    status=FindingStatus.DISMISSED,
                    changed_by_user_id=inspector_id,
                    comment="Результат рассмотрен инспектором",
                ),
            )
    return check_service.get_check(db, check.id)


def _create_verified_task(
    db: Session,
    *,
    project_id: int,
    stage_id: int,
    manager_id: int,
    worker_id: int,
    check_id: int,
) -> models.Task:
    task = task_service.create_task(
        db,
        TaskCreate(
            project_id=project_id,
            stage_id=stage_id,
            assigned_to_user_id=worker_id,
            created_by_user_id=manager_id,
            title="Добавить ответственного проверяющего",
            description=(
                f"Устранить замечание проверки №{check_id} и добавить поле "
                "«Ответственный проверяющий»."
            ),
            priority=TaskPriority.HIGH,
        ),
    )
    task_service.update_task_status(
        db,
        task.id,
        TaskStatusUpdate(
            status=TaskStatus.ACTIVE,
            changed_by_user_id=worker_id,
            comment="Рабочий приступил к выполнению задачи",
        ),
    )
    task_service.update_task_status(
        db,
        task.id,
        TaskStatusUpdate(
            status=TaskStatus.PENDING_VERIFICATION,
            changed_by_user_id=worker_id,
            comment="Работа завершена и отправлена на проверку",
        ),
    )
    return task_service.update_task_status(
        db,
        task.id,
        TaskStatusUpdate(
            status=TaskStatus.VERIFIED,
            changed_by_user_id=manager_id,
            comment="Прораб проверил и принял выполненную работу",
        ),
    )


def _create_approved_act(
    db: Session,
    *,
    check_id: int,
    manager_id: int,
) -> models.AcceptanceAct:
    today = date.today()
    act = act_service.create_acceptance_act(
        db,
        AcceptanceActCreate(
            check_id=check_id,
            act_type=AcceptanceActType.STAGE_ACCEPTANCE,
            work_description="Проверка и приёмка документации этапа фундамента",
            period_start=today,
            period_end=today,
            created_by_user_id=manager_id,
        ),
    )
    act_service.update_acceptance_act_status(
        db,
        act.id,
        AcceptanceActStatusUpdate(
            status=AcceptanceActStatus.READY,
            changed_by_user_id=manager_id,
            comment="Акт подготовлен к утверждению",
        ),
    )
    return act_service.update_acceptance_act_status(
        db,
        act.id,
        AcceptanceActStatusUpdate(
            status=AcceptanceActStatus.APPROVED,
            changed_by_user_id=manager_id,
            comment="Технический акт утверждён прорабом",
        ),
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_credentials(
    path: Path,
    users: dict[str, models.User],
    password: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Временный доступ к приёмочному сценарию BuildTrack Backend",
        "",
        f"Общий временный пароль: {password}",
        "",
        "Учётные записи:",
    ]
    lines.extend(
        f"- {user.full_name}: {user.email}" for user in users.values()
    )
    lines.extend(
        [
            "",
            "Перед публикацией замените эти данные на реальные учётные записи.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def write_acceptance_guide(path: Path, summary: dict) -> None:
    """Записать короткую инструкцию с точными ID созданного сценария."""

    project_id = summary["project"]["id"]
    check_id = summary["check"]["id"]
    task_id = summary["task"]["id"]
    act_id = summary["act"]["id"]
    lines = [
        "КАК ПРОВЕРИТЬ ПРИЁМОЧНЫЙ СЦЕНАРИЙ BUILDTRACK BACKEND",
        "",
        "1. Откройте http://127.0.0.1:8001/docs.",
        "2. Возьмите логин и временный пароль из файла access.txt.",
        "3. Выполните POST /auth/login и вставьте токен в кнопку Authorize.",
        "4. Последовательно откройте:",
        f"   - GET /projects/{project_id};",
        f"   - GET /checks/{check_id}/report;",
        f"   - GET /tasks/{task_id} и GET /tasks/{task_id}/audit;",
        f"   - GET /acts/{act_id} и GET /acts/{act_id}/audit.",
        "5. Откройте PDF-отчёт, путь к нему указан в scenario-summary.json.",
        "",
        "ОЖИДАЕМЫЙ РЕЗУЛЬТАТ",
        f"- Проект №{project_id}: {summary['project']['name']}.",
        f"- Проверка №{check_id}: completed / invalid.",
        f"- Задача №{task_id}: verified.",
        f"- Акт №{act_id}: approved.",
        "- У замечаний статусы resolved и dismissed.",
        "",
        "Статус invalid относится к исходной версии PDF и не переписывается задним числом.",
        "Устранение замечания подтверждают история, принятая задача и утверждённый акт.",
        "Контрольные правила не являются реальными ГОСТ, СП или СНиП.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_acceptance_scenario(
    db: Session,
    *,
    password: str,
    project_name: str = DEFAULT_PROJECT_NAME,
    source_pdf_path: Path = DEFAULT_SOURCE_PDF,
    report_pdf_path: Path = DEFAULT_REPORT_PDF,
    summary_path: Path = DEFAULT_SUMMARY,
    credentials_path: Path | None = DEFAULT_CREDENTIALS,
    guide_path: Path = DEFAULT_GUIDE,
) -> dict:
    """Создать полный сценарий и вернуть итоговые идентификаторы без пароля."""

    UserCreate(
        email="password-check@buildtrack.local",
        full_name="Проверка пароля",
        password=password,
    )
    _preflight(db, project_name)
    generated_pdf = generate_demo_pdf(source_pdf_path)
    project, stage = _create_project_and_stage(db, project_name)
    users = _create_users_and_memberships(db, project.id, password)
    normatives = _create_normatives(db, stage.id)

    with generated_pdf.open("rb") as stream:
        document = document_service.create_document(
            db,
            project_id=project.id,
            stage_id=stage.id,
            title="Документация по фундаменту",
            document_type="project_documentation",
            version="1.0",
            uploader_id=users["project_manager"].id,
            stream=stream,
            original_filename=generated_pdf.name,
            content_type="application/pdf",
        )

    check = check_service.create_and_run_check(
        db,
        document_id=document.id,
        initiated_by_user_id=users["inspector"].id,
    )
    check = _review_findings(db, check, users["inspector"].id)

    report_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    report_pdf_path.write_bytes(report_service.generate_check_report_pdf(check))

    task = _create_verified_task(
        db,
        project_id=project.id,
        stage_id=stage.id,
        manager_id=users["project_manager"].id,
        worker_id=users["contractor"].id,
        check_id=check.id,
    )
    act = _create_approved_act(
        db,
        check_id=check.id,
        manager_id=users["project_manager"].id,
    )

    summary = {
        "project": {"id": project.id, "name": project.name},
        "stage": {"id": stage.id, "name": stage.name},
        "users": {
            key: {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": str(USER_BLUEPRINTS[key]["role"]),
            }
            for key, user in users.items()
        },
        "normative_ids": [normative.id for normative in normatives],
        "document": {
            "id": document.id,
            "sha256": document.file_hash,
            "source_pdf": str(generated_pdf),
        },
        "check": {
            "id": check.id,
            "status": check.status,
            "verdict": check.verdict,
            "finding_ids": [finding.id for finding in check.findings],
            "finding_statuses": [finding.status for finding in check.findings],
            "report_pdf": str(report_pdf_path.resolve()),
        },
        "task": {"id": task.id, "status": task.status},
        "act": {
            "id": act.id,
            "number": act.act_number,
            "status": act.status,
            "report_hash": act.report_hash,
        },
        "credentials_file": (
            str(credentials_path.resolve()) if credentials_path is not None else None
        ),
        "guide_file": str(guide_path.resolve()),
        "password_stored_in_summary": False,
    }
    _write_json(summary_path, summary)
    if credentials_path is not None:
        _write_credentials(credentials_path, users, password)
    write_acceptance_guide(guide_path, summary)
    return summary


def _prompt_password() -> str:
    first = getpass.getpass("Временный пароль для четырёх ролей: ")
    second = getpass.getpass("Повторите пароль: ")
    if first != second:
        raise ValueError("Введённые пароли не совпадают")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", default=DEFAULT_PROJECT_NAME)
    parser.add_argument(
        "--generate-password",
        action="store_true",
        help="Создать случайный временный пароль без интерактивного запроса.",
    )
    parser.add_argument("--source-pdf", type=Path, default=DEFAULT_SOURCE_PDF)
    parser.add_argument("--report-pdf", type=Path, default=DEFAULT_REPORT_PDF)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--guide", type=Path, default=DEFAULT_GUIDE)
    args = parser.parse_args()

    password = secrets.token_urlsafe(18) if args.generate_password else _prompt_password()
    db = SessionLocal()
    try:
        summary = create_acceptance_scenario(
            db,
            password=password,
            project_name=args.project_name,
            source_pdf_path=args.source_pdf,
            report_pdf_path=args.report_pdf,
            summary_path=args.summary,
            credentials_path=args.credentials,
            guide_path=args.guide,
        )
    except Exception as exc:
        db.rollback()
        raise SystemExit(f"Не удалось создать приёмочный сценарий: {exc}") from exc
    finally:
        db.close()

    print("Приёмочный сценарий создан.")
    print(f"Проект: #{summary['project']['id']} - {summary['project']['name']}")
    print(f"Проверка: #{summary['check']['id']} - {summary['check']['verdict']}")
    print(f"Задача: #{summary['task']['id']} - {summary['task']['status']}")
    print(f"Акт: #{summary['act']['id']} - {summary['act']['status']}")
    print(f"Итоговые ID: {args.summary.resolve()}")
    print(f"Инструкция: {args.guide.resolve()}")
    print(f"Доступы: {args.credentials.resolve()}")
    print(f"PDF-отчёт: {args.report_pdf.resolve()}")


if __name__ == "__main__":
    main()
