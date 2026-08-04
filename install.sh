#!/usr/bin/env sh
set -eu

# This bootstrap installs the small host-side controller. Vueio itself remains
# entirely inside Docker Compose; this script never mounts the Docker socket.
VERSION=${VUEIO_VERSION:-}
INSTALL_DIR=${VUEIO_HOME:-/opt/vueio}
BIN_DIR=${VUEIO_BIN_DIR:-/usr/local/bin}
RELEASE_ROOT_URL=${VUEIO_RELEASE_ROOT_URL:-https://github.com/rfxmedia/vueio/releases}
ASSET_BASE_URL="$RELEASE_ROOT_URL/download/$VERSION"

printf '%s\n' "$VERSION" |
  grep -Eq '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-alpha\.(0|[1-9][0-9]*)$' || {
  echo "VUEIO_VERSION must be an immutable vX.Y.Z-alpha.N release tag without leading zeroes." >&2
  exit 1
}

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root (for example: curl ... | sudo sh)." >&2
  exit 1
fi
command -v curl >/dev/null 2>&1 || {
  echo "curl is required." >&2
  exit 1
}
command -v bash >/dev/null 2>&1 || {
  echo "bash is required." >&2
  exit 1
}
command -v sha256sum >/dev/null 2>&1 || {
  echo "sha256sum is required." >&2
  exit 1
}
command -v docker >/dev/null 2>&1 || {
  echo "Docker Engine is required. Install Docker, then run this command again." >&2
  exit 1
}
docker compose version >/dev/null 2>&1 || {
  echo "Docker Compose v2 is required." >&2
  exit 1
}
[ ! -e "$INSTALL_DIR/.env" ] || {
  echo "Vueio is already installed in $INSTALL_DIR. Use 'vueioctl update' instead." >&2
  exit 1
}

mkdir -p "$BIN_DIR"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT INT TERM
curl -fsSL "$ASSET_BASE_URL/SHA256SUMS" -o "$STAGE/SHA256SUMS"
curl -fsSL "$ASSET_BASE_URL/vueioctl" -o "$STAGE/vueioctl"
curl -fsSL "$ASSET_BASE_URL/compose.release.yml" -o "$STAGE/compose.release.yml"
curl -fsSL "$ASSET_BASE_URL/LICENSE.md" -o "$STAGE/LICENSE.md"
grep -Eq '[[:space:]]vueioctl$' "$STAGE/SHA256SUMS" || {
  echo "Release checksums do not include vueioctl." >&2
  exit 1
}
grep -Eq '[[:space:]]compose\.release\.yml$' "$STAGE/SHA256SUMS" || {
  echo "Release checksums do not include compose.release.yml." >&2
  exit 1
}
grep -Eq '[[:space:]]LICENSE\.md$' "$STAGE/SHA256SUMS" || {
  echo "Release checksums do not include LICENSE.md." >&2
  exit 1
}
(cd "$STAGE" && sha256sum --ignore-missing -c SHA256SUMS)
bash -n "$STAGE/vueioctl"

if [ "${VUEIO_NONINTERACTIVE:-0}" = 1 ]; then
  VUEIO_HOME="$INSTALL_DIR" \
  VUEIO_RELEASE_COMPOSE="$STAGE/compose.release.yml" \
  VUEIO_RELEASE_LICENSE="$STAGE/LICENSE.md" \
  VUEIO_RELEASE_ROOT_URL="$RELEASE_ROOT_URL" \
  bash "$STAGE/vueioctl" install
else
  [ -r /dev/tty ] || {
    echo "Interactive setup needs a terminal. Set VUEIO_NONINTERACTIVE=1 and provide VUEIO_INITIAL_STORAGE_PATH for automation." >&2
    exit 1
  }
  VUEIO_HOME="$INSTALL_DIR" \
  VUEIO_RELEASE_COMPOSE="$STAGE/compose.release.yml" \
  VUEIO_RELEASE_LICENSE="$STAGE/LICENSE.md" \
  VUEIO_RELEASE_ROOT_URL="$RELEASE_ROOT_URL" \
  bash "$STAGE/vueioctl" install </dev/tty
fi

install -m 0755 "$STAGE/vueioctl" "$BIN_DIR/vueioctl"
