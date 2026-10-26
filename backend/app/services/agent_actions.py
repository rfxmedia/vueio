"""Vue.io API actions for agents.

An agent can do what its person can do in Vue.io because every agent action is
an ordinary API route. The catalog is built from the live OpenAPI description,
so a new route reaches agents in the release that adds it. An action runs as an
in-process request to its route that carries the agent's own key: validation,
permission checks and history are the web app's own. Nothing in this module
decides what a person may do.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, replace
from urllib.parse import quote, urlencode

import anyio
import httpx
from fastapi.routing import APIRoute, iter_route_contexts

from app.services.auth import INTERNAL_CALL_SCOPE_KEY

logger = logging.getLogger(__name__)

# A response larger than this is refused instead of read into memory.
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
CALL_TIMEOUT_SECONDS = 180

# Routes agents do not see. These are not a person's work in Vue.io, so hiding
# them keeps the catalog small. The routes still enforce every permission.
_HIDDEN_TAGS = frozenset({'auth', 'oauth', 'setup', 'health', 'share-preview', 'share-media', 'streaming'})
_HIDDEN_ROUTES = tuple(
    (frozenset(methods) if methods else None, re.compile(pattern))
    for methods, pattern in (
        # Credentials: agents cannot manage passwords or agent keys.
        (None, r'^/api/me/password$'),
        (None, r'^/api/me/agent-keys'),
        (None, r'^/api/admin/agent-keys'),
        (('PUT',), r'^/api/admin/notification-providers/discord$'),
        # Routes for people who open a share link.
        (None, r'^/api/share/\{share_id\}'),
        (None, r'^/api/projects/shared/'),
        (None, r'^/api/shared/'),
        # Host administration stays with people at the server.
        (None, r'^/api/admin/(update|storage|media-processing|transcodes|system-health)'),
        # Viewing history and live event streams.
        (None, r'^/api/recently-viewed'),
        (('POST',), r'/views$'),
        (None, r'^/api/folder-events$'),
        # Upload links take raw file chunks; agents get them from version_upload.
        (None, r'^/api/upload-links/'),
        # Raw media, archives and chunked uploads. Agents read thumbnails and frames instead.
        (None, r'/(stream|file|download|download-zip|download-latest-zip|download-latest-zip-form|folder-zip|model)$'),
        (None, r'/hls/'),
        (None, r'/uploads(/|$)'),
        # Retired default-tracker routes.
        (None, r'^/api/projects/\{project_id\}/shots'),
    )
)
# Query parameters used only by people who open a share link.
_HIDDEN_QUERY_PARAMETERS = frozenset({'share_id', 'share_token'})
# Schema keywords whose values are data, not schemas.
_DATA_KEYWORDS = frozenset({'default', 'example', 'examples', 'const', 'enum'})

# Verbs people use for each method, so "add a comment" finds POST /api/comments.
_METHOD_WORDS = {
    'GET': ('get', 'list', 'read', 'show', 'view', 'find'),
    'POST': ('add', 'create', 'new', 'post', 'make', 'run'),
    'PUT': ('update', 'edit', 'change', 'set', 'rename'),
    'PATCH': ('update', 'edit', 'change', 'set'),
    'DELETE': ('delete', 'remove'),
}
_STOP_WORDS = frozenset({'a', 'an', 'the', 'to', 'of', 'for', 'on', 'in', 'and', 'or', 'with', 'my', 'me', 'i', 'api', 'id', 'by', 'from', 'all'})
_WORD = re.compile(r'[a-z0-9]+')

# Format and bidirectional control characters can hide instructions in text
# that other people wrote; results never carry them.
_HIDDEN_CHARACTERS = re.compile(
    '[­؜᠎​-‏‪-‮⁠-⁤⁦-⁯﻿￹-￻\U000e0000-\U000e007f]'
)


class ActionInputError(ValueError):
    """The agent's input cannot become a request; Vue.io was not called."""


@dataclass(frozen=True)
class Action:
    name: str
    method: str
    path: str
    summary: str
    description: str
    tag: str
    tool: str | None
    admin_only: bool
    input_schema: dict
    # Input name -> (location, wire name). Locations: path, query, body, form, file, whole_body.
    targets: dict
    body_kind: str | None
    slash_parameters: frozenset
    words: frozenset
    name_words: frozenset

    @property
    def reads(self) -> bool:
        return self.method == 'GET'


@dataclass(frozen=True)
class ActionResponse:
    status: int
    content_type: str
    body: bytes

    @property
    def is_json(self) -> bool:
        media_type = self.content_type.split(';', 1)[0].strip().lower()
        return media_type == 'application/json' or media_type.endswith('+json')

    def json(self):
        return json.loads(self.body.decode('utf-8')) if self.body else None


def _words(*texts: str) -> set[str]:
    words = set()
    for text in texts:
        for word in _WORD.findall((text or '').lower()):
            words.add(word[:-1] if len(word) > 3 and word.endswith('s') else word)
    return words


def _hidden(method: str, path: str, operation: dict) -> bool:
    if not path.startswith('/api/') or operation.get('deprecated'):
        return True
    if _HIDDEN_TAGS.intersection(operation.get('tags') or ()):
        return True
    return any((methods is None or method in methods) and pattern.search(path) for methods, pattern in _HIDDEN_ROUTES)


def _inline(schema, components: dict, seen: tuple = ()):
    """Inline `$ref`s and drop generated titles, so one schema reads on its own."""
    if isinstance(schema, list):
        return [_inline(item, components, seen) for item in schema]
    if not isinstance(schema, dict):
        return schema
    ref = schema.get('$ref')
    if isinstance(ref, str):
        name = ref.rsplit('/', 1)[-1]
        if name in seen or name not in components:
            return {'type': 'object'}
        merged = {**components[name], **{key: value for key, value in schema.items() if key != '$ref'}}
        return _inline(merged, components, (*seen, name))
    result = {}
    for key, value in schema.items():
        if key == 'title':
            continue
        if key in _DATA_KEYWORDS:
            result[key] = value
        elif key == 'properties' and isinstance(value, dict):
            result[key] = {name: _inline(item, components, seen) for name, item in value.items()}
        else:
            result[key] = _inline(value, components, seen)
    return result


def _is_file(schema: dict) -> bool:
    if schema.get('type') == 'array':
        return _is_file(schema.get('items') or {})
    return schema.get('format') == 'binary' or 'contentMediaType' in schema


_FILE_INPUT = {
    'type': 'object',
    'properties': {
        'filename': {'type': 'string'},
        'content_base64': {'type': 'string', 'description': 'The file contents, base64 encoded.'},
        'content_type': {'type': 'string', 'description': 'For example image/png.'},
    },
    'required': ['filename', 'content_base64'],
}


def _file_input(schema: dict) -> dict:
    description = f'A file, up to {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.'
    if schema.get('type') == 'array':
        return {'type': 'array', 'items': _FILE_INPUT, 'description': description}
    return {**_FILE_INPUT, 'description': description}


def _build_action(name: str, method: str, route, operation: dict, components: dict) -> Action:
    properties: dict = {}
    required: list[str] = []
    targets: dict = {}
    for parameter in operation.get('parameters') or ():
        location = parameter.get('in')
        wire = parameter.get('name')
        if location not in ('path', 'query') or (location == 'query' and wire in _HIDDEN_QUERY_PARAMETERS):
            continue
        schema = _inline(parameter.get('schema') or {}, components)
        if parameter.get('description'):
            schema = {**schema, 'description': parameter['description']}
        properties[wire] = schema
        targets[wire] = (location, wire)
        if parameter.get('required'):
            required.append(wire)

    body_kind = None
    request_body = operation.get('requestBody') or {}
    content = request_body.get('content') or {}
    for media_type, kind in (('application/json', 'json'), ('multipart/form-data', 'form'), ('application/x-www-form-urlencoded', 'form')):
        if media_type in content:
            body_kind = kind
            body_schema = _inline(content[media_type].get('schema') or {}, components)
            break
    if body_kind:
        fields = body_schema.get('properties')
        if isinstance(fields, dict) and fields and not body_schema.get('additionalProperties'):
            body_required = set(body_schema.get('required') or ())
            for field_name, field_schema in fields.items():
                input_name = field_name if field_name not in properties else f'body_{field_name}'
                if body_kind == 'form' and _is_file(field_schema):
                    properties[input_name] = _file_input(field_schema)
                    targets[input_name] = ('file', field_name)
                else:
                    properties[input_name] = field_schema
                    targets[input_name] = ('body' if body_kind == 'json' else 'form', field_name)
                if field_name in body_required:
                    required.append(input_name)
        else:
            properties['body'] = body_schema
            targets['body'] = ('whole_body', '')
            if request_body.get('required'):
                required.append('body')

    input_schema = {'type': 'object', 'properties': properties, 'additionalProperties': False}
    if required:
        input_schema['required'] = required
    path = route.path_format
    summary = operation.get('summary') or name.replace('_', ' ').capitalize()
    description = (operation.get('description') or '').strip()
    tag = (operation.get('tags') or [''])[0]
    return Action(
        name=name,
        method=method,
        path=path,
        summary=summary,
        description=description,
        tag=tag,
        tool=operation.get('x-mcp-tool'),
        admin_only=path.startswith('/api/admin/'),
        input_schema=input_schema,
        targets=targets,
        body_kind=body_kind,
        slash_parameters=frozenset(re.findall(r'\{(\w+):path\}', route.path)),
        words=frozenset(_words(name, path, summary, description, tag, ' '.join(properties), ' '.join(_METHOD_WORDS.get(method, ())))),
        name_words=frozenset(_words(name, path)),
    )


def _unused_name(actions: dict, base: str) -> str:
    name, count = base, 2
    while name in actions:
        name, count = f'{base}_{count}', count + 1
    return name


def build_catalog(app) -> dict[str, Action]:
    """Return every agent action, keyed by name, in route registration order."""
    spec = app.openapi()
    components = (spec.get('components') or {}).get('schemas') or {}
    actions: dict[str, Action] = {}
    endpoints: dict[str, object] = {}
    # Included routers are walked the way FastAPI builds its OpenAPI description.
    for route in iter_route_contexts(app.routes):
        if not isinstance(route.original_route, APIRoute) or not route.include_in_schema:
            continue
        for method in sorted((route.methods or set()) - {'HEAD', 'OPTIONS'}):
            operation = (spec.get('paths', {}).get(route.path_format) or {}).get(method.lower())
            if operation is None or _hidden(method, route.path_format, operation):
                continue
            name = route.name
            if name in actions:
                if endpoints[name] is route.endpoint and actions[name].method == method:
                    # The same handler under a second path.
                    continue
                if method == 'GET' and not actions[name].reads:
                    # A read keeps the plain name; the change takes a method suffix.
                    displaced = actions.pop(name)
                    renamed = _unused_name(actions, f'{name}_{displaced.method.lower()}')
                    actions[renamed] = replace(displaced, name=renamed)
                    endpoints[renamed] = endpoints.pop(name)
                else:
                    name = _unused_name(actions, f'{name}_{method.lower()}')
            actions[name] = _build_action(name, method, route, operation, components)
            endpoints[name] = route.endpoint
    return actions


def visible_actions(catalog: dict[str, Action], *, is_admin: bool) -> list[Action]:
    return [action for action in catalog.values() if is_admin or not action.admin_only]


def find_actions(catalog: dict[str, Action], query: str, *, is_admin: bool, limit: int) -> list[Action]:
    words = [word for word in _words(query) if word not in _STOP_WORDS]
    if not words:
        return []
    scored = []
    for index, action in enumerate(visible_actions(catalog, is_admin=is_admin)):
        score = sum(3 if word in action.name_words else 1 if word in action.words else 0 for word in words)
        if score:
            # Among equals: the more specific action, then named tools, then registration order.
            scored.append((-score, len(action.name_words), 0 if action.tool else 1, index, action))
    scored.sort(key=lambda item: item[:4])
    return [item[4] for item in scored[:limit]]


def describe(action: Action) -> dict:
    return {
        'action': action.name,
        'kind': 'read' if action.reads else 'write',
        'run_with': 'call_read_action' if action.reads else 'call_write_action',
        'method': action.method,
        'path': action.path,
        'summary': action.summary,
        'description': action.description,
        'inputs': action.input_schema,
        **({'tool': action.tool} if action.tool else {}),
    }


def _form_text(value) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def _decode_file(name: str, value) -> tuple[str, bytes, str]:
    if not isinstance(value, dict) or not value.get('filename') or not isinstance(value.get('content_base64'), str):
        raise ActionInputError(f'{name} must be an object with filename and content_base64.')
    try:
        data = base64.b64decode(value['content_base64'], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ActionInputError(f'{name}.content_base64 is not valid base64.') from exc
    if len(data) > MAX_UPLOAD_BYTES:
        raise ActionInputError(f'{name} is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.')
    return str(value['filename']), data, str(value.get('content_type') or 'application/octet-stream')


def build_request(action: Action, arguments: dict, *, idempotency_key: str | None = None) -> tuple[str, str, bytes, str | None]:
    """Return (path, query string, body, content type) for one call."""
    arguments = dict(arguments or {})
    unknown = sorted(set(arguments) - set(action.targets))
    if unknown:
        raise ActionInputError(f'{action.name} has no input named {", ".join(unknown)}. Call describe_action to see its inputs.')
    missing = [name for name in action.input_schema.get('required', ()) if arguments.get(name) is None]
    if missing:
        raise ActionInputError(f'{action.name} needs {", ".join(missing)}.')

    path = action.path
    query: list[tuple[str, str]] = []
    json_body: dict = {}
    form: dict = {}
    files: list = []
    whole_body = None
    for name, value in arguments.items():
        location, wire = action.targets[name]
        if location == 'path':
            text = str(value)
            if not text:
                raise ActionInputError(f'{name} cannot be empty.')
            path = path.replace(f'{{{wire}}}', quote(text, safe='/' if wire in action.slash_parameters else ''))
        elif value is None and location not in ('body', 'whole_body'):
            continue
        elif location == 'query':
            for item in value if isinstance(value, list) else [value]:
                query.append((wire, _form_text(item)))
        elif location == 'body':
            json_body[wire] = value
        elif location == 'form':
            form[wire] = _form_text(value)
        elif location == 'file':
            for item in value if isinstance(value, list) else [value]:
                files.append((wire, _decode_file(name, item)))
        else:
            whole_body = value

    if action.body_kind == 'json':
        body = json.dumps(whole_body if 'body' in arguments else json_body).encode()
        content_type = 'application/json'
    elif action.body_kind == 'form':
        # A fixed boundary keeps a retried upload byte-identical for idempotency.
        boundary = hashlib.sha256((idempotency_key or uuid.uuid4().hex).encode()).hexdigest()[:32]
        request = httpx.Request(
            'POST',
            'http://vueio.internal/',
            data=form,
            files=files or None,
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'} if files else None,
        )
        body = request.read()
        content_type = request.headers.get('content-type')
    else:
        body, content_type = b'', None
    return path, urlencode(query), body, content_type


class ResponseTooLarge(Exception):
    pass


async def _asgi_call(app, *, method: str, path: str, query: str, headers: list[tuple[bytes, bytes]], body: bytes, client) -> ActionResponse:
    """Run one request through the whole application, in process."""
    from urllib.parse import unquote

    scope = {
        'type': 'http',
        'asgi': {'version': '3.0', 'spec_version': '2.3'},
        'http_version': '1.1',
        'method': method,
        'scheme': 'http',
        'path': unquote(path),
        'raw_path': path.encode(),
        'root_path': '',
        'query_string': query.encode(),
        'headers': headers,
        'client': client,
        'server': ('vueio.internal', 80),
        'state': {},
        INTERNAL_CALL_SCOPE_KEY: True,
    }
    request_sent = False
    finished = anyio.Event()
    status = 500
    content_type = ''
    chunks: list[bytes] = []
    size = 0

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        # Streaming responses watch for a disconnect; there is none until the response ends.
        await finished.wait()
        return {'type': 'http.disconnect'}

    async def send(message):
        nonlocal status, content_type, size
        if message['type'] == 'http.response.start':
            status = message['status']
            for name, value in message.get('headers') or ():
                if name.lower() == b'content-type':
                    content_type = value.decode('latin-1')
        elif message['type'] == 'http.response.body':
            chunk = message.get('body') or b''
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise ResponseTooLarge
            chunks.append(chunk)
            if not message.get('more_body'):
                finished.set()

    try:
        with anyio.fail_after(CALL_TIMEOUT_SECONDS):
            await app(scope, receive, send)
    except ResponseTooLarge:
        detail = 'This result is too large to send to an agent. Narrow the request.'
        if method not in {'GET', 'HEAD', 'OPTIONS'}:
            detail = 'This request may have changed Vue.io, but its result is too large to show. Read the current state before making another change. Do not retry with a new key without checking.'
        return ActionResponse(413, 'application/json', json.dumps({'detail': detail}).encode())
    except TimeoutError:
        return ActionResponse(504, 'application/json', json.dumps({'detail': 'Vue.io did not finish this request in time.'}).encode())
    except Exception:
        # The application already logged it and sent a 500.
        if not finished.is_set():
            logger.exception('Agent action failed: %s %s', method, path)
            return ActionResponse(500, 'application/json', json.dumps({'detail': 'Vue.io could not complete this request.'}).encode())
    finally:
        finished.set()
    return ActionResponse(status, content_type, b''.join(chunks))


async def run_action(
    app,
    action: Action,
    arguments: dict,
    *,
    agent_key: str,
    client,
    origin: str,
    idempotency_key: str | None = None,
) -> ActionResponse:
    """Run an action as the key's person, through the same route the web app uses."""
    path, query, body, content_type = build_request(action, arguments, idempotency_key=idempotency_key)
    scheme, _, host = origin.partition('://')
    headers = [
        # The address the client used, so links the route makes point there.
        (b'host', host.encode('latin-1')),
        (b'x-forwarded-proto', scheme.encode('latin-1')),
        (b'x-vueio-agent-key', agent_key.encode('latin-1')),
        (b'user-agent', b'Vue.io MCP'),
        (b'accept', b'application/json, image/*;q=0.9, */*;q=0.1'),
        (b'content-length', str(len(body)).encode()),
    ]
    if content_type:
        headers.append((b'content-type', content_type.encode('latin-1')))
    if idempotency_key and not action.reads:
        headers.append((b'idempotency-key', idempotency_key.encode('utf-8')))
    return await _asgi_call(app, method=action.method, path=path, query=query, headers=headers, body=body, client=client)


def clean_text(text: str) -> str:
    return _HIDDEN_CHARACTERS.sub('', text)
