import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.services import storage_service


PDF_V1 = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"
PDF_V2 = b"%PDF-1.4\n% version two\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"


def create_project_stage(
    client: TestClient,
    name: str = "Document project",
) -> tuple[int, int]:
    project = client.post("/projects/", json={"name": name}).json()
    stage = client.post(
        "/stages/",
        json={"project_id": project["id"], "name": "Foundation"},
    ).json()
    return project["id"], stage["id"]


def create_uploader(client: TestClient, project_id: int) -> int:
    user = client.post(
        "/users",
        json={"email": "uploader@example.com", "full_name": "PDF Uploader"},
    ).json()
    membership = client.post(
        f"/projects/{project_id}/members",
        json={"user_id": user["id"], "role": "project_manager"},
    )
    assert membership.status_code == 201
    return user["id"]


def upload_pdf(
    client: TestClient,
    *,
    project_id: int,
    stage_id: int,
    version: str,
    content: bytes,
    uploader_id: int | None = None,
):
    data = {
        "project_id": str(project_id),
        "stage_id": str(stage_id),
        "title": "Foundation design",
        "document_type": "project_documentation",
        "version": version,
    }
    if uploader_id is not None:
        data["uploaded_by_user_id"] = str(uploader_id)
    return client.post(
        "/documents/upload",
        data=data,
        files={"file": ("foundation.pdf", content, "application/pdf")},
    )


def test_pdf_upload_download_filters_and_soft_delete(client: TestClient) -> None:
    project_id, stage_id = create_project_stage(client)
    uploader_id = create_uploader(client, project_id)

    response = upload_pdf(
        client,
        project_id=project_id,
        stage_id=stage_id,
        version="1.0",
        content=PDF_V1,
        uploader_id=uploader_id,
    )
    assert response.status_code == 201
    document = response.json()
    assert document["status"] == "active"
    assert document["supersedes_id"] is None
    assert document["uploaded_by_user_id"] == uploader_id
    assert document["file_hash"] == hashlib.sha256(PDF_V1).hexdigest()
    assert document["size_bytes"] == len(PDF_V1)
    assert not Path(document["storage_key"]).is_absolute()
    assert (settings.upload_dir / document["storage_key"]).read_bytes() == PDF_V1

    filtered = client.get(
        "/documents/",
        params={"project_id": project_id, "stage_id": stage_id, "status": "active"},
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()] == [document["id"]]

    download = client.get(f"/documents/{document['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content == PDF_V1

    deleted = client.delete(f"/documents/{document['id']}")
    assert deleted.status_code == 204
    persisted = client.get(f"/documents/{document['id']}")
    assert persisted.status_code == 200
    assert persisted.json()["status"] == "inactive"
    assert (settings.upload_dir / document["storage_key"]).is_file()


def test_document_versioning_preserves_history(client: TestClient) -> None:
    project_id, stage_id = create_project_stage(client)
    first = upload_pdf(
        client,
        project_id=project_id,
        stage_id=stage_id,
        version="1.0",
        content=PDF_V1,
    ).json()

    second_response = client.post(
        f"/documents/{first['id']}/versions",
        data={"version": "2.0", "title": "Foundation design revised"},
        files={"file": ("foundation-v2.pdf", PDF_V2, "application/pdf")},
    )
    assert second_response.status_code == 201
    second = second_response.json()
    assert second["series_key"] == first["series_key"]
    assert second["supersedes_id"] == first["id"]
    assert second["version"] == "2.0"
    assert second["status"] == "active"

    previous = client.get(f"/documents/{first['id']}").json()
    assert previous["status"] == "inactive"
    history = client.get(f"/documents/{second['id']}/versions")
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [second["id"], first["id"]]

    branch = client.post(
        f"/documents/{first['id']}/versions",
        data={"version": "3.0"},
        files={"file": ("foundation-v3.pdf", PDF_V2, "application/pdf")},
    )
    assert branch.status_code == 409

    duplicate = client.post(
        f"/documents/{second['id']}/versions",
        data={"version": "2.0"},
        files={"file": ("duplicate.pdf", PDF_V2, "application/pdf")},
    )
    assert duplicate.status_code == 409


def test_document_rejects_invalid_files_links_and_uploaders(client: TestClient) -> None:
    project_id, stage_id = create_project_stage(client, "First project")
    other_project_id, other_stage_id = create_project_stage(client, "Second project")

    wrong_extension = client.post(
        "/documents/upload",
        data={
            "project_id": project_id,
            "stage_id": stage_id,
            "title": "Wrong extension",
            "version": "1.0",
        },
        files={"file": ("document.txt", PDF_V1, "application/pdf")},
    )
    assert wrong_extension.status_code == 400

    fake_pdf = client.post(
        "/documents/upload",
        data={
            "project_id": project_id,
            "stage_id": stage_id,
            "title": "Fake PDF",
            "version": "1.0",
        },
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
    )
    assert fake_pdf.status_code == 400

    wrong_stage = upload_pdf(
        client,
        project_id=project_id,
        stage_id=other_stage_id,
        version="1.0",
        content=PDF_V1,
    )
    assert wrong_stage.status_code == 409

    outsider = client.post(
        "/users",
        json={"email": "outsider@example.com", "full_name": "Outsider"},
    ).json()
    denied = upload_pdf(
        client,
        project_id=other_project_id,
        stage_id=other_stage_id,
        version="1.0",
        content=PDF_V1,
        uploader_id=outsider["id"],
    )
    assert denied.status_code == 403
    assert not list(settings.upload_dir.rglob("*.pdf"))


def test_document_enforces_configured_size_limit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, stage_id = create_project_stage(client)
    monkeypatch.setattr(
        storage_service,
        "settings",
        replace(settings, max_pdf_size_bytes=8),
    )

    response = upload_pdf(
        client,
        project_id=project_id,
        stage_id=stage_id,
        version="1.0",
        content=PDF_V1,
    )
    assert response.status_code == 413
    assert not list(settings.upload_dir.rglob("*.pdf"))
