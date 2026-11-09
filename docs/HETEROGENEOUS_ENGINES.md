# Heterogeneous distributed inference: evidence and engineering options

## Why vLLM is only one execution engine

vLLM/Ray is a good fit for compatible Linux GPU nodes. It does not provide a portable unified RAM pool for iPhones, Android phones and arbitrary Windows PCs. A multi-device solution needs several runtime adapters with separately verified platform support, not a universal memory-size addition.

## exo (current project: exo-explore/exo)

- Provides automatic peer discovery, topology-aware model partitioning and OpenAI-compatible inference.
- Current maintained exo README emphasizes Apple silicon Macs, MLX distributed and Thunderbolt 5 RDMA. The macOS app requires Apple silicon and macOS 15.1+.
- Nodes need the same exo version, cluster name and compatible build. The current project explicitly says a Mac and Linux machine do not join as one cluster even on the same commit because of different MLX builds.
- Do not assume that old exo marketing claims for iPhones/Android are working in the current release. Check exact version and mobile implementation before treating phones as workers.
- The exo API can be registered in MulDeAIServ as a separate OpenAI-compatible backend once an independent exo cluster is already running.

Reference: https://github.com/exo-explore/exo

## llama.cpp RPC (experimental)

- Official llama.cpp RPC allows ggml to offload tensors to GPU and CPU devices exposed by remote RPC servers. The reference describes splitting model weights and KV cache according to reported device memory.
- RPC support needs to be compiled and enabled on every participating host; host uses the --rpc option on llama-server/llama-cli.
- RPC is marked fragile and insecure by the maintainers. It must run only on trusted isolated networks; never expose RPC to the public Internet.
- Android-specific RPC worker experiments exist in third-party projects, but hardware/driver/model/backend matching and security must be benchmarked case by case. This does not imply iOS compatibility.
- For the first MulDeAIServ release, register the OpenAI-compatible API exposed by a preconfigured llama-server. Automatic RPC deployment is future work.

References:
- https://github.com/ggml-org/llama.cpp/blob/master/tools/rpc/README.md
- https://github.com/adil-adysh/llama-cpp-android-node (third party, not a supported MulDeAIServ integration)

## MLC LLM for mobile local models

- Supports native mobile inference on Android and iOS using device GPU backends.
- Provides OpenAI-compatible APIs in some deployment modes, but local mobile inference is not the same as pooling all device memory for one model.
- Android/iOS native worker integration, per-device thermal/power limits, network transport and permissions need their own implementation and tests.

Reference: https://github.com/mlc-ai/mlc-llm

## Engineering decision

1. Implement separate deployment adapters: vLLM/Ray for compatible GPU servers, exo for supported MLX clusters and experimental llama.cpp RPC for trusted local networks.
2. Keep a unified model API, inventory and planner UI but use runtime-specific compatibility matrices and real memory feasibility measurements.
3. Add iOS/Android worker support only after reproducible native implementation and benchmark results, not by assuming web browser memory can be reallocated to a remote model.
4. Benchmark effective tokens/sec, cold start, peak resident memory, link throughput, battery and thermals. A weaker node can reduce latency performance even when it contributes memory.
5. Prevent untrusted peers from executing code or reading model data. Never publicly expose Ray or llama.cpp RPC ports.
