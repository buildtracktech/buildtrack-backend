import json
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfReader

from scripts.generate_demo_pdf import generate_demo_pdf


def test_demo_pdf_contains_expected_markers_and_intentional_omission(
    tmp_path: Path,
) -> None:
    output_path = generate_demo_pdf(tmp_path / "primer-fundament.pdf")
    reader = PdfReader(output_path)
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) == 1
    assert "ПРИЁМОЧНЫЙ ПРИМЕР - НЕ ДЛЯ СТРОИТЕЛЬСТВА" in extracted
    assert "Этап" in extracted
    assert "Редакция" in extracted
    assert "Ответственный проверяющий" not in extracted


def test_generated_demo_pdf_produces_expected_findings(
    client: TestClient,
    tmp_path: Path,
) -> None:
    project = client.post(
        "/projects/",
        json={"name": "Проверка учебного PDF"},
    ).json()
    stage = client.post(
        "/stages/",
        json={"project_id": project["id"], "name": "Фундамент"},
    ).json()

    fixture_path = Path(__file__).parent / "fixtures" / "demo_normatives.json"
    rules = json.loads(fixture_path.read_text(encoding="utf-8"))
    for rule in rules:
        rule.pop("stage_name_hint")
        rule["stage_ids"] = [stage["id"]]
        response = client.post("/normatives/", json=rule)
        assert response.status_code == 201, response.text

    pdf_path = generate_demo_pdf(tmp_path / "primer-fundament.pdf")
    with pdf_path.open("rb") as stream:
        document_response = client.post(
            "/documents/upload",
            data={
                "project_id": project["id"],
                "stage_id": stage["id"],
                "title": "Учебная документация по фундаменту",
                "version": "1.0",
            },
            files={"file": (pdf_path.name, stream, "application/pdf")},
        )
    assert document_response.status_code == 201, document_response.text

    check_response = client.post(
        "/checks/",
        json={"document_id": document_response.json()["id"]},
    )
    assert check_response.status_code == 201, check_response.text
    check = check_response.json()
    assert check["status"] == "completed"
    assert check["verdict"] == "invalid"
    assert check["pages_count"] == 1
    assert len(check["normative_snapshots"]) == 3
    assert {
        finding["kind"] for finding in check["findings"]
    } == {"non_compliance", "manual_review"}
    non_compliance = next(
        finding
        for finding in check["findings"]
        if finding["kind"] == "non_compliance"
    )
    assert "BT-TEST-003" in non_compliance["title"]
    assert "Ответственный проверяющий" in non_compliance["evidence_text"]
    assert non_compliance["title"].startswith("Не найдена обязательная информация")
