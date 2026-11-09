"""FastAPI control plane, static dashboard and OpenAI-compatible proxy."""
import os
import platform
import secrets
import shutil
import sys
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from .diagnostics import collect_runtime
from .gateway import backend_health, forward_chat
from .ollama_discovery import discover_local_ollama
from .planner import make_plan
from .rpc_planner import plan_rpc
from .setup_guide import make_setup_guide
from .storage import DeviceStore
from .studio_store import StudioStore

STATIC = Path(__file__).with_name("static")

class GPU(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    vendor: str = Field(min_length=1, max_length=40)
    memory_mb: int = Field(ge=0, le=2000000)
    free_memory_mb: int | None = Field(default=None, ge=0, le=2000000)
    utilization_percent: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def free_memory_not_greater_than_total(self):
        if self.free_memory_mb is not None and self.free_memory_mb > self.memory_mb:
            raise ValueError("Reported free GPU memory cannot exceed total GPU memory.")
        return self

class RuntimeInfo(BaseModel):
    python_version: str | None = Field(default=None, max_length=120)
    cuda_driver: str | None = Field(default=None, max_length=120)
    vllm_version: str | None = Field(default=None, max_length=120)
    ray_version: str | None = Field(default=None, max_length=120)
    docker_present: bool = False
    docker_version: str | None = Field(default=None, max_length=120)
    nvidia_smi_present: bool = False
    ollama_present: bool = False
    llama_server_present: bool = False
    rpc_server_present: bool = False
    exo_present: bool = False
    disk_free_mb: int = Field(default=0, ge=0, le=1000000000)

class Hardware(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    platform: Literal["windows", "linux", "darwin", "android", "ios", "other"]
    os_version: str = Field(max_length=240)
    cpu_count: int = Field(ge=0, le=4096)
    ram_mb: int = Field(ge=0, le=100000000)
    gpus: list[GPU] = Field(max_length=128)
    runtime: RuntimeInfo = Field(default_factory=RuntimeInfo)

class Enrollment(BaseModel):
    join_token: str = Field(min_length=24, max_length=256)
    hardware: Hardware

class Heartbeat(BaseModel):
    device_id: str
    agent_token: str
    hardware: Hardware

class JoinRequest(BaseModel):
    expires_minutes: int = Field(default=15, ge=5, le=120)

class BackendRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=180)
    base_url: str = Field(min_length=10, max_length=300)
    kind: Literal["vllm", "ollama", "openai-compatible", "exo", "llama-cpp"] = "vllm"

class RpcWorker(BaseModel):
    device_id: str = Field(min_length=12, max_length=80)
    endpoint: str = Field(min_length=5, max_length=160)

class RpcPlanRequest(BaseModel):
    model_id: str
    workers: list[RpcWorker] = Field(min_length=1, max_length=16)
    network_acknowledged: bool = False

class InferenceKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)

class StudioConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    model_id: str = Field(min_length=1, max_length=180)
    system_prompt: str = Field(default="", max_length=8000)
    temperature: float = Field(default=0.7, ge=0, le=2)

class StudioConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    model_id: str | None = Field(default=None, min_length=1, max_length=180)
    system_prompt: str | None = Field(default=None, max_length=8000)
    temperature: float | None = Field(default=None, ge=0, le=2)

class StudioMessageCreate(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=32768)

class PlanRequest(BaseModel):
    model_id: str
    parameters_b: float = Field(ge=.1, le=2000)
    quantization_bits: Literal[4, 8, 16] = 4
    device_ids: list[str] | None = None

def create_app(db_path=None, admin_token=None, transport=None):
    app = FastAPI(title="MulDeAIServ", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.store = DeviceStore(db_path or os.getenv("MULDEAI_DB_PATH", "./data/muldeaiserv.db"))
    app.state.secret = admin_token if admin_token is not None else os.getenv("MULDEAI_ADMIN_TOKEN", "")
    app.state.transport = transport
    app.state.studio = StudioStore(app.state.store)

    def require_admin(authorization: str | None = Header(default=None)):
        secret = app.state.secret
        if len(secret) < 24:
            raise HTTPException(503, "Set MULDEAI_ADMIN_TOKEN (at least 24 characters) on the server.")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Bearer token required.", headers={"WWW-Authenticate": "Bearer"})
        if not secrets.compare_digest(authorization[7:], secret):
            raise HTTPException(401, "Invalid admin token.", headers={"WWW-Authenticate": "Bearer"})

    def require_inference(authorization: str | None = Header(default=None)):
        secret = app.state.secret
        if len(secret) < 24:
            raise HTTPException(503, "Controller admin token not configured.")
        token = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
        if not ((len(token) == len(secret) and secrets.compare_digest(token, secret))
                or app.state.store.verify_inference_key(token)):
            raise HTTPException(401, "Invalid inference key.", headers={"WWW-Authenticate": "Bearer"})

    @app.get("/api/health")
    def health():
        return {"status": "ok", "configured": len(app.state.secret) >= 24}

    @app.get("/api/overview", dependencies=[Depends(require_admin)])
    def overview():
        return app.state.store.overview()

    @app.get("/api/doctor", dependencies=[Depends(require_admin)])
    def doctor():
        return {"os": platform.platform(), "python": sys.version.split()[0],
                "docker": bool(shutil.which("docker")), "ray": bool(shutil.which("ray")),
                "vllm": bool(shutil.which("vllm")), "nvidia_smi": bool(shutil.which("nvidia-smi")),
                "runtime": collect_runtime(),
                "note": "These checks describe the controller host only. They do not install or configure GPU runtimes."}

    @app.get("/api/setup/guide", dependencies=[Depends(require_admin)])
    def setup_guide(engine: Literal["controller", "vllm", "llama-cpp-rpc", "exo"] = "controller",
                    platform_name: Literal["windows", "linux", "darwin", "android", "ios", "other"] = "linux",
                    device_id: str | None = None):
        runtime = collect_runtime()
        system = platform_name
        if device_id:
            device = next((d for d in app.state.store.devices() if d["id"] == device_id), None)
            if device is None:
                raise HTTPException(404, "Device not found.")
            system = device["platform"]
            runtime = device.get("runtime") or {}
        return make_setup_guide(engine, system, runtime)

    @app.post("/api/join-tokens", dependencies=[Depends(require_admin)])
    def join(payload: JoinRequest):
        return app.state.store.create_join(payload.expires_minutes)

    @app.post("/api/agent/enroll")
    def enroll(payload: Enrollment):
        try:
            return app.state.store.enroll(payload.join_token, payload.hardware.model_dump())
        except ValueError:
            raise HTTPException(401, "Join token invalid or expired.") from None

    @app.post("/api/agent/heartbeat")
    def heartbeat(payload: Heartbeat):
        if not app.state.store.heartbeat(payload.device_id, payload.agent_token,
                                         payload.hardware.model_dump()):
            raise HTTPException(401, "Agent credentials invalid.")
        return {"accepted": True}

    @app.delete("/api/devices/{device_id}", dependencies=[Depends(require_admin)])
    def delete_device(device_id: str):
        if not app.state.store.revoke_device(device_id):
            raise HTTPException(404, "Device not found.")
        return {"revoked": True}

    @app.get("/api/inference-keys", dependencies=[Depends(require_admin)])
    def list_inference_keys():
        return app.state.store.inference_keys()

    @app.post("/api/inference-keys", dependencies=[Depends(require_admin)], status_code=201)
    def create_inference_key(payload: InferenceKeyRequest):
        try:
            return app.state.store.create_inference_key(payload.name)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.delete("/api/inference-keys/{key_id}", dependencies=[Depends(require_admin)])
    def revoke_inference_key(key_id: str):
        if not app.state.store.revoke_inference_key(key_id):
            raise HTTPException(404, "Key not found.")
        return {"revoked": True}

    @app.post("/api/plans", dependencies=[Depends(require_admin)])
    def plan(payload: PlanRequest):
        try:
            return make_plan(app.state.store.devices(), payload.model_id,
                             payload.parameters_b, payload.quantization_bits, payload.device_ids)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/plans/llama-rpc", dependencies=[Depends(require_admin)])
    def llama_rpc_plan(payload: RpcPlanRequest):
        try:
            return plan_rpc(app.state.store.devices(), payload.model_id,
                            [w.model_dump() for w in payload.workers], payload.network_acknowledged)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/discovery/ollama", dependencies=[Depends(require_admin)])
    async def discover_ollama():
        return await discover_local_ollama(app.state.transport)

    @app.get("/api/backends", dependencies=[Depends(require_admin)])
    def backends():
        return app.state.store.backends()

    @app.post("/api/backends", status_code=201, dependencies=[Depends(require_admin)])
    def add_backend(payload: BackendRequest):
        try:
            return app.state.store.create_backend(
                payload.name, payload.model_id, payload.base_url, payload.kind)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/backends/{backend_id}/health", dependencies=[Depends(require_admin)])
    async def check_backend_health(backend_id: str):
        backend = next((b for b in app.state.store.backends() if b["id"] == backend_id), None)
        if backend is None:
            raise HTTPException(404, "Backend not found.")
        return await backend_health(backend["base_url"], app.state.transport)

    @app.delete("/api/backends/{backend_id}", dependencies=[Depends(require_admin)])
    def delete_backend(backend_id: str):
        if not app.state.store.delete_backend(backend_id):
            raise HTTPException(404, "Backend not found.")
        return {"deleted": True}

    @app.get("/api/studio/conversations", dependencies=[Depends(require_admin)])
    def studio_list():
        return app.state.studio.list()

    @app.post("/api/studio/conversations", status_code=201, dependencies=[Depends(require_admin)])
    def studio_create(payload: StudioConversationCreate):
        if app.state.store.backend_for_model(payload.model_id) is None:
            raise HTTPException(422, "Choose a registered model before starting a chat.")
        try:
            return app.state.studio.create(
                payload.title, payload.model_id, payload.system_prompt, payload.temperature
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/studio/conversations/{conversation_id}", dependencies=[Depends(require_admin)])
    def studio_get(conversation_id: str):
        result = app.state.studio.get(conversation_id)
        if result is None:
            raise HTTPException(404, "Conversation not found.")
        return result

    @app.patch("/api/studio/conversations/{conversation_id}", dependencies=[Depends(require_admin)])
    def studio_update(conversation_id: str, payload: StudioConversationUpdate):
        changes = payload.model_dump(exclude_unset=True)
        if any(value is None for value in changes.values()):
            raise HTTPException(422, "Conversation values cannot be null.")
        if "model_id" in changes and app.state.store.backend_for_model(changes["model_id"]) is None:
            raise HTTPException(422, "Choose a registered model.")
        try:
            result = app.state.studio.update(conversation_id, **changes)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if result is None:
            raise HTTPException(404, "Conversation not found.")
        return result

    @app.post("/api/studio/conversations/{conversation_id}/messages", status_code=201,
              dependencies=[Depends(require_admin)])
    def studio_message(conversation_id: str, payload: StudioMessageCreate):
        try:
            result = app.state.studio.add_message(conversation_id, payload.role, payload.content)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if result is None:
            raise HTTPException(404, "Conversation not found.")
        return result

    @app.delete("/api/studio/conversations/{conversation_id}", dependencies=[Depends(require_admin)])
    def studio_delete(conversation_id: str):
        if not app.state.studio.delete(conversation_id):
            raise HTTPException(404, "Conversation not found.")
        return {"deleted": True}

    @app.get("/v1/models", dependencies=[Depends(require_inference)])
    def models():
        return {"object": "list", "data": [
            {"id": b["model_id"], "object": "model", "owned_by": "muldeaiserv"}
            for b in app.state.store.backends()]}

    @app.post("/v1/chat/completions", dependencies=[Depends(require_inference)])
    async def chat(payload: dict):
        model_id = payload.get("model")
        if not isinstance(model_id, str) or not isinstance(payload.get("messages"), list):
            raise HTTPException(422, "Supply model and messages.")
        backend = app.state.store.backend_for_model(model_id)
        if not backend:
            raise HTTPException(404, "Model not registered.")
        return await forward_chat(backend["base_url"], payload, app.state.transport)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app

app = create_app()
