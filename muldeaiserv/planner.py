"""Read-only, conservative vLLM deployment planning. No remote command execution."""
from .security import MODEL_ID

def make_plan(devices, model_id, parameters_b, bits, device_ids=None):
    if not MODEL_ID.fullmatch(model_id):
        raise ValueError("Invalid model ID.")
    if not 0.1 <= parameters_b <= 2000:
        raise ValueError("Parameter count must be between 0.1B and 2000B.")
    if bits not in (4, 8, 16):
        raise ValueError("Quantization must be 4, 8 or 16 bits.")
    if device_ids:
        if len(device_ids) != len(set(device_ids)):
            raise ValueError("Duplicate device IDs.")
        known = {d["id"] for d in devices}
        if any(identifier not in known for identifier in device_ids):
            raise ValueError("Unknown device ID.")
        nodes = [d for d in devices if d["id"] in device_ids]
    else:
        nodes = [d for d in devices if d["online"] and d["platform"] == "linux" and d["gpus"]]
    blockers = []
    if not nodes:
        blockers.append("No compatible GPU devices selected or online.")
    for d in nodes:
        if not d["online"]:
            blockers.append(d["name"] + ": offline.")
        if d["platform"] != "linux":
            blockers.append(d["name"] + ": needs Linux CUDA runtime (WSL2 may be suitable).")
        if not d["gpus"]:
            blockers.append(d["name"] + ": no GPU detected.")
        for gpu in d["gpus"]:
            if gpu["vendor"] != "nvidia" or gpu["memory_mb"] <= 0:
                blockers.append(d["name"] + ": only NVIDIA GPUs supported by this MVP planner.")
    counts = [len(d["gpus"]) for d in nodes]
    if len(set(counts)) > 1:
        blockers.append("All selected nodes must expose the same number of GPUs in this template.")
    gpu_count = sum(counts)
    vram = sum(g["memory_mb"] for d in nodes for g in d["gpus"])
    all_gpus = [g for d in nodes for g in d["gpus"]]
    known_free = len(all_gpus) > 0 and all(
        g.get("free_memory_mb") is not None for g in all_gpus
    )
    free_vram = sum(g["free_memory_mb"] for g in all_gpus) if known_free else None
    usable = min(round(vram * .75), round(free_vram * .90)) if known_free else round(vram * .75)
    estimated = round(parameters_b * 1e9 * bits / 8 / (1024**2) * 1.25)
    fits = gpu_count > 0 and estimated <= usable
    tp = counts[0] if counts else 0
    pp = len(nodes)
    command = None
    if not blockers:
        command = (f"vllm serve {model_id} --tensor-parallel-size {tp} "
                   f"--pipeline-parallel-size {pp}"
                   + (" --distributed-executor-backend ray" if pp > 1 else ""))
    return {
        "model_id":model_id,"parameters_b":parameters_b,"quantization_bits":bits,
        "node_count":pp,"gpu_count":gpu_count,"total_gpu_vram_mb":vram,
        "conservative_usable_vram_mb":usable,"reported_free_vram_mb":free_vram,
        "estimated_model_weights_mb":estimated,
        "likely_fits_weights_only":fits,"can_generate_command":not blockers,
        "tensor_parallel_size":tp,"pipeline_parallel_size":pp,"command":command,
        "blockers":blockers,
        "warnings":[
            "VRAM is summed for a rough feasibility check; it is not a shared memory address space.",
            "Includes an estimated 25% model-weight overhead. Reserves 25% of total VRAM; when all free-memory reports exist, also limits to 90% of reported free VRAM.",
            "KV cache, activations, runtime support, model architecture and communication speed can change feasibility.",
            "Every node needs matching drivers, vLLM environment and model files; multi-node Ray must be configured separately.",
            "iOS, Android and CPU RAM do not participate in this vLLM GPU configuration."
        ] + ([] if fits else ["Weights exceed the conservative usable VRAM estimate."])
    }
