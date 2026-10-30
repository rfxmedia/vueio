from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('vueio')
settings = get_settings()


def _insecure_runtime_default_failures() -> list[str]:
    failures = []
    if settings.SECRET_KEY == 'vueio-secret-key-change-in-production':
        failures.append('using default SECRET_KEY')
    local_http_bootstrap = settings.VUEIO_LOCAL_HTTP and not str(settings.VUEIO_PUBLIC_BASE_URL or '').strip()
    if (
        not settings.SESSION_COOKIE_SECURE
        and not (settings.is_development or settings.is_horizons_development_override or local_http_bootstrap)
    ):
        failures.append('SESSION_COOKIE_SECURE is disabled outside development or explicit local HTTP mode')
    if settings.cors_allow_origins == ['*']:
        failures.append('CORS_ALLOW_ORIGINS is wildcard')
    return failures


def _validate_secure_production_runtime_defaults() -> None:
    if settings.is_development or settings.is_horizons_development_override:
        return
    failures = _insecure_runtime_default_failures()
    if failures:
        raise RuntimeError(f'Insecure production configuration rejected: {", ".join(failures)}')


def _warn_insecure_runtime_defaults() -> None:
    if settings.is_development or settings.is_horizons_development_override:
        for message in _insecure_runtime_default_failures():
            logger.warning(f'SECURITY WARNING: {message}')
    if not settings.VUEIO_AGENT_API_KEY:
        logger.info('No legacy environment agent key configured; managed agent keys remain available')
    if settings.VUEIO_LOCAL_HTTP:
        logger.warning(
            'SECURITY WARNING: VUEIO_LOCAL_HTTP is enabled; use this only on a trusted local network '
            'and disable it before exposing Vueio through a public URL'
        )


def create_app() -> FastAPI:
    _validate_secure_production_runtime_defaults()

    from app.db import SessionLocal, run_migrations
    from app.limiter import limiter
    from app.routes.account import router as account_router
    from app.routes.admin import router as admin_router
    from app.routes.auth import router as auth_router
    from app.routes.comments import router as comments_router
    from app.routes.app_state import router as app_state_router
    from app.routes.files import router as files_router
    from app.routes.folder_events import router as folder_events_router
    from app.routes.horizons_fresh import router as horizons_fresh_router
    from app.routes.horizons_media_objects import router as horizons_media_objects_router
    from app.routes.horizons_project_support import router as horizons_project_support_router
    from app.routes.health import router as health_router
    from app.routes.luts import router as luts_router
    from app.routes.media_assets import router as media_assets_router
    from app.routes.mention_search import router as mention_search_router
    from app.routes.notifications import router as notifications_router
    from app.routes.oauth import router as oauth_router
    from app.routes.project_media import router as project_media_router
    from app.routes.project_storage import router as project_storage_router
    from app.routes.projects import router as projects_router
    from app.routes.share_media import router as share_media_router
    from app.routes.share_preview import router as share_preview_router
    from app.routes.shot_extras import router as shot_extras_router
    from app.routes.shot_registry import router as shot_registry_router
    from app.routes.setup import router as setup_router
    from app.routes.shares import router as shares_router
    from app.routes.streaming import router as streaming_router
    from app.routes.trackers_basic import router as trackers_basic_router
    from app.routes.tracker_workflow import router as tracker_workflow_router
    from app.routes.users import router as users_router
    from app.services.notifications import is_discord_provider_configured, start_notification_dispatcher
    from app.services.file_operation_journal import run_pending_file_operation_repairs
    from app.services.history_retention import prune_persistent_history
    from app.services.transcode_lifecycle import enforce_transcode_cache_budget
    from app.services.zip_utils import cleanup_orphaned_zip_temp_files, recover_interrupted_package_jobs
    from app.services.voice_transcription import start_voice_transcription_worker
    from app.services.folder_events import folder_events
    from app.services.mcp_server import McpEndpoint
    from app.services.oauth import prune_expired_tokens as prune_expired_oauth_tokens
    from app.services.agent_idempotency import prune_expired_receipts

    run_migrations()
    _warn_insecure_runtime_defaults()

    async def maintain_preview_cache():
        while True:
            try:
                await asyncio.to_thread(prune_expired_receipts)
                await asyncio.to_thread(prune_expired_oauth_tokens)
                result = await asyncio.to_thread(enforce_transcode_cache_budget, expire_unused=True)
                if result['evicted_jobs']:
                    logger.info('Cleared %s unused preview(s), reclaiming %s bytes', result['evicted_jobs'], result['evicted_bytes'])
            except Exception:
                logger.exception('Preview cache cleanup failed')
            await asyncio.sleep(60 * 60)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with SessionLocal() as db:
            pruned_history = prune_persistent_history(db)
            db.commit()
        if any(pruned_history.values()):
            logger.info('Pruned bounded operational history: %s', pruned_history)
        prune_expired_oauth_tokens()
        cleaned_zip_temps = cleanup_orphaned_zip_temp_files()
        if cleaned_zip_temps:
            logger.info('Removed %s orphaned ZIP temp file(s)', cleaned_zip_temps)
        recovered_package_jobs = recover_interrupted_package_jobs()
        if recovered_package_jobs:
            logger.info('Marked %s interrupted package job(s) for retry', recovered_package_jobs)
        try:
            repaired = run_pending_file_operation_repairs()
            if repaired:
                logger.info('Repaired %s pending file operation(s)', repaired)
        except Exception:
            logger.exception('Pending file operation repair failed')
        if is_discord_provider_configured():
            start_notification_dispatcher()
        else:
            logger.info('Discord bot token not configured; notification dispatcher is idle')
        start_voice_transcription_worker()
        preview_cleanup = asyncio.create_task(maintain_preview_cache())
        try:
            async with mcp_endpoint.run():
                yield
        finally:
            preview_cleanup.cancel()
            with suppress(asyncio.CancelledError):
                await preview_cleanup
            folder_events.close()

    app = FastAPI(title='vue.io', version=settings.VUEIO_VERSION, lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(auth_router)
    app.include_router(account_router)
    app.include_router(setup_router)
    app.include_router(comments_router)
    app.include_router(users_router)
    app.include_router(admin_router)
    app.include_router(files_router)
    app.include_router(folder_events_router)
    app.include_router(health_router)
    app.include_router(luts_router)
    app.include_router(horizons_fresh_router)
    app.include_router(horizons_media_objects_router)
    app.include_router(shot_extras_router)
    app.include_router(horizons_project_support_router)
    app.include_router(media_assets_router)
    app.include_router(mention_search_router)
    app.include_router(notifications_router)
    app.include_router(oauth_router)
    app.include_router(projects_router)
    app.include_router(project_media_router)
    app.include_router(project_storage_router)
    app.include_router(share_media_router)
    app.include_router(share_preview_router)
    app.include_router(shot_registry_router)
    app.include_router(app_state_router)
    app.include_router(shares_router)
    app.include_router(streaming_router)
    app.include_router(trackers_basic_router)
    app.include_router(tracker_workflow_router)
    # Agents connect here with their agent key; see app/services/mcp_server.py.
    mcp_endpoint = McpEndpoint(app)
    app.router.add_route('/api/mcp', mcp_endpoint, methods=['GET', 'POST', 'DELETE'], include_in_schema=False)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    @app.middleware('http')
    async def log_slow_requests(request: Request, call_next):
        from starlette.concurrency import run_in_threadpool

        from app.services.auth import (
            INTERNAL_CALL_SCOPE_KEY,
            request_agent_credential,
            reset_request_agent_identity,
            reset_request_agent_key,
            reset_request_internal_call,
            resolve_request_agent_identity,
            set_request_agent_identity,
            set_request_agent_key,
            set_request_internal_call,
        )
        from app.services.share_access import reset_request_share_access_token, set_request_share_access_token

        agent_key = request_agent_credential(request)
        internal_token = set_request_internal_call(request.scope.get(INTERNAL_CALL_SCOPE_KEY) is True)
        credential_token = set_request_agent_key(agent_key)
        agent_identity_token = set_request_agent_identity(None)
        share_credential_token = set_request_share_access_token(request.cookies.get('vueio_share_access'))
        start = time.perf_counter()
        try:
            agent_identity = await run_in_threadpool(resolve_request_agent_identity, agent_key) if agent_key and request.url.path != '/api/mcp' else None
            set_request_agent_identity(agent_identity)
            if agent_identity:
                from fastapi.responses import JSONResponse

                from app.limiter import agent_request_allowed
                from app.services.agent_idempotency import run_with_idempotency

                if not request.scope.get(INTERNAL_CALL_SCOPE_KEY) and not agent_request_allowed(agent_identity['key_id']):
                    return JSONResponse({'detail': 'Too many agent requests. Wait a minute, then retry.'}, status_code=429, headers={'Retry-After': '60'})
                response = await run_with_idempotency(request, call_next, agent_identity['key_id'])
            else:
                response = await call_next(request)
        finally:
            reset_request_share_access_token(share_credential_token)
            reset_request_agent_identity(agent_identity_token)
            reset_request_agent_key(credential_token)
            reset_request_internal_call(internal_token)
        duration = time.perf_counter() - start
        if duration > 0.5:
            logger.warning(f'SLOW REQUEST: {request.method} {request.url.path} took {duration:.2f}s')
        response.headers['X-Response-Time'] = f'{duration:.3f}'
        return response

    return app
