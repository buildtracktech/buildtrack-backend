from fastapi.testclient import TestClient


def test_existing_project_stage_scan_flow(client: TestClient) -> None:
    project_response = client.post(
        "/projects/",
        json={
            "name": "BuildTrack Object",
            "description": "Construction project",
            "location": "Moscow",
        },
    )
    assert project_response.status_code == 200
    project = project_response.json()
    assert project["location"] == "Moscow"

    stage_response = client.post(
        "/stages/",
        json={
            "project_id": project["id"],
            "name": "Foundation",
            "description": "Foundation works",
        },
    )
    assert stage_response.status_code == 200
    stage = stage_response.json()

    get_stage_response = client.get(f"/stages/{stage['id']}")
    assert get_stage_response.status_code == 200
    assert get_stage_response.json()["name"] == "Foundation"

    upload_response = client.post(
        "/scans/upload",
        data={"project_id": project["id"], "stage_id": stage["id"]},
        files={"file": ("scan.txt", b"BuildTrack scan data", "text/plain")},
    )
    assert upload_response.status_code == 200
    scan = upload_response.json()
    assert scan["status"] == "pending"
    assert len(scan["file_hash"]) == 64

    invalid_status_response = client.patch(
        f"/scans/{scan['id']}/status",
        json={"status": "not_a_status"},
    )
    assert invalid_status_response.status_code == 400

    status_response = client.patch(
        f"/scans/{scan['id']}/status",
        json={
            "status": "manual_review",
            "comment": "Inspector review required",
            "checked_by": "inspector",
        },
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "manual_review"

    audit_response = client.get(f"/scans/{scan['id']}/audit")
    assert audit_response.status_code == 200
    assert [entry["new_status"] for entry in audit_response.json()] == [
        "manual_review",
        "pending",
    ]

    report_response = client.get(f"/projects/{project['id']}/report")
    assert report_response.status_code == 200
    assert report_response.json()["summary"]["final_object_status"] == "manual_review"

    first_proof = client.get(f"/projects/{project['id']}/digital-proof")
    second_proof = client.get(f"/projects/{project['id']}/digital-proof")
    assert first_proof.status_code == 200
    assert first_proof.json()["digital_proof_hash"] == second_proof.json()["digital_proof_hash"]
    assert first_proof.json()["proof_payload"]["external_registry_ready"] is False


def test_relationship_validation_and_status_validation(client: TestClient) -> None:
    missing_project_stage = client.post(
        "/stages/",
        json={"project_id": 999, "name": "Foundation"},
    )
    assert missing_project_stage.status_code == 404

    missing_scan = client.patch(
        "/scans/999/status",
        json={"status": "valid"},
    )
    assert missing_scan.status_code == 404
