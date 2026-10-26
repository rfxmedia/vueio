"""Sign in with Vue.io: discovery, consent, tokens and connected apps.

See app/services/oauth.py for the rules. The consent page is plain HTML from
the engine, so it works before the web app loads and needs no script.
"""
from __future__ import annotations

import hashlib
import hmac
import html
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.limiter import enforce_rate_limit
from app.services import oauth
from app.services.auth import (
    authenticate_and_create_session,
    get_user_from_session,
    require_signed_in_user,
)

router = APIRouter(tags=['oauth'])
settings = get_settings()

AUTHORIZE_FIELDS = ('response_type', 'client_id', 'redirect_uri', 'code_challenge', 'code_challenge_method', 'state', 'scope', 'resource')
NO_STORE = {'Cache-Control': 'no-store', 'Pragma': 'no-cache'}


# Discovery

@router.get('/.well-known/oauth-authorization-server', include_in_schema=False)
def authorization_server_metadata(request: Request):
    return JSONResponse(oauth.authorization_server_metadata(oauth.public_origin(request)))


@router.get('/.well-known/oauth-protected-resource', include_in_schema=False)
@router.get('/.well-known/oauth-protected-resource/api/mcp', include_in_schema=False)
def protected_resource_metadata(request: Request):
    return JSONResponse(oauth.protected_resource_metadata(oauth.public_origin(request)))


# Consent

def _csrf_token(session_id: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f'oauth-consent:{session_id}'.encode(), hashlib.sha256).hexdigest()


def _origin_of(uri: str) -> str:
    parts = urlsplit(uri)
    return f'{parts.scheme}://{parts.netloc}'


def _page(title: str, body: str, *, status: int = 200, form_targets: tuple[str, ...] = ()) -> HTMLResponse:
    form_action = ' '.join(("'self'", *form_targets))
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>{html.escape(title)} · Vue.io</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px; background: #0a0f14; color: #eef5f4;
  font: 15px/1.5 system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; -webkit-font-smoothing: antialiased; }}
main {{ width: 100%; max-width: 420px; background: #141c23; border: 1px solid #212930; border-radius: 14px; padding: 28px; }}
.mark {{ width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center; background: #76dda8; color: #0a0f14; font-weight: 800; margin-bottom: 18px; }}
h1 {{ font-size: 19px; line-height: 1.3; margin: 0 0 8px; }}
p {{ margin: 0 0 14px; color: #c9d6d8; }}
ul {{ margin: 0 0 18px; padding-left: 18px; color: #c9d6d8; }}
li {{ margin-bottom: 6px; }}
.note {{ font-size: 13px; color: #8b9a9e; }}
.error {{ color: #ff6b6b; }}
label {{ display: block; font-size: 13px; color: #c9d6d8; margin: 0 0 6px; }}
input[type=text], input[type=password] {{ width: 100%; margin-bottom: 14px; padding: 10px 12px; border-radius: 10px; border: 1px solid #2a343c; background: #0f161c; color: #eef5f4; font: inherit; }}
input:focus {{ outline: none; border-color: #76dda8; }}
.actions {{ display: flex; gap: 10px; margin-top: 6px; }}
button {{ flex: 1; padding: 10px 14px; border-radius: 10px; border: 1px solid #2a343c; background: transparent; color: #eef5f4; font: inherit; font-weight: 600; cursor: pointer; }}
button.primary {{ background: #76dda8; border-color: #76dda8; color: #0a0f14; font-weight: 700; }}
button:focus-visible {{ outline: 2px solid #76dda8; outline-offset: 2px; }}
strong {{ color: #eef5f4; }}
</style>
</head>
<body><main><div class="mark" aria-hidden="true">V</div>{body}</main></body>
</html>"""
    headers = {
        **NO_STORE,
        'X-Frame-Options': 'DENY',
        'Referrer-Policy': 'no-referrer',
        'Content-Security-Policy': f"default-src 'none'; style-src 'unsafe-inline'; form-action {form_action}; frame-ancestors 'none'; base-uri 'none'",
    }
    return HTMLResponse(document, status_code=status, headers=headers)


def _error_page(message: str, status: int = 400) -> HTMLResponse:
    return _page('Cannot connect', f'<h1>This app cannot connect</h1><p class="error">{html.escape(message)}</p>'
                 '<p class="note">Close this page and try again from the app.</p>', status=status)


def _redirect_with(redirect_uri: str, origin: str, **values) -> RedirectResponse:
    query = urlencode({key: value for key, value in {**values, 'iss': origin}.items() if value is not None})
    separator = '&' if urlsplit(redirect_uri).query else '?'
    return RedirectResponse(f'{redirect_uri}{separator}{query}', status_code=303, headers=NO_STORE)


def _hidden_fields(params: dict) -> str:
    return ''.join(
        f'<input type="hidden" name="{name}" value="{html.escape(params[name] or "", quote=True)}">'
        for name in AUTHORIZE_FIELDS
        if params.get(name)
    )


async def _validated_request(request: Request, params: dict):
    """Check an authorization request. Return (client, redirect_uri, resource) or an error response."""
    origin = oauth.public_origin(request)
    try:
        enforce_rate_limit(request, '30/minute', scope='oauth-authorize')
    except HTTPException as exc:
        return _error_page('Too many connection attempts. Wait a minute, then try again.', status=exc.status_code)
    try:
        client = await oauth.get_client(params.get('client_id') or '')
    except oauth.OAuthError as exc:
        return _error_page(exc.description)
    registered = oauth.client_redirect_uris(client)
    redirect_uri = params.get('redirect_uri') or (registered[0] if len(registered) == 1 else '')
    if not redirect_uri or not oauth.redirect_uri_allowed(redirect_uri, registered):
        # Never redirect to an address the client did not register.
        return _error_page('The redirect address is not registered for this app.')
    state = params.get('state')
    if params.get('response_type') != 'code':
        return _redirect_with(redirect_uri, origin, error='unsupported_response_type', error_description='Use response_type=code.', state=state)
    if not params.get('code_challenge') or (params.get('code_challenge_method') or 'S256') != 'S256':
        return _redirect_with(redirect_uri, origin, error='invalid_request', error_description='PKCE with S256 is required.', state=state)
    resource = params.get('resource') or oauth.resource_url(origin)
    if not oauth.same_resource(resource, oauth.resource_url(origin)):
        return _redirect_with(redirect_uri, origin, error='invalid_target', error_description='This server only issues tokens for its MCP server.', state=state)
    return client, redirect_uri, oauth.resource_url(origin)


def _sign_in_page(client_name: str, query: str, *, error: str = '', status: int = 200) -> HTMLResponse:
    message = f'<p class="error" role="alert">{html.escape(error)}</p>' if error else ''
    body = f"""<h1>Sign in to connect {html.escape(client_name)}</h1>
<p>Sign in to Vue.io. Then you choose whether {html.escape(client_name)} may use your account.</p>
{message}
<form method="post" action="/oauth/sign-in">
<input type="hidden" name="next" value="{html.escape('/oauth/authorize?' + query, quote=True)}">
<label for="username">Username</label>
<input id="username" name="username" type="text" autocomplete="username" required autofocus>
<label for="password">Password</label>
<input id="password" name="password" type="password" autocomplete="current-password" required>
<div class="actions"><button class="primary" type="submit">Sign in</button></div>
</form>"""
    return _page('Sign in', body, status=status)


@router.get('/oauth/authorize', include_in_schema=False)
async def authorize_page(request: Request, vueio_session: str | None = Cookie(None)):
    params = {name: request.query_params.get(name) for name in AUTHORIZE_FIELDS}
    checked = await _validated_request(request, params)
    if isinstance(checked, Response):
        return checked
    client, redirect_uri, _resource = checked
    user = await run_in_threadpool(get_user_from_session, vueio_session, allow_agent_fallback=False)
    if not user:
        return _sign_in_page(client.name, request.url.query)
    name = html.escape(client.name)
    person = html.escape(user.get('display_name') or user.get('username') or 'you')
    destination = html.escape(urlsplit(redirect_uri).hostname or redirect_uri)
    body = f"""<h1>Connect {name} to Vue.io</h1>
<p><strong>{name}</strong> wants to act as <strong>{person}</strong> in Vue.io.</p>
<ul>
<li>It can do everything you can do in Vue.io: read and change projects, trackers, shots, versions, comments and shares.</li>
<li>It cannot change your password or manage agent keys.</li>
<li>Vue.io shows its changes as yours, made with {name}.</li>
</ul>
<form method="post" action="/oauth/authorize">
{_hidden_fields({**params, 'redirect_uri': redirect_uri})}
<input type="hidden" name="csrf" value="{_csrf_token(vueio_session)}">
<div class="actions">
<button type="submit" name="decision" value="deny">Cancel</button>
<button class="primary" type="submit" name="decision" value="allow">Allow</button>
</div>
</form>
<p class="note" style="margin-top:16px">After you choose, Vue.io sends you back to {destination}. You can disconnect {name} at any time in Settings → Agent keys.</p>"""
    return _page(f'Connect {client.name}', body, form_targets=(_origin_of(redirect_uri),))


@router.post('/oauth/authorize', include_in_schema=False)
async def authorize_decision(request: Request, vueio_session: str | None = Cookie(None)):
    form = await request.form()
    params = {name: (str(form.get(name)) if form.get(name) is not None else None) for name in AUTHORIZE_FIELDS}
    checked = await _validated_request(request, params)
    if isinstance(checked, Response):
        return checked
    client, redirect_uri, resource = checked
    user = await run_in_threadpool(get_user_from_session, vueio_session, allow_agent_fallback=False)
    if not user or not hmac.compare_digest(str(form.get('csrf') or ''), _csrf_token(vueio_session)):
        return _error_page('Your sign-in changed. Start again from the app.', status=403)
    origin = oauth.public_origin(request)
    state = params.get('state')
    if form.get('decision') != 'allow':
        return _redirect_with(redirect_uri, origin, error='access_denied', error_description='The person did not allow access.', state=state)
    code = await run_in_threadpool(
        oauth.create_code,
        user=user,
        client=client,
        redirect_uri=redirect_uri,
        code_challenge=params['code_challenge'],
        resource=resource,
    )
    return _redirect_with(redirect_uri, origin, code=code, state=state)


@router.post('/oauth/sign-in', include_in_schema=False)
async def oauth_sign_in(request: Request):
    try:
        enforce_rate_limit(request, '5/minute', scope='oauth-sign-in')
    except HTTPException as exc:
        return _error_page('Too many sign-in attempts. Wait a minute, then try again.', status=exc.status_code)
    form = await request.form()
    next_url = str(form.get('next') or '')
    if not next_url.startswith('/oauth/authorize?'):
        return _error_page('This sign-in link is not valid.')
    query = next_url.split('?', 1)[1]
    try:
        client = await oauth.get_client((parse_qs(query).get('client_id') or [''])[0])
    except oauth.OAuthError:
        return _error_page('This app is not known to Vue.io.')
    client_name = client.name
    try:
        _user, session_id = await run_in_threadpool(
            authenticate_and_create_session,
            str(form.get('username') or '')[:120],
            str(form.get('password') or '')[:1024],
        )
    except HTTPException as exc:
        message = 'Too many attempts. Wait a minute, then try again.' if exc.status_code == 429 else 'The username or password is not correct.'
        return _sign_in_page(client_name, query, error=message, status=exc.status_code if exc.status_code in (401, 429) else 400)
    response = RedirectResponse(next_url, status_code=303, headers=NO_STORE)
    response.set_cookie(
        key='vueio_session',
        value=session_id,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        max_age=settings.SESSION_COOKIE_MAX_AGE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
    )
    return response


# Tokens and clients

def _oauth_error(exc: oauth.OAuthError) -> JSONResponse:
    return JSONResponse({'error': exc.error, 'error_description': exc.description}, status_code=exc.status, headers=NO_STORE)


@router.post('/api/oauth/token', include_in_schema=False)
async def token(request: Request):
    form = await request.form()
    grant_type = form.get('grant_type')
    client_id = str(form.get('client_id') or '')
    resource = str(form.get('resource')) if form.get('resource') else None
    try:
        if grant_type == 'authorization_code':
            tokens = await run_in_threadpool(
                oauth.exchange_code,
                code=str(form.get('code') or ''),
                client_id=client_id,
                redirect_uri=str(form.get('redirect_uri') or ''),
                code_verifier=str(form.get('code_verifier') or ''),
                resource=resource,
            )
        elif grant_type == 'refresh_token':
            tokens = await run_in_threadpool(
                oauth.refresh_tokens,
                refresh_token=str(form.get('refresh_token') or ''),
                client_id=client_id,
                resource=resource,
            )
        else:
            raise oauth.OAuthError('unsupported_grant_type', 'Use authorization_code or refresh_token.')
    except oauth.OAuthError as exc:
        return _oauth_error(exc)
    return JSONResponse(tokens, headers=NO_STORE)


@router.post('/api/oauth/register', include_in_schema=False)
async def register(request: Request):
    enforce_rate_limit(request, '20/hour', scope='oauth-register')
    try:
        metadata = await request.json()
    except ValueError:
        metadata = None
    try:
        client = await run_in_threadpool(oauth.register_client, metadata)
    except oauth.OAuthError as exc:
        return _oauth_error(exc)
    return JSONResponse(client, status_code=201, headers=NO_STORE)


@router.post('/api/oauth/revoke', include_in_schema=False)
async def revoke(request: Request):
    form = await request.form()
    await run_in_threadpool(oauth.revoke_token, str(form.get('token') or ''))
    return Response(status_code=200, headers=NO_STORE)


# Connected apps: a person manages these in Settings; agents cannot.

@router.get('/api/me/connected-apps', summary='List my connected apps')
def list_connected_apps(vueio_session: str | None = Cookie(None)):
    """List the apps this person connected with Sign in with Vue.io."""
    user = require_signed_in_user(vueio_session)
    return {'apps': oauth.list_user_grants(user['id'])}


@router.delete('/api/me/connected-apps/{grant_id}', summary='Disconnect an app')
def disconnect_connected_app(grant_id: str, vueio_session: str | None = Cookie(None)):
    """Disconnect an app. Its tokens stop working at once."""
    user = require_signed_in_user(vueio_session)
    if not oauth.disconnect_user_grant(user['id'], grant_id):
        raise HTTPException(status_code=404, detail='Connected app not found')
    return {'status': 'disconnected'}
