from sqlalchemy.exc import OperationalError


def _upload(client, content, name="t.csv", **form):
    return client.post("/upload/attendance", files={"file": (name, content, "text/csv")}, data=form)


def test_home_page_serves_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_health_reports_database(client):
    assert client.get("/health").json()["database"] == "connected"


def test_download_template(client):
    response = client.get("/upload/template")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")


def test_upload_rejects_missing_file(client):
    assert client.post("/upload/attendance", files={}).status_code == 422


def test_upload_rejects_bad_type_with_400(client):
    r = client.post("/upload/attendance", files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400


def test_upload_missing_columns_is_400(client):
    r = _upload(client, b"A,B\n1,2\n")
    assert r.status_code == 400
    assert "Missing required columns" in r.json()["detail"]


def test_upload_saves_rows_and_reports_errors(client, make_csv):
    content = make_csv("1,1,0001,Demo A,0,1,0,0,2025/01/18 09:00:00",
                       "2,1,0002,Demo B,0,1,0,0,not-a-date")
    r = _upload(client, content)
    assert r.status_code == 200
    body = r.json()
    assert (body["total_records"], body["saved"], body["failed_imports"]) == (2, 1, 1)
    assert body["errors"][0]["row"] == 3
    assert body["preview"][0]["uid"] == "0001"

    records = client.get("/api/database/attendance/records").json()
    assert len(records) == 1 and records[0]["punch_at"] == "2025-01-18T09:00:00"
    batch = client.get(f"/api/database/batches/{body['batch_id']}").json()
    assert batch["status"] == "completed_with_errors"


def test_reupload_skips_duplicates(client, make_csv):
    content = make_csv("1,1,0001,Demo A,0,1,0,0,2025/01/18 09:00:00",
                       "2,1,0001,Demo A,0,1,0,0,2025/01/18 09:00:00",  # duplicate inside the file
                       "3,1,0002,Demo B,0,1,0,0,2025/01/18 09:05:00")
    first = _upload(client, content).json()
    assert (first["saved"], first["duplicates_skipped"]) == (2, 1)
    second = _upload(client, content).json()
    assert (second["saved"], second["duplicates_skipped"]) == (0, 3)
    assert client.get("/api/database/attendance/records/count").json()["count"] == 2


def test_dry_run_saves_nothing(client, make_csv):
    r = _upload(client, make_csv("1,1,0001,Demo A,0,1,0,0,2025/01/18 09:00:00"), dry_run="true")
    assert r.status_code == 200 and r.json()["saved"] == 0 and r.json()["valid_records"] == 1
    assert client.get("/api/database/attendance/records/count").json()["count"] == 0


def test_database_down_returns_503_not_success(client, make_csv, monkeypatch):
    from services import database_service

    def boom(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(database_service.DatabaseService, "save_upload", boom)
    r = _upload(client, make_csv("1,1,0001,Demo A,0,1,0,0,2025/01/18 09:00:00"))
    assert r.status_code == 503
    assert "Nothing was saved" in r.json()["detail"]


def test_date_filters(client, make_csv):
    _upload(client, make_csv("1,1,0001,A,0,1,0,0,2025/01/10 09:00:00",
                             "2,1,0001,A,0,1,0,0,2025/02/10 09:00:00"))
    r = client.get("/api/database/attendance/records", params={"date_from": "2025-02-01T00:00:00"})
    assert [x["date_time"] for x in r.json()] == ["2025/02/10 09:00:00"]


def test_database_route_requires_api_key_when_configured(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key")
    assert client.get("/api/database/batches").status_code == 401
    assert client.get("/api/database/batches", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/database/batches", headers={"X-API-Key": "secret-key"}).status_code == 200


def test_upload_requires_api_key_when_configured(client, monkeypatch, make_csv):
    monkeypatch.setenv("API_KEY", "secret-key")
    assert _upload(client, make_csv("1,1,1,A,0,1,0,0,2025/01/18 09:00:00")).status_code == 401
