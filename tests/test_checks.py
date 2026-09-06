from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.services import check_engine


PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"


def create_project_stage_document(client: TestClient) -> tuple[int, int, int]:
    project = client.post(
        "/projects/",
        json={"name": "Check engine project"},
    ).json()
    stage = client.post(
        "/stages/",
        json={"project_id": project["id"], "name": "Foundation"},
    ).json()
    document_response = client.post(
        "/documents/upload",
        data={
            "project_id": project["id"],
            "stage_id": stage["id"],
            "title": "Foundation design",
            "version": "1.0",
        },
        files={"file": ("foundation.pdf", PDF_BYTES, "application/pdf")},
    )
    assert document_response.status_code == 201
    return project["id"], stage["id"], document_response.json()["id"]


def create_rule(
    client: TestClient,
    stage_id: int,
    *,
    phrase: str,
    is_demo: bool,
    expert_validated: bool,
) -> dict:
    response = client.post(
        "/normatives/",
        json={
            "title": "Обязательная отметка об утверждении",
            "document_code": "BT-TEST-CHECK-001",
            "section": "Титульный лист",
            "requirement_text": "Документ содержит обязательную отметку об утверждении.",
            "source": "Учебное правило BuildTrack, не является строительным нормативом.",
            "version": "1.0",
            "stage_ids": [stage_id],
            "rule_type": "required_phrase",
            "rule_config": {"phrase": phrase},
            "recommendation": "Добавить обязательную отметку на титульный лист.",
            "severity": "major",
            "is_demo": is_demo,
            "expert_validated": expert_validated,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_check_finds_issue_snapshots_rule_and_supports_review(
    client: TestClient,
    monkeypatch,
) -> None:
    project_id, stage_id, document_id = create_project_stage_document(client)
    normative = create_rule(
        client,
        stage_id,
        phrase="Approved for construction",
        is_demo=True,
        expert_validated=False,
    )
    monkeypatch.setattr(
        check_engine,
        "extract_pdf_pages",
        lambda _path: ["Stage Foundation. Revision 1.0. Prepared for manual review."],
    )

    response = client.post("/checks/", json={"document_id": document_id})
    assert response.status_code == 201, response.text
    check = response.json()
    assert check["project_id"] == project_id
    assert check["stage_id"] == stage_id
    assert check["status"] == "completed"
    assert check["verdict"] == "invalid"
    assert check["pages_count"] == 1
    assert len(check["normative_snapshots"]) == 1
    snapshot = check["normative_snapshots"][0]
    assert snapshot["normative_id"] == normative["id"]
    assert snapshot["version"] == "1.0"
    assert snapshot["rule_config"] == {"phrase": "Approved for construction"}

    non_compliance = next(
        finding
        for finding in check["findings"]
        if finding["kind"] == "non_compliance"
    )
    assert non_compliance["status"] == "open"
    assert "Approved for construction" in non_compliance["evidence_text"]
    assert any(
        finding["kind"] == "manual_review" for finding in check["findings"]
    )

    updated_normative = client.post(
        f"/normatives/{normative['id']}/versions",
        json={
            "version": "2.0",
            "requirement_text": "A later requirement must not rewrite old checks.",
            "rule_config": {"phrase": "A later marker"},
        },
    )
    assert updated_normative.status_code == 201
    persisted_check = client.get(f"/checks/{check['id']}").json()
    assert persisted_check["normative_snapshots"][0]["version"] == "1.0"
    assert persisted_check["normative_snapshots"][0]["requirement_text"] == (
        "Документ содержит обязательную отметку об утверждении."
    )

    confirmed = client.patch(
        f"/findings/{non_compliance['id']}",
        json={"status": "confirmed", "comment": "Подтверждено при учебной проверке"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    resolved = client.patch(
        f"/findings/{non_compliance['id']}",
        json={"status": "resolved", "comment": "Corrected in revision"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    audit = client.get(f"/findings/{non_compliance['id']}/audit")
    assert audit.status_code == 200
    assert [entry["new_status"] for entry in audit.json()] == [
        "open",
        "confirmed",
        "resolved",
    ]

    report = client.get(f"/checks/{check['id']}/report")
    assert report.status_code == 200
    assert report.json()["summary"] == {
        "total_normatives": 1,
        "total_findings": 2,
        "non_compliance_findings": 1,
        "manual_review_findings": 1,
        "open_findings": 1,
        "confirmed_findings": 0,
        "dismissed_findings": 0,
        "resolved_findings": 1,
    }
    assert "не является заключением строительной экспертизы" in report.json()["disclaimer"]

    pdf_report = client.get(f"/checks/{check['id']}/report.pdf")
    assert pdf_report.status_code == 200
    assert pdf_report.headers["content-type"] == "application/pdf"
    reader = PdfReader(BytesIO(pdf_report.content))
    assert len(reader.pages) == 2
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "BuildTrack" in extracted
    assert "Отчет проверки проектной документации" in extracted
    assert "BT-TEST-CHECK-001" in extracted
    assert "Approved for construction" in extracted
    assert "есть несоответствия" in extracted
    assert "несоответствие" in extracted


def test_expert_validated_rule_can_produce_valid_result(
    client: TestClient,
    monkeypatch,
) -> None:
    _, stage_id, document_id = create_project_stage_document(client)
    create_rule(
        client,
        stage_id,
        phrase="Revision 1.0",
        is_demo=False,
        expert_validated=True,
    )
    monkeypatch.setattr(
        check_engine,
        "extract_pdf_pages",
        lambda _path: ["Foundation design. Revision 1.0."],
    )

    response = client.post("/checks/", json={"document_id": document_id})
    assert response.status_code == 201
    assert response.json()["verdict"] == "valid"
    assert response.json()["findings"] == []


def test_check_requires_stage_rules_and_persists_extraction_failure(
    client: TestClient,
    monkeypatch,
) -> None:
    _, stage_id, document_id = create_project_stage_document(client)
    no_rules = client.post("/checks/", json={"document_id": document_id})
    assert no_rules.status_code == 409

    create_rule(
        client,
        stage_id,
        phrase="Revision",
        is_demo=True,
        expert_validated=False,
    )

    def fail_extraction(_path):
        raise check_engine.CheckExecutionError("Synthetic extraction failure")

    monkeypatch.setattr(check_engine, "extract_pdf_pages", fail_extraction)
    failed = client.post("/checks/", json={"document_id": document_id})
    assert failed.status_code == 201
    assert failed.json()["status"] == "failed"
    assert failed.json()["verdict"] is None
    assert failed.json()["error_message"] == "Synthetic extraction failure"


def test_image_only_pdf_requires_manual_review(
    client: TestClient,
    monkeypatch,
) -> None:
    _, stage_id, document_id = create_project_stage_document(client)
    create_rule(
        client,
        stage_id,
        phrase="Revision",
        is_demo=False,
        expert_validated=True,
    )
    monkeypatch.setattr(check_engine, "extract_pdf_pages", lambda _path: [""])

    response = client.post("/checks/", json={"document_id": document_id})
    assert response.status_code == 201
    assert response.json()["verdict"] == "manual_review"
    assert response.json()["findings"][0]["kind"] == "manual_review"
    assert "OCR" in response.json()["findings"][0]["recommendation"]
