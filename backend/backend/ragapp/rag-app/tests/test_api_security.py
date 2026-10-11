"""Security checks for query and upload routes.

Cloud clients are mocked. These tests must pass without Zilliz or OpenAI.
"""

import importlib
import json
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
ALICE = "alice-token-aaaaaaaa"
BOB = "bob-token-bbbbbbbbbb"
TOKEN_CONFIG = json.dumps(
    [
        {"token": ALICE, "user_id": "alice", "tenant_id": "acme"},
        {"token": BOB, "user_id": "bob", "tenant_id": "globex"},
    ]
)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _load_app(monkeypatch, tmp_path, **overrides):
    env = {
        "RING_API_TOKENS": TOKEN_CONFIG,
        "FRONTEND_ORIGIN": "http://localhost:3000",
        "QUERY_QUOTA": "2",
        "UPLOAD_QUOTA": "2",
        "QUOTA_WINDOW_SECONDS": "3600",
        "UPLOAD_FOLDER": str(tmp_path),
        "MAX_UPLOAD_BYTES": str(1024 * 1024),
        "MAX_FILES_PER_REQUEST": "5",
    }
    env.update(overrides)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))

    import security

    importlib.reload(security)
    import app as app_module

    app_module = importlib.reload(app_module)
    return app_module


@pytest.fixture
def api(monkeypatch, tmp_path):
    module = _load_app(monkeypatch, tmp_path)
    module.app.config["TESTING"] = True
    return module


@pytest.fixture
def client(api):
    return api.app.test_client()


def _query_module(answer_docs=None):
    module = MagicMock()
    module.retrieve_documents.return_value = [] if answer_docs is None else answer_docs
    module.get_or_create_collection.return_value = "tenant-collection"
    module.format_docs.return_value = "Title: t\nDescription: d"
    module.generate_prompt.return_value = "prompt"
    module.call_openai.return_value = "answer"
    return module


def test_token_parsing_rejects_short_wildcard_and_duplicates():
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    import security

    importlib.reload(security)

    parsed = security.parse_api_tokens(
        json.dumps(
            [
                {"token": "short", "user_id": "a", "tenant_id": "t"},
                {"token": ALICE, "user_id": "alice", "tenant_id": "acme"},
                {"token": ALICE, "user_id": "mallory", "tenant_id": "other"},
            ]
        )
    )
    assert list(parsed) == [ALICE]
    assert parsed[ALICE]["user_id"] == "alice"

    simple = security.parse_api_tokens(f"{BOB}:bob:globex,{ALICE}:alice:acme")
    assert simple[BOB]["tenant_id"] == "globex"
    assert security._parse_origins("*") == ["http://localhost:3000"]
    assert security._parse_origins("") == ["http://localhost:3000"]


def test_collection_names_are_stable_and_isolated():
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    import security

    importlib.reload(security)

    acme = security.collection_name_for_tenant("acme")
    again = security.collection_name_for_tenant("acme")
    globex = security.collection_name_for_tenant("globex")
    spaced = security.collection_name_for_tenant("acme ")
    assert acme == again
    assert acme != globex
    assert acme != spaced
    assert acme != "AIS_Information"
    assert security.is_safe_collection_name(acme)
    assert security.is_safe_collection_name(globex)
    assert not security.is_safe_collection_name("AIS_Information;drop")
    assert not security.is_safe_collection_name("../AIS_Information")


def test_missing_and_invalid_credentials_are_rejected(client, api):
    query = {"query_text": "repeat the retrieved context"}
    routes = [
        ("/query", {"json": query}),
        ("/upload_file", {}),
        ("/upload_folder", {}),
        ("/process_url", {"json": {"url": "https://example.com"}}),
    ]
    for path, kwargs in routes:
        response = client.post(path, **kwargs)
        assert response.status_code == 401, path
        assert response.get_json()["error"] == "Authentication required."

    response = client.post("/query", json=query, headers={"Authorization": "Basic alice"})
    assert response.status_code == 401
    response = client.post("/query", json=query, headers={"Authorization": "Bearer"})
    assert response.status_code == 401
    response = client.post("/query", json=query, headers={"Authorization": f"Bearer {ALICE[:8]}"})
    assert response.status_code == 401
    response = client.post(f"/query?access_token={ALICE}", json=query)
    assert response.status_code == 401
    response = client.get("/query")
    assert response.status_code == 401
    response = client.post("/not-a-route")
    assert response.status_code == 401

    cloud = _query_module()
    api._load_query_module = lambda: cloud
    # Rebind the function on the module the route uses.
    import app as app_module

    app_module._load_query_module = lambda: cloud
    response = client.post("/query", json=query, headers=_auth(ALICE))
    assert response.status_code == 200
    assert cloud.connect_to_zilliz.call_count == 1


def test_unauthenticated_routes_do_not_call_cloud_or_write_files(client, api, tmp_path, monkeypatch):
    cloud = _query_module()
    uploads = MagicMock()
    monkeypatch.setattr(api, "_load_query_module", lambda: cloud)
    monkeypatch.setattr(api, "_load_upload_module", lambda: uploads)

    response = client.post(
        "/upload_file",
        data={"file": (BytesIO(b"secret business plan"), "plan.txt")},
    )
    assert response.status_code == 401
    assert list(tmp_path.rglob("*")) == []
    uploads.restructure_files.assert_not_called()
    cloud.connect_to_zilliz.assert_not_called()


def test_query_uses_token_tenant_and_ignores_body_collection(client, api, monkeypatch):
    cloud = _query_module()
    monkeypatch.setattr(api, "_load_query_module", lambda: cloud)

    response = client.post(
        "/query",
        json={
            "query_text": "What is in the index?",
            "tenant_id": "globex",
            "collection": "AIS_Information",
        },
        headers={**_auth(ALICE), "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert response.get_json()["answer"] == "No relevant documents found."
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"

    collection_name = cloud.get_or_create_collection.call_args.args[0]
    assert collection_name == api.collection_name_for_tenant("acme")
    assert collection_name != "AIS_Information"
    cloud.call_openai.assert_not_called()

    bob_cloud = _query_module(answer_docs=[[object()]])
    monkeypatch.setattr(api, "_load_query_module", lambda: bob_cloud)
    response = client.post(
        "/query",
        json={"query_text": "Summarize my documents"},
        headers=_auth(BOB),
    )
    assert response.status_code == 200
    assert response.get_json()["answer"] == "answer"
    assert bob_cloud.get_or_create_collection.call_args.args[0] == api.collection_name_for_tenant("globex")
    bob_cloud.call_openai.assert_called_once()


def test_cors_does_not_allow_arbitrary_origins(client, api, monkeypatch):
    monkeypatch.setattr(api, "_load_query_module", lambda: _query_module())
    evil = client.options(
        "/query",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert evil.headers.get("Access-Control-Allow-Origin") != "https://evil.example"
    assert evil.headers.get("Access-Control-Allow-Origin") != "*"

    allowed = client.options(
        "/query",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert allowed.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"

    reflected = client.post(
        "/query",
        json={"query_text": "hi"},
        headers={**_auth(ALICE), "Origin": "https://evil.example"},
    )
    assert reflected.headers.get("Access-Control-Allow-Origin") != "https://evil.example"
    assert reflected.headers.get("Access-Control-Allow-Origin") != "*"


def test_wildcard_origin_config_stays_closed(monkeypatch, tmp_path):
    module = _load_app(monkeypatch, tmp_path, FRONTEND_ORIGIN="*")
    client = module.app.test_client()
    response = client.options(
        "/query",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers.get("Access-Control-Allow-Origin") != "https://evil.example"
    assert response.headers.get("Access-Control-Allow-Origin") != "*"
    assert module.settings.origins == ["http://localhost:3000"]


def test_quotas_are_per_user_and_do_not_call_cloud_when_exceeded(client, api, monkeypatch):
    cloud = _query_module()
    monkeypatch.setattr(api, "_load_query_module", lambda: cloud)

    for _ in range(2):
        response = client.post("/query", json={"query_text": "hello"}, headers=_auth(ALICE))
        assert response.status_code == 200

    blocked = client.post("/query", json={"query_text": "hello again"}, headers=_auth(ALICE))
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]
    assert cloud.get_or_create_collection.call_count == 2

    bob = client.post("/query", json={"query_text": "bob can still ask"}, headers=_auth(BOB))
    assert bob.status_code == 200
    assert cloud.get_or_create_collection.call_count == 3

    uploads = MagicMock()
    uploads.restructure_files.return_value = [["t"], ["body"]]
    monkeypatch.setattr(api, "_load_upload_module", lambda: uploads)
    upload_cloud = _query_module()
    monkeypatch.setattr(api, "_load_query_module", lambda: upload_cloud)

    first = _upload(client, ALICE, "one.txt", b"one")
    assert first.status_code == 200
    second = _upload(client, ALICE, "two.txt", b"two")
    assert second.status_code == 200
    third = _upload(client, ALICE, "three.txt", b"three")
    assert third.status_code == 429
    assert uploads.restructure_files.call_count == 2

    # Upload quota does not consume the query quota of another user, and Bob
    # still has upload budget after Alice is exhausted.
    bob_upload = _upload(client, BOB, "bob.txt", b"bob")
    assert bob_upload.status_code == 200


def test_upload_is_confined_to_the_tenant_directory(client, api, tmp_path, monkeypatch):
    seen = []

    def capture(paths, hashes, **kwargs):
        seen.append("marker" in hashes)
        hashes.add("marker")
        return [["plan.txt - 1"], ["business text"]]

    uploads = MagicMock()
    uploads.restructure_files.side_effect = capture
    cloud = _query_module()
    monkeypatch.setattr(api, "_load_upload_module", lambda: uploads)
    monkeypatch.setattr(api, "_load_query_module", lambda: cloud)

    response = client.post(
        "/upload_file",
        data={"file": (BytesIO(b"business text"), "../../secret.txt")},
        headers=_auth(ALICE),
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert ".." not in body
    assert str(tmp_path) not in body
    assert "AIS_Information" not in body

    saved = list(tmp_path.rglob("*.txt"))
    assert len(saved) == 1
    assert saved[0].name == "secret.txt"
    assert tmp_path in saved[0].parents
    assert cloud.get_or_create_collection.call_args.args[0] == api.collection_name_for_tenant("acme")

    bob = client.post(
        "/upload_file",
        data={"file": (BytesIO(b"other"), "notes.txt")},
        headers=_auth(BOB),
    )
    assert bob.status_code == 200
    assert seen == [False, False]
    assert cloud.get_or_create_collection.call_args.args[0] == api.collection_name_for_tenant("globex")


def test_folder_upload_counts_each_file_and_hides_server_paths(client, api, tmp_path, monkeypatch):
    uploads = MagicMock()
    uploads.restructure_files.return_value = [[], []]
    monkeypatch.setattr(api, "_load_upload_module", lambda: uploads)

    response = client.post(
        "/upload_folder",
        data={
            "files": [
                (BytesIO(b"a"), "a.txt"),
                (BytesIO(b"b"), "nested/b.txt"),
            ]
        },
        headers=_auth(ALICE),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert str(tmp_path) not in json.dumps(payload)
    assert payload["files"]
    assert uploads.restructure_files.call_count == 1

    blocked = client.post(
        "/upload_folder",
        data={"files": [(BytesIO(b"c"), "c.txt"), (BytesIO(b"d"), "d.txt")]},
        headers=_auth(ALICE),
    )
    assert blocked.status_code == 429
    assert uploads.restructure_files.call_count == 1


def test_cloud_errors_do_not_leak_secrets(client, api, monkeypatch):
    def explode():
        raise RuntimeError("ZILLIZ_TOKEN super-secret-value")

    monkeypatch.setattr(api, "_load_query_module", explode)
    response = client.post(
        "/query",
        json={"query_text": "hello"},
        headers=_auth(ALICE),
    )
    assert response.status_code == 500
    raw = response.get_data(as_text=True)
    assert "super-secret-value" not in raw
    assert "ZILLIZ_TOKEN" not in raw
    assert response.get_json()["error"] == "Query failed."


def test_process_url_requires_auth_and_http_scheme(client):
    denied = client.post("/process_url", json={"url": "https://example.com"})
    assert denied.status_code == 401

    bad = client.post(
        "/process_url",
        json={"url": "file:///etc/passwd"},
        headers=_auth(ALICE),
    )
    assert bad.status_code == 400

    ok = client.post(
        "/process_url",
        json={"url": "https://user:secret@example.com/private"},
        headers=_auth(ALICE),
    )
    assert ok.status_code == 200
    assert "secret" not in ok.get_data(as_text=True)
    assert "example.com" not in ok.get_data(as_text=True)


def test_oversized_upload_is_rejected(monkeypatch, tmp_path):
    module = _load_app(monkeypatch, tmp_path, MAX_UPLOAD_BYTES="40")
    client = module.app.test_client()
    response = client.post(
        "/upload_file",
        data={"file": (BytesIO(b"x" * 80), "notes.txt")},
        headers=_auth(ALICE),
    )
    assert response.status_code == 413


def _upload(client, token, name, content):
    return client.post(
        "/upload_file",
        data={"file": (BytesIO(content), name)},
        headers=_auth(token),
    )
