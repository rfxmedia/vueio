from __future__ import annotations

from ipaddress import ip_address

from fastapi import HTTPException, Request
from limits import parse
from slowapi import Limiter

from app.config import get_settings


def client_rate_limit_key(request: Request) -> str:
    """Return the original client address forwarded by Vueio's own proxy."""
    def parsed(candidate: str | None):
        value = str(candidate or '').strip()
        try:
            return ip_address(value)
        except ValueError:
            return None

    settings = get_settings()
    direct_address = parsed(request.client.host if request.client else None)
    trusted_proxy = bool(
        settings.VUEIO_TRUST_PROXY_HEADERS
        and direct_address
        and (direct_address.is_private or direct_address.is_loopback)
    )
    proxy_address = parsed(request.headers.get('x-real-ip')) if trusted_proxy else None
    cloudflare_address = (
        parsed(request.headers.get('cf-connecting-ip'))
        if trusted_proxy and settings.VUEIO_TRUST_CLOUDFLARE
        else None
    )
    if cloudflare_address:
        return str(cloudflare_address)
    if proxy_address:
        return str(proxy_address)
    return str(direct_address) if direct_address else 'unknown'


limiter = Limiter(key_func=client_rate_limit_key)


def enforce_rate_limit(request: Request, limit_value: str, *, scope: str) -> None:
    """Apply a small fixed-window limit without wrapping FastAPI endpoints."""
    if not limiter.enabled:
        return
    if not limiter.limiter.hit(parse(limit_value), scope, client_rate_limit_key(request)):
        raise HTTPException(status_code=429, detail='Rate limit exceeded')
