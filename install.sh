#!/usr/bin/env sh
set -eu

# This bootstrap installs the host controller and update service. The web app
# runs in Docker Compose without access to the Docker socket.
VERSION=${VUEIO_VERSION:-}
PLATFORM=$(uname -s 2>/dev/null || true)
if [ "$PLATFORM" = Darwin ]; then
  INSTALL_DIR=${VUEIO_HOME:-"$HOME/Library/Application Support/Vueio"}
  BIN_DIR=${VUEIO_BIN_DIR:-"$HOME/.local/bin"}
else
  INSTALL_DIR=${VUEIO_HOME:-/opt/vueio}
  BIN_DIR=${VUEIO_BIN_DIR:-/usr/local/bin}
fi
RELEASE_ROOT_URL=${VUEIO_RELEASE_ROOT_URL:-https://github.com/rfxmedia/vueio/releases}
ASSET_BASE_URL="$RELEASE_ROOT_URL/download/$VERSION"

if [ -t 1 ] && [ "${TERM:-dumb}" != dumb ] && [ "${VUEIO_PLAIN:-0}" != 1 ] && [ -z "${NO_COLOR:-}" ]; then
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
  printf '\n  %s%svueio%s   %sSETUP · 1 / 5%s\n' "$BOLD" "$MINT" "$RESET" "$MUTED" "$RESET"
  printf '  %s--------------------------------------------%s\n' "$MUTED" "$RESET"
  printf '\n  %sPrepare this computer%s\n\n' "$BOLD" "$RESET"
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
  curl -fsSL --connect-timeout 10 --max-time 180 "$ASSET_BASE_URL/$label" -o "$destination" ||
    fail "Could not download $label. Check the server's internet connection and try again."
}

mac_tools_path() {
  for tools_prefix in /opt/homebrew /usr/local; do
    if [ -x "$tools_prefix/bin/brew" ]; then
      PATH="$tools_prefix/opt/coreutils/libexec/gnubin:$tools_prefix/opt/findutils/libexec/gnubin:$tools_prefix/bin:$PATH"
      export PATH
      break
    fi
  done
}

heading
step "Checking this computer"

printf '%s\n' "$VERSION" |
  grep -Eq '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-alpha\.(0|[1-9][0-9]*)(\.dev\.(0|[1-9][0-9]*))?$' || {
  fail "This installer does not contain a valid Vueio release version."
}

case "$PLATFORM" in
  Linux|Darwin) ;;
  *) fail "This installer supports Linux and the Mac preview. Windows installation is not available yet." ;;
esac
if [ "$PLATFORM" = Darwin ] && [ "$(uname -m)" != arm64 ]; then
  fail "The Mac preview needs Apple Silicon. Intel Macs are not supported."
fi
case "$(uname -m 2>/dev/null || true)" in
  x86_64|amd64|aarch64|arm64) ;;
  *) fail "This processor is not supported. Vueio needs 64-bit Intel/AMD or ARM." ;;
esac

command -v curl >/dev/null 2>&1 || fail "curl is required. Install curl, then run the Vueio command again."
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT INT TERM

if [ "$PLATFORM" = Linux ] && [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 || fail "Run this installer as the server administrator. sudo is not installed."
  step "Linux needs administrator approval — enter this computer's password if asked"
  # A piped installer has no script filename. Fetch this exact release again,
  # rather than a moving latest version, before continuing with sudo.
  download install.sh "$STAGE/install.sh"
  vueio_env_names=$(env | sed -n 's/^\(VUEIO_[A-Z0-9_]*\)=.*/\1/p' | paste -sd, -)
  if sudo "--preserve-env=${vueio_env_names:-VUEIO_VERSION}" sh "$STAGE/install.sh"; then exit 0; else exit $?; fi
fi
if [ "$PLATFORM" = Darwin ]; then
  [ "$(id -u)" -ne 0 ] || fail "On Mac, run this install command without sudo. Vueio runs as your Mac account."
  warn "Apple Silicon preview · Use test data."
  mac_tools_path
  if ! command -v brew >/dev/null 2>&1; then
    printf '\nVueio uses Homebrew to install its Mac host tools.\n'
    printf 'Its official installer may also install Apple Command Line Tools.\n'
    printf 'Your Mac may ask for its password. Characters stay hidden while you type.\n'
    printf 'Install Homebrew and continue? [y/N] '
    [ "${VUEIO_NONINTERACTIVE:-0}" != 1 ] && read -r install_brew </dev/tty || install_brew=n
    case "$install_brew" in
      y|Y)
        step "Downloading the official Homebrew installer"
        curl -fsSL --proto '=https' --connect-timeout 10 --max-time 60 \
          https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$STAGE/homebrew.sh" ||
          fail "Homebrew could not be downloaded. Check your internet connection and try again."
        /bin/bash "$STAGE/homebrew.sh" </dev/tty ||
          fail "Homebrew setup did not finish. Check its message above, then run this same Vueio command again."
        mac_tools_path
        command -v brew >/dev/null 2>&1 || fail "Homebrew was not found after setup. See https://brew.sh for help."
        ;;
      *) fail "Homebrew is needed for the Mac installer. No Vueio data was created." ;;
    esac
  fi
  # Installing Vueio's tools must not trigger cleanup of unrelated packages.
  export HOMEBREW_NO_INSTALL_CLEANUP=1
  if ! brew list --versions bash coreutils findutils python ffmpeg >/dev/null 2>&1; then
    printf '\nVueio needs host tools and FFmpeg for optional GPU processing.\n'
    printf 'Install these with Homebrew? [y/N] '
    [ "${VUEIO_NONINTERACTIVE:-0}" != 1 ] && read -r install_tools </dev/tty || install_tools=n
    case "$install_tools" in
      y|Y) brew install bash coreutils findutils python ffmpeg || fail "The host tools could not be installed. Check Homebrew's message above, then try again. No Vueio data was created." ;;
      *) fail "Run 'brew install bash coreutils findutils python ffmpeg', then try again. Nothing in Vueio was changed." ;;
    esac
  fi
  if [ ! -d /Applications/Docker.app ]; then
    printf '\nVueio uses Docker Desktop to run the same app as Linux.\n'
    printf 'Docker Desktop is subject to Docker\047s licensing terms.\n'
    printf 'Install Docker Desktop with Homebrew? [y/N] '
    [ "${VUEIO_NONINTERACTIVE:-0}" != 1 ] && read -r install_docker </dev/tty || install_docker=n
    case "$install_docker" in
      y|Y) brew install --cask docker-desktop || fail "Docker Desktop could not be installed. Check Homebrew's message above, then try again. No Vueio data was created." ;;
      *) fail "Install Docker Desktop from https://www.docker.com/products/docker-desktop/, then try again." ;;
    esac
  fi
  PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
  export PATH
  if ! docker info >/dev/null 2>&1; then
    open -a Docker
    step "Finish Docker Desktop's first-run prompts. Waiting for Docker to start…"
    remaining=120
    until docker info >/dev/null 2>&1; do
      remaining=$((remaining - 1))
      [ "$remaining" -gt 0 ] || fail "Docker is not ready yet. Finish its setup, then run this command again."
      sleep 2
    done
  fi
  case "$(docker context inspect --format '{{.Endpoints.docker.Host}}')" in
    unix://*) ;;
    *) fail "Use Docker Desktop on this Mac, not a remote Docker connection." ;;
  esac
  [ "$(docker info --format '{{.OperatingSystem}}')" = 'Docker Desktop' ] || fail "The Mac preview requires local Docker Desktop."
fi
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
  fail "Vueio is already installed here. Open Settings → Updates in Vueio to update it. Your installation was not changed."
}
ok "$PLATFORM and Docker are ready"

available_kb=$(df -Pk / 2>/dev/null | awk 'NR == 2 { print $4 }')
if [ -n "$available_kb" ]; then
  available_gb=$((available_kb / 1024 / 1024))
  if [ "$available_gb" -lt 40 ]; then
    warn "Only ${available_gb} GiB is free on the system disk. Vueio recommends at least 40 GiB before adding project media."
  else
    ok "${available_gb} GiB is available on the system disk"
  fi
fi

step "Downloading Vueio $VERSION"
download SHA256SUMS "$STAGE/SHA256SUMS"
download vueioctl "$STAGE/vueioctl"
download vueio-updater.py "$STAGE/vueio-updater.py"
download vueio-media.py "$STAGE/vueio-media.py"
download compose.release.yml "$STAGE/compose.release.yml"
download LICENSE.md "$STAGE/LICENSE.md"
grep -Eq '[[:space:]]vueioctl$' "$STAGE/SHA256SUMS" || {
  fail "The release checksum list is incomplete. Nothing was installed."
}
grep -Eq '[[:space:]]vueio-updater\.py$' "$STAGE/SHA256SUMS" || {
  fail "The release checksum list is incomplete. Nothing was installed."
}
grep -Eq '[[:space:]]vueio-media\.py$' "$STAGE/SHA256SUMS" || fail "The media helper checksum is missing. Nothing was installed."
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
python3 -c 'import ast, sys; ast.parse(open(sys.argv[1], encoding="utf-8").read())' "$STAGE/vueio-media.py" || fail "The media helper is invalid. Nothing was installed."
ok "Release files are verified"

if [ "${VUEIO_NONINTERACTIVE:-0}" = 1 ]; then
  VUEIO_DEFER_SETUP_INFO=1 \
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
  VUEIO_DEFER_SETUP_INFO=1 \
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
if [ "$PLATFORM" = Darwin ] || { command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; }; then
  step "Enable updates and drive management"
  if VUEIO_HOME="$INSTALL_DIR" "$BIN_DIR/vueioctl" updater enable >"$INSTALL_DIR/logs/install-updater.log" 2>&1; then
    ok "Updates and drive management are ready"
  else
    warn "Vueio is installed, but drive management and updates need attention."
    printf 'Details: %s/logs/install-updater.log\n' "$INSTALL_DIR" >&2
    if [ "$PLATFORM" = Darwin ]; then
      printf 'Retry with: VUEIO_HOME="%s" "%s/vueioctl" updater enable\n' "$INSTALL_DIR" "$BIN_DIR" >&2
    else
      printf 'Retry with: sudo env VUEIO_HOME="%s" "%s/vueioctl" updater enable\n' "$INSTALL_DIR" "$BIN_DIR" >&2
    fi
  fi
else
  warn "To enable updates from Settings, configure your host service manager to run 'vueioctl updater serve' as root. See the self-hosting guide."
fi

if [ "$PLATFORM" = Darwin ]; then
  # Keep the updatable controller user-owned. The optional global link merely
  # makes the same command discoverable in new terminals and sudo's PATH.
  if [ "${VUEIO_NONINTERACTIVE:-0}" != 1 ] && [ -t 1 ] &&
     [ ! -e /usr/local/bin/vueioctl ] && [ ! -L /usr/local/bin/vueioctl ]; then
    step "Making vueioctl available in your terminal — your Mac may ask for its password"
    if ! { sudo mkdir -p /usr/local/bin && sudo ln -s "$BIN_DIR/vueioctl" /usr/local/bin/vueioctl; }; then
      warn "The short command could not be installed. Use the full command below; Vueio is still installed."
    fi
  fi
fi

VUEIO_HOME="$INSTALL_DIR" "$BIN_DIR/vueioctl" setup-info
if [ "$PLATFORM" = Darwin ]; then
  printf '\nOpen the terminal menu with: VUEIO_HOME="%s" "%s/vueioctl"\n' "$INSTALL_DIR" "$BIN_DIR"
  open "$(sed -n 's/^VUEIO_CORS_ALLOW_ORIGINS=//p' "$INSTALL_DIR/.env")"
fi
