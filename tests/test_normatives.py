from fastapi.testclient import TestClient


def create_project_and_stages(client: TestClient) -> tuple[int, int, int]:
    project = client.post(
        "/projects/",
        json={"name": "Normative test project"},
    ).json()
    foundation = client.post(
        "/stages/",
        json={"project_id": project["id"], "name": "Foundation"},
    ).json()
    monolith = client.post(
        "/stages/",
        json={"project_id": project["id"], "name": "Monolith"},
    ).json()
    return project["id"], foundation["id"], monolith["id"]


def test_normative_crud_filters_and_versioning(client: TestClient) -> None:
    _, foundation_id, monolith_id = create_project_and_stages(client)

    create_response = client.post(
        "/normatives/",
        json={
            "title": "Concrete strength requirement",
            "document_code": "SP 63.13330",
            "section": "6.1",
            "requirement_text": "Concrete strength must match the project specification.",
            "source": "Construction standard",
            "version": "1.0",
            "effective_date": "2026-01-01",
            "stage_ids": [foundation_id, monolith_id, foundation_id],
        },
    )
    assert create_response.status_code == 201
    normative = create_response.json()
    assert normative["status"] == "active"
    assert normative["supersedes_id"] is None
    assert [stage["id"] for stage in normative["stages"]] == [
        foundation_id,
        monolith_id,
    ]

    filtered_response = client.get(
        "/normatives/",
        params={"stage_id": foundation_id, "status": "active"},
    )
    assert filtered_response.status_code == 200
    assert [item["id"] for item in filtered_response.json()] == [normative["id"]]

    update_response = client.patch(
        f"/normatives/{normative['id']}",
        json={"stage_ids": [foundation_id]},
    )
    assert update_response.status_code == 200
    assert [stage["id"] for stage in update_response.json()["stages"]] == [
        foundation_id,
    ]

    in_place_content_change = client.patch(
        f"/normatives/{normative['id']}",
        json={"requirement_text": "This must be a new version"},
    )
    assert in_place_content_change.status_code == 422

    version_response = client.post(
        f"/normatives/{normative['id']}/versions",
        json={
            "version": "2.0",
            "requirement_text": "Updated concrete strength requirement.",
            "effective_date": "2026-09-01",
        },
    )
    assert version_response.status_code == 201
    new_version = version_response.json()
    assert new_version["family_key"] == normative["family_key"]
    assert new_version["supersedes_id"] == normative["id"]
    assert new_version["status"] == "active"
    assert [stage["id"] for stage in new_version["stages"]] == [
        foundation_id,
    ]

    previous_version = client.get(f"/normatives/{normative['id']}")
    assert previous_version.status_code == 200
    assert previous_version.json()["status"] == "inactive"

    branch_from_inactive_version = client.post(
        f"/normatives/{normative['id']}/versions",
        json={"version": "3.0"},
    )
    assert branch_from_inactive_version.status_code == 409

    duplicate_version = client.post(
        f"/normatives/{new_version['id']}/versions",
        json={"version": "2.0"},
    )
    assert duplicate_version.status_code == 409

    active_for_stage = client.get(
        "/normatives/",
        params={"stage_id": foundation_id, "status": "active"},
    )
    assert [item["id"] for item in active_for_stage.json()] == [new_version["id"]]

    delete_response = client.delete(f"/normatives/{new_version['id']}")
    assert delete_response.status_code == 204
    deleted_normative = client.get(f"/normatives/{new_version['id']}")
    assert deleted_normative.json()["status"] == "inactive"


def test_normative_validates_stage_links_and_required_fields(client: TestClient) -> None:
    _, foundation_id, _ = create_project_and_stages(client)

    missing_stage = client.post(
        "/normatives/",
        json={
            "title": "Foundation requirement",
            "document_code": "SP TEST",
            "requirement_text": "Test requirement",
            "stage_ids": [foundation_id, 999],
        },
    )
    assert missing_stage.status_code == 404
    assert missing_stage.json()["detail"]["missing_stage_ids"] == [999]

    no_stages = client.post(
        "/normatives/",
        json={
            "title": "Foundation requirement",
            "document_code": "SP TEST",
            "requirement_text": "Test requirement",
            "stage_ids": [],
        },
    )
    assert no_stages.status_code == 422
