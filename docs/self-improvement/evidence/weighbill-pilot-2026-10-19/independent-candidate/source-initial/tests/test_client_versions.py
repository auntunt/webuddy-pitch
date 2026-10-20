"""Isolated SQLite + ScriptedVision HTTP regressions for stale browser writes."""
import pytest
from fastapi.testclient import TestClient
from tests.test_workflow import F, make, up
from tests.fixtures import photo

H = {"X-Portal-User": "reviewer"}
PREFIX = "/pv/WBILL-1/__commit/" + "a" * 40


def setup(tmp_path, **settings):
    svc, a = make(tmp_path, [F("粤B12345", "2026-10-10", "08:00", "08:10", "11000", "10000", "1000")], **settings)
    b = TestClient(a.app)
    a.headers.update(H); b.headers.update(H)
    return svc, a, b


def test_two_clients_save_reconcile_approve_and_lost_ack(tmp_path):
    svc, a, b = setup(tmp_path)
    rid = up(a).json()["records"][0]["id"]
    path = f"/api/v1/records/{rid}"
    old = a.get(path).json(); same = b.get(path).json()
    assert old["version"] == same["version"]
    fresh = b.patch(path, json={"expected_version": same["version"], "fields": {"净重": "900", "总重": "10900"}}).json()
    draft = {**old["fields"], "货名": "A 的完整草稿"}
    body = {"expected_version": old["version"], "fields": draft}
    history = svc.history(rid)
    assert a.patch(path, json=body).status_code == 409
    result = a.post("/api/v1/records/approve", json={"ids": [rid], "versions": {rid: old["version"]}}).json()
    assert result["approved"] == [] and result["skipped"][0]["code"] == "Conflict"
    assert svc.history(rid) == history
    assert a.get(path).json() == fresh
    # Explicit reconciliation keeps B's new weights and A's intended goods edit.
    latest = a.get(path).json()
    merged = {**latest["fields"], "货名": draft["货名"]}
    retry = {"expected_version": latest["version"], "fields": merged}
    assert a.patch(path, json=retry).status_code == 200  # ACK deliberately discarded.
    current = b.get(path).json()
    after_b = b.patch(path, json={"expected_version": current["version"], "fields": {"备注": "B later"}}).json()
    history = svc.history(rid)
    assert a.patch(path, json=retry).status_code == 409
    assert a.get(path).json() == after_b and svc.history(rid) == history
    viewed = a.get(path).json()
    assert viewed["fields"]["净重"] == "900" and viewed["fields"]["货名"] == draft["货名"]
    assert a.post("/api/v1/records/approve", json={"ids": [rid], "versions": {rid: viewed["version"]}}).json()["approved"] == [rid]
    approved = a.get(path).json()
    edited = a.patch(path, json={"expected_version": approved["version"], "fields": {"备注": "needs review"}}).json()
    assert edited["stage"] == "submitted" and edited["approved_by"] is None


@pytest.mark.parametrize("invalid", [None, True, False, "0", -1, 1.0, [], {}])
def test_explicit_invalid_versions_never_become_unconditional(tmp_path, invalid):
    svc, a, b = setup(tmp_path)
    rid = up(a).json()["records"][0]["id"]
    before = a.get(f"/api/v1/records/{rid}").json(); history = svc.history(rid)
    for prefix in ["/api", "/api/v1"]:
        assert a.patch(f"{prefix}/records/{rid}", json={"fields": {"货名": "bad"}, "expected_version": invalid}).status_code == 422
    assert a.post(f"/api/v1/records/{rid}/submit", json={"expected_version": invalid}).status_code == 422
    result = a.post("/api/v1/records/approve", json={"ids": [rid], "versions": {rid: invalid}}).json()
    assert result["approved"] == [] and result["skipped"][0]["code"] == "InvalidInput"
    assert a.get(f"/api/v1/records/{rid}").json() == before and svc.history(rid) == history


def test_legacy_omission_and_partial_batch(tmp_path):
    svc, a, b = setup(tmp_path)
    rid = up(a).json()["records"][0]["id"]
    assert a.patch(f"/api/records/{rid}", json={"fields": {"货名": "legacy"}}).status_code == 200
    assert a.post(f"/api/v1/records/{rid}/submit", json={}).status_code == 200
    for invalid in [None, False, "0", -1, []]:
        assert a.post("/api/v1/records/approve", json={"ids": [rid], "versions": invalid}).status_code == 422
    assert a.post("/api/v1/records/approve", json={"ids": [rid], "versions": {}}).json()["approved"] == []
    assert a.post("/api/v1/records/approve", json={"ids": [rid]}).json()["approved"] == [rid]


def test_mixed_batch_keeps_per_record_results(tmp_path):
    svc, a = make(tmp_path, [F(f"粤B{i}", "2026-10-10", "08:00", "08:10", "11000", "10000", "1000") for i in range(3)])
    a.headers.update(H)
    records = [up(a).json()["records"][0] for _ in range(3)]
    ids = [r["id"] for r in records]
    a.patch(f"/api/v1/records/{ids[0]}", json={"fields": {"货名": "changed"}})
    versions = {r["id"]: r["version"] for r in records}; versions[ids[1]] = None
    histories = [svc.history(i) for i in ids]
    res = a.post("/api/v1/records/approve", json={"ids": ids, "versions": versions}).json()
    assert res["approved"] == [ids[2]] and len(res["skipped"]) == 2
    assert [svc.history(i) for i in ids[:2]] == histories[:2]


def test_real_prefix_http_paths_images_and_security(tmp_path):
    svc, a, b = setup(tmp_path, base_path=PREFIX, local_preview_origins=["http://localhost:9090"], capture_links={"tok": {"label": "现场"}})
    raw = photo(1)
    uploaded = a.post(PREFIX + "/api/v1/records", files={"photo": ("original.jpg", raw, "image/jpeg")}, data={"doc_type": "site_in"})
    assert uploaded.status_code == 201
    rec = uploaded.json()["records"][0]
    assert rec["orig_path"].startswith(PREFIX + "/files/")
    assert a.get(rec["orig_path"]).content == raw
    assert a.get(PREFIX + "/api/v1/records/" + rec["id"]).json()["version"] == rec["version"]
    assert a.patch(PREFIX + "/api/v1/records/" + rec["id"], json={"expected_version": rec["version"], "fields": {"货名": "prefixed"}}).status_code == 200
    for page in ["/", "/report", "/c/tok"]:
        html = a.get(PREFIX + page)
        assert html.status_code == 200 and '__WB_BASE_PATH__' not in html.text
        assert f'href="{PREFIX}/static/app.css' in html.text
        assert 'href="/report' not in html.text and 'fetch("/api' not in html.text
    assert a.get(PREFIX + "/static/app.css").status_code == 200
    sw = a.get(PREFIX + "/sw.js")
    assert sw.status_code == 200 and sw.headers["service-worker-allowed"] == PREFIX + "/"
    assert a.get("/api/v1/records").status_code == 404
    svc.blobs.url = lambda key: "https://s3.example/bucket/" + key
    assert svc.record_view(svc.get(rec["id"]))["orig_path"].startswith("https://s3.example/")
    local = TestClient(a.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 4000))
    path = PREFIX + "/api/v1/records/approve"
    headers = {**H, "Origin": "http://localhost:9090"}
    assert local.post(path, json={"ids": [], "versions": {}}, headers=headers).status_code == 200
    assert a.post(path, json={"ids": []}, headers=headers).status_code == 403
    for extra in [{"Origin": "http://evil.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}, {"Origin": "http://evil.example", "X-Forwarded-Host": "evil.example"}]:
        assert local.post(path, json={"ids": []}, headers={**headers, **extra}).status_code == 403


@pytest.mark.parametrize("path", ["/", "//host", "/a/../b", "/a/", "/a?x=1", "/a%2fb", "https://x", None])
def test_invalid_base_paths(tmp_path, path):
    with pytest.raises(ValueError, match="base_path"):
        setup(tmp_path, base_path=path)


def test_capture_prefix_submit_version_and_source_isolation(tmp_path):
    svc, a, _ = setup(tmp_path, base_path=PREFIX, capture_links={"tok": {"label": "现场"}, "other": {"label": "现场"}})
    raw = photo(2)
    cap = PREFIX + "/api/v1/capture/tok"
    rec = a.post(cap + "/records", files={"photo": ("a.jpg", raw, "image/jpeg")}).json()["records"][0]
    assert rec["orig_path"].startswith(cap + "/files/")
    assert a.get(rec["orig_path"]).content == raw
    assert a.get(rec["orig_path"].replace("/capture/tok/", "/capture/other/")).status_code == 404
    path = cap + "/records/" + rec["id"] + "/submit"
    assert a.post(path, json={"expected_version": None}).status_code == 422
    assert a.post(path, json={"expected_version": rec["version"], "fields": {"货名": "现场核对"}}).status_code == 200
    before = svc.history(rec["id"])
    assert a.post(path, json={"expected_version": rec["version"], "fields": {"货名": "旧值"}}).status_code == 409
    assert svc.history(rec["id"]) == before


def test_editor_state_machine():
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the delivered page controller regression test")
    result = subprocess.run([node, "tests/client_editor_state.cjs"], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
