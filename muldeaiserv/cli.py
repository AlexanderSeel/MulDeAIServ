"""Local setup diagnostics and safe controller startup."""
import argparse
import json
import platform
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
    guide = commands.add_parser("guide", help="Print manual setup instructions for an engine")
    guide.add_argument("--engine", choices=("controller","vllm","llama-cpp-rpc","exo"),
                       default="controller")
    guide.add_argument("--platform", choices=("windows","linux","darwin","android","ios","other"),
                       default=platform.system().lower() if platform.system().lower() in
                       ("windows","linux","darwin") else "other")
    guide.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "guide":
        from .setup_guide import make_setup_guide
        from .diagnostics import collect_runtime
        result = make_setup_guide(args.engine, args.platform, collect_runtime())
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Engine: {result['engine']} | platform: {result['platform']} | mode: manual review only")
            for problem in result["blockers"]:
                print("BLOCKER:", problem)
            for index, step in enumerate(result["steps"], 1):
                print(f"\n{index}. {step['title']}\n   {step['note']}")
                if step["command"]:
                    print("   $", step["command"])
            for warning in result["warnings"]:
                print("WARNING:", warning)
        return 0 if result["supported"] else 2
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
