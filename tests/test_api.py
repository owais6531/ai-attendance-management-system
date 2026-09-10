import os


def test_home_page_serves_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_app_info(client):
    response = client.get("/info")
    assert response.status_code == 200
    assert response.json()["name"] == "Bilal Attendance System"


def test_upload_health(client):
    response = client.get("/upload/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_download_template(client):
    response = client.get("/upload/template")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_upload_rejects_missing_file(client):
    response = client.post("/upload/attendance", files={})
    assert response.status_code == 422


def test_database_route_requires_api_key_when_configured(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key")

    response = client.get("/api/database/batches")

    assert response.status_code == 401


def test_database_route_accepts_correct_api_key(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key")

    response = client.get(
        "/api/database/batches", headers={"X-API-Key": "secret-key"}
    )

    # No live database in tests, so we only assert auth passed (no 401)
    assert response.status_code != 401


def test_database_route_open_when_api_key_unset(client, monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)

    response = client.get("/api/database/batches")

    assert response.status_code != 401
