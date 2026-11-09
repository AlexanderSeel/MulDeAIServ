"""Local setup diagnostics and safe controller startup."""
import argparse
import os
import secrets
import shutil
import sys

def main(argv=None):
    parser = argparse.ArgumentParser(prog="muldeaiserv")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Start the private controller and web UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--allow-lan", action="store_true")
    commands.add_parser("doctor", help="Check local runtime dependencies")
    args = parser.parse_args(argv)
    if args.command == "doctor":
        from .agent import probe
        from .diagnostics import readiness
        hardware = probe()
        print("Hardware:", hardware)
        print("Readiness:", readiness({**hardware, "online": True}))
        for name in ("docker", "nvidia-smi", "ray", "vllm"):
            print(name + ":", shutil.which(name) or "not found (optional for controller)")
        print("Controller:", "FastAPI package installed")
        return 0
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    nonlocal_host = args.host not in ("127.0.0.1", "::1", "localhost")
    if nonlocal_host and not args.allow_lan:
        parser.error("Non-loopback binding requires --allow-lan and secure network access.")
    token = os.environ.get("MULDEAI_ADMIN_TOKEN", "")
    if len(token) < 24:
        if nonlocal_host:
            parser.error("For LAN, set MULDEAI_ADMIN_TOKEN to a strong secret (24+ characters).")
        token = secrets.token_urlsafe(32)
        print("\nTemporary dashboard admin token (keep private):\n", token, "\n", flush=True)
    if nonlocal_host:
        print("WARNING: Plain HTTP carries admin credentials. Use a private VPN or HTTPS reverse proxy.", file=sys.stderr)
    from .app import create_app
    import uvicorn
    uvicorn.run(create_app(admin_token=token), host=args.host, port=args.port, log_level="info")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
