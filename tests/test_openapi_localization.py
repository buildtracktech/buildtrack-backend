from fastapi.testclient import TestClient


def test_main_swagger_sections_and_actions_are_in_russian(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert schema["paths"]["/users"]["post"]["tags"] == ["Пользователи и роли"]
    assert schema["paths"]["/users"]["post"]["summary"] == "Создать пользователя"
    assert schema["paths"]["/checks/"]["post"]["summary"] == (
        "Запустить проверку документа"
    )
    assert schema["paths"]["/acts/"]["post"]["summary"] == "Создать технический акт"
