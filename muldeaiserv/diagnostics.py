"""Bounded, passive local runtime diagnostics for the MulDeAIServ agent.

Never invokes a shell, installs packages, probes network addresses or executes
controller-provided instructions. All executable names and arguments are fixed.
"""
from __future__ import annotations

import importlib.metadata
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

MAX_VERSION = 120


def _which(command: str) -> bool:
    return shutil.which(command) is not None


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)[:MAX_VERSION]
    except importlib.metadata.PackageNotFoundError:
        return None


def _fixed_command_output(args: list[str]) -> str | None:
    try:
        output = subprocess.run(
            args, capture_output=True, text=True, timeout=4, check=True,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (output.stdout or output.stderr).strip()[:MAX_VERSION] or None


def _nvidia_driver() -> str | None:
    if not _which("nvidia-smi"):
        return None
    output = _fixed_command_output([
        "nvidia-smi", "--query-gpu=driver_version",
        "--format=csv,noheader,nounits"
    ])
    if not output:
        return None
    first = output.splitlines()[0].strip()
    return first if re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", first) else None


def collect_runtime() -> dict:
    """Only send a fixed, non-sensitive summary; avoid usernames and paths."""
    disk_free_mb = 0
    try:
        disk_free_mb = shutil.disk_usage(Path.home()).free // (1024 ** 2)
    except OSError:
        pass
    return {
        "python_version": platform.python_version()[:MAX_VERSION],
        "cuda_driver": _nvidia_driver(),
        "vllm_version": _distribution_version("vllm"),
        "ray_version": _distribution_version("ray"),
        "docker_present": _which("docker"),
        "docker_version": _fixed_command_output(["docker", "--version"]) if _which("docker") else None,
        "nvidia_smi_present": _which("nvidia-smi"),
        "ollama_present": _which("ollama"),
        "llama_server_present": _which("llama-server"),
        "rpc_server_present": _which("ggml-rpc-server"),
        "exo_present": _which("exo"),
        "disk_free_mb": int(max(0, disk_free_mb)),
    }


def readiness(device: dict) -> dict:
    """Conservative preflight, not an assurance of successful model deployment."""
    runtime = device.get("runtime") or {}
    system = device.get("platform", "other")
    gpus = device.get("gpus") or []
    cuda_gpus = [g for g in gpus if g.get("vendor") == "nvidia" and g.get("memory_mb", 0) > 0]
    warnings = []
    if not device.get("online", True):
        warnings.append("Agent offline: live runtime checks may be stale.")
    if system != "linux":
        warnings.append("vLLM multi-node execution requires a compatible Linux runtime.")
    if not cuda_gpus:
        warnings.append("No NVIDIA GPU with reported VRAM detected.")
    if not runtime.get("cuda_driver"):
        warnings.append("NVIDIA driver is not verified in the device runtime probe.")
    if not runtime.get("docker_present") and not runtime.get("vllm_version"):
        warnings.append("Neither Docker nor local vLLM is reported.")
    if system == "darwin":
        warnings.append("Apple hardware needs a separate Metal/MLX-capable engine for model partitioning.")
    return {
        "vllm_candidate": system == "linux" and bool(cuda_gpus),
        "vllm_runtime_verified": (
            system == "linux" and bool(cuda_gpus) and bool(runtime.get("cuda_driver"))
            and (bool(runtime.get("vllm_version")) or bool(runtime.get("docker_present")))
        ),
        "rpc_worker_candidate": (
            system in ("windows", "linux", "darwin") and bool(runtime.get("rpc_server_present"))
        ),
        "exo_detected": bool(runtime.get("exo_present")),
        "warnings": warnings,
    }
