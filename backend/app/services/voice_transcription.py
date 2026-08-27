from __future__ import annotations

import json
import logging
import queue
import subprocess
import tempfile
import threading
from pathlib import Path

from app.config import get_settings
from app.db import SessionLocal
from app.models import Comment
from app.services.comments import (
    VOICE_NOTE_MAX_DURATION_SECONDS,
    VOICE_NOTE_TRANSCRIPTION_MAX_CHARS,
    load_attachment_list,
    resolve_attachment_target,
)

logger = logging.getLogger('vueio.voice_transcription')
settings = get_settings()

MAX_PENDING_TRANSCRIPTIONS = 128
_jobs: queue.Queue[tuple[int, str]] = queue.Queue(maxsize=MAX_PENDING_TRANSCRIPTIONS)
_queued_jobs: set[tuple[int, str]] = set()
_state_lock = threading.Lock()
_worker_started = False
_transcriber = None


def _is_voice_note(attachment: dict) -> bool:
    return (
        attachment.get('attachment_type') == 'upload'
        and attachment.get('kind') == 'audio'
        and attachment.get('duration') is not None
        and isinstance(attachment.get('peaks'), list)
    )


def enqueue_voice_note_transcription(comment_id: int, attachment_id: str) -> bool:
    if not settings.VOICE_TRANSCRIPTION_ENABLED:
        return False
    job = (int(comment_id), str(attachment_id))
    with _state_lock:
        if job in _queued_jobs:
            return False
        try:
            _jobs.put_nowait(job)
        except queue.Full:
            logger.warning('Voice transcription queue is full')
            return False
        _queued_jobs.add(job)
    return True


def _recover_pending_voice_notes() -> int:
    recovered = 0
    with SessionLocal() as db:
        comments = db.query(Comment).filter(Comment.attachments_data.isnot(None)).yield_per(100)
        for comment in comments:
            if recovered >= MAX_PENDING_TRANSCRIPTIONS:
                break
            attachments = load_attachment_list(comment)
            for attachment in attachments:
                status = attachment.get('transcription_status')
                attachment_id = str(attachment.get('id') or '')
                if (
                    attachment_id
                    and _is_voice_note(attachment)
                    and not attachment.get('transcription')
                    and status in (None, 'queued', 'processing')
                    and enqueue_voice_note_transcription(comment.id, attachment_id)
                ):
                    recovered += 1
    return recovered


def _lock_and_reload_comment(db, comment_id: int) -> Comment | None:
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if comment is None:
        return None
    from app.services.tracker_events import lock_tracker_for_comment_target

    lock_tracker_for_comment_target(
        db,
        project_id=comment.project_id,
        shot_version_id=comment.horizons_shot_version_id,
        media_asset_id=comment.horizons_media_asset_id,
    )
    return (
        db.query(Comment)
        .populate_existing()
        .filter(Comment.id == comment_id)
        .first()
    )


def _load_job(comment_id: int, attachment_id: str) -> Path | None:
    with SessionLocal() as db:
        comment = _lock_and_reload_comment(db, comment_id)
        if comment is None:
            return None
        attachments = load_attachment_list(comment)
        attachment = next((item for item in attachments if str(item.get('id')) == attachment_id), None)
        if attachment is None or not _is_voice_note(attachment):
            return None
        if attachment.get('transcription'):
            if attachment.get('transcription_status') != 'complete':
                attachment['transcription_status'] = 'complete'
                comment.attachments_data = json.dumps(attachments)
                db.commit()
            return None
        audio_path, _identity = resolve_attachment_target(comment, attachment_id)
        attachment['transcription_status'] = 'processing'
        comment.attachments_data = json.dumps(attachments)
        db.commit()
        return audio_path


def _save_result(comment_id: int, attachment_id: str, *, transcription: str | None, status: str) -> None:
    with SessionLocal() as db:
        comment = _lock_and_reload_comment(db, comment_id)
        if comment is None:
            return
        attachments = load_attachment_list(comment)
        attachment = next((item for item in attachments if str(item.get('id')) == attachment_id), None)
        if attachment is None or not _is_voice_note(attachment):
            return
        if attachment.get('transcription'):
            attachment['transcription_status'] = 'complete'
        else:
            attachment['transcription'] = transcription
            attachment['transcription_status'] = status
        comment.attachments_data = json.dumps(attachments)
        db.commit()


def _get_transcriber():
    global _transcriber
    if _transcriber is not None:
        return _transcriber

    model_path = settings.MOONSHINE_MODEL_PATH
    if not model_path.is_dir():
        raise RuntimeError('Moonshine model is unavailable')

    from moonshine_voice import ModelArch, Transcriber

    _transcriber = Transcriber(str(model_path), ModelArch.SMALL_STREAMING)
    logger.info('Moonshine voice transcription model loaded')
    return _transcriber


def _transcribe_audio_file(audio_path: Path) -> str | None:
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix='voice-note-',
        suffix='.wav',
        dir=settings.cache_dir,
        delete=False,
    ) as temporary:
        wav_path = Path(temporary.name)

    try:
        command = [
            'ffmpeg',
            '-v', 'error',
            '-nostdin',
            '-y',
            '-i', str(audio_path),
            '-t', str(VOICE_NOTE_MAX_DURATION_SECONDS),
            '-vn',
            '-ac', '1',
            '-ar', '16000',
            '-c:a', 'pcm_s16le',
            str(wav_path),
        ]
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=VOICE_NOTE_MAX_DURATION_SECONDS + 60,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError('FFmpeg could not decode the voice note') from exc

        from moonshine_voice import load_wav_file

        audio, sample_rate = load_wav_file(wav_path)
        result = _get_transcriber().transcribe_without_streaming(audio, sample_rate)
        text = ' '.join(line.text.strip() for line in result.lines if line.text.strip()).strip()
        return text[:VOICE_NOTE_TRANSCRIPTION_MAX_CHARS] or None
    finally:
        wav_path.unlink(missing_ok=True)


def _transcribe_job(comment_id: int, attachment_id: str) -> None:
    audio_path = _load_job(comment_id, attachment_id)
    if audio_path is None:
        return
    transcription = _transcribe_audio_file(audio_path)
    _save_result(comment_id, attachment_id, transcription=transcription, status='complete')


def _worker_main() -> None:
    recovered = _recover_pending_voice_notes()
    if recovered:
        logger.info('Queued %s pending voice note transcription(s)', recovered)
    while True:
        comment_id, attachment_id = _jobs.get()
        try:
            _transcribe_job(comment_id, attachment_id)
        except Exception:
            logger.exception('Voice note transcription failed for comment %s', comment_id)
            try:
                _save_result(comment_id, attachment_id, transcription=None, status='failed')
            except Exception:
                logger.exception('Could not save voice note transcription failure state')
        finally:
            with _state_lock:
                _queued_jobs.discard((comment_id, attachment_id))
            _jobs.task_done()


def start_voice_transcription_worker() -> None:
    global _worker_started
    if not settings.VOICE_TRANSCRIPTION_ENABLED:
        logger.info('Voice transcription is disabled')
        return
    with _state_lock:
        if _worker_started:
            return
        _worker_started = True
    threading.Thread(
        target=_worker_main,
        name='vueio-voice-transcription',
        daemon=True,
    ).start()
    logger.info('Local Moonshine voice transcription worker started')
