from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from subprocess import Popen

from .config import get_settings

settings = get_settings()

# Thread pool for background tasks
executor = ThreadPoolExecutor(max_workers=4)

# Track transcode progress in memory (thread-safe access via lock)
transcode_progress: dict[str, dict] = {}
_transcode_progress_lock = threading.Lock()
transcode_processes: dict[str, Popen] = {}
transcode_cancel_requested: set[str] = set()
TRANSCODE_CLEANUP_AGE = 300  # Remove completed/error entries after 5 minutes

def cleanup_old_transcode_entries() -> None:
    """Remove transcode_progress entries that completed/errored more than 5 minutes ago."""
    import time

    now = time.time()
    with _transcode_progress_lock:
        to_remove = [
            key for key, value in transcode_progress.items()
            if value.get('status') in ('complete', 'error')
            and value.get('completed_at', 0) < now - TRANSCODE_CLEANUP_AGE
        ]
        for key in to_remove:
            transcode_progress.pop(key, None)


# Track faststart remux jobs in progress (to avoid duplicate submissions)
_faststart_in_progress: set[str] = set()
_faststart_lock = threading.Lock()

# Global search index (in-memory cache)
SEARCH_INDEX_TTL_SECONDS = settings.SEARCH_INDEX_TTL_SECONDS
SEARCH_INDEX_MAX_FILES = settings.SEARCH_INDEX_MAX_FILES
_search_index_lock = threading.Lock()
_search_index_cache = {
    'built_at': 0.0,
    'projects': [],
    'trackers': [],
    'files': [],
}
