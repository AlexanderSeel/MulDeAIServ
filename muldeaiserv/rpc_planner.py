"""Planning for the experimental llama.cpp RPC multi-device backend.

This produces reviewed commands only. It never connects to RPC ports, runs
remote code, or claims that observed device RAM is usable for a model.
"""
import ipaddress
from urllib.parse import urlsplit

from .security import MODEL_ID

def rpc_endpoint(address: str) -> str:
    """Accept an explicit TCP endpoint on a trusted private IP literal only."""
    raw = address.strip()
    if not raw or any(ch.isspace() for ch in raw):
        raise ValueError("RPC endpoint must be a private IP address and explicit port.")
    if "://" in raw or "/" in raw or "@" in raw or "?" in raw or "#" in raw:
        raise ValueError("RPC endpoint must be an IP:port, without URL scheme or path.")
    try:
        parsed = urlsplit("tcp://" + raw)
        if not parsed.hostname or not parsed.port:
            raise ValueError("RPC endpoint requires a port.")
        ip = ipaddress.ip_address(parsed.hostname)
        if ip.version == 4:
            trusted = any(ip in block for block in (
                ipaddress.ip_network("10.0.0.0/8"),
                ipaddress.ip_network("172.16.0.0/12"),
                ipaddress.ip_network("192.168.0.0/16"),
                ipaddress.ip_network("127.0.0.0/8")))
        else:
            trusted = ip in ipaddress.ip_network("fc00::/7") or ip.is_loopback
        if not trusted:
            raise ValueError("Only private/loopback IP literals are allowed; no WAN/public RPC.")
        host = f"[{ip.compressed}]" if ip.version == 6 else str(ip)
        return f"{host}:{parsed.port}"
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid RPC endpoint: {exc}") from exc

def plan_rpc(devices: list[dict], model_id: str, workers: list[dict],
             network_acknowledged: bool = False) -> dict:
    """Build safe, non-executing RPC command and per-worker requirements."""
    if not MODEL_ID.fullmatch(model_id):
        raise ValueError("Provide a Hugging Face GGUF repository identifier.")
    if not 1 <= len(workers) <= 16:
        raise ValueError("Select 1 to 16 RPC workers.")
    known = {d["id"]: d for d in devices}
    seen_ids, endpoints, blockers, info = set(), set(), [], []
    for worker in workers:
        identifier = worker["device_id"]
        if identifier in seen_ids:
            raise ValueError("A device cannot appear more than once.")
        seen_ids.add(identifier)
        device = known.get(identifier)
        if device is None:
            raise ValueError("Selected device is not registered.")
        endpoint = rpc_endpoint(worker["endpoint"])
        if endpoint in endpoints:
            raise ValueError("Each worker must have a unique RPC endpoint.")
        endpoints.add(endpoint)
        if not device["online"]:
            blockers.append(f"{device['name']}: agent is offline.")
        if device["platform"] not in ("windows", "linux", "darwin"):
            blockers.append(f"{device['name']}: no native RPC worker support established for {device['platform']}.")
        info.append({
            "device_id": identifier, "name": device["name"],
            "platform": device["platform"], "endpoint": endpoint,
            "reported_ram_mb": device["ram_mb"],
            "reported_gpu_vram_mb": sum(g["memory_mb"] for g in device["gpus"]),
            "runtime_verified": False,
        })
    if not network_acknowledged:
        blockers.append("Acknowledge that llama.cpp RPC is experimental and must only run on an isolated trusted network.")
    command = None if blockers else (
        f"llama-server -hf {model_id} -ngl 99 --rpc "
        + ",".join(item["endpoint"] for item in info)
    )
    return {
        "engine": "llama.cpp-rpc", "model_id": model_id,
        "worker_count": len(info), "workers": info,
        "can_generate_command": not blockers,
        "command": command, "blockers": blockers,
        "reported_total_system_ram_mb": sum(x["reported_ram_mb"] for x in info),
        "reported_total_gpu_vram_mb": sum(x["reported_gpu_vram_mb"] for x in info),
        "warnings": [
            "EXPERIMENTAL AND INSECURE upstream RPC protocol. Use only isolated trusted networks; never Internet.",
            "Device agent enrollment does not install or validate ggml-rpc-server or open ports.",
            "Reported RAM/VRAM is inventory, NOT verified usable offload memory or one shared address space.",
            "Real model fit depends on memory actually free on each worker, GPU backend, quantization, KV cache and network performance.",
            "Compile compatible llama.cpp versions with GGML_RPC=ON on each worker and head before running this command.",
            "Start each worker's ggml-rpc-server on its specified interface and port, with firewall restrictions.",
            "The model identifier must refer to a compatible GGUF repository supported by the installed llama.cpp version.",
        ],
    }
