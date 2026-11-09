"""Discover already-running Ollama models on the controller host.

Only the fixed 127.0.0.1:11434 endpoint is queried. The controller does not
run installation commands, follow redirects or scan private networks.
"""
from __future__ import annotations

import httpx

from .gateway import client_for
from .security import MODEL_ID

OLLAMA_ORIGIN = "http://127.0.0.1:11434"
MAX_DISCOVERED = 100


async def discover_local_ollama(transport=None) -> dict:
    try:
        async with client_for(transport, timeout=4) as client:
            response = await client.get(OLLAMA_ORIGIN + "/api/tags")
    except httpx.RequestError:
        return {
            "status": "unavailable",
            "origin": OLLAMA_ORIGIN,
            "models": [],
            "message": "No Ollama server responded on the controller at 127.0.0.1:11434.",
        }
    if response.is_redirect:
        return {
            "status": "unavailable", "origin": OLLAMA_ORIGIN,
            "models": [], "message": "The local Ollama endpoint redirected the request.",
        }
    if response.status_code != 200:
        return {
            "status": "unavailable", "origin": OLLAMA_ORIGIN,
            "models": [], "message": f"Ollama returned HTTP {response.status_code}.",
        }
    try:
        raw = response.json()
    except ValueError:
        raw = {}
    if not isinstance(raw, dict) or not isinstance(raw.get("models"), list):
        return {
            "status": "unavailable", "origin": OLLAMA_ORIGIN,
            "models": [], "message": "Ollama returned an invalid model inventory.",
        }
    models = []
    seen = set()
    for item in raw["models"][:MAX_DISCOVERED]:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("model")
        if not isinstance(name, str) or not MODEL_ID.fullmatch(name) or name in seen:
            continue
        seen.add(name)
        size = item.get("size")
        models.append({
            "model_id": name,
            "size_bytes": size if isinstance(size, int) and 0 <= size <= 10**15 else None,
        })
    return {
        "status": "available",
        "origin": OLLAMA_ORIGIN,
        "models": models,
        "message": f"Found {len(models)} installed model(s) on the controller's Ollama server.",
    }
