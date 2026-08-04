from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from limits import parse
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MEDIA_ROOT: Path = Path('/media')
    PROJECTS_ROOT: Optional[Path] = None
    ARCHIVE_ROOT: Optional[Path] = None
    PROJECT_STORAGE_ROOTS: str = ''
    DATA_DIR: Path = Path('./data')
    DATABASE_URL: Optional[str] = None
    APP_ENV: str = 'development'
    VUEIO_VERSION: str = 'development'
    VUEIO_UPDATE_REPOSITORY: str = ''
    VUEIO_UPDATE_GITHUB_TOKEN: str = ''
    VUEIO_HIDDEN_STORAGE_FOLDERS: str = '.vueio,_gsdata_,.DS_Store'
    SECRET_KEY: str = 'vueio-secret-key-change-in-production'
    VUEIO_AGENT_API_KEY: str = ''
    VUEIO_AGENT_USER: str = 'agent_ro'
    VUEIO_PUBLIC_BASE_URL: str = ''
    VUEIO_LOCAL_HTTP: bool = False
    DISCORD_BOT_TOKEN: str = ''
    SESSION_COOKIE_SECURE: bool = False
    SESSION_COOKIE_SAMESITE: str = 'lax'
    SESSION_COOKIE_MAX_AGE: int = 86400 * 7
    CORS_ALLOW_ORIGINS: str = '*'
    VUEIO_SETUP_TOKEN: str = ''
    UPLOAD_MAX_FILE_BYTES: int = 100 * 1024 * 1024 * 1024
    UPLOAD_MAX_SESSION_BYTES: int = 500 * 1024 * 1024 * 1024
    UPLOAD_MAX_FILES_PER_SESSION: int = 10000
    UPLOAD_MIN_FREE_BYTES: int = 20 * 1024 * 1024 * 1024
    DATA_MIN_FREE_BYTES: int = 20 * 1024 * 1024 * 1024
    UPLOAD_SESSION_TTL_SECONDS: int = 24 * 60 * 60
    COMMENT_ATTACHMENT_MAX_FILE_BYTES: int = 256 * 1024 * 1024
    COMMENT_ATTACHMENT_MAX_TOTAL_BYTES: int = 500 * 1024 * 1024
    COMMENT_ANNOTATION_MAX_BYTES: int = 2 * 1024 * 1024
    VOICE_TRANSCRIPTION_ENABLED: bool = True
    MOONSHINE_MODEL_PATH: Path = Path(
        '/app/moonshine-models/download.moonshine.ai/model/small-streaming-en/quantized'
    )
    PUBLIC_UPLOAD_MAX_ACTIVE_SESSIONS: int = 25
    PUBLIC_UPLOAD_MAX_ACTIVE_SESSIONS_PER_CLIENT: int = 5
    PUBLIC_UPLOAD_MAX_SHARE_BYTES: int = 1024 * 1024 * 1024 * 1024
    PUBLIC_UPLOAD_MAX_FILES_PER_SESSION: int = 2000
    PUBLIC_UPLOAD_CREATE_RATE_LIMIT: str = '20/hour'
    PUBLIC_UPLOAD_CHUNK_RATE_LIMIT: str = '240/minute'
    PUBLIC_COMMENT_CREATE_RATE_LIMIT: str = '60/hour'
    PUBLIC_COMMENT_BATCH_RATE_LIMIT: str = '240/minute'
    PUBLIC_SHARE_PASSWORD_RATE_LIMIT: str = '30/minute'
    VUEIO_TRUST_PROXY_HEADERS: bool = False
    VUEIO_TRUST_CLOUDFLARE: bool = False
    PROJECT_DIRECTORY_MODE: str = '0777'
    PROJECT_FILE_MODE: str = '0666'
    TRANSCODE_RESOLUTION: str = '1080'
    TRANSCODE_CACHE_MAX_BYTES: int = 250 * 1024 * 1024 * 1024
    USE_HARDWARE_ACCEL: bool = False
    SEARCH_INDEX_TTL_SECONDS: int = 180
    SEARCH_INDEX_MAX_FILES: int = 25000
    PACKAGE_SYNC_MAX_BYTES: int = 250 * 1024 * 1024 * 1024
    PACKAGE_SYNC_MAX_FILES: int = 10000
    PACKAGE_SYNC_MAX_DEPTH: int = 64
    PACKAGE_SYNC_MAX_ROOTS: int = 1000
    PACKAGE_SYNC_MAX_ACTIVE_BUILDS: int = 1

    model_config = SettingsConfigDict(env_file='.env', case_sensitive=True)

    @field_validator('PROJECTS_ROOT', 'ARCHIVE_ROOT', mode='before')
    @classmethod
    def normalize_optional_storage_roots(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode='after')
    def validate_release_limits(self):
        if self.UPLOAD_SESSION_TTL_SECONDS <= 0:
            raise ValueError('UPLOAD_SESSION_TTL_SECONDS must be greater than zero')
        for name in (
            'UPLOAD_MAX_FILE_BYTES',
            'UPLOAD_MAX_SESSION_BYTES',
            'UPLOAD_MAX_FILES_PER_SESSION',
            'UPLOAD_MIN_FREE_BYTES',
            'DATA_MIN_FREE_BYTES',
            'COMMENT_ATTACHMENT_MAX_FILE_BYTES',
            'COMMENT_ATTACHMENT_MAX_TOTAL_BYTES',
            'COMMENT_ANNOTATION_MAX_BYTES',
            'TRANSCODE_CACHE_MAX_BYTES',
            'PUBLIC_UPLOAD_MAX_ACTIVE_SESSIONS',
            'PUBLIC_UPLOAD_MAX_ACTIVE_SESSIONS_PER_CLIENT',
            'PUBLIC_UPLOAD_MAX_SHARE_BYTES',
            'PUBLIC_UPLOAD_MAX_FILES_PER_SESSION',
        ):
            if getattr(self, name) < 0:
                raise ValueError(f'{name} cannot be negative')
        for name in (
            'PUBLIC_UPLOAD_CREATE_RATE_LIMIT',
            'PUBLIC_UPLOAD_CHUNK_RATE_LIMIT',
            'PUBLIC_COMMENT_CREATE_RATE_LIMIT',
            'PUBLIC_COMMENT_BATCH_RATE_LIMIT',
            'PUBLIC_SHARE_PASSWORD_RATE_LIMIT',
        ):
            try:
                parse(getattr(self, name))
            except ValueError as exc:
                raise ValueError(f'{name} is not a valid rate limit') from exc
        self._parse_permission_mode(self.PROJECT_DIRECTORY_MODE, 'PROJECT_DIRECTORY_MODE')
        self._parse_permission_mode(self.PROJECT_FILE_MODE, 'PROJECT_FILE_MODE')
        return self

    @property
    def database_dir(self) -> Path:
        return self.DATA_DIR / 'database'

    @property
    def cache_dir(self) -> Path:
        return self.DATA_DIR / 'cache'

    @property
    def thumbnail_dir(self) -> Path:
        return self.cache_dir / 'thumbnails'

    @property
    def transcode_dir(self) -> Path:
        return self.cache_dir / 'transcodes'

    @property
    def package_tmp_dir(self) -> Path:
        return self.DATA_DIR / 'packages' / 'tmp'

    @property
    def projects_dir(self) -> Path:
        return self.DATA_DIR / 'projects'

    @property
    def users_file(self) -> Path:
        return self.DATA_DIR / 'users.json'

    @property
    def notification_provider_settings_file(self) -> Path:
        return self.DATA_DIR / 'notification-provider-settings.json'

    @property
    def comment_attachments_dir(self) -> Path:
        return self.DATA_DIR / 'comment_attachments'

    @property
    def database_url(self) -> str:
        return self.DATABASE_URL or f'sqlite:///{self.database_dir}/vueio.db'

    @property
    def cors_allow_origins(self) -> list[str]:
        raw = (self.CORS_ALLOW_ORIGINS or '*').strip()
        if raw == '*':
            return ['*']
        return [origin.strip() for origin in raw.split(',') if origin.strip()]

    @property
    def hidden_storage_folders(self) -> set[str]:
        return {
            name.strip()
            for name in self.VUEIO_HIDDEN_STORAGE_FOLDERS.split(',')
            if name.strip()
        }

    @staticmethod
    def _parse_permission_mode(value: str, name: str) -> int:
        raw = str(value or '').strip().lower()
        if raw.startswith('0o'):
            raw = raw[2:]
        if not raw or any(char not in '01234567' for char in raw):
            raise ValueError(f'{name} must be an octal permission mode such as 0775')
        mode = int(raw, 8)
        if mode < 0 or mode > 0o777:
            raise ValueError(f'{name} must be between 0000 and 0777')
        return mode

    @property
    def project_directory_mode(self) -> int:
        return self._parse_permission_mode(self.PROJECT_DIRECTORY_MODE, 'PROJECT_DIRECTORY_MODE')

    @property
    def project_file_mode(self) -> int:
        return self._parse_permission_mode(self.PROJECT_FILE_MODE, 'PROJECT_FILE_MODE')

    @property
    def is_development(self) -> bool:
        return self.APP_ENV.lower() in {'dev', 'development', 'local'}

    @property
    def is_horizons_development_override(self) -> bool:
        return self.APP_ENV.lower() == 'horizons-development'

    def ensure_directories(self) -> None:
        for path in (
            self.database_dir,
            self.thumbnail_dir,
            self.transcode_dir,
            self.package_tmp_dir,
            self.projects_dir,
            self.comment_attachments_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
