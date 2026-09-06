from fastapi.testclient import TestClient


def test_health_and_documentation_are_available(client: TestClient) -> None:
    health = client.get("/health")
    docs = client.get("/docs")
    openapi = client.get("/openapi.json")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert docs.status_code == 200
    assert openapi.status_code == 200
    assert "/projects/" in openapi.json()["paths"]
