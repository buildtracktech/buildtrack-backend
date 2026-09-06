from fastapi.testclient import TestClient

from app.services import check_engine


PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"


def create_user_with_role(
    client: TestClient,
    project_id: int,
    *,
    email: str,
    name: str,
    role: str,
) -> dict:
    user_response = client.post(
        "/users",
        json={"email": email, "full_name": name},
    )
    assert user_response.status_code == 201
    user = user_response.json()
    membership = client.post(
        f"/projects/{project_id}/members",
        json={"user_id": user["id"], "role": role},
    )
    assert membership.status_code == 201
    return user


def prepare_check(
    client: TestClient,
    monkeypatch,
    *,
    is_demo: bool,
    expert_validated: bool,
) -> tuple[dict, dict, dict]:
    project = client.post("/projects/", json={"name": "Act project"}).json()
    stage = client.post(
        "/stages/",
        json={"project_id": project["id"], "name": "Foundation"},
    ).json()
    manager = create_user_with_role(
        client,
        project["id"],
        email="manager@example.com",
        name="Project Manager",
        role="project_manager",
    )
    inspector = create_user_with_role(
        client,
        project["id"],
        email="inspector@example.com",
        name="Inspector",
        role="inspector",
    )
    normative = client.post(
        "/normatives/",
        json={
            "title": "Revision marker",
            "document_code": "BT-TEST-ACT-001",
            "requirement_text": "The document includes a revision marker.",
            "source": "Synthetic test rule; not a construction normative.",
            "stage_ids": [stage["id"]],
            "rule_type": "required_phrase",
            "rule_config": {"phrase": "Revision 1.0"},
            "recommendation": "Add a revision marker.",
            "is_demo": is_demo,
            "expert_validated": expert_validated,
        },
    )
    assert normative.status_code == 201
    document = client.post(
        "/documents/upload",
        data={
            "project_id": project["id"],
            "stage_id": stage["id"],
            "title": "Act source document",
            "version": "1.0",
        },
        files={"file": ("act-source.pdf", PDF_BYTES, "application/pdf")},
    ).json()
    monkeypatch.setattr(
        check_engine,
        "extract_pdf_pages",
        lambda _path: ["Foundation. Revision 1.0."],
    )
    check_response = client.post(
        "/checks/",
        json={"document_id": document["id"], "initiated_by_user_id": manager["id"]},
    )
    assert check_response.status_code == 201
    return check_response.json(), manager, inspector


def test_acceptance_act_lifecycle_and_snapshots(
    client: TestClient,
    monkeypatch,
) -> None:
    check, manager, inspector = prepare_check(
        client,
        monkeypatch,
        is_demo=False,
        expert_validated=True,
    )
    assert check["verdict"] == "valid"

    create_response = client.post(
        "/acts/",
        json={
            "check_id": check["id"],
            "act_type": "stage_acceptance",
            "act_number": "BT-ACT-TEST-001",
            "version": "1.0",
            "work_description": "Technical acceptance of the foundation stage.",
            "period_start": "2026-09-01",
            "period_end": "2026-09-05",
            "created_by_user_id": manager["id"],
        },
    )
    assert create_response.status_code == 201, create_response.text
    act = create_response.json()
    assert act["status"] == "draft"
    assert act["document_id"] == check["document_id"]
    assert act["document_hash"] == check["document_hash_snapshot"]
    assert len(act["report_hash"]) == 64
    assert {participant["role"] for participant in act["participant_snapshot"]} == {
        "project_manager",
        "inspector",
    }

    invalid_approval = client.patch(
        f"/acts/{act['id']}/status",
        json={"status": "approved", "changed_by_user_id": inspector["id"]},
    )
    assert invalid_approval.status_code == 409

    ready = client.patch(
        f"/acts/{act['id']}/status",
        json={
            "status": "ready",
            "changed_by_user_id": manager["id"],
            "comment": "Ready for inspector approval",
        },
    )
    assert ready.status_code == 200
    approved = client.patch(
        f"/acts/{act['id']}/status",
        json={
            "status": "approved",
            "changed_by_user_id": manager["id"],
            "comment": "Approved by the project foreman",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by_user_id"] == manager["id"]
    assert approved.json()["approved_at"] is not None

    duplicate = client.post(
        "/acts/",
        json={
            "check_id": check["id"],
            "act_type": "stage_acceptance",
            "act_number": "BT-ACT-TEST-001",
            "version": "1.0",
            "work_description": "Duplicate",
            "created_by_user_id": manager["id"],
        },
    )
    assert duplicate.status_code == 409

    audit = client.get(f"/acts/{act['id']}/audit")
    assert audit.status_code == 200
    assert [entry["new_status"] for entry in audit.json()] == [
        "draft",
        "ready",
        "approved",
    ]
    assert audit.json()[0]["comment"] == "Технический акт создан"


def test_stage_acceptance_waits_for_training_rule_review(
    client: TestClient,
    monkeypatch,
) -> None:
    check, manager, inspector = prepare_check(
        client,
        monkeypatch,
        is_demo=True,
        expert_validated=False,
    )
    assert check["verdict"] == "manual_review"
    act = client.post(
        "/acts/",
        json={
            "check_id": check["id"],
            "act_type": "stage_acceptance",
            "work_description": "Учебная приёмка после рассмотрения замечаний.",
            "created_by_user_id": manager["id"],
        },
    ).json()

    blocked = client.patch(
        f"/acts/{act['id']}/status",
        json={"status": "ready", "changed_by_user_id": manager["id"]},
    )
    assert blocked.status_code == 409

    for finding in check["findings"]:
        reviewed = client.patch(
            f"/findings/{finding['id']}",
            json={
                "status": "dismissed",
                "changed_by_user_id": inspector["id"],
                "comment": "Рассмотрено в учебном сценарии",
            },
        )
        assert reviewed.status_code == 200

    ready = client.patch(
        f"/acts/{act['id']}/status",
        json={"status": "ready", "changed_by_user_id": manager["id"]},
    )
    assert ready.status_code == 200
    assert ready.json()["finding_snapshot"][0]["status"] == "dismissed"
