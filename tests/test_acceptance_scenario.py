import json
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app import models
from app.database import SessionLocal
from scripts.seed_acceptance_scenario import (
    ScenarioConflictError,
    create_acceptance_scenario,
)


def test_acceptance_scenario_creates_complete_russian_flow(
    client: TestClient,
    tmp_path: Path,
) -> None:
    password = "BuildTrack-acceptance-test-2026"
    source_pdf = tmp_path / "source.pdf"
    report_pdf = tmp_path / "report.pdf"
    summary_path = tmp_path / "summary.json"
    credentials_path = tmp_path / "access.txt"
    guide_path = tmp_path / "how-to-check.txt"
    project_name = "Приёмочный сценарий для автотеста"

    db = SessionLocal()
    try:
        summary = create_acceptance_scenario(
            db,
            password=password,
            project_name=project_name,
            source_pdf_path=source_pdf,
            report_pdf_path=report_pdf,
            summary_path=summary_path,
            credentials_path=credentials_path,
            guide_path=guide_path,
        )

        assert summary["project"]["name"] == project_name
        assert summary["check"]["status"] == "completed"
        assert summary["check"]["verdict"] == "invalid"
        assert sorted(summary["check"]["finding_statuses"]) == [
            "dismissed",
            "resolved",
        ]
        assert summary["task"]["status"] == "verified"
        assert summary["act"]["status"] == "approved"

        task_audit = (
            db.query(models.TaskAuditLog)
            .filter(models.TaskAuditLog.task_id == summary["task"]["id"])
            .order_by(models.TaskAuditLog.id)
            .all()
        )
        assert [row.new_status for row in task_audit] == [
            "created",
            "active",
            "pending_verification",
            "verified",
        ]
        assert all(row.comment and row.comment[0].isupper() for row in task_audit)

        act_audit = (
            db.query(models.AcceptanceActAuditLog)
            .filter(models.AcceptanceActAuditLog.act_id == summary["act"]["id"])
            .order_by(models.AcceptanceActAuditLog.id)
            .all()
        )
        assert [row.new_status for row in act_audit] == [
            "draft",
            "ready",
            "approved",
        ]
        assert [row.comment for row in act_audit] == [
            "Технический акт создан",
            "Акт подготовлен к утверждению",
            "Технический акт утверждён прорабом",
        ]

        with pytest.raises(ScenarioConflictError, match="уже существует"):
            create_acceptance_scenario(
                db,
                password=password,
                project_name=project_name,
                source_pdf_path=source_pdf,
                report_pdf_path=report_pdf,
                summary_path=summary_path,
                credentials_path=credentials_path,
                guide_path=guide_path,
            )
    finally:
        db.close()

    summary_text = summary_path.read_text(encoding="utf-8")
    assert password not in summary_text
    assert json.loads(summary_text)["password_stored_in_summary"] is False
    assert password in credentials_path.read_text(encoding="utf-8")
    assert stat.S_IMODE(credentials_path.stat().st_mode) == 0o600
    guide_text = guide_path.read_text(encoding="utf-8")
    assert password not in guide_text
    assert f"GET /projects/{summary['project']['id']}" in guide_text
    assert "invalid относится к исходной версии PDF" in guide_text

    assert len(PdfReader(source_pdf).pages) == 1
    assert len(PdfReader(report_pdf).pages) >= 2
