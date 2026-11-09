# Architecture and trust boundaries

## Components

**Controller (Python/FastAPI):** local-first HTTP service, SQLite registry, static dashboard, planner, backend gateway. Start with Python module or command-line entry point. The controller does not load model weights itself.

**Hardware agent (Python):** optional process on Windows, Linux or macOS. Reports OS name, CPU count, total system RAM, NVIDIA GPU names and reported VRAM. Enrollment uses a 15-minute (configurable) single-use token; after first enrollment each agent uses its distinct long-lived credential. Agent does not poll for, receive, or execute shell commands.

**Dashboard (browser):** client for all controller operations. Runs in desktop and mobile browsers. Admin bearer secret lives only in JavaScript process memory; refreshing the page requires re-entering it. No telemetry is fake or seeded.

**Model backends:** independently configured vLLM, Ollama, or other OpenAI-compatible service on a private IP and explicit port. The gateway sends non-streaming chat completions to the backend selected by model ID and exposes its model list via one authenticated endpoint.

**vLLM/Ray (optional):** manually prepared Linux GPU nodes for a single sharded model. The planner outputs estimated VRAM, blockers, tensor-parallel size, pipeline-parallel size and a command, without performing any installation or launch.

## Data flows

1. Operator launches localhost controller and obtains a secret.
2. Browser sends bearer secret to admin routes. Credentials are not stored in browser persistent storage.
3. Operator issues short-lived enrollment secret; agent exchanges it for per-device ID/secret over HTTPS or loopback.
4. Agent refreshes its hardware report every 20 seconds. A device is offline after 75 seconds.
5. Operator plans a supported distributed deployment, manually launches it and registers the final private inference endpoint.
6. Authenticated inference request selects the explicit model ID; controller forwards to the matched private backend; response is returned without exposing admin credentials upstream.

## Security invariants and limitations

- Admin token: 24+ characters, configured by environment or generated transiently by localhost-only CLI.
- Agent secrets and join tokens: SHA-256 digests in local SQLite; original one-time join token is shown only when created.
- SQLite data and local agent configuration are sensitive; protect file-system access. Agent configuration is chmod 0600 on POSIX. Windows file ACL protection is left to the account.
- Private backend URL requirement rejects hostnames except localhost and non-private destinations; this intentionally limits convenience to constrain SSRF. Only admin may register backends.
- No arbitrary remote commands, automatic package installation, public model downloads or network-port exposure.
- The API currently uses the same admin bearer token for management and inference; dedicated scoped API keys are P1.
- Controller HTTP on non-loopback is insecure unless protected with TLS/proxy/VPN. Do not expose Ray, NVIDIA runtime, model APIs or controller on the public Internet.
- The gateway supports non-streaming JSON chat requests only. Streaming, backend-specific API keys, tool/function compatibility matrix, usage quotas and health checks remain P1.
- Device memory measurements show totals from currently online agents. They are not a shared RAM or VRAM address space.
- The current planner is NVIDIA/Linux-specific. It cannot predict real memory feasibility from a parameter count alone, especially with MoE, KV cache and runtime overhead.
- The current native agent is not an Android/iOS mobile worker. Mobile devices can access the responsive browser UI.

## Database schema

Devices: platform, CPU, total RAM, GPUs JSON, agent credential digest and last-seen timestamp.
Join tokens: credential digests, expiry and consumed timestamp.
Backends: model ID, runtime type, name, private origin, created time.

No messages, prompts or model weights are stored by the controller in v0.1.

## API routes

- Public: GET /api/health
- Single-use enrollment: POST /api/agent/enroll
- Agent-only: POST /api/agent/heartbeat (requires unique device credentials)
- Admin: GET /api/overview, GET /api/doctor, POST /api/join-tokens, POST /api/plans
- Admin: GET/POST /api/backends, DELETE /api/backends/{id}
- Admin: GET /v1/models, POST /v1/chat/completions

## Future evolution

- Signed, allowlisted deployments with explicit approval, TLS identities, short-lived scoped tokens and audited actions.
- Genuine distributed vLLM node deployment and link benchmarking.
- Independently routable llama.cpp/Metal/Vulkan and specialized edge services.
- Native mobile companion apps and separately verified experimental distributed inference.
