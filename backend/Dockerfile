FROM python:3.11-slim-trixie@sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6 AS base

# Use the patched upstream release without a codec fork or desktop capture stack.
# Build tools stay in this stage. Runtime dependencies are resolved by Debian.
FROM base AS media-build
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    build-essential curl pkg-config nasm xz-utils \
    libx264-dev libx265-dev libvpx-dev libdav1d-dev libopus-dev libmp3lame-dev \
    libvorbis-dev libwebp-dev libopenjp2-7-dev libjxl-dev libva-dev libdrm-dev \
    libffmpeg-nvenc-dev libzimg-dev libsoxr-dev zlib1g-dev libbz2-dev liblzma-dev
WORKDIR /build
# This hash was checked against FFmpeg's signed 9.0.1 release archive.
RUN curl --fail --show-error --silent --location --retry 3 \
        https://ffmpeg.org/releases/ffmpeg-9.0.1.tar.xz -o ffmpeg-9.0.1.tar.xz && \
    echo 'cf38e0e28c7e5605942c4a77755349b0145804a397af37eb1fb4c77cb237f635  ffmpeg-9.0.1.tar.xz' | sha256sum -c - && \
    tar -xf ffmpeg-9.0.1.tar.xz
WORKDIR /build/ffmpeg-9.0.1
RUN ./configure --prefix=/usr --disable-doc --disable-debug --disable-ffplay \
    --disable-autodetect --disable-shared --enable-static --enable-pic --enable-gpl \
    --disable-indevs --enable-indev=lavfi --disable-outdevs \
    --enable-libx264 --enable-libx265 --enable-libvpx --enable-libdav1d \
    --enable-libopus --enable-libmp3lame --enable-libvorbis --enable-libwebp \
    --enable-libopenjpeg --enable-libjxl --enable-libzimg --enable-libsoxr \
    --enable-vaapi --enable-libdrm --enable-ffnvcodec --enable-nvenc --enable-nvdec \
    --enable-zlib --enable-bzlib --enable-lzma \
    --extra-cflags='-O2 -fstack-protector-strong -D_FORTIFY_SOURCE=3' \
    --extra-ldflags='-Wl,-z,relro,-z,now -pie' && \
    make -j4 ffmpeg ffprobe && strip ffmpeg ffprobe
# Install a real package: do not make FFmpeg invisible to scanners or SBOMs.
# Keep its exact source and notices with the binaries for redistribution.
RUN mkdir -p /package/usr/bin /package/usr/share/doc/ffmpeg /package/DEBIAN debian && \
    cp ffmpeg ffprobe /package/usr/bin/ && \
    cp COPYING.* LICENSE.md ../ffmpeg-9.0.1.tar.xz /package/usr/share/doc/ffmpeg/ && \
    cp /usr/share/doc/libffmpeg-nvenc-dev/copyright /package/usr/share/doc/ffmpeg/nv-codec-headers-copyright && \
    ./ffmpeg -hide_banner -buildconf > /package/usr/share/doc/ffmpeg/build-configuration.txt 2>&1 && \
    printf 'Source: ffmpeg\nMaintainer: Vueio maintainers\n\nPackage: ffmpeg\nArchitecture: any\nDescription: FFmpeg for Vueio media processing\n' > debian/control && \
    depends=$(dpkg-shlibdeps -O -effmpeg -effprobe | sed -n 's/^shlibs:Depends=//p') && test -n "$depends" && \
    printf 'Package: ffmpeg\nVersion: 7:9.0.1-0vueio1\nArchitecture: %s\nMaintainer: Vueio maintainers\nDepends: %s\nDescription: FFmpeg for Vueio media processing\n' "$(dpkg --print-architecture)" "$depends" > /package/DEBIAN/control && \
    dpkg-deb --build --root-owner-group /package /build/ffmpeg.deb

FROM base AS model-build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ca-certificates libimath-dev zlib1g-dev
COPY app/model_decoder /build/model-decoder
RUN cmake -S /build/model-decoder -B /build/output -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr && \
    cmake --build /build/output --target vueio-model-preview -j4 && \
    DESTDIR=/package cmake --install /build/output --component decoder && \
    strip /package/usr/bin/vueio-model-preview
# Keep upstream source references, versions and licenses with this small decoder.
RUN mkdir -p /package/DEBIAN /package/usr/share/doc/vueio-model-preview debian && \
    cp /build/model-decoder/CMakeLists.txt /package/usr/share/doc/vueio-model-preview/ && \
    printf 'Source: vueio-model-preview\nMaintainer: Vueio maintainers\n\nPackage: vueio-model-preview\nArchitecture: any\nDescription: Alembic mesh preview decoder\n' > debian/control && \
    depends=$(dpkg-shlibdeps -O -e/package/usr/bin/vueio-model-preview | sed -n 's/^shlibs:Depends=//p') && test -n "$depends" && \
    printf 'Package: vueio-model-preview\nVersion: 1.8.12-1\nArchitecture: %s\nMaintainer: Vueio maintainers\nDepends: %s\nBuilt-Using: alembic (= 1.8.12), mapbox-earcut (= 2.2.4)\nDescription: Bounded Ogawa polygon-mesh preview decoder\n' "$(dpkg --print-architecture)" "$depends" > /package/DEBIAN/control && \
    dpkg-deb --build --root-owner-group /package /build/model-preview.deb

FROM base

LABEL org.opencontainers.image.title="Vue.io Engine" \
      org.opencontainers.image.licenses="PolyForm-Perimeter-1.0.1" \
      org.opencontainers.image.url="https://polyformproject.org/licenses/perimeter/1.0.1"

COPY --from=media-build /build/ffmpeg.deb /tmp/ffmpeg.deb
COPY --from=model-build /build/model-preview.deb /tmp/model-preview.deb
# Each release tag refreshes OS packages instead of reusing a cached upgrade.
ARG VUEIO_PACKAGE_REFRESH=
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends /tmp/ffmpeg.deb /tmp/model-preview.deb mesa-va-drivers pciutils && \
    rm /tmp/ffmpeg.deb /tmp/model-preview.deb && \
    rm -rf /var/lib/apt/lists/*

# Debian slim drops optional package documentation during installation.
COPY --from=media-build /package/usr/share/doc/ffmpeg /usr/share/doc/ffmpeg
COPY --from=model-build /package/usr/share/doc/vueio-model-preview /usr/share/doc/vueio-model-preview

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
