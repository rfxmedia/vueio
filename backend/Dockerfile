FROM python:3.11-slim-trixie@sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6

LABEL org.opencontainers.image.title="Vue.io Engine" \
      org.opencontainers.image.licenses="PolyForm-Perimeter-1.0.1" \
      org.opencontainers.image.url="https://polyformproject.org/licenses/perimeter/1.0.1"

# Install only the runtime media stack.
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.lock moonshine-models.sha256 ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && \
    python -c "from pathlib import Path; from moonshine_voice import ModelArch, get_model_for_language; get_model_for_language('en', ModelArch.SMALL_STREAMING, cache_root=Path('/app/moonshine-models'))" && \
    cd /app/moonshine-models && \
    sha256sum -c /app/moonshine-models.sha256 && \
    cd /app && \
    python -c "from importlib.metadata import distribution; from pathlib import Path; dist = distribution('moonshine-voice'); source = next(dist.locate_file(file) for file in dist.files if str(file).endswith('licenses/LICENSE')); Path('/app/moonshine-models/MOONSHINE_LICENSE.txt').write_bytes(Path(source).read_bytes())" && \
    rm -rf /usr/local/lib/python3.11/site-packages/moonshine_voice/assets && \
    pip uninstall -y pip setuptools wheel && \
    rm -f /app/requirements.lock /app/moonshine-models.sha256

COPY main.py .
COPY app ./app
COPY alembic.ini .
COPY alembic/env.py ./alembic/env.py
COPY alembic/versions ./alembic/versions

RUN groupadd --gid 10001 vueio && \
    useradd --uid 10001 --gid vueio --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin vueio && \
    mkdir -p /app/data/thumbnails /app/data/transcodes && \
    chown -R vueio:vueio /app && \
    chmod -R a+rX /app

USER vueio

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
