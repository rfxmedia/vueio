"""Sign in with Vue.io: OAuth 2.1 for MCP clients.

Chat apps such as Claude and ChatGPT connect to /api/mcp without a pasted
agent key: the person signs in to Vue.io and allows the app. Vue.io is its own
authorization server. A grant is one connected app for one person; its access
tokens act exactly like an agent key of that person, and only on the MCP
server. Clients identify themselves with a metadata document URL (preferred)
or by registering. Codes need PKCE (S256); refresh tokens rotate.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import secrets
import socket
import time
import uuid
from urllib.parse import urlsplit

import anyio
import httpx
from fastapi import Request
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.db import SessionLocal
from app.models import OAuthClient, OAuthGrant, OAuthToken
from app.services.auth import OAUTH_ACCESS_TOKEN_PREFIX as ACCESS_TOKEN_PREFIX
from app.services.auth import credential_is_current, load_users
from app.services.external_urls import normalize_external_http_url

SCOPE = 'vueio'
REFRESH_TOKEN_PREFIX = 'vueio_ort_'
ACCESS_TOKEN_SECONDS = 60 * 60
REFRESH_TOKEN_SECONDS = 90 * 24 * 60 * 60
CODE_SECONDS = 10 * 60
CLIENT_DOCUMENT_CACHE_SECONDS = 24 * 60 * 60
CLIENT_DOCUMENT_MAX_BYTES = 64 * 1024
LAST_USED_WRITE_SECONDS = 60
MAX_REDIRECT_URIS = 10
LOOPBACK_HOSTS = {'localhost', '127.0.0.1', '[::1]', '::1'}
_document_slots = anyio.Semaphore(4)


class OAuthError(Exception):
    """An error for the client, in RFC 6749 form."""

    def __init__(self, error: str, description: str, status: int = 400):
        super().__init__(description)
        self.error = error
        self.description = description
        self.status = status


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_access_token(token: str | None) -> bool:
    return bool(token) and token.startswith(ACCESS_TOKEN_PREFIX)


# Addresses

def public_origin(request: Request) -> str:
    """The origin the client used, as the web front forwards it."""
    proto = (request.headers.get('x-forwarded-proto') or request.url.scheme or 'http').split(',')[0].strip().lower()
    host = (request.headers.get('host') or request.url.netloc).strip()
    return f"{'https' if proto == 'https' else 'http'}://{host.lower()}"


def resource_url(origin: str) -> str:
    return f'{origin}/api/mcp'


def same_resource(left: str | None, right: str | None) -> bool:
    def normalized(value: str | None) -> str:
        value = (value or '').strip()
        if not value or normalize_external_http_url(value, max_length=2048) != value:
            return ''
        parts = urlsplit(value)
        if parts.query or parts.fragment:
            return ''
        port = parts.port
        default = {'http': 80, 'https': 443}.get(parts.scheme)
        netloc = (parts.hostname or '') + (f':{port}' if port and port != default else '')
        return f'{parts.scheme}://{netloc}{parts.path.rstrip("/")}'
    target = normalized(left)
    return bool(target) and target == normalized(right)


def authorization_server_metadata(origin: str) -> dict:
    return {
        'issuer': origin,
        'authorization_endpoint': f'{origin}/oauth/authorize',
        'token_endpoint': f'{origin}/api/oauth/token',
        'registration_endpoint': f'{origin}/api/oauth/register',
        'revocation_endpoint': f'{origin}/api/oauth/revoke',
        'scopes_supported': [SCOPE],
        'response_types_supported': ['code'],
        'grant_types_supported': ['authorization_code', 'refresh_token'],
        'code_challenge_methods_supported': ['S256'],
        'token_endpoint_auth_methods_supported': ['none'],
        'revocation_endpoint_auth_methods_supported': ['none'],
        'client_id_metadata_document_supported': True,
        'authorization_response_iss_parameter_supported': True,
    }


def protected_resource_metadata(origin: str) -> dict:
    return {
        'resource': resource_url(origin),
        'resource_name': 'Vue.io',
        'authorization_servers': [origin],
        'scopes_supported': [SCOPE],
        'bearer_methods_supported': ['header'],
    }


# Clients

def _is_loopback_redirect(uri: str) -> bool:
    parts = urlsplit(uri)
    return parts.scheme == 'http' and (parts.hostname or '') in LOOPBACK_HOSTS


def _valid_redirect_uri(uri: str) -> bool:
    if not uri or normalize_external_http_url(uri, max_length=2048) != uri:
        return False
    parts = urlsplit(uri)
    if parts.fragment or not parts.hostname:
        return False
    if parts.scheme == 'https':
        return True
    # Native apps listen on a loopback port (RFC 8252).
    return _is_loopback_redirect(uri)


def redirect_uri_allowed(uri: str, registered: list[str]) -> bool:
    if not _valid_redirect_uri(uri):
        return False
    if uri in registered:
        return True
    # A loopback redirect may use any port (RFC 8252, section 7.3).
    if _is_loopback_redirect(uri):
        parts = urlsplit(uri)
        for candidate in registered:
            other = urlsplit(candidate)
            if _is_loopback_redirect(candidate) and other.hostname == parts.hostname and other.path == parts.path and other.query == parts.query:
                return True
    return False


def _clean_redirect_uris(value) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > MAX_REDIRECT_URIS:
        raise OAuthError('invalid_client_metadata', f'redirect_uris must list 1 to {MAX_REDIRECT_URIS} addresses.')
    uris = [str(item) for item in value if isinstance(item, str)]
    if len(uris) != len(value) or not all(_valid_redirect_uri(uri) for uri in uris):
        raise OAuthError('invalid_redirect_uri', 'Each redirect URI must use https, or http on a loopback address, with no fragment.')
    return uris


def _client_name(metadata: dict, fallback: str) -> str:
    name = str(metadata.get('client_name') or '').strip()
    return (name or fallback)[:120]


def _is_metadata_document_id(client_id: str) -> bool:
    if normalize_external_http_url(client_id, max_length=2048) != client_id:
        return False
    parts = urlsplit(client_id)
    return parts.scheme == 'https' and bool(parts.hostname) and parts.path not in ('', '/')


async def _fetch_client_document(client_id: str) -> dict:
    """Bound DNS and download time; connect only to an address we checked."""
    try:
        _document_slots.acquire_nowait()
    except anyio.WouldBlock as exc:
        raise OAuthError('temporarily_unavailable', 'Too many apps are connecting. Try again shortly.', 503) from exc
    try:
        with anyio.fail_after(10):
            url = httpx.URL(client_id)
            if url.userinfo or url.fragment:
                raise OAuthError('invalid_client', 'The client document URL must not contain credentials or a fragment.')
            addresses = await anyio.getaddrinfo(url.host, url.port or 443, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(info[4][0]).is_global for info in addresses):
                raise OAuthError('invalid_client', 'The client metadata document must be on a public address.')
            # Keep the original Host and TLS name, but never resolve the host a second time.
            pinned = url.copy_with(host=addresses[0][4][0])
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=False, trust_env=False) as client:
                async with client.stream('GET', pinned, headers={
                    'Host': url.netloc.decode('ascii'), 'Accept': 'application/json', 'Accept-Encoding': 'identity',
                }, extensions={'sni_hostname': url.host}) as response:
                    if response.status_code != 200 or response.headers.get('content-encoding', 'identity') != 'identity':
                        raise OAuthError('invalid_client', 'The client metadata document must return uncompressed JSON.')
                    body = bytearray()
                    async for chunk in response.aiter_raw():
                        if len(body) + len(chunk) > CLIENT_DOCUMENT_MAX_BYTES:
                            raise OAuthError('invalid_client', 'The client metadata document is too large.')
                        body.extend(chunk)
    except (httpx.HTTPError, OSError, TimeoutError) as exc:
        raise OAuthError('invalid_client', 'The client metadata document could not be read.') from exc
    finally:
        _document_slots.release()
    try:
        document = json.loads(body)
    except ValueError as exc:
        raise OAuthError('invalid_client', 'The client metadata document is not JSON.') from exc
    if not isinstance(document, dict) or document.get('client_id') != client_id:
        raise OAuthError('invalid_client', 'The client metadata document must name this client_id.')
    return document


def _cached_client(client_id: str) -> OAuthClient | None:
    with SessionLocal() as db:
        client = db.get(OAuthClient, client_id)
        if client:
            db.expunge(client)
        return client


def _cache_client_document(client_id: str, document: dict) -> OAuthClient:
    db = SessionLocal()
    try:
        client = db.get(OAuthClient, client_id)
        redirect_uris = _clean_redirect_uris(document.get('redirect_uris'))
        now = time.time()
        if client is None:
            client = OAuthClient(id=client_id, source='metadata_document', created_at=now)
            db.add(client)
        client.name = _client_name(document, urlsplit(client_id).hostname or client_id)
        client.redirect_uris_json = json.dumps(redirect_uris)
        client.metadata_json = json.dumps(document)[:CLIENT_DOCUMENT_MAX_BYTES]
        client.updated_at = now
        try:
            db.commit()
        except IntegrityError:
            # Another request cached this document while we fetched it.
            db.rollback()
            client = db.query(OAuthClient).filter(OAuthClient.id == client_id).one()
        db.refresh(client)
        db.expunge(client)
        return client
    finally:
        db.close()


async def get_client(client_id: str) -> OAuthClient:
    """Load a client without holding a database connection during its download."""
    client_id = (client_id or '').strip()
    if not client_id or len(client_id) > 2048:
        raise OAuthError('invalid_client', 'client_id is missing or too long.')
    client = await run_in_threadpool(_cached_client, client_id)
    if client and (client.source == 'registered' or time.time() - (client.updated_at or 0) < CLIENT_DOCUMENT_CACHE_SECONDS):
        return client
    if not _is_metadata_document_id(client_id):
        raise OAuthError('invalid_client', 'This client is not known. Register it, or use a client metadata document URL.')
    document = await _fetch_client_document(client_id)
    return await run_in_threadpool(_cache_client_document, client_id, document)


def client_redirect_uris(client: OAuthClient) -> list[str]:
    try:
        return [uri for uri in json.loads(client.redirect_uris_json or '[]') if isinstance(uri, str)]
    except ValueError:
        return []


def register_client(metadata: dict) -> dict:
    """Dynamic client registration (RFC 7591) for public clients."""
    if not isinstance(metadata, dict):
        raise OAuthError('invalid_client_metadata', 'Send the client metadata as a JSON object.')
    method = metadata.get('token_endpoint_auth_method') or 'none'
    if method != 'none':
        raise OAuthError('invalid_client_metadata', 'Only public clients are supported: token_endpoint_auth_method must be none.')
    for grant in metadata.get('grant_types') or ['authorization_code']:
        if grant not in ('authorization_code', 'refresh_token'):
            raise OAuthError('invalid_client_metadata', f'Grant type {grant!r} is not supported.')
    redirect_uris = _clean_redirect_uris(metadata.get('redirect_uris'))
    now = time.time()
    client_id = f'vueio-client-{uuid.uuid4().hex}'
    name = _client_name(metadata, 'MCP client')
    client = OAuthClient(
        id=client_id,
        name=name,
        redirect_uris_json=json.dumps(redirect_uris),
        source='registered',
        metadata_json=json.dumps({key: metadata[key] for key in ('client_name', 'client_uri', 'logo_uri', 'software_id', 'software_version') if key in metadata})[:4096],
        created_at=now,
        updated_at=now,
    )
    db = SessionLocal()
    try:
        db.add(client)
        db.commit()
    finally:
        db.close()
    return {
        'client_id': client_id,
        'client_id_issued_at': int(now),
        'client_name': name,
        'redirect_uris': redirect_uris,
        'token_endpoint_auth_method': 'none',
        'grant_types': ['authorization_code', 'refresh_token'],
        'response_types': ['code'],
        'scope': SCOPE,
    }


# Codes and tokens

def _new_token(db, *, kind: str, grant_id: str, seconds: int, prefix: str = '', data: dict | None = None) -> str:
    token = prefix + secrets.token_urlsafe(32)
    now = time.time()
    db.add(OAuthToken(
        token_hash=_hash(token),
        grant_id=grant_id,
        kind=kind,
        expires_at=now + seconds,
        data_json=json.dumps(data) if data else None,
        created_at=now,
    ))
    return token


def create_code(*, user: dict, client: OAuthClient, redirect_uri: str, code_challenge: str, resource: str) -> str:
    db = SessionLocal()
    try:
        code = _new_token(db, kind='code', grant_id='', seconds=CODE_SECONDS, data={
            'user_id': user['id'],
            'account_created_at': user.get('created_at'),
            'credentials_changed_at': user.get('credentials_changed_at'),
            'client_id': client.id,
            'client_name': client.name,
            'redirect_uri': redirect_uri,
            'code_challenge': code_challenge,
            'resource': resource,
        })
        db.commit()
        return code
    finally:
        db.close()


def _issue_tokens(db, grant: OAuthGrant) -> dict:
    access = _new_token(db, kind='access', grant_id=grant.id, seconds=ACCESS_TOKEN_SECONDS, prefix=ACCESS_TOKEN_PREFIX)
    refresh = _new_token(db, kind='refresh', grant_id=grant.id, seconds=REFRESH_TOKEN_SECONDS, prefix=REFRESH_TOKEN_PREFIX)
    return {
        'access_token': access,
        'token_type': 'Bearer',
        'expires_in': ACCESS_TOKEN_SECONDS,
        'refresh_token': refresh,
        'scope': SCOPE,
    }


def _verify_pkce(verifier: str, challenge: str) -> bool:
    if not (43 <= len(verifier or '') <= 128):
        return False
    digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    return secrets.compare_digest(digest, challenge or '')


def exchange_code(*, code: str, client_id: str, redirect_uri: str, code_verifier: str, resource: str | None) -> dict:
    db = SessionLocal()
    try:
        record = db.query(OAuthToken).filter(OAuthToken.token_hash == _hash(code or '')).first()
        now = time.time()
        if record is None or record.kind != 'code':
            raise OAuthError('invalid_grant', 'The authorization code is not valid.')
        data = json.loads(record.data_json or '{}')
        if record.expires_at < now:
            raise OAuthError('invalid_grant', 'The authorization code has expired.')
        if data.get('client_id') != client_id or data.get('redirect_uri') != redirect_uri:
            raise OAuthError('invalid_grant', 'client_id or redirect_uri does not match the authorization request.')
        if not _verify_pkce(code_verifier, data.get('code_challenge')):
            raise OAuthError('invalid_grant', 'The PKCE code_verifier does not match.')
        if resource and not same_resource(resource, data.get('resource')):
            raise OAuthError('invalid_target', 'The resource does not match the authorization request.')
        user = load_users().get(data.get('user_id'))
        if (not credential_is_current(user, record.created_at)
                or data.get('credentials_changed_at') != user.get('credentials_changed_at')
                or data.get('account_created_at') != user.get('created_at')):
            raise OAuthError('invalid_grant', 'This account changed. Connect the app again.')
        _consume_token(db, record, now)

        grant = (
            db.query(OAuthGrant)
            .filter(OAuthGrant.user_id == data['user_id'], OAuthGrant.client_id == client_id, OAuthGrant.resource == data['resource'])
            .filter(OAuthGrant.revoked_at.is_(None))
            .first()
        )
        if grant is None:
            grant = OAuthGrant(
                id=uuid.uuid4().hex,
                user_id=data['user_id'],
                client_id=client_id,
                client_name=data.get('client_name') or client_id,
                resource=data['resource'],
                created_at=now,
            )
            db.add(grant)
        grant.last_used_at = now
        record.grant_id = grant.id
        tokens = _issue_tokens(db, grant)
        db.commit()
        return tokens
    finally:
        db.close()


def refresh_tokens(*, refresh_token: str, client_id: str, resource: str | None) -> dict:
    db = SessionLocal()
    try:
        record = db.query(OAuthToken).filter(OAuthToken.token_hash == _hash(refresh_token or '')).first()
        now = time.time()
        if record is None or record.kind != 'refresh':
            raise OAuthError('invalid_grant', 'The refresh token is not valid.')
        grant = db.query(OAuthGrant).filter(OAuthGrant.id == record.grant_id).first()
        if grant is None or grant.revoked_at is not None:
            raise OAuthError('invalid_grant', 'This app was disconnected. Connect it again.')
        if record.expires_at < now:
            raise OAuthError('invalid_grant', 'The refresh token has expired. Connect the app again.')
        if grant.client_id != client_id:
            raise OAuthError('invalid_grant', 'The refresh token belongs to another client.')
        if resource and not same_resource(resource, grant.resource):
            raise OAuthError('invalid_target', 'The resource does not match this connection.')
        if not credential_is_current(load_users().get(grant.user_id), grant.created_at):
            raise OAuthError('invalid_grant', 'This account changed. Connect the app again.')
        _consume_token(db, record, now)
        grant.last_used_at = now
        tokens = _issue_tokens(db, grant)
        db.commit()
        return tokens
    finally:
        db.close()


def _consume_token(db, record: OAuthToken, now: float) -> None:
    # Compare and set works on SQLite as well as PostgreSQL. Only one caller wins.
    changed = db.query(OAuthToken).filter(
        OAuthToken.token_hash == record.token_hash, OAuthToken.used_at.is_(None), OAuthToken.expires_at >= now,
    ).update({'used_at': now}, synchronize_session=False)
    if changed:
        return
    token_hash = record.token_hash
    db.expire_all()
    used = db.get(OAuthToken, token_hash)
    if used and used.grant_id:
        _revoke_grant(db, used.grant_id, now)
    db.commit()
    raise OAuthError('invalid_grant', 'This code or token was already used. Connect the app again.')


def _revoke_grant(db, grant_id: str, now: float) -> None:
    db.query(OAuthGrant).filter(OAuthGrant.id == grant_id, OAuthGrant.revoked_at.is_(None)).update({'revoked_at': now}, synchronize_session=False)
    db.query(OAuthToken).filter(OAuthToken.grant_id == grant_id).delete(synchronize_session=False)


def revoke_token(token: str) -> None:
    """RFC 7009: revoking either token disconnects the app."""
    db = SessionLocal()
    try:
        record = db.query(OAuthToken).filter(OAuthToken.token_hash == _hash(token or '')).first()
        if record is not None and record.kind in ('access', 'refresh') and record.grant_id:
            _revoke_grant(db, record.grant_id, time.time())
            db.commit()
    finally:
        db.close()


def resolve_access_token(token: str, *, resource: str | None = None) -> dict | None:
    """Return the agent identity {key_id, name, user_id} of a valid access token."""
    if not is_access_token(token):
        return None
    db = SessionLocal()
    try:
        record = db.query(OAuthToken).filter(OAuthToken.token_hash == _hash(token)).first()
        now = time.time()
        if record is None or record.kind != 'access' or record.expires_at < now:
            return None
        grant = db.query(OAuthGrant).filter(OAuthGrant.id == record.grant_id).first()
        if grant is None or grant.revoked_at is not None:
            return None
        if not credential_is_current(load_users().get(grant.user_id), grant.created_at):
            return None
        if resource is not None and not same_resource(resource, grant.resource):
            return None
        if not grant.last_used_at or now - grant.last_used_at > LAST_USED_WRITE_SECONDS:
            grant.last_used_at = now
            db.commit()
        return {'key_id': f'oauth:{grant.id}', 'name': grant.client_name, 'user_id': grant.user_id}
    finally:
        db.close()


def prune_expired_tokens() -> int:
    db = SessionLocal()
    try:
        removed = db.query(OAuthToken).filter(OAuthToken.expires_at < time.time() - 24 * 60 * 60).delete(synchronize_session=False)
        db.commit()
        return removed
    finally:
        db.close()


# Connected apps

def serialize_grant(grant: OAuthGrant) -> dict:
    return {
        'id': grant.id,
        'client_name': grant.client_name,
        'client_id': grant.client_id,
        'created_at': grant.created_at,
        'last_used_at': grant.last_used_at,
    }


def list_user_grants(user_id: str) -> list[dict]:
    db = SessionLocal()
    try:
        grants = (
            db.query(OAuthGrant)
            .filter(OAuthGrant.user_id == user_id, OAuthGrant.revoked_at.is_(None))
            .order_by(OAuthGrant.created_at.desc())
            .all()
        )
        return [serialize_grant(grant) for grant in grants]
    finally:
        db.close()


def disconnect_user_grant(user_id: str, grant_id: str) -> bool:
    db = SessionLocal()
    try:
        grant = db.query(OAuthGrant).filter(OAuthGrant.id == grant_id, OAuthGrant.user_id == user_id, OAuthGrant.revoked_at.is_(None)).first()
        if grant is None:
            return False
        _revoke_grant(db, grant.id, time.time())
        db.commit()
        return True
    finally:
        db.close()


def delete_user_grants(user_id: str) -> int:
    db = SessionLocal()
    try:
        for code in db.query(OAuthToken).filter(OAuthToken.kind == 'code', OAuthToken.grant_id == '').all():
            if json.loads(code.data_json or '{}').get('user_id') == user_id:
                db.delete(code)
        grant_ids = [grant_id for grant_id, in db.query(OAuthGrant.id).filter(OAuthGrant.user_id == user_id).all()]
        if grant_ids:
            db.query(OAuthToken).filter(OAuthToken.grant_id.in_(grant_ids)).delete(synchronize_session=False)
            db.query(OAuthGrant).filter(OAuthGrant.id.in_(grant_ids)).delete(synchronize_session=False)
        db.commit()
        return len(grant_ids)
    finally:
        db.close()
