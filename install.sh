#!/usr/bin/env sh
set -eu

# This bootstrap installs the host controller and update service. The web app
# runs in Docker Compose without access to the Docker socket.
VERSION=${VUEIO_VERSION:-}
INSTALL_DIR=${VUEIO_HOME:-/opt/vueio}
BIN_DIR=${VUEIO_BIN_DIR:-/usr/local/bin}
RELEASE_ROOT_URL=${VUEIO_RELEASE_ROOT_URL:-https://github.com/rfxmedia/vueio/releases}
ASSET_BASE_URL="$RELEASE_ROOT_URL/download/$VERSION"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  RESET=$(printf '\033[0m')
  BOLD=$(printf '\033[1m')
  MUTED=$(printf '\033[2m')
  GREEN=$(printf '\033[32m')
  MINT=$(printf '\033[38;5;121m')
  YELLOW=$(printf '\033[33m')
else
  RESET=
  BOLD=
  MUTED=
  GREEN=
  MINT=
  YELLOW=
fi

heading() {
  printf '\n%s%sVueio%s\n' "$BOLD" "$MINT" "$RESET"
  printf '%sSelf-hosted media review%s\n\n' "$MUTED" "$RESET"
}

step() {
  printf '%s→%s %s\n' "$MINT" "$RESET" "$1"
}

ok() {
  printf '%s✓%s %s\n' "$GREEN" "$RESET" "$1"
}

warn() {
  printf '%s!%s %s\n' "$YELLOW" "$RESET" "$1" >&2
}

fail() {
  printf '\n%sInstallation stopped:%s %s\n' "$BOLD" "$RESET" "$1" >&2
  exit 1
}

download() {
  label=$1
  destination=$2
  curl -fsSL "$ASSET_BASE_URL/$label" -o "$destination" ||
    fail "Could not download $label. Check the server's internet connection and try again."
}

heading
step "Checking this Linux server"

printf '%s\n' "$VERSION" |
  grep -Eq '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-alpha\.(0|[1-9][0-9]*)(\.dev\.(0|[1-9][0-9]*))?$' || {
  fail "This installer does not contain a valid Vueio release version."
}

[ "$(uname -s 2>/dev/null || true)" = Linux ] ||
  fail "Vueio currently supports Linux servers only."
case "$(uname -m 2>/dev/null || true)" in
  x86_64|amd64|aarch64|arm64) ;;
  *) fail "This processor is not supported. Vueio supports 64-bit Intel/AMD and ARM Linux." ;;
esac

if [ "$(id -u)" -ne 0 ]; then
  fail "Run the website's install command with sudo."
fi
command -v curl >/dev/null 2>&1 || {
  fail "curl is required. Install curl, then run the Vueio command again."
}
command -v bash >/dev/null 2>&1 || {
  fail "bash is required. Install bash, then run the Vueio command again."
}
command -v python3 >/dev/null 2>&1 || {
  fail "Python 3.9 or newer is required for host management. Install python3, then try again."
}
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' ||
  fail "Python 3.9 or newer is required for host management."
command -v sha256sum >/dev/null 2>&1 || {
  fail "sha256sum is required. Install your distribution's coreutils package, then try again."
}
command -v docker >/dev/null 2>&1 || {
  fail "Docker is not installed. Follow https://docs.docker.com/engine/install/ and then run the Vueio command again."
}
docker compose version >/dev/null 2>&1 || {
  fail "Docker Compose v2 is missing. Install the Docker Compose plugin, then run the Vueio command again."
}
docker info >/dev/null 2>&1 ||
  fail "Docker is installed but is not running. Start Docker and then run the Vueio command again."
[ ! -e "$INSTALL_DIR/.env" ] || {
  fail "Vueio is already installed. Use 'sudo vueioctl update <version>' instead."
}
ok "Linux and Docker are ready"

available_kb=$(df -Pk / 2>/dev/null | awk 'NR == 2 { print $4 }')
if [ -n "$available_kb" ]; then
  available_gb=$((available_kb / 1024 / 1024))
  if [ "$available_gb" -lt 40 ]; then
    warn "Only ${available_gb} GiB is free on the system disk. Vueio recommends at least 40 GiB before adding project media."
  else
    ok "${available_gb} GiB is available on the system disk"
  fi
fi

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT INT TERM
step "Downloading Vueio $VERSION"
download SHA256SUMS "$STAGE/SHA256SUMS"
download vueioctl "$STAGE/vueioctl"
download vueio-updater.py "$STAGE/vueio-updater.py"
download compose.release.yml "$STAGE/compose.release.yml"
download LICENSE.md "$STAGE/LICENSE.md"
grep -Eq '[[:space:]]vueioctl$' "$STAGE/SHA256SUMS" || {
  fail "The release checksum list is incomplete. Nothing was installed."
}
grep -Eq '[[:space:]]vueio-updater\.py$' "$STAGE/SHA256SUMS" || {
  fail "The release checksum list is incomplete. Nothing was installed."
}
grep -Eq '[[:space:]]compose\.release\.yml$' "$STAGE/SHA256SUMS" || {
  fail "The release checksum list is incomplete. Nothing was installed."
}
grep -Eq '[[:space:]]LICENSE\.md$' "$STAGE/SHA256SUMS" || {
  fail "The release checksum list is incomplete. Nothing was installed."
}
(cd "$STAGE" && sha256sum --ignore-missing --quiet -c SHA256SUMS) ||
  fail "Release verification failed. Nothing was installed."
bash -n "$STAGE/vueioctl" ||
  fail "The downloaded management command is invalid. Nothing was installed."
python3 -c 'import ast, sys; ast.parse(open(sys.argv[1], encoding="utf-8").read())' "$STAGE/vueio-updater.py" ||
  fail "The downloaded update service is invalid. Nothing was installed."
ok "Release files are verified"

if [ "${VUEIO_NONINTERACTIVE:-0}" = 1 ]; then
  VUEIO_HOME="$INSTALL_DIR" \
  VUEIO_VERSION="$VERSION" \
  VUEIO_RELEASE_COMPOSE="$STAGE/compose.release.yml" \
  VUEIO_RELEASE_LICENSE="$STAGE/LICENSE.md" \
  VUEIO_RELEASE_UPDATER="$STAGE/vueio-updater.py" \
  VUEIO_RELEASE_ROOT_URL="$RELEASE_ROOT_URL" \
  bash "$STAGE/vueioctl" install </dev/null
else
  [ -r /dev/tty ] || {
    echo "Interactive setup needs a terminal. Set VUEIO_NONINTERACTIVE=1 and provide VUEIO_INITIAL_STORAGE_PATH for automation." >&2
    exit 1
  }
  VUEIO_HOME="$INSTALL_DIR" \
  VUEIO_VERSION="$VERSION" \
  VUEIO_RELEASE_COMPOSE="$STAGE/compose.release.yml" \
  VUEIO_RELEASE_LICENSE="$STAGE/LICENSE.md" \
  VUEIO_RELEASE_UPDATER="$STAGE/vueio-updater.py" \
  VUEIO_RELEASE_ROOT_URL="$RELEASE_ROOT_URL" \
  bash "$STAGE/vueioctl" install </dev/tty
fi

[ -f "$INSTALL_DIR/.installed" ] || {
  step "Setup was cancelled. Nothing was installed."
  exit 0
}
mkdir -p "$BIN_DIR"
install -m 0755 "$STAGE/vueioctl" "$BIN_DIR/vueioctl"
ok "Management command installed at $BIN_DIR/vueioctl"
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  step "Enabling updates from Settings"
  VUEIO_HOME="$INSTALL_DIR" "$BIN_DIR/vueioctl" updater enable ||
    warn "Vueio is installed. Enable updates later with 'sudo vueioctl updater enable'."
else
  warn "To enable updates from Settings, configure your host service manager to run 'vueioctl updater serve' as root. See the self-hosting guide."
fi
