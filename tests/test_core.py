import pytest

from muldeaiserv.planner import make_plan
from muldeaiserv.security import private_origin
from muldeaiserv.storage import DeviceStore

HW = {"name":"test-linux","platform":"linux","os_version":"Linux 6.x",
      "cpu_count":8,"ram_mb":32768,
      "gpus":[{"name":"NVIDIA Test","vendor":"nvidia","memory_mb":12288}]}

def test_enrollment_is_single_use_and_credentials_are_not_exposed(tmp_path):
    store = DeviceStore(tmp_path / "cluster.db")
    issued = store.create_join(15)
    session = store.enroll(issued["token"], HW)
    assert store.heartbeat(session["device_id"],session["agent_token"],HW)
    assert not store.heartbeat(session["device_id"],"incorrect",HW)
    assert store.devices()[0]["online"]
    assert "agent_token" not in store.overview()["devices"][0]
    assert "agent_digest" not in store.overview()["devices"][0]
    with pytest.raises(ValueError):
        store.enroll(issued["token"], HW)
    with store.connection() as db:
        stored = db.execute("SELECT digest FROM joins").fetchone()["digest"]
    assert stored != issued["token"]

def test_join_token_expires(tmp_path):
    store = DeviceStore(tmp_path / "cluster.db")
    join = store.create_join()
    with store.connection() as db:
        db.execute("UPDATE joins SET expires=0")
    with pytest.raises(ValueError):
        store.enroll(join["token"], HW)

@pytest.mark.parametrize("url", [
    "http://8.8.8.8:80", "http://169.254.169.254:80",
    "http://example.com:8080", "http://127.0.0.1:80/v1",
    "http://user:password@127.0.0.1:8001", "file:///etc/passwd",
    "http://0.0.0.0:1234", "http://127.0.0.1",
])
def test_reject_unsafe_backends(url):
    with pytest.raises(ValueError):
        private_origin(url)

def test_allow_private_backends():
    assert private_origin("http://127.0.0.1:8001/") == "http://127.0.0.1:8001"
    assert private_origin("http://192.168.1.25:11434") == "http://192.168.1.25:11434"

def test_planner_requires_real_supported_gpu_nodes():
    device = {**HW,"id":"n1","online":True}
    other = {**HW,"id":"n2","online":True}
    result = make_plan([device,other],"org/model-8b",8,4)
    assert result["can_generate_command"]
    assert result["tensor_parallel_size"] == 1
    assert result["pipeline_parallel_size"] == 2
    assert "--distributed-executor-backend ray" in result["command"]
    unsupported = make_plan([{**device,"platform":"windows"}],"org/model-8b",8,4,["n1"])
    assert not unsupported["can_generate_command"]
    assert unsupported["blockers"]
    empty = make_plan([],"org/model-8b",8,4)
    assert empty["command"] is None

def test_backend_registry(tmp_path):
    store = DeviceStore(tmp_path / "cluster.db")
    backend = store.create_backend("Local","model-1","http://127.0.0.1:8001","vllm")
    assert store.backend_for_model("model-1")["id"] == backend["id"]
    with pytest.raises(ValueError):
        store.create_backend("Duplicate","model-1","http://127.0.0.1:8002","ollama")
    assert store.delete_backend(backend["id"])
    assert store.backend_for_model("model-1") is None

def test_exo_and_llama_cpp_backend_metadata(tmp_path):
    store = DeviceStore(tmp_path / 'engines.db')
    for kind in ('exo', 'llama-cpp'):
        created = store.create_backend(kind, kind + '-test', 'http://127.0.0.1:8001', kind)
        assert created['kind'] == kind

def test_inference_key_storage_and_revoke(tmp_path):
    store = DeviceStore(tmp_path / "keys.db")
    key = store.create_inference_key("Agent")
    assert store.verify_inference_key(key["token"])
    assert not store.verify_inference_key(key["token"] + "bad")
    assert "digest" not in store.inference_keys()[0]
    assert "token" not in store.inference_keys()[0]
    assert store.revoke_inference_key(key["id"])
    assert not store.verify_inference_key(key["token"])

def test_rpc_endpoint_validation_and_network_policy():
    from muldeaiserv.rpc_planner import rpc_endpoint, plan_rpc
    assert rpc_endpoint("192.168.1.25:50052") == "192.168.1.25:50052"
    assert rpc_endpoint("[fd12::1]:50052") == "[fd12::1]:50052"
    for addr in ("8.8.8.8:50052", "169.254.169.254:50052", "https://localhost:50052",
                 "192.168.1.4", "192.168.1.4:0", "example.org:50052", "10.0.0.1:22/path"):
        with pytest.raises(ValueError):
            rpc_endpoint(addr)
    device = {**HW, "id":"worker1", "online":True, "platform":"windows"}
    selected = [{"device_id":"worker1","endpoint":"192.168.1.30:50052"}]
    no_ack = plan_rpc([device], "ggml-org/gemma-3-1b-it-GGUF", selected, False)
    assert not no_ack["can_generate_command"]
    ok = plan_rpc([device], "ggml-org/gemma-3-1b-it-GGUF", selected, True)
    assert ok["can_generate_command"]
    assert "--rpc 192.168.1.30:50052" in ok["command"]
    assert ok["workers"][0]["runtime_verified"] is False
    assert "reported_total_system_ram_mb" in ok
    offline = plan_rpc([{**device,"online":False}], "ggml-org/gemma-3-1b-it-GGUF", selected, True)
    assert not offline["can_generate_command"]
    with pytest.raises(ValueError):
        plan_rpc([device], "ggml-org/gemma-3-1b-it-GGUF", selected*2, True)

def test_runtime_diagnostics_persist_and_old_database_migrates(tmp_path):
    import sqlite3
    file = tmp_path / "old.db"
    with sqlite3.connect(file) as db:
        db.execute("CREATE TABLE devices (id TEXT PRIMARY KEY,name TEXT NOT NULL,platform TEXT NOT NULL,os_version TEXT NOT NULL,cpu_count INTEGER NOT NULL,ram_mb INTEGER NOT NULL,gpus TEXT NOT NULL,agent_digest TEXT NOT NULL,created REAL NOT NULL,seen REAL NOT NULL)")
    store = DeviceStore(file)
    hw = {**HW, "runtime":{"cuda_driver":"550.60","docker_present":True,"rpc_server_present":True}}
    session = store.enroll(store.create_join()["token"],hw)
    device = store.devices()[0]
    assert device["runtime"]["cuda_driver"] == "550.60"
    assert device["readiness"]["vllm_runtime_verified"]
    assert device["readiness"]["rpc_worker_candidate"]
    assert store.heartbeat(session["device_id"],session["agent_token"],{**HW})
    assert store.devices()[0]["runtime"] == {}

def test_manual_setup_guides_distinguish_unsupported_platforms():
    from muldeaiserv.setup_guide import make_setup_guide
    controller = make_setup_guide("controller","windows")
    assert controller["supported"]
    assert any("setup.ps1" in (s["command"] or "") for s in controller["steps"])
    assert not make_setup_guide("vllm","android")["supported"]
    assert not make_setup_guide("exo","windows")["supported"]
    assert make_setup_guide("exo","darwin")["supported"]
    rpc = make_setup_guide("llama-cpp-rpc","linux")
    assert rpc["supported"]
    assert rpc["mode"] == "manual_review_only"

def test_free_vram_budgets_only_when_all_nodes_report_it():
    from muldeaiserv.planner import make_plan
    gpu = {"name":"NVIDIA demo","vendor":"nvidia","memory_mb":24576,
           "free_memory_mb":2048,"utilization_percent":84}
    device = {**HW,"gpus":[gpu],"id":"node", "online":True}
    plan = make_plan([device],"example/8b",8,4)
    assert plan["reported_free_vram_mb"] == 2048
    assert plan["conservative_usable_vram_mb"] == round(2048*.9)
    legacy = {**device,"gpus":[{k:v for k,v in gpu.items() if k != "free_memory_mb"}]}
    assert make_plan([legacy],"example/8b",8,4)["reported_free_vram_mb"] is None

def test_nvidia_gpu_query_with_free_memory(monkeypatch):
    from muldeaiserv.agent import nvidia_gpus
    from types import SimpleNamespace
    monkeypatch.setattr("muldeaiserv.agent.subprocess.run",lambda *a,**kw:
                        SimpleNamespace(stdout="NVIDIA GPU, 12288, 8192, 33\\n"))
    gpus = nvidia_gpus()
    assert len(gpus) == 1
    assert gpus[0]["memory_mb"] == 12288
    assert gpus[0]["free_memory_mb"] == 8192
    assert gpus[0]["utilization_percent"] == 33
