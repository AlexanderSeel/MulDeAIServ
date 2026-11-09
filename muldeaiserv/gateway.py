"""Private model gateway with optional OpenAI-style SSE forwarding."""
import json

import httpx
from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse


def client_for(transport=None, timeout=120):
    """Never trust environment proxy settings or follow redirects."""
    return httpx.AsyncClient(
        transport=transport, timeout=timeout, trust_env=False, follow_redirects=False
    )


async def backend_health(origin: str, transport=None) -> dict:
    """On-demand readiness check; never probes public destinations."""
    try:
        async with client_for(transport, timeout=5) as client:
            reply = await client.get(origin + "/v1/models")
        if reply.is_redirect:
            return {"status": "unhealthy", "reason": "Backend redirect refused."}
        if reply.status_code != 200:
            return {"status": "unhealthy", "http_status": reply.status_code}
        try:
            result = reply.json()
            if not isinstance(result, dict) or not isinstance(result.get("data"), list):
                raise ValueError("Missing OpenAI model list.")
            return {"status": "healthy", "model_count": len(result["data"])}
        except ValueError:
            return {"status": "unhealthy", "reason": "Backend returned an invalid /v1/models response."}
    except httpx.RequestError:
        return {"status": "unreachable", "reason": "Unable to contact backend within five seconds."}


async def forward_chat(origin: str, payload: dict, transport=None):
    """Forward JSON or SSE without forwarding the controller's bearer token.

    Response and HTTP client must stay open for the whole stream lifetime.
    A redirect is never followed, and non-SSE responses cannot pretend to
    be streaming.
    """
    client = client_for(transport)
    try:
        request = client.build_request(
            "POST", origin + "/v1/chat/completions", json=payload,
            headers={"Accept": "text/event-stream" if payload.get("stream") else "application/json"}
        )
        upstream = await client.send(request, stream=True)
    except httpx.RequestError as exc:
        await client.aclose()
        raise HTTPException(502, "Model backend unavailable.") from exc

    if upstream.is_redirect:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(502, "Model backend attempted a redirect.")

    if payload.get("stream") and upstream.status_code == 200:
        mime = upstream.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if mime != "text/event-stream":
            await upstream.aclose()
            await client.aclose()
            raise HTTPException(502, "Backend did not return a text/event-stream response.")

        async def iterator():
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        return StreamingResponse(iterator(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    try:
        data = await upstream.aread()
        if len(data) > 16 * 1024 * 1024:
            raise HTTPException(502, "Backend response exceeded the 16 MB limit.")
        try:
            decoded = json.loads(data)
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(502, "Backend did not return valid JSON.") from exc
        return JSONResponse(decoded, status_code=upstream.status_code)
    except httpx.RequestError as exc:
        raise HTTPException(502, "Model backend connection interrupted.") from exc
    finally:
        await upstream.aclose()
        await client.aclose()
