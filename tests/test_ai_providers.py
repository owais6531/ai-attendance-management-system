"""AI backends against a real local HTTP server standing in for the provider. No real AI service is used."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from services.ai import api_client, ollama_client, provider, system_check
from services.ai.errors import AiError

SECRET = "sk-test-not-a-real-key"
BODY = {"columns": [{"name": "Karkun Number", "samples": ["0012"]}], "already_mapped": []}
REPLY = {"columns": [{"column": "Karkun Number", "field": "employee_code", "confidence": 0.9}]}


class Fake(BaseHTTPRequestHandler):
    status = 200
    answer = {}
    seen = []
    extra_headers = {}

    def _send(self):
        self.send_response(self.status)
        for key, value in self.extra_headers.items():
            self.send_header(key, value)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(self.answer).encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        Fake.seen.append({"path": self.path, "auth": self.headers.get("Authorization"),
                          "body": json.loads(self.rfile.read(length))})
        self._send()

    def do_GET(self):
        Fake.seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": None})
        self._send()

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    Fake.status, Fake.answer, Fake.seen, Fake.extra_headers = 200, {}, [], {}
    httpd = HTTPServer(("127.0.0.1", 0), Fake)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def api_env(server, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "api")
    monkeypatch.setenv("AI_API_URL", server + "/v1")
    monkeypatch.setenv("AI_API_KEY", SECRET)
    monkeypatch.setenv("AI_API_MODEL", "test-model")
    return server


def _chat(content):
    return {"choices": [{"message": {"content": content}}]}


# ---------- API (own key) ----------
def test_api_suggestion_end_to_end(client, api_env):
    Fake.answer = _chat(json.dumps(REPLY))
    body = client.post("/import/ai/suggest", json=BODY).json()
    assert body["suggestions"][0]["field"] == "employee_code" and body["model"] == "test-model"
    sent = Fake.seen[0]
    assert sent["path"] == "/v1/chat/completions" and sent["auth"] == f"Bearer {SECRET}"
    assert sent["body"]["model"] == "test-model" and "employee_code" in json.dumps(sent["body"]["messages"])


def test_api_accepts_json_in_a_code_fence(client, api_env):
    Fake.answer = _chat("```json\n" + json.dumps(REPLY) + "\n```")
    assert client.post("/import/ai/suggest", json=BODY).json()["suggestions"]


@pytest.mark.parametrize("code,word", [(401, "AI_API_KEY"), (404, "AI_API_MODEL"), (429, "limit"), (500, "500")])
def test_api_errors_are_clear_and_never_show_the_key(client, api_env, code, word):
    Fake.status, Fake.answer = code, {"error": f"bad key {SECRET}"}
    r = client.post("/import/ai/suggest", json=BODY)
    assert r.status_code == 503 and word in r.json()["detail"] and SECRET not in r.text


def test_api_reply_goes_through_the_same_whitelist(client, api_env):
    Fake.answer = _chat(json.dumps({"columns": [{"column": "Karkun Number", "field": "drop_table", "confidence": 1}]}))
    assert client.post("/import/ai/suggest", json=BODY).json()["suggestions"] == []


def test_api_not_json_is_503(client, api_env):
    Fake.answer = _chat("I think it is an employee code")
    assert client.post("/import/ai/suggest", json=BODY).status_code == 503


def test_api_does_not_follow_redirects_with_the_key(client, api_env):
    Fake.status, Fake.extra_headers = 302, {"Location": api_env + "/stolen"}
    assert client.post("/import/ai/suggest", json=BODY).status_code == 503
    assert [s["path"] for s in Fake.seen] == ["/v1/chat/completions"]


def test_api_status_lists_what_is_missing(client, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "api")
    for name in ("AI_API_URL", "AI_API_KEY", "AI_API_MODEL"):
        monkeypatch.delenv(name, raising=False)
    body = client.get("/import/ai/status").json()
    assert body["available"] is False and "AI_API_KEY" in body["hint"]
    assert client.post("/import/ai/suggest", json=BODY).status_code == 503


def test_api_status_never_contains_the_key_and_says_where_data_goes(client, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "api")
    monkeypatch.setenv("AI_API_URL", "https://api.example.com/v1")
    monkeypatch.setenv("AI_API_KEY", SECRET)
    monkeypatch.setenv("AI_API_MODEL", "m")
    r = client.get("/import/ai/status")
    assert r.json()["available"] and r.json()["external"] and r.json()["host"] == "api.example.com"
    assert SECRET not in r.text and SECRET not in client.get("/import/ai/setup").text


def test_api_refuses_plain_http_to_another_host(monkeypatch):
    monkeypatch.setenv("AI_API_URL", "http://api.example.com/v1")
    monkeypatch.setenv("AI_API_KEY", SECRET)
    monkeypatch.setenv("AI_API_MODEL", "m")
    assert "https" in api_client.config_problem()
    with pytest.raises(AiError):
        api_client.complete([], {})


# ---------- Ollama and the switch ----------
def test_ollama_over_real_http(client, server, monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("OLLAMA_URL", server)
    monkeypatch.setenv("OLLAMA_TEXT_MODEL", "small:1b")
    Fake.answer = {"models": [{"name": "small:1b"}], "message": {"content": json.dumps(REPLY)}}
    status = client.get("/import/ai/status").json()
    assert status["available"] and status["provider"] == "ollama" and status["external"] is False
    assert client.post("/import/ai/suggest", json=BODY).json()["suggestions"]
    chat = Fake.seen[-1]
    assert chat["path"] == "/api/chat" and chat["auth"] is None and chat["body"]["format"]["type"] == "object"


def test_ai_can_be_turned_off(client, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "off")
    assert client.get("/import/ai/status").json()["available"] is False
    assert client.post("/import/ai/suggest", json=BODY).status_code == 503


def test_unknown_provider_falls_back_to_local(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "something")
    assert provider.name() == "ollama"


def test_off_is_the_same_error_type_for_callers(monkeypatch):
    assert issubclass(ollama_client.OllamaError, AiError)


# ---------- specs check ----------
def _facts(monkeypatch, ram, disk, cores):
    monkeypatch.setattr(system_check, "total_ram_gb", lambda: ram)
    monkeypatch.setattr(system_check, "free_disk_gb", lambda: disk)
    monkeypatch.setattr(system_check.os, "cpu_count", lambda: cores)


def test_specs_enough(client, monkeypatch):
    _facts(monkeypatch, 16.0, 100.0, 8)
    body = client.get("/import/ai/setup").json()
    assert body["system"]["verdict"] == "ok"
    assert all(line["ok"] for line in body["system"]["lines"])
    assert "ollama pull" in body["local"]["pull_command"] and "AI_API_KEY" in body["api"]["env_example"]


def test_specs_too_low_points_to_api(client, monkeypatch):
    _facts(monkeypatch, 4.0, 100.0, 8)
    system = client.get("/import/ai/setup").json()["system"]
    assert system["verdict"] == "low" and "API key" in system["message"]
    assert [line["ok"] for line in system["lines"]] == [False, True, True]


def test_specs_unknown_is_not_called_ok(monkeypatch):
    _facts(monkeypatch, None, 100.0, 8)
    assert system_check.check()["verdict"] == "unknown"


def test_specs_read_real_values_from_this_machine():
    assert system_check.total_ram_gb() > 0 and system_check.free_disk_gb() >= 0


def test_setup_needs_api_key_when_configured(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key")
    assert client.get("/import/ai/setup").status_code == 401
