"""Cross-platform hardware reporting agent. Never runs remotely supplied commands."""
import argparse
import ctypes
import json
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .diagnostics import collect_runtime

CONFIG = Path.home() / ".config" / "muldeaiserv" / "agent.json"

def ram_mb():
    system = platform.system().lower()
    if system == "windows":
        class Memory(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                        ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                        ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                        ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                        ("avail_ext", ctypes.c_ulonglong)]
        status = Memory()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.total // (1024 * 1024)
    if system == "darwin":
        try:
            return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=3)) // (1024**2)
        except (OSError, ValueError, subprocess.SubprocessError):
            return 0
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") // (1024**2)
    except (OSError, ValueError, AttributeError):
        return 0

def probe(name=None):
    gpus = []
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            text=True, capture_output=True, timeout=5, check=True)
        for line in result.stdout.splitlines():
            if "," not in line:
                continue
            gpu_name, memory = line.rsplit(",", 1)
            gpus.append({"name":gpu_name.strip(),"vendor":"nvidia","memory_mb":int(memory.strip())})
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    system = platform.system().lower()
    return {"name": name or socket.gethostname(), "platform":system if system in
            ("windows","linux","darwin") else "other",
            "os_version":platform.platform()[:240], "cpu_count":os.cpu_count() or 0,
            "ram_mb":ram_mb(), "gpus":gpus, "runtime":collect_runtime()}

def safe_server_url(server, allow_insecure_lan=False):
    parsed = urlsplit(server)
    if parsed.scheme not in ("http","https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Server must be a valid http(s) URL without embedded credentials.")
    if parsed.path not in ("","/") or parsed.query or parsed.fragment:
        raise ValueError("Provide the server origin, without a path/query/fragment.")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost","127.0.0.1","::1") and not allow_insecure_lan:
        raise ValueError("Remote HTTP exposes agent credentials. Use HTTPS or --allow-insecure-lan for a trusted test network.")
    return server.rstrip("/")

def save_session(session):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(session, indent=2), encoding="utf-8")
    if os.name != "nt":
        CONFIG.chmod(0o600)

def main(argv=None):
    parser = argparse.ArgumentParser(description="MulDeAIServ passive hardware agent")
    parser.add_argument("--server", required=True, help="Controller origin, preferably HTTPS")
    parser.add_argument("--join-token", default=os.getenv("MULDEAI_JOIN_TOKEN"))
    parser.add_argument("--name", default=socket.gethostname())
    parser.add_argument("--allow-insecure-lan", action="store_true", help="Development only")
    parser.add_argument("--once", action="store_true", help="Send one heartbeat and exit")
    args = parser.parse_args(argv)
    try:
        server = safe_server_url(args.server, args.allow_insecure_lan)
    except ValueError as exc:
        parser.error(str(exc))
    session = {}
    if CONFIG.is_file():
        try:
            session = json.loads(CONFIG.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            session = {}
    if session.get("server") != server or args.join_token:
        if not args.join_token:
            parser.error("No saved enrollment for this server. Supply --join-token or MULDEAI_JOIN_TOKEN.")
        try:
            with httpx.Client(timeout=15, trust_env=False) as client:
                response = client.post(server + "/api/agent/enroll", json={
                    "join_token":args.join_token,"hardware":probe(args.name)})
                response.raise_for_status()
                session = {**response.json(),"server":server,"name":args.name}
            save_session(session)
            print("Device enrolled; credential stored in", CONFIG)
        except httpx.HTTPError as exc:
            print("Enrollment failed:", str(exc), file=sys.stderr)
            return 1
    print("Reporting hardware to", server, "(Ctrl+C to stop)")
    try:
        while True:
            try:
                with httpx.Client(timeout=15, trust_env=False) as client:
                    response = client.post(server + "/api/agent/heartbeat", json={
                        "device_id":session["device_id"],"agent_token":session["agent_token"],
                        "hardware":probe(session.get("name", args.name))})
                    response.raise_for_status()
                print("Heartbeat sent:", time.strftime("%H:%M:%S"))
            except (httpx.HTTPError, KeyError) as exc:
                print("Heartbeat failed:", str(exc), file=sys.stderr)
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 401:
                    return 1
            if args.once:
                return 0
            time.sleep(20)
    except KeyboardInterrupt:
        print("\nAgent stopped.")
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
