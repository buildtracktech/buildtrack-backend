from fastapi.testclient import TestClient

from app.main import app


def test_business_api_requires_authentication(client: TestClient) -> None:
    with TestClient(app) as anonymous_client:
        response = anonymous_client.get("/projects/")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    malformed = client.get(
        "/projects/",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert malformed.status_code == 401


def test_login_me_password_change_and_token_revocation(client: TestClient) -> None:
    login = client.post(
        "/auth/login",
        data={
            "username": "test-admin@buildtrack.local",
            "password": "BuildTrack-test-password-2026",
        },
    )
    assert login.status_code == 200
    old_token = login.json()["access_token"]
    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "test-admin@buildtrack.local"
    assert me.json()["is_system_admin"] is True
    assert me.json()["has_password"] is True

    wrong_password = client.post(
        "/auth/login",
        data={"username": "test-admin@buildtrack.local", "password": "wrong-password"},
    )
    assert wrong_password.status_code == 401

    changed = client.put(
        "/auth/password",
        headers={"Authorization": f"Bearer {old_token}"},
        json={
            "current_password": "BuildTrack-test-password-2026",
            "new_password": "BuildTrack-new-password-2026",
        },
    )
    assert changed.status_code == 204
    revoked = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert revoked.status_code == 401

    relogin = client.post(
        "/auth/login",
        data={
            "username": "test-admin@buildtrack.local",
            "password": "BuildTrack-new-password-2026",
        },
    )
    assert relogin.status_code == 200


def test_bootstrap_can_run_only_once(client: TestClient) -> None:
    repeated = client.post(
        "/auth/bootstrap",
        json={
            "email": "second-admin@buildtrack.local",
            "full_name": "Second Administrator",
            "password": "Second-admin-password-2026",
        },
    )
    assert repeated.status_code == 409


def test_system_admin_can_replace_training_account_details(client: TestClient) -> None:
    created = client.post(
        "/users",
        json={
            "email": "training-admin@buildtrack.local",
            "full_name": "Учебный администратор",
            "is_system_admin": True,
            "password": "Training-admin-password-2026",
        },
    )
    assert created.status_code == 201, created.text

    updated = client.patch(
        f"/users/{created.json()['id']}",
        json={
            "email": "real.admin@example.com",
            "full_name": "Алексей Администратор",
            "password": "Real-admin-password-2026",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["email"] == "real.admin@example.com"
    assert updated.json()["full_name"] == "Алексей Администратор"
    assert "password" not in updated.json()

    old_login = client.post(
        "/auth/login",
        data={
            "username": "training-admin@buildtrack.local",
            "password": "Training-admin-password-2026",
        },
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/auth/login",
        data={
            "username": "real.admin@example.com",
            "password": "Real-admin-password-2026",
        },
    )
    assert new_login.status_code == 200


def test_project_roles_prevent_privilege_escalation(client: TestClient) -> None:
    project = client.post("/projects/", json={"name": "RBAC project"}).json()
    investor = client.post(
        "/users",
        json={
            "email": "investor-rbac@example.com",
            "full_name": "Read Only Investor",
            "password": "Investor-password-2026",
        },
    ).json()
    membership = client.post(
        f"/projects/{project['id']}/members",
        json={"user_id": investor["id"], "role": "investor"},
    )
    assert membership.status_code == 201
    login = client.post(
        "/auth/login",
        data={
            "username": "investor-rbac@example.com",
            "password": "Investor-password-2026",
        },
    )
    investor_headers = {
        "Authorization": f"Bearer {login.json()['access_token']}"
    }

    assert client.get(
        f"/projects/{project['id']}",
        headers=investor_headers,
    ).status_code == 200
    forbidden_user = client.post(
        "/users",
        headers=investor_headers,
        json={"email": "escalation@example.com", "full_name": "Escalation"},
    )
    assert forbidden_user.status_code == 403
    forbidden_stage = client.post(
        "/stages/",
        headers=investor_headers,
        json={"project_id": project["id"], "name": "Forbidden stage"},
    )
    assert forbidden_stage.status_code == 403
    forbidden_delete = client.delete(
        f"/projects/{project['id']}",
        headers=investor_headers,
    )
    assert forbidden_delete.status_code == 403
    forbidden_normative = client.post(
        "/normatives/",
        headers=investor_headers,
        json={
            "title": "Privilege escalation",
            "document_code": "FORBIDDEN",
            "requirement_text": "Must not be created",
            "stage_ids": [999],
        },
    )
    assert forbidden_normative.status_code == 403


def test_project_creator_becomes_project_manager(client: TestClient) -> None:
    manager = client.post(
        "/users",
        json={
            "email": "creator-manager@example.com",
            "full_name": "Project Creator",
            "password": "Project-creator-password-2026",
        },
    ).json()
    login = client.post(
        "/auth/login",
        data={
            "username": "creator-manager@example.com",
            "password": "Project-creator-password-2026",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    project = client.post(
        "/projects/",
        headers=headers,
        json={"name": "Creator-owned project"},
    )
    assert project.status_code == 200
    stage = client.post(
        "/stages/",
        headers=headers,
        json={"project_id": project.json()["id"], "name": "Managed stage"},
    )
    assert stage.status_code == 200
    members = client.get(
        f"/projects/{project.json()['id']}/members",
        headers=headers,
    )
    assert members.status_code == 200
    assert members.json()[0]["user_id"] == manager["id"]
    assert members.json()[0]["role"] == "project_manager"
