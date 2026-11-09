# MulDeAIServ — implementation plan

Updated 2026-11-09. Checked items describe features present in source, not proof of a real GPU deployment.

## Product objective

Build a safe and approachable tool to connect multiple computers, assess GPU capacity, install and operate compatible inference runtimes, and expose local model APIs behind one gateway. Preferred workflow: check host → install controller → pair devices → assess model → deploy runtime → register endpoint → chat.

**Technical contract:** vLLM/Ray partitions a model across compatible GPU processes, not arbitrary device RAM. A 16 GB iPhone, a 32 GB Windows desktop and a 12 GB NVIDIA GPU do not automatically make a 60 GB unified memory pool. Independent model routing is different from model sharding.

## Mode matrix

| Mode | Platform | Current stage | Splits one model across devices? |
| --- | --- | --- | --- |
| Single vLLM | Linux NVIDIA GPU | Plan + manually connect | Within compatible GPUs |
| vLLM Ray TP/PP | Compatible Linux NVIDIA GPU nodes | Plan/runbook only | Yes, after manual deployment |
| Ollama/OpenAI-compatible backend | Windows/Linux/macOS | Gateway supported | No; independent runtime |
| Mobile dashboard | Android/iOS browser | UI implemented | No; clients |
| Native mobile worker | Android/iOS | Future research | Depends on separate inference engine |
| Arbitrary pooled CPU/GPU RAM | Heterogeneous hardware | Not supported in vLLM | No |

## Phase 0 — initial software foundation (implemented in source)

- [x] Python 3.11+ package, initial documentation and CLI.
- [x] Local-first server and admin-token authentication.
- [x] REST control plane, SQLite registry, health and diagnostics endpoints.
- [x] Short-lived single-use node enrollment, hashed node credentials, authenticated heartbeats.
- [x] Passive Windows/Linux/macOS RAM, CPU and NVIDIA GPU inventory.
- [x] Responsive desktop/mobile dashboard, overview and monitoring.
- [x] Conservative model-weight and available VRAM estimates; compatibility-gated Ray/vLLM command generation.
- [x] Registration of IP-literal private/local model servers, no public URL proxy.
- [x] Authenticated OpenAI-compatible models endpoint and non-streaming chat completions proxy.
- [x] In-browser model test, backend management and diagnostic display.
- [x] Cross-platform setup scripts, unit/API test suite and CI configuration.
- [ ] Run real multi-GPU/multi-node vLLM end-to-end validation (requires compatible hardware).
- [ ] Security audit and scan, formal release and versioned installer.

## Phase 1 — installation and secure network operations (P1)

- [ ] Guided wizard: install Python/Docker/drivers/CUDA/container runtime/Ray/vLLM with dry-run and explicit consent.
- [ ] Assisted private networking and QR enrollment, certificate management and trusted peer discovery.
- [ ] Accurate AMD/ROCm, Intel, Apple Metal and CPU inventory adapters.
- [ ] Credential revocation/rotation, RBAC, inference-only API keys and audit logging.
- [ ] Backend readiness, health checks, request limits, retries and SSE streaming.
- [ ] Database migrations, secure updates, backup/restore and metrics dashboards.

## Phase 2 — fully managed vLLM Ray clusters (P1)

- [ ] Validate runtime versions, model architecture, GPU counts, CUDA/NCCL and fast network links.
- [ ] Model-specific weight/KV cache budget and throughput/latency feasibility.
- [ ] Stage model weights with checksums and license acceptance across selected nodes.
- [ ] Generate pinned container deployments, health-check Ray head/worker and model processes.
- [ ] Explicitly approved, allowlisted start/stop/restart operations, monitoring and rollback; no arbitrary shell execution.
- [ ] Two-machine GPU integration tests with actual distributed inference and resource measurements.

## Phase 3 — heterogeneous inference fabric (P2)

- [ ] Independent inference backend routing, pooling, queueing, failover and affinity.
- [ ] Optional llama.cpp HTTP workers and runtime-specific CPU, Metal, Vulkan and CUDA support.
- [ ] Model catalog, quantization choices, licenses and assisted downloads.
- [ ] Independent specialized workers for embeddings, retrieval, reranking and tool tasks.
- [ ] Clearly distinguish model partitioning from multiple model servers in the UI.

## Phase 4 — Android/iOS (P3)

- [ ] Offline-capable installable PWA and native companion app.
- [ ] Secure Android/iOS telemetry and opt-in delegated tasks.
- [ ] Evaluate mobile model runtimes and credible heterogeneous layer-partitioning approaches with reproducible benchmarks before promising device RAM pooling.
- [ ] Battery, thermal, permissions and network privacy safeguards.

## Phase 5 — release quality (P2)

- [ ] Topology visualization, real GPU utilization history, chat sessions and comparisons.
- [ ] Desktop installers, migration tests, cross-OS CI, accessibility and visual regression.
- [ ] Hardware-in-the-loop GPU benchmarking, documented limits and stable releases.

## Validation gates

After each coherent batch run Python compileall, pytest and wheel build. Inspect CI and fix regressions. Never mark true distributed GPU deployment complete based only on command-generation tests or mock backends. Avoid secrets, unsafe remote code execution, fabricated statistics or misleading pooled-memory claims.

## References

- [vLLM 0.7 distributed serving](https://docs.vllm.ai/en/v0.7.0/serving/distributed_serving.html)
- [Current vLLM parallelism guide](https://docs.vllm.ai/en/latest/serving/parallelism_scaling.html)
- [Architecture](docs/ARCHITECTURE.md)
- [Manual vLLM runbook](docs/VLLM_RUNBOOK.md)

## Research update — heterogeneous model partitioning (2026-11-09)

- [x] Document technical options in docs/HETEROGENEOUS_ENGINES.md: current exo MLX clusters, llama.cpp RPC and mobile MLC inference.
- [x] Add metadata types to register existing exo and llama.cpp OpenAI-compatible APIs behind the gateway.
- [ ] Add version-specific exo setup and cluster health detection; current exo release is Apple silicon/MLX focused and Mac/Linux cluster mixing is documented as unsupported.
- [ ] Add isolated-network-only llama.cpp RPC setup and security safeguards, plus per-device remote memory accounting.
- [ ] Implement and benchmark verified Android native RPC/MLC integration; investigate iOS separately.
