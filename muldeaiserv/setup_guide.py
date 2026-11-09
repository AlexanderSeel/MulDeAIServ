"""Platform-aware, manual setup instructions. No installer runs on the controller.

Every step is displayed for operator review. We intentionally do not accept
shell commands or arbitrary URL inputs from device telemetry.
"""
from __future__ import annotations

ENGINES = ("controller", "vllm", "llama-cpp-rpc", "exo")
PLATFORMS = ("windows", "linux", "darwin", "android", "ios", "other")


def _step(title: str, command: str | None, note: str, ready: bool | None = None) -> dict:
    return {"title": title, "command": command, "note": note, "detected": ready}


def make_setup_guide(engine: str, platform: str, runtime: dict | None = None) -> dict:
    if engine not in ENGINES:
        raise ValueError("Unsupported engine.")
    if platform not in PLATFORMS:
        raise ValueError("Unsupported platform.")
    runtime = runtime or {}
    errors = []
    warnings = [
        "Instructions are manual and non-executing. Review paths, versions, permissions and firewall changes.",
        "Cluster endpoints and distributed runtime control ports must only be reachable on private trusted networks.",
    ]
    steps: list[dict] = []

    if engine == "controller":
        if platform not in ("windows", "linux", "darwin"):
            errors.append("Controller installation requires Windows, Linux or macOS and Python 3.11+.")
        elif platform == "windows":
            steps = [
                _step("Clone MulDeAIServ", "git clone https://github.com/AlexanderSeel/MulDeAIServ.git", "Use your private Git identity.", None),
                _step("Open the project", "cd MulDeAIServ", "Run commands in PowerShell.", None),
                _step("Install isolated dependencies", r".\scripts\setup.ps1", "Creates .venv; Python 3.11+ required.", bool(runtime.get("python_version"))),
                _step("Start localhost dashboard", r".\.venv\Scripts\python.exe -m muldeaiserv serve", "An admin token is displayed for localhost access.", None),
            ]
        else:
            steps = [
                _step("Clone MulDeAIServ", "git clone https://github.com/AlexanderSeel/MulDeAIServ.git", "Use a trusted source checkout.", None),
                _step("Open the project", "cd MulDeAIServ", "Run in your terminal.", None),
                _step("Install dependencies", "bash scripts/setup.sh", "Creates an isolated .venv.", bool(runtime.get("python_version"))),
                _step("Start localhost dashboard", ".venv/bin/python -m muldeaiserv serve", "An admin token is displayed for localhost access.", None),
            ]

    elif engine == "vllm":
        if platform != "linux":
            errors.append("Multi-node vLLM/Ray instructions require Linux and a supported GPU runtime; WSL2 must be verified separately.")
        steps = [
            _step("Verify NVIDIA GPU and driver", "nvidia-smi", "Check GPU identity and driver compatibility.", bool(runtime.get("cuda_driver"))),
            _step("Verify Docker engine", "docker info", "Use a pinned GPU-ready vLLM container and a matching NVIDIA Container Toolkit.", bool(runtime.get("docker_present"))),
            _step("Prepare matching containers", None, "Follow the vLLM v0.7 run_cluster.sh head/worker runbook. Use the SAME image, model paths and private head IP on all hosts.", None),
            _step("Check Ray cluster", "ray status", "Run inside the head container after its worker containers are connected.", bool(runtime.get("ray_version"))),
            _step("Review the vLLM model plan", None, "In Models & API, generate a command after checking GPU counts and estimated VRAM. Do not launch until all host and network checks pass.", None),
        ]
        warnings.append("Driver and Docker presence alone do not verify CUDA container access, model fit, GPU interconnect or container image compatibility.")

    elif engine == "llama-cpp-rpc":
        if platform not in ("windows", "linux", "darwin"):
            errors.append("Native llama.cpp RPC setup is only documented here for Windows, Linux and macOS.")
        steps = [
            _step("Verify CMake and C++ toolchain", "cmake --version", "Requires a supported C/C++ compiler; Windows should use MSVC Developer PowerShell.", None),
            _step("Clone llama.cpp source", "git clone https://github.com/ggml-org/llama.cpp.git", "Pin a compatible commit/release on every participating computer.", None),
            _step("Configure RPC build", "cmake -S llama.cpp -B llama.cpp/build -DGGML_RPC=ON",
                  "For CUDA GPUs also enable -DGGML_CUDA=ON after confirming driver/toolkit support.", bool(runtime.get("rpc_server_present"))),
            _step("Build RPC worker and llama-server", "cmake --build llama.cpp/build --config Release",
                  "Use the same llama.cpp version and compatible backends across hosts.", None),
            _step("Restrict RPC access", None,
                  "RPC is insecure and experimental: isolate the network, restrict inbound firewall rules to the model head IP, and never publish RPC ports.", None),
            _step("Start and validate workers", None,
                  "Run the built ggml-rpc-server on each worker, inspect its actual listen address and supported devices; verify private connectivity before starting the head.", None),
            _step("Build command from paired devices", None,
                  "Select devices and private IP:port endpoints under Models & API to generate a llama-server --rpc command.", None),
        ]
        warnings.append("The official llama.cpp maintainers label RPC proof-of-concept, fragile and insecure. Only use on an isolated trusted LAN.")

    elif engine == "exo":
        if platform != "darwin":
            errors.append("This guide supports the current macOS Apple silicon/MLX exo flow. Windows/Android/iOS and mixed Mac/Linux exo clusters are not validated.")
        steps = [
            _step("Confirm Apple silicon macOS", None, "macOS 15.1+ with supported Apple silicon is required by the current exo app.", None),
            _step("Install exo (macOS)", "brew install --cask exo", "Operator review required; Homebrew is optional and must be installed separately.", bool(runtime.get("exo_present"))),
            _step("Join supported cluster", None, "Start exo on each Mac on the same trusted LAN. Versions, namespace and MLX builds must match.", None),
            _step("Register exo API", None, "After verifying exo's API locally, register its private HTTP origin as an exo backend in Models & API.", None),
        ]
        warnings.append("Current exo is primarily Apple silicon/MLX; not a general-purpose PC/iOS/Android pooled-memory runtime.")

    return {
        "engine": engine, "platform": platform,
        "supported": not errors,
        "blockers": errors, "warnings": warnings, "steps": steps,
        "mode": "manual_review_only",
    }
