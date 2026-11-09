# Manual vLLM/Ray cluster deployment

This is an operator runbook, **not an automatic install script**. The commands follow the linked vLLM v0.7.0 distributed serving guide. Verify command-line compatibility again when using a newer version of vLLM.

## Supported v0.1 scenario

- Two or more Linux machines with compatible NVIDIA GPUs and CUDA runtime; fast and reliable private network.
- Consistent vLLM/PyTorch environment across nodes. Prefer reproducible, pinned Docker images.
- Same GPU count on every node for the initial planner; use the same model path/cache and container mapping.
- vLLM 0.7 multi-node inference managed through Ray. Avoid WAN links and exposed public ports.
- iPhones, iPads, Android devices, and unrelated CPU RAM are not vLLM model shards.

## Checklist

1. Confirm nvidia-smi on each Linux host and compatibility of container GPU access, NVIDIA driver and runtime.
2. Verify that all Ray nodes reach the head's private IP, and firewall policy permits the Ray/NCCL ports used by your trusted deployment.
3. Mount/download the identical model revision on all nodes at matching paths, with appropriate model license and access rights.
4. Check memory estimates in MulDeAIServ (Models & API). The estimate is heuristic, not approval to deploy.
5. Review and, if needed, pin the vLLM Docker image and run_cluster.sh helper from one matching vLLM version.
6. Avoid copying secrets to shell history or public logs; do not open runtime management services to untrusted networks.

## Example (two nodes, one GPU each)

On the selected head node, using the helper from the matching vLLM source release:

    bash examples/online_serving/run_cluster.sh vllm/vllm-openai 192.168.1.10 --head /srv/huggingface

On the second GPU node:

    bash examples/online_serving/run_cluster.sh vllm/vllm-openai 192.168.1.10 --worker /srv/huggingface

Keep the launched containers running, then enter the head container:

    docker exec -it node /bin/bash
    ray status
    vllm serve /srv/huggingface/models/YOUR_MODEL --tensor-parallel-size 1 --pipeline-parallel-size 2

For two nodes with four compatible GPUs each, the planner will suggest TP=4 and PP=2. Adjust only after checking GPU consistency, model and supported parallelism.

## Observability and diagnostics

- Check Ray status and logs from the head.
- Run actual inference and monitor model load, VRAM, token generation and request latency.
- Verify GPU interconnect performance (NCCL and network), particularly if tensor parallelism crosses nodes.
- If the deployment uses only plain TCP sockets, cross-node tensor parallelism may be too slow for practical use. Pipeline parallelism can reduce some communication overhead depending on topology.
- Reserve VRAM for KV cache, activations and CUDA runtime; the initial planner does not measure these precisely.
- Register the running vLLM API in MulDeAIServ using its private IP and port, for example http://192.168.1.10:8000 (without /v1).
- Use the dashboard playground to send a non-streaming test prompt through MulDeAIServ.

## Windows and mobile

Windows can be a controller, chat client, and independent Ollama model server. Running GPU vLLM under WSL2 may work on compatible hardware, but it needs its own verified setup and is not auto-managed by this release. Android and iOS are browser clients, not Ray GPU workers.

## Official documentation

- https://docs.vllm.ai/en/v0.7.0/serving/distributed_serving.html
- https://docs.vllm.ai/en/latest/serving/parallelism_scaling.html
