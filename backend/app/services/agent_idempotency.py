"""Safe retries for agent writes.

MCP clients re-send a request when a connection drops, so an agent's write can
arrive twice. An agent that sends `Idempotency-Key` gets the first result back
for every retry with the same key, and the write runs once. Receipts belong to
one agent key, cover one method and path, and expire after a day.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid

import anyio
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import AgentMutationReceipt

RECEIPT_TTL_SECONDS = 24 * 60 * 60
MAX_KEY_LENGTH = 200
# Larger or binary results retain a completion receipt without their contents.
MAX_STORED_BODY_BYTES = 1024 * 1024
WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def request_fingerprint(method: str, path: str, query: str, body: bytes) -> str:
    digest = hashlib.sha256()
    for part in (method.encode(), path.encode(), query.encode(), body):
        digest.update(len(part).to_bytes(8, 'big'))
        digest.update(part)
    return digest.hexdigest()


def begin(agent_key_id: str, operation: str, key: str, fingerprint: str) -> tuple[str, dict | None]:
    """Return ('run', {'id'}), ('replay', stored), ('mismatch', None) or ('busy', None)."""
    now = time.time()
    db = SessionLocal()
    try:
        existing = (
            db.query(AgentMutationReceipt)
            .filter(AgentMutationReceipt.agent_key_id == agent_key_id)
            .filter(AgentMutationReceipt.operation == operation)
            .filter(AgentMutationReceipt.idempotency_key == key)
            .first()
        )
        if existing is not None and existing.created_at < now - RECEIPT_TTL_SECONDS:
            db.delete(existing)
            db.commit()
            existing = None
        if existing is not None:
            stored = json.loads(existing.response_json)
            if stored.get('fingerprint') != fingerprint:
                return 'mismatch', None
            if stored.get('state') != 'complete':
                return ('uncertain' if existing.created_at < now - 300 else 'busy'), None
            return 'replay', stored
        receipt = AgentMutationReceipt(
            id=uuid.uuid4().hex,
            agent_key_id=agent_key_id,
            operation=operation,
            idempotency_key=key,
            response_json=json.dumps({'state': 'running', 'fingerprint': fingerprint}),
            created_at=now,
        )
        db.add(receipt)
        try:
            db.commit()
        except IntegrityError:
            # Another copy of this request started first.
            db.rollback()
            return 'busy', None
        return 'run', {'id': receipt.id}
    finally:
        db.close()


def complete(receipt_id: str, fingerprint: str, status_code: int, body: bytes, content_type: str) -> None:
    db = SessionLocal()
    try:
        receipt = db.query(AgentMutationReceipt).filter(AgentMutationReceipt.id == receipt_id).first()
        if receipt is None:
            return
        receipt.response_json = json.dumps({
            'state': 'complete',
            'fingerprint': fingerprint,
            'status_code': status_code,
            'content_type': content_type,
            'body': body.decode('utf-8'),
        })
        db.commit()
    finally:
        db.close()


def prune_expired_receipts() -> None:
    with SessionLocal() as db:
        db.query(AgentMutationReceipt).filter(
            AgentMutationReceipt.created_at < time.time() - RECEIPT_TTL_SECONDS,
        ).delete(synchronize_session=False)
        db.commit()


_UNCERTAIN = {'detail': 'This request may have changed Vue.io before it stopped. Read the current state before making another change. Do not retry with a new key without checking.'}


async def run_with_idempotency(request, call_next, agent_key_id: str):
    """Run one agent request, replaying the first result for a repeated key."""
    from fastapi.responses import JSONResponse, Response
    from starlette.concurrency import run_in_threadpool

    key = (request.headers.get('Idempotency-Key') or '').strip()
    if not key or request.method not in WRITE_METHODS:
        return await call_next(request)
    if len(key) > MAX_KEY_LENGTH:
        return JSONResponse({'detail': f'Idempotency-Key must be {MAX_KEY_LENGTH} characters or fewer.'}, status_code=400)

    body = await request.body()
    if request.headers.get('content-type', '').split(';', 1)[0].strip() == 'application/json':
        try:
            body = json.dumps(json.loads(body), sort_keys=True, separators=(',', ':')).encode()
        except ValueError:
            pass  # The route will return its usual invalid-body response.
    fingerprint = request_fingerprint(request.method, request.url.path, request.url.query, body)
    operation = f'{request.method} {request.url.path}'
    outcome, data = await run_in_threadpool(begin, agent_key_id, operation, key, fingerprint)
    if outcome == 'replay':
        return Response(
            content=data['body'],
            status_code=data['status_code'],
            media_type=data.get('content_type') or None,
            headers={'Idempotent-Replayed': 'true'},
        )
    if outcome == 'mismatch':
        return JSONResponse({'detail': 'This Idempotency-Key was already used for a different request. Use a new key.'}, status_code=422)
    if outcome == 'busy':
        return JSONResponse({'detail': 'A request with this Idempotency-Key is still running. Wait, then retry.'}, status_code=409)
    if outcome == 'uncertain':
        return JSONResponse(_UNCERTAIN, status_code=409)

    receipt_id = data['id']
    try:
        response = await call_next(request)
    except BaseException:
        with anyio.CancelScope(shield=True):
            await run_in_threadpool(complete, receipt_id, fingerprint, 409, json.dumps(_UNCERTAIN).encode(), 'application/json')
        raise
    content_type = response.headers.get('content-type', '')
    iterator = response.body_iterator

    async def capture():
        body = bytearray()
        keep_body = content_type.startswith('application/json')
        try:
            async for chunk in iterator:
                if keep_body and len(body) + len(chunk) <= MAX_STORED_BODY_BYTES:
                    body.extend(chunk)
                else:
                    keep_body = False
                    body.clear()
                yield chunk
            status = response.status_code
            if status >= 500:
                stored = _UNCERTAIN
            else:
                stored = {'status': 'completed' if status < 400 else 'refused', 'original_status': status,
                          'detail': 'This request already finished. Its result was not retained. Read the current state; do not repeat the change.'}
            saved_body = bytes(body) if keep_body and status < 500 else json.dumps(stored).encode()
            if status in (204, 304):
                saved_body = b''
            await run_in_threadpool(complete, receipt_id, fingerprint, status, saved_body, 'application/json')
        except BaseException:
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(complete, receipt_id, fingerprint, 409, json.dumps(_UNCERTAIN).encode(), 'application/json')
            raise

    response.body_iterator = capture()
    return response
