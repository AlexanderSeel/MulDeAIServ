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
        json={"model":"local-test","messages":[],"stream":True}).status_code == 502
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

def test_rpc_planner_endpoint_is_admin_only(tmp_path):
    c = client(tmp_path)
    join = c.post("/api/join-tokens",headers=HEADERS,json={}).json()
    enrolled = c.post("/api/agent/enroll", json={"join_token":join["token"],"hardware":HW}).json()
    payload = {
        "model_id":"ggml-org/gemma-3-1b-it-GGUF",
        "workers":[{"device_id":enrolled["device_id"],"endpoint":"192.168.1.33:50052"}],
        "network_acknowledged":True
    }
    assert c.post("/api/plans/llama-rpc",json=payload).status_code == 401
    result = c.post("/api/plans/llama-rpc",headers=HEADERS,json=payload)
    assert result.status_code == 200
    assert result.json()["can_generate_command"]
    payload["workers"][0]["endpoint"] = "8.8.8.8:50052"
    assert c.post("/api/plans/llama-rpc",headers=HEADERS,json=payload).status_code == 422

def test_sse_proxy_streams_and_backend_probe(tmp_path):
    requests = []
    def upstream(req):
        requests.append(req)
        if req.method == "GET":
            return httpx.Response(200, json={"object":"list","data":[{"id":"local-test"}]})
        return httpx.Response(
            200, headers={"content-type":"text/event-stream"},
            content=b'data: {"choices":[{"delta":{"content":"hello"}}]}\\n\\n'
                    b'data: {"choices":[{"delta":{"content":" world"}}]}\\n\\n'
                    b'data: [DONE]\\n\\n'
        )
    c = client(tmp_path, httpx.MockTransport(upstream))
    item = c.post("/api/backends", headers=HEADERS, json={
        "name":"Local","model_id":"local-test","base_url":"http://127.0.0.1:8001","kind":"llama-cpp"
    }).json()
    health = c.get("/api/backends/" + item["id"] + "/health", headers=HEADERS)
    assert health.json() == {"status":"healthy","model_count":1}
    with c.stream("POST","/v1/chat/completions", headers=HEADERS,
                  json={"model":"local-test","messages":[],"stream":True}) as reply:
        body = reply.read().decode()
        assert reply.status_code == 200
        assert "text/event-stream" in reply.headers["content-type"]
        assert "hello" in body and "[DONE]" in body
    assert len(requests) == 2
    assert "authorization" not in requests[-1].headers

def test_readiness_reports_unreachable_without_disclosing_internal_error(tmp_path):
    def failed(req):
        raise httpx.ConnectError("sensitive internal detail",request=req)
    c = client(tmp_path, httpx.MockTransport(failed))
    item = c.post("/api/backends", headers=HEADERS, json={
        "name":"Down","model_id":"model-down","base_url":"http://127.0.0.1:8001","kind":"vllm"
    }).json()
    result = c.get("/api/backends/" + item["id"] + "/health", headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["status"] == "unreachable"
    assert "sensitive" not in str(result.json())

def test_setup_guides_and_selected_device_runtime(tmp_path):
    c = client(tmp_path)
    r = c.get("/api/setup/guide", params={"engine":"exo","platform_name":"windows"}, headers=HEADERS)
    assert r.status_code == 200
    assert not r.json()["supported"]
    token = c.post("/api/join-tokens",headers=HEADERS,json={}).json()["token"]
    hw = {**HW,"runtime":{"cuda_driver":"550.60","docker_present":True,"python_version":"3.11.9"}}
    session = c.post("/api/agent/enroll",json={"join_token":token,"hardware":hw}).json()
    resp = c.get("/api/setup/guide",params={
        "engine":"vllm","platform_name":"windows","device_id":session["device_id"]
    },headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["platform"] == "linux"
    assert resp.json()["supported"]
    assert c.get("/api/setup/guide",params={"device_id":"no-such-device"},
                 headers=HEADERS).status_code == 404
    assert c.get("/api/setup/guide",headers={"Authorization":"Bearer invalid"}).status_code == 401

def test_agent_gpu_telemetry_rejects_impossible_free_memory(tmp_path):
    c = client(tmp_path)
    token = c.post("/api/join-tokens", headers=HEADERS, json={}).json()["token"]
    impossible = {**HW, "gpus":[{"name":"Test","vendor":"nvidia",
                                  "memory_mb":4096,"free_memory_mb":8192}]}
    assert c.post("/api/agent/enroll",json={"join_token":token,"hardware":impossible}).status_code == 422
    valid = {**HW, "gpus":[{"name":"Test","vendor":"nvidia",
                             "memory_mb":8192,"free_memory_mb":4096}]}
    assert c.post("/api/agent/enroll",json={"join_token":token,"hardware":valid}).status_code == 200

def test_static_dashboard_resources_served(tmp_path):
    c = client(tmp_path)
    assert c.get("/static/app.js").status_code == 200
    assert c.get("/static/styles.css").status_code == 200
