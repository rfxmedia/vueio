# Self-hosting Vueio Alpha

Vueio Alpha is a single-server Linux application distributed with Docker
Compose. Docker runs the website, media engine, and PostgreSQL database
together without installing their language runtimes directly on the host.

## Alpha support boundary

The first public alpha supports:

- one x86-64 or ARM64 Linux server;
- Docker Engine with Docker Compose v2;
- local disks and NAS folders that are already mounted on Linux;
- one PostgreSQL database managed by the included Compose project;
- CPU transcoding; and
- a user-managed HTTPS reverse proxy, VPN, or tunnel for internet access.

Windows, Kubernetes, clusters, high availability, Podman, and a built-in
internet tunnel are not supported by the first alpha. Hardware-accelerator
device mappings are also outside the supported release Compose file for this
alpha; advanced private overrides are not portable release configuration.
Source project media remains the server owner's responsibility to back up.

## Voice note transcription

Vueio transcribes English voice notes inside the media engine with the bundled
Moonshine Small model. Audio is not sent to a transcription service, and one
voice note is processed at a time to keep server load predictable. Set
`VUEIO_VOICE_TRANSCRIPTION_ENABLED=false` before starting Vueio to disable it.

## Before you install

The practical starting point for the alpha is:

- 4 CPU cores;
- 8 GiB of memory;
- 40 GiB of free local space for Vueio, its database, and working data as a
  starting point; and
- separate capacity for source media.

Larger or high-resolution media libraries may need considerably more CPU,
memory, and local space for generated previews and transcodes. The installer
checks Docker Engine and Docker Compose v2 before changing the server. If
either is missing, it stops with a direct explanation and can be run again
after Docker is installed. You can confirm both yourself with:

```bash
docker --version
docker compose version
```

## Install

Each tagged GitHub release contains `install.sh`, `vueioctl`, and
`compose.release.yml`. To install from downloaded release assets:

```bash
sudo sh ./install.sh
```

The one-line form runs the same installer:

```bash
curl -fsSL https://github.com/rfxmedia/vueio/releases/latest/download/install.sh \
  | sudo sh
```

The installer:

1. verifies Linux, Docker, Docker Compose, disk space, and the web port;
2. offers a dedicated local project folder or accepts an existing mounted
   folder;
3. creates random database, session, and first-setup secrets;
4. gives only the selected folder to the media engine;
5. starts the versioned Vueio containers and runs safety checks; and
6. prints the local URL and one-time setup token.

It never mounts the Docker socket, the host root, or an unselected drive.

By default Vueio listens only on `127.0.0.1`. To complete setup from another
computer, use an SSH tunnel:

```bash
ssh -L 9000:127.0.0.1:9000 user@vueio-server
```

Then open `http://127.0.0.1:9000`. Advanced users may deliberately set a LAN
bind address and matching `VUEIO_LOCAL_URL` during installation.

If the terminal output is no longer visible, retrieve the one-time code with:

```bash
sudo vueioctl setup-token
```

## Storage

Docker cannot safely grant itself access to arbitrary host drives after it
starts. Authorize storage from the host:

```bash
sudo vueioctl storage add "Fast projects" /mnt/nvme/projects rw
sudo vueioctl storage add "Studio archive" /mnt/archive/projects ro
sudo vueioctl storage list
```

Vueio sees stable internal paths such as `/storage/root-1`; users see the
labels. Host paths remain installation-specific and never enter the Vueio
application database.

The explicit `install` and `storage add` commands create a small read-only
`.vueio-storage-id` marker when the selected folder does not already have one.
If a valid marker already exists, that explicit command records it instead.
Ordinary startup never creates or silently adopts a marker. The marker lets
`vueioctl doctor` distinguish the intended disk from an empty mount point or a
different disk mounted at the same host path. Do not delete, overwrite, or copy
the marker to another root. Startup and `doctor` fail closed when the marker is
absent, invalid, or different from the value originally registered.

For NAS storage, mount the share in Linux before starting Vueio. Stop Vueio
before intentionally disconnecting it:

```bash
sudo vueioctl stop
# disconnect or remount the NAS here
sudo vueioctl start
sudo vueioctl doctor
```

If the NAS comes back at the expected path with its original marker, Vueio can
use it again. If the mount is absent or its identity is different, `doctor`
fails and Vueio refuses to treat that location as the configured project
storage. This protects against writing into an empty local mount point.

Removing a root does not delete files, but projects using it will be offline:

```bash
sudo vueioctl storage remove "Studio archive"
```

The engine runs as `VUEIO_PUID:VUEIO_PGID` and applies `VUEIO_UMASK`.
The installer defaults these IDs to the account that invoked `sudo`. Set them
explicitly when project folders belong to a dedicated NAS account. Vueio does
not recursively change permissions on project storage.

## Internet exposure

Local HTTP mode exists only to complete first-run setup. Never port-forward
the Vueio HTTP port directly to the internet.

After configuring an HTTPS reverse proxy, Cloudflare Tunnel, or VPN hostname:

```bash
sudo vueioctl exposure set https://vue.example.com
```

This enables secure cookies, uses the exact public origin for browser access,
and disables local bootstrap mode. Vueio does not create or control the
external tunnel.

For a Cloudflare Tunnel, explicitly trust Cloudflare's client-address header:

```bash
sudo vueioctl exposure set https://vue.example.com --cloudflare
```

For the simplest supported arrangement, run `cloudflared` as a host service
and point the tunnel at:

```text
http://127.0.0.1:9000
```

If `cloudflared` runs in a container, `127.0.0.1` refers to that container, not
the host. Container networking for an external tunnel is an advanced
operator-managed configuration. Cloudflare account and upload limits still
apply.

For a small host-installed Caddy reverse proxy, a minimal Caddyfile is:

```caddyfile
vue.example.com {
    reverse_proxy 127.0.0.1:9000
}
```

Point DNS at the server, let Caddy obtain HTTPS, then run `exposure set` with
the same public origin. Keep the upstream on loopback. Caddy's reverse proxy
passes byte-range requests needed for media seeking; avoid adding response
buffering or range-stripping middleware.

Return to loopback-only local testing with:

```bash
sudo vueioctl exposure local
```

`exposure set` applies the change and runs `doctor`. `exposure local` applies
loopback-only mode; run `sudo vueioctl doctor` afterwards if you want a full
health check. If a new proxy is not ready, the recovery command printed by
Vueio returns it to loopback-only mode.

The web server sends a conservative browser-security baseline: MIME sniffing is
disabled, referrers are limited, sensitive browser permissions are disabled,
pages may only be framed by the same origin, and a Content Security Policy
limits scripts, connections, media, workers, and embedded resources to the
Vueio origin and the browser-managed data or blob URLs the media tools require.

## Operations

```bash
sudo vueioctl start
sudo vueioctl stop
sudo vueioctl restart
sudo vueioctl status
sudo vueioctl version
sudo vueioctl logs
sudo vueioctl doctor
sudo vueioctl doctor --fix
```

`version` prints the selected release and both application image names.
`doctor` also prints the release, update channel, and configured browser
origin. It checks the Compose configuration, versioned image pins, update
state, backup and log locations, free space, application data, every storage
mount's identity and permissions, PostgreSQL, UI, API, and exposure mode.
`doctor --fix` performs only safe repairs: it clears known stale staging
folders when no update is active, reconciles image pins to the installed
version, and restarts unhealthy services. It never changes project storage or
restores a backup. Local HTTP produces a warning even when every required
check passes.

## Backups and restores

Create an application-state backup:

```bash
sudo vueioctl backup
sudo vueioctl backups
```

The archive contains:

- a consistent PostgreSQL dump;
- accounts and Vueio-managed application data;
- a reference copy of configuration and authorized-storage definitions.

It deliberately does **not** copy source footage or other files in authorized
storage roots. It also excludes reproducible thumbnails, transcodes, and
temporary package files so a backup cannot silently grow to media-library
size. Back source storage up with the NAS or storage system. Every regular file
inside the backup payload is covered by an internal SHA-256 manifest, the
finished archive has an adjacent SHA-256 checksum, and the PostgreSQL dump is
validated before the backup is accepted.

Backups contain account and installation secrets. Keep them private; the
controller writes archives and checksums with owner-only permissions.

Restore intentionally keeps the current host's paths, storage mounts, database
password, and session secret. It restores the database and application data;
the archived configuration is present only for manual recovery or comparison.
This prevents a backup moved to another server from silently mounting old host
paths or breaking the destination database password.

The engine pauses briefly so account files and the database cannot change
during the backup. Restore is intentionally guarded:

```bash
sudo vueioctl restore /opt/vueio/backups/vueio-20260729T120000Z.tar.gz
```

Restore requires typing `RESTORE`. Before changing the current installation,
it validates the archive and checks that enough free space exists beside the
application data directory to stage the restored copy. It then:

1. stages restored application data without replacing the current copy;
2. stops the engine and creates a fresh safety backup;
3. switches to the staged application data;
4. restores the database in one transaction; and
5. starts Vueio and requires `doctor` to pass.

If a later step fails, Vueio attempts to restore the safety database and old
application data. If automatic recovery cannot complete, Vueio stays stopped
and prints the safety-backup path instead of continuing with mixed state. A
successful restore keeps the replaced data directory temporarily and prints
the exact cleanup command. Run that command only after verifying accounts,
projects, and playback.

Test both backup and restore on a disposable installation before relying on
them for production.

Vueio keeps the five newest controller-managed backups by default and always
protects the newest pre-update backup. Set `VUEIO_BACKUP_KEEP` when invoking
the controller to choose a different positive retention count.

## Upload safety limits

Vueio limits resumable chunks to 8 MiB, reserves 20 GiB of free space by
default, and refreshes an upload session's one-day expiration while it is in
use. A normal upload accepts at most 10,000 files; a public file request accepts
at most 2,000. Each file-request link has a configurable 1 TiB allocation
ceiling, 25 active sessions overall, and five active sessions per client.
Creating public upload sessions is limited to 20 per hour, public chunk
requests to 240 per minute, public comments to 60 per hour, public comment
batch reads to 240 per minute, and share-password attempts to 30 per minute.
Comment attachments are limited to 256 MiB per file and 500 MiB per comment.

These are defensive alpha defaults, not storage quotas or a substitute for a
reverse proxy's abuse controls. They can be changed through the corresponding
`VUEIO_*` values in `/opt/vueio/.env`.

## Updates

Updates are explicit during the alpha. The Updates screen gives the owner the
exact command for the newest release in the selected channel:

```bash
sudo vueioctl update v0.1.1-alpha.1
```

The command checks the current installation, available space, Docker, release
metadata, and target images before changing anything. It downloads and
checksum-verifies the release files, pulls the versioned images before the
short restart window, creates a validated pre-update backup, starts the new
release, and requires `doctor` to pass. Progress is written to
`/opt/vueio/logs/update-<timestamp>.log`; the newest ten update logs are kept.

If an update fails after the safety backup is complete, Vueio automatically
restores the prior application version and data. An interrupted command is
also detected on the next run and recovered before the update is retried.
Running the same update command against an already healthy version is a safe
no-op.

Administrators can see the installed version and check for a newer release in
**Settings → Updates**. When a release is available, Vueio also shows a small
update indicator at the bottom of the sidebar. The web app provides the exact
host command to run; it never receives Docker or host-control access.

Stable is the default channel. Stable releases use immutable
`vX.Y.Z-alpha.N` tags and are not GitHub prereleases. Nightly releases are test
builds, use `vX.Y.Z-alpha.N.dev.M` tags, and are marked prerelease. Select a
channel with:

```bash
sudo vueioctl channel stable
sudo vueioctl channel nightly
```

Nightly sees both stable and nightly releases; stable sees stable releases
only. Switching from nightly to stable does not downgrade the running app. It
waits for a stable release newer than the installed nightly because database
migrations are one-way.

The immutable release tag is carried into the engine, UI images, installer,
and update screen, so version numbers do not need to be edited in several
places.

To undo an update that completed successfully, use:

```bash
sudo vueioctl rollback
```

Rollback is not an in-place downgrade. It restores the newest pre-update
backup and repins the matching application images. The command prints the
version and backup time and requires typing `RESTORE`. **Anything created or
changed in Vueio after that backup is discarded.** Source project files and
media are not changed. Database migrations are one-way, so never run an older
image against a newer database without restoring its matching backup.

Every release must be tested in two paths:

1. a completely fresh installation; and
2. an upgrade restored from a copy of an existing Vueio installation.

Every installation should use the published images and release Compose model,
with only its environment and explicitly authorized storage paths differing.
