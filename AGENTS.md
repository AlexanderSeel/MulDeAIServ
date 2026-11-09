# Agent instructions — MulDeAIServ

Read README.md and PLAN.md before changes. Treat PLAN.md as a living implementation record. Work in meaningful batches, then run tests, build/package checks and security checks.

## Non-negotiable architecture
- Never claim vLLM pools arbitrary RAM/VRAM across PC, Android and iOS.
- vLLM/Ray single-model sharding: Linux GPU hosts only after compatibility checks; all other devices are clients, capacity telemetry, or independent backends.
- Never remotely execute commands received from the server on agents. Planners produce reviewed instructions, not arbitrary scripts.
- All admin operations require strong bearer authentication. Agent tokens are distinct, hashed at rest, and enrollment is short-lived/single-use.
- Keep secrets out of logs, URLs, git, web storage and model prompts.
- Restrict backend URLs to private/loopback origins; review SSRF protections before enabling DNS/public hosts.
- No silent model downloads, driver installation, cluster launch or cloud billing.
- Escape untrusted device/backend content in browser rendering and preserve accessible layouts.
- Do not fake device telemetry, compatibility, model fit or validation.

## Required validation
- Python 3.11+ installation
- pytest -q
- python -m compileall -q muldeaiserv
- Verify deployed commands against official vLLM documentation.
- Update checked and unchecked PLAN.md items truthfully.

## Priorities
1. Secure controller, device agent and API gateway.
2. Dashboard, test coverage, diagnostics and local install.
3. Authentic Ray/vLLM deployment with dry-run, observability and rollback.
4. Independent llama.cpp/MLC edge backends and future native mobile-worker research.
