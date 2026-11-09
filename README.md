# MulDeAIServ

**Multi-Device AI Service — a private, hardware-aware control plane for local LLMs.**

MulDeAIServ discovers and monitors your computers, helps plan compatible vLLM deployments, and exposes registered local inference backends through one OpenAI-compatible endpoint. It includes a responsive dashboard and a lightweight device agent.

> **Important:** vLLM can distribute model weights across supported GPU nodes using tensor and pipeline parallelism, typically coordinated through Ray. It **cannot** transparently pool arbitrary Windows, iOS, Android, CPU RAM and GPU VRAM into a single address space. Mobile devices are supported as dashboard/chat clients in the first release; experimental mobile compute workers are roadmap items, not shipped capabilities.

## Quick start (Python 3.11+)

```powershell
# Windows PowerShell
./scripts/setup.ps1
$env:MULDEAI_ADMIN_TOKEN = "replace-with-a-long-random-secret"
.venv/Scripts/python.exe -m muldeaiserv serve
```

```bash
# Linux/macOS
bash scripts/setup.sh
export MULDEAI_ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
.venv/bin/python -m muldeaiserv serve
```

Open **http://127.0.0.1:8765** and paste your admin token into the dashboard. The server binds to loopback by default. For LAN/mobile access, use an HTTPS reverse proxy or a private VPN; never expose an unencrypted admin token or Ray/vLLM cluster ports to the Internet.

From the dashboard, generate a short-lived join token, then on another Windows/Linux/macOS computer:

```bash
python -m muldeaiserv.agent --server https://your-private-server --join-token YOUR_JOIN_TOKEN
```

The agent reports CPU RAM and available GPUs, then sends heartbeats. It does not accept arbitrary remote shell commands.

After running a vLLM or another OpenAI-compatible model server, register its private network URL and model ID under **Backends**. Use `GET /v1/models` and `POST /v1/chat/completions` on MulDeAIServ with the same bearer admin token. vLLM deployments are **planned**, never silently executed.

## Included

- Responsive dashboard for local and LAN clients, including mobile browser UI.
- Short-lived, single-use device enrollment credentials and per-device heartbeat credentials.
- OS, RAM and NVIDIA GPU diagnostics; online/offline awareness.
- Conservative model-weight memory estimates and compatibility-gated vLLM/Ray command generation.
- Configurable local OpenAI-compatible model backends and authenticated chat proxy.
- Cross-platform Python CLI, Windows PowerShell and POSIX setup scripts, automated tests.
- A phased implementation plan in [PLAN.md](PLAN.md).

## Runtime and security

- Python 3.11+; FastAPI, Uvicorn and HTTPX. No Node toolchain required.
- Set `MULDEAI_ADMIN_TOKEN` before starting; unset/short secrets block privileged endpoints.
- `MULDEAI_DB_PATH` defaults to `./data/muldeaiserv.db`.
- Private-IP-literal backend addresses only in v0.1; no direct public Internet proxy endpoints.
- API keys must be kept secret. Do not publish the dashboard on public HTTP.
- The application stores backend metadata, device credentials as hashes, and no model weights.
- vLLM/Ray, GPU drivers, models and high-speed network configuration are separate deployment prerequisites.

## Tests

```bash
python -m pip install -e ".[dev]"
pytest -q
```

See [PLAN.md](PLAN.md) for limitations, architecture, platform support and implementation priorities.

Reference: [vLLM 0.7 distributed serving documentation](https://docs.vllm.ai/en/v0.7.0/serving/distributed_serving.html).

## Heterogeneous runtimes

The gateway can also register existing exo and llama.cpp HTTP model servers. These may support distributing parts of a model across supported devices in their own runtimes, but MulDeAIServ **does not yet install or manage their distributed workers**. See [Heterogeneous engine research](docs/HETEROGENEOUS_ENGINES.md). Current exo documentation focuses on compatible Apple silicon/MLX clusters, while llama.cpp RPC remains experimental and warns against open-network use.

## Setup guide and runtime diagnostics (v0.2 foundation)

MulDeAIServ now provides *non-executing* setup checklists and passive runtime preflight for registered Windows/Linux/macOS devices. The checklist helps distinguish model-server prerequisites from a configured distributed cluster.

In the dashboard open **Setup & diagnostics → Guided installation checklist**, select the engine (controller, vLLM/Ray, llama.cpp RPC or exo) and a registered device or operating system. Review every generated command before using it. This wizard does not install packages or start workers.

To generate the same checklist locally in the terminal (no controller necessary after package installation):

```powershell
.\.venv\Scripts\python.exe -m muldeaiserv guide --engine llama-cpp-rpc --platform windows
.\.venv\Scripts\python.exe -m muldeaiserv guide --engine vllm --platform linux --json
```

A paired agent reports Python version, detected NVIDIA driver, vLLM/Ray Python package versions, Docker executable, optional llama.cpp RPC, Ollama and exo executables, disk free space and NVIDIA GPU utilization/free VRAM when available. A missing component is reported as missing/unverified; detecting its binary **does not** prove that a distributed runtime is functional.

The Models & API screen also supports reviewed llama.cpp RPC worker endpoint plans (with an isolated-network acknowledgement). This creates a command, **not** a listener, package installation or worker launch. Treat llama.cpp RPC as experimental/insecure and do not use it outside an isolated trusted network.

### API client keys and health

Admin users can create revocable **inference-only** bearer tokens in Models & API. The full key appears once, is stored as a hash, and authorizes only OpenAI-compatible inference endpoints, not administrative operations. The administrator may revoke keys or an enrolled device at any time. Device revocation invalidates its heartbeat secret immediately.

The inference proxy supports OpenAI-compatible non-streaming chat and SSE streaming chat, with private-backend redirect refusal. The backend Test button checks the model server's `/v1/models` readiness endpoint. These capabilities are still under development; rate limits, backend-specific authentication, full audit logs and production security review are not yet implemented.

Reported total VRAM and currently free NVIDIA VRAM are shown separately. The model planner uses conservative heuristics and never guarantees weights/KV cache will fit.

### Important limits

- Runtime diagnostics and setup checklists are **not** automatic installation or cluster execution.
- Actual multi-node vLLM, exo and llama.cpp RPC integrations must still be validated using compatible hardware and private networking.
- Android and iOS currently access the browser dashboard; native worker apps are future work.
- `MULDEAI_ADMIN_TOKEN` is still an administrator credential. Use a scoped inference token in external AI clients, and prefer TLS/VPN for all non-local traffic.


## AI Studio — chat with your connected models

Open the dashboard at http://127.0.0.1:8765 and select **AI Studio**. This is an actual multi-turn chat client for the registered model endpoints, not a preview or mock. You can:

- Choose a connected vLLM, Ollama, llama.cpp HTTP or exo model.
- Send prompts with optional system instructions, model temperature and output token budget.
- Stream token responses when the selected backend supports OpenAI-compatible SSE, or switch to regular non-streaming chat.
- Start, reopen, search, rename and delete conversations stored in the controller's SQLite database.
- Stop a streaming generation and export an existing conversation as Markdown.
- Switch back to Overview, Device network, Models & API, or Setup & diagnostics without losing the saved conversation history.

**First-run shortcut:** In **Models & API**, choose **Connect local Ollama → Discover**. MulDeAIServ queries only the controller's own http://127.0.0.1:11434/api/tags endpoint. If Ollama is running and models are installed, select **Register** next to a model, then open **AI Studio**. For other model servers, register the private API origin and its served model ID manually.

**Privacy:** Saved chat titles, prompts, system instructions and AI responses are stored **unencrypted** in the controller's local SQLite database. Protect the data directory and system backups. No chat history is sent to a third-party server by MulDeAIServ itself, but your configured model backend receives chat prompts and history. Conversations require the admin token; inference-only API keys cannot read saved chats. Currently the chat sends up to the 40 most recent stored user/assistant messages to the model. Local generation still requires an actual running inference backend. See [AI Studio guide](docs/AI_STUDIO.md).

**Scope:** The web dashboard manages registered nodes, backend endpoints and setup plans. It does not yet deploy distributed vLLM/Ray/exo/llama.cpp RPC workers or combine arbitrary Android/iOS memory into a single RAM pool.
