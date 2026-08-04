from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db

router = APIRouter(tags=['health'])
settings = get_settings()


@router.get('/api/health/live')
def liveness():
    """Confirm that the API process can serve requests."""
    return {'status': 'ok'}


@router.get('/api/health/ready')
def readiness(db: Session = Depends(get_db)):
    """Confirm that required state is available before routing traffic."""
    try:
        db.execute(text('SELECT 1'))
        data_dir_ready = settings.DATA_DIR.is_dir() and os.access(settings.DATA_DIR, os.R_OK | os.W_OK)
    except (OSError, SQLAlchemyError):
        data_dir_ready = False
    if not data_dir_ready:
        return JSONResponse(status_code=503, content={'status': 'not_ready'})
    return {'status': 'ready'}
