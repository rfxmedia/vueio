import uuid

from fastapi import APIRouter, Cookie, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import WorkspaceLut
from app.services.auth import require_admin, require_auth
from app.services.cube_luts import MAX_LIBRARY_BYTES, MAX_LIBRARY_COUNT, MAX_LUT_BYTES, validate_cube
from app.services.share_access import validate_share


router = APIRouter()
SHARE_TYPES = ['file', 'folder', 'project-file', 'project-folder', 'project', 'tracker', 'page']


def metadata(lut):
    return {'id': lut.id, 'name': lut.name, 'size': lut.size, 'byte_size': lut.byte_size}


def library(db):
    return {'luts': [metadata(lut) for lut in db.query(WorkspaceLut).order_by(WorkspaceLut.name, WorkspaceLut.id).all()]}


def get_lut(db, lut_id):
    lut = db.get(WorkspaceLut, lut_id)
    if lut is None:
        raise HTTPException(status_code=404, detail='LUT not found')
    return lut


def cube_response(lut):
    return PlainTextResponse(lut.cube_text, headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


def lock_library(db):
    # Serialize quota checks and writes across workers, including an empty library.
    if db.get_bind().dialect.name == 'postgresql':
        db.execute(text('LOCK TABLE workspace_luts IN SHARE ROW EXCLUSIVE MODE'))
    else:
        db.execute(text('BEGIN IMMEDIATE'))


@router.get('/api/luts')
def list_luts(response: Response, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    require_auth(vueio_session)
    response.headers['Cache-Control'] = 'private, no-store'
    return library(db)


@router.get('/api/luts/{lut_id}')
def read_lut(lut_id: str, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    require_auth(vueio_session)
    return cube_response(get_lut(db, lut_id))


@router.post('/api/admin/luts', status_code=201)
def upload_lut(file: UploadFile = File(...), vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    require_admin(vueio_session)
    if not (file.filename or '').lower().endswith('.cube'):
        raise HTTPException(status_code=400, detail='Select a .cube LUT file.')
    if file.size is not None and file.size > MAX_LUT_BYTES:
        raise HTTPException(status_code=413, detail='The LUT file must be 32 MiB or smaller.')
    content = file.file.read(MAX_LUT_BYTES + 1)
    if len(content) > MAX_LUT_BYTES:
        raise HTTPException(status_code=413, detail='The LUT file must be 32 MiB or smaller.')
    try:
        cube_text = content.decode('utf-8')
        name, size = validate_cube(cube_text, file.filename)
    except (UnicodeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error) if not isinstance(error, UnicodeError) else 'The LUT must be UTF-8 text.') from error
    lock_library(db)
    count, byte_size = db.query(func.count(WorkspaceLut.id), func.coalesce(func.sum(WorkspaceLut.byte_size), 0)).one()
    if count >= MAX_LIBRARY_COUNT or byte_size + len(content) > MAX_LIBRARY_BYTES:
        raise HTTPException(status_code=409, detail='The LUT library is full (64 files or 256 MiB). Remove a LUT before adding another.')
    lut = WorkspaceLut(id=uuid.uuid4().hex, name=name, size=size, byte_size=len(content), cube_text=cube_text)
    db.add(lut)
    db.commit()
    return metadata(lut)


@router.delete('/api/admin/luts/{lut_id}', status_code=204)
def delete_lut(lut_id: str, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    require_admin(vueio_session)
    lock_library(db)
    db.delete(get_lut(db, lut_id))
    db.commit()
    return Response(status_code=204)


@router.get('/api/shared/{share_id}/luts')
def list_shared_luts(share_id: str, response: Response, share_token: str | None = None, db: Session = Depends(get_db)):
    validate_share(share_id, None, db, SHARE_TYPES, share_token=share_token, track_access=False)
    response.headers['Cache-Control'] = 'private, no-store'
    return library(db)


@router.get('/api/shared/{share_id}/luts/{lut_id}')
def read_shared_lut(share_id: str, lut_id: str, share_token: str | None = None, db: Session = Depends(get_db)):
    validate_share(share_id, None, db, SHARE_TYPES, share_token=share_token, track_access=False)
    return cube_response(get_lut(db, lut_id))
