import re

from fastapi import HTTPException

USERNAME_PATTERN = re.compile(r'^[A-Za-z0-9_.-]{3,48}$')
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 1024


def normalize_username(value: str) -> str:
    username = str(value or '').strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise HTTPException(
            status_code=400,
            detail='Username must be 3-48 characters and only use letters, numbers, dots, dashes, or underscores',
        )
    return username


def validate_password(value: str, *, label: str = 'Password') -> str:
    password = str(value or '')
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f'{label} must be at least {MIN_PASSWORD_LENGTH} characters')
    if len(password) > MAX_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f'{label} is too long')
    return password


def normalize_display_name(value: str | None, *, fallback: str) -> str:
    return str(value or '').strip()[:120] or fallback
