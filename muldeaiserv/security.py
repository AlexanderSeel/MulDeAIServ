"""Credential hashing and conservative backend URL validation."""
import hashlib
import hmac
import ipaddress
import re
from urllib.parse import urlsplit

MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:-]{0,179}$")

def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def verify(expected_digest: str, token: str) -> bool:
    return hmac.compare_digest(expected_digest, digest(token))

def private_origin(raw: str) -> str:
    """Accept private or loopback IP-literal origins only, to constrain SSRF."""
    try:
        parsed = urlsplit(raw.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Backend URL must use http(s) and a host.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("URL credentials, queries and fragments are not allowed.")
        if parsed.path not in ("", "/"):
            raise ValueError("Supply only the origin, without /v1 or any other path.")
        if parsed.hostname.lower() != "localhost":
            ip = ipaddress.ip_address(parsed.hostname)
            if not (ip.is_private or ip.is_loopback) or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
                raise ValueError("Backend must be on a private or loopback IP.")
        if parsed.port is None:
            raise ValueError("An explicit port is required.")
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname.lower()
        return f"{parsed.scheme}://{host}:{parsed.port}"
    except (ValueError, TypeError) as exc:
        raise ValueError(str(exc) or "Invalid private backend origin.") from exc
