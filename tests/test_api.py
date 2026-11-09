import httpx
from fastapi.testclient import TestClient

from muldeaiserv.app import create_app

ADMIN = "a-very-long-secret-for-ci-tests-123"
HEADERS = {"Authorization":"Bearer " + ADMIN}
HW = {"name":"worker","platform":"linux","os_version":"Linux","cpu_count":8,"ram_mb":8192,
      "gpus":[{"name":"NVIDIA Demo","vendor":"nvidia","memory_mb":12288}]}

def client(tmp_path, transport=None):
    return TestClient(create_app(db_path=tmp_path / "api.db", admin_token=ADMIN, transport=transport))

def test_authentication_enrollment_and_planner(tmp_path):
    c = client(tmp_path)
    assert c.get("/").status_code == 200
    assert c.get("/api/overview").status_code == 401
    assert c.get("/api/overview", headers={"Authorization":"Bearer wrong"}).status_code == 401
    token = c.post("/api/join-tokens", json={}, headers=HEADERS)
    assert token.status_code == 200
    payload = {"join_token":token.json()["token"],"hardware":HW}
    enroll = c.post("/api/agent/enroll", json=payload)
    assert enroll.status_code == 200
    assert c.post("/api/agent/enroll", json=payload).status_code == 401
    session = enroll.json()
    heartbeat = c.post("/api/agent/heartbeat", json={
        "device_id":session["device_id"],"agent_token":session["agent_token"],"hardware":HW})
    assert heartbeat.status_code == 200
    overview = c.get("/api/overview", headers=HEADERS).json()
    assert overview["stats"]["online_devices"] == 1
    plan = c.post("/api/plans", headers=HEADERS,
        json={"model_id":"org/test-8b","parameters_b":8,"quantization_bits":4})
    assert plan.status_code == 200
    assert plan.json()["can_generate_command"]

def test_chat_proxy_uses_configured_backend_without_forwarding_admin_token(tmp_path):
    captured = []
    def upstream(req):
        captured.append(req)
        return httpx.Response(200,json={"choices":[{"message":{"content":"hello from local model"}}]})
    c = client(tmp_path, httpx.MockTransport(upstream))
    created = c.post("/api/backends", headers=HEADERS, json={
        "name":"Test","model_id":"local-test","base_url":"http://127.0.0.1:8001","kind":"vllm"})
    assert created.status_code == 201
    assert c.get("/v1/models",headers=HEADERS).json()["data"][0]["id"] == "local-test"
    answer = c.post("/v1/chat/completions",headers=HEADERS,
        json={"model":"local-test","messages":[{"role":"user","content":"hi"}]})
    assert answer.status_code == 200
    assert answer.json()["choices"][0]["message"]["content"] == "hello from local model"
    assert str(captured[0].url) == "http://127.0.0.1:8001/v1/chat/completions"
    assert "authorization" not in captured[0].headers
    assert c.post("/v1/chat/completions",headers=HEADERS,
        json={"model":"local-test","messages":[],"stream":True}).status_code == 422
    assert c.delete("/api/backends/" + created.json()["id"],headers=HEADERS).status_code == 200

def test_invalid_backend_url_cannot_be_registered(tmp_path):
    c = client(tmp_path)
    response = c.post("/api/backends",headers=HEADERS,json={
        "name":"bad","model_id":"bad","base_url":"http://169.254.169.254:80","kind":"vllm"})
    assert response.status_code == 422

def test_admin_secret_is_required(tmp_path):
    c = TestClient(create_app(db_path=tmp_path / "unset.db", admin_token=""))
    assert c.get("/api/overview").status_code == 503

def test_scoped_inference_key_and_agent_revocation(tmp_path):
    c = client(tmp_path)
    join = c.post("/api/join-tokens", headers=HEADERS, json={}).json()
    enrolled = c.post("/api/agent/enroll", json={"join_token":join["token"], "hardware":HW}).json()
    key = c.post("/api/inference-keys", headers=HEADERS, json={"name":"CI client"})
    assert key.status_code == 201
    token = key.json()["token"]
    assert token.startswith("mda_")
    infer_headers = {"Authorization":"Bearer " + token}
    assert c.get("/v1/models", headers=infer_headers).status_code == 200
    assert c.get("/api/overview", headers=infer_headers).status_code == 401
    keys = c.get("/api/inference-keys", headers=HEADERS).json()
    assert len(keys) == 1 and "token" not in keys[0] and "digest" not in keys[0]
    assert c.delete("/api/devices/" + enrolled["device_id"], headers=HEADERS).status_code == 200
    assert c.post("/api/agent/heartbeat", json={
        "device_id":enrolled["device_id"],"agent_token":enrolled["agent_token"],
        "hardware":HW}).status_code == 401
    assert c.delete("/api/inference-keys/" + key.json()["id"], headers=HEADERS).status_code == 200
    assert c.get("/v1/models", headers=infer_headers).status_code == 401
