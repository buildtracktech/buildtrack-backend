def _create_project_and_stage(client):
    project = client.post(
        "/projects/",
        json={"name": "Учебный проект", "location": "Тестовая площадка"},
    ).json()
    stage = client.post(
        "/stages/",
        json={"project_id": project["id"], "name": "Foundation"},
    ).json()
    return project, stage


TEST_PASSWORD = "BuildTrack-role-test-2026"


def _create_user(
    client,
    email,
    full_name,
    is_system_admin=False,
    password=None,
):
    response = client.post(
        "/users",
        json={
            "email": email,
            "full_name": full_name,
            "is_system_admin": is_system_admin,
            "password": password,
        },
    )
    assert response.status_code == 201
    return response.json()


def _login(client, email, password=TEST_PASSWORD):
    response = client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200, response.text
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"


def test_users_project_roles_and_task_lifecycle(client):
    project, stage = _create_project_and_stage(client)
    manager = _create_user(client, "Manager@Example.com", "Project Manager")
    contractor = _create_user(client, "contractor@example.com", "Contractor")

    manager_membership = client.post(
        f"/projects/{project['id']}/members",
        json={"user_id": manager["id"], "role": "project_manager"},
    )
    assert manager_membership.status_code == 201
    contractor_membership = client.post(
        f"/projects/{project['id']}/members",
        json={"user_id": contractor["id"], "role": "contractor"},
    )
    assert contractor_membership.status_code == 201

    members = client.get(f"/projects/{project['id']}/members")
    assert members.status_code == 200
    assert {item["role"] for item in members.json()} == {
        "project_manager",
        "contractor",
    }

    task_response = client.post(
        "/tasks/",
        json={
            "project_id": project["id"],
            "stage_id": stage["id"],
            "title": "Complete foundation work",
            "priority": "high",
            "assigned_to_user_id": contractor["id"],
            "created_by_user_id": manager["id"],
        },
    )
    assert task_response.status_code == 201
    task = task_response.json()
    assert task["status"] == "created"

    invalid_transition = client.patch(
        f"/tasks/{task['id']}/status",
        json={"status": "verified", "changed_by_user_id": manager["id"]},
    )
    assert invalid_transition.status_code == 409

    transitions = [
        ("active", manager["id"]),
        ("pending_verification", contractor["id"]),
        ("rejected", manager["id"]),
        ("active", contractor["id"]),
        ("pending_verification", contractor["id"]),
        ("verified", manager["id"]),
    ]
    for target_status, actor_id in transitions:
        response = client.patch(
            f"/tasks/{task['id']}/status",
            json={
                "status": target_status,
                "changed_by_user_id": actor_id,
                "comment": f"Move to {target_status}",
            },
        )
        assert response.status_code == 200

    completed = client.get(f"/tasks/{task['id']}").json()
    assert completed["status"] == "verified"
    assert completed["completed_at"] is not None

    audit = client.get(f"/tasks/{task['id']}/audit")
    assert audit.status_code == 200
    assert [item["new_status"] for item in audit.json()] == [
        "created",
        "active",
        "pending_verification",
        "rejected",
        "active",
        "pending_verification",
        "verified",
    ]
    assert audit.json()[0]["comment"] == "Задача создана"


def test_user_and_task_domain_conflicts(client):
    project, stage = _create_project_and_stage(client)
    member = _create_user(client, "member@example.com", "Member")
    outsider = _create_user(client, "outsider@example.com", "Outsider")

    duplicate_user = client.post(
        "/users",
        json={"email": "MEMBER@example.com", "full_name": "Duplicate"},
    )
    assert duplicate_user.status_code == 409

    membership_payload = {"user_id": member["id"], "role": "inspector"}
    assert client.post(
        f"/projects/{project['id']}/members",
        json=membership_payload,
    ).status_code == 201
    assert client.post(
        f"/projects/{project['id']}/members",
        json=membership_payload,
    ).status_code == 409

    outsider_assignment = client.post(
        "/tasks/",
        json={
            "project_id": project["id"],
            "stage_id": stage["id"],
            "title": "Cannot assign outsider",
            "assigned_to_user_id": outsider["id"],
        },
    )
    assert outsider_assignment.status_code == 409

    deactivate = client.delete(f"/users/{member['id']}")
    assert deactivate.status_code == 204
    inactive_user = client.get(f"/users/{member['id']}").json()
    assert inactive_user["status"] == "inactive"


def test_task_permissions_for_manager_executor_and_investor(client):
    admin_authorization = client.headers["Authorization"]
    project, stage = _create_project_and_stage(client)
    manager = _create_user(
        client,
        "foreman@example.com",
        "Site Foreman",
        password=TEST_PASSWORD,
    )
    first_executor = _create_user(
        client,
        "executor-one@example.com",
        "First Executor",
        password=TEST_PASSWORD,
    )
    second_executor = _create_user(
        client,
        "executor-two@example.com",
        "Second Executor",
        password=TEST_PASSWORD,
    )
    investor = _create_user(
        client,
        "investor@example.com",
        "Project Investor",
        password=TEST_PASSWORD,
    )
    for user, role in (
        (manager, "project_manager"),
        (first_executor, "contractor"),
        (second_executor, "contractor"),
        (investor, "investor"),
    ):
        response = client.post(
            f"/projects/{project['id']}/members",
            json={"user_id": user["id"], "role": role},
        )
        assert response.status_code == 201, response.text

    _login(client, manager["email"])
    first_task_response = client.post(
        "/tasks/",
        json={
            "project_id": project["id"],
            "stage_id": stage["id"],
            "title": "Prepare formwork",
            "assigned_to_user_id": first_executor["id"],
        },
    )
    assert first_task_response.status_code == 201, first_task_response.text
    first_task = first_task_response.json()
    assert first_task["created_by_user_id"] == manager["id"]
    second_task_response = client.post(
        "/tasks/",
        json={
            "project_id": project["id"],
            "stage_id": stage["id"],
            "title": "Place reinforcement",
            "assigned_to_user_id": second_executor["id"],
        },
    )
    assert second_task_response.status_code == 201, second_task_response.text
    second_task = second_task_response.json()

    manager_tasks = client.get("/tasks/")
    assert manager_tasks.status_code == 200
    assert {task["id"] for task in manager_tasks.json()} == {
        first_task["id"],
        second_task["id"],
    }

    _login(client, first_executor["email"])
    executor_tasks = client.get("/tasks/")
    assert executor_tasks.status_code == 200
    assert [task["id"] for task in executor_tasks.json()] == [first_task["id"]]
    assert client.get(f"/tasks/{second_task['id']}").status_code == 403
    assert client.get(f"/tasks/{second_task['id']}/audit").status_code == 403
    assert client.patch(
        f"/tasks/{first_task['id']}",
        json={"title": "Executor cannot rename this task"},
    ).status_code == 403
    assert client.post(
        "/tasks/",
        json={
            "project_id": project["id"],
            "title": "Executor cannot create tasks",
        },
    ).status_code == 403

    spoofed_actor = client.patch(
        f"/tasks/{first_task['id']}/status",
        json={"status": "active", "changed_by_user_id": manager["id"]},
    )
    assert spoofed_actor.status_code == 403
    started = client.patch(
        f"/tasks/{first_task['id']}/status",
        json={"status": "active", "comment": "Work started"},
    )
    assert started.status_code == 200, started.text
    submitted = client.patch(
        f"/tasks/{first_task['id']}/status",
        json={"status": "pending_verification", "comment": "Ready for review"},
    )
    assert submitted.status_code == 200, submitted.text
    forbidden_verification = client.patch(
        f"/tasks/{first_task['id']}/status",
        json={"status": "verified"},
    )
    assert forbidden_verification.status_code == 403

    _login(client, investor["email"])
    investor_tasks = client.get(f"/tasks/?project_id={project['id']}")
    assert investor_tasks.status_code == 200
    assert {task["id"] for task in investor_tasks.json()} == {
        first_task["id"],
        second_task["id"],
    }
    assert client.patch(
        f"/tasks/{first_task['id']}/status",
        json={"status": "verified"},
    ).status_code == 403

    _login(client, manager["email"])
    verified = client.patch(
        f"/tasks/{first_task['id']}/status",
        json={"status": "verified", "comment": "Accepted by the foreman"},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["completed_at"] is not None
    audit = client.get(f"/tasks/{first_task['id']}/audit")
    assert [entry["changed_by_user_id"] for entry in audit.json()] == [
        manager["id"],
        first_executor["id"],
        first_executor["id"],
        manager["id"],
    ]

    client.headers["Authorization"] = admin_authorization


def test_investor_cannot_be_assigned_a_task(client):
    project, stage = _create_project_and_stage(client)
    investor = _create_user(client, "readonly@example.com", "Read-only Investor")
    membership = client.post(
        f"/projects/{project['id']}/members",
        json={"user_id": investor["id"], "role": "investor"},
    )
    assert membership.status_code == 201

    response = client.post(
        "/tasks/",
        json={
            "project_id": project["id"],
            "stage_id": stage["id"],
            "title": "Invalid investor assignment",
            "assigned_to_user_id": investor["id"],
        },
    )
    assert response.status_code == 409
    assert "роль инвестора доступна только для просмотра" in response.json()["detail"]
