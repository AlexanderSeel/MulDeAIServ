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
