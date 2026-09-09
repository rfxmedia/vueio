# Self-hosting Vueio Alpha

Vueio Alpha is a single-server Linux application distributed with Docker
Compose. Docker runs the website, media engine, and PostgreSQL database
together without installing their language runtimes directly on the host.

## Alpha support boundary

The first public alpha supports:

- one x86-64 or ARM64 Linux server;
- Docker Engine with Docker Compose v2;
- Python 3.9 or newer on the host for the management command and update service;
- local disks, USB drives, and network storage that are already mounted on Linux;
- one PostgreSQL database managed by the included Compose project;
- CPU transcoding; and
- a user-managed HTTPS reverse proxy, VPN, or tunnel for internet access.

An unreleased Mac installer preview is described below. It is not yet a verified
production platform. Windows launchers, Kubernetes, clusters, high availability, Podman, and a built-in
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

Each tagged GitHub release contains `install.sh`, `vueioctl`,
`vueio-updater.py`, and `compose.release.yml`. To install from downloaded release assets:

```bash
sh ./install.sh
```

The one-line form runs the same installer:

```bash
curl -fsSL https://github.com/rfxmedia/vueio/releases/latest/download/install.sh \
  | sh
```

The installer asks for administrator approval on Linux. On Mac, run it without
`sudo`; it runs as your Mac account and guides you through missing prerequisites.
The Mac path is still an unreleased preview; see its verification limits below.

The installer:

1. verifies Linux, Docker, Docker Compose, disk space, and the web port;
2. asks for a private Vue data folder, then separately offers media storage
   on this computer, an eligible connected drive, or an existing folder;
3. creates random database, session, and first-setup secrets;
4. gives only the selected folder to the media engine;
5. starts the versioned Vueio containers and runs safety checks; and
6. enables host management where supported, then prints the local URL,
   one-time setup code, and browser instructions.

The update channel follows the downloaded release, so setup does not ask you
to choose a channel. You can change it later in **Settings → Updates**.
For storage, press Enter to accept the dedicated local folder. Invalid drive
numbers and missing folder paths can be corrected without restarting setup.
Review the storage and web address before confirming the installation.

### Your data folder

New installations ask where to keep **Vue data**. Enter an absolute directory
on the internal drive or a suitable external drive. Use a new or empty folder;
Vueio does not overwrite existing files or format a drive. The default is
`/opt/vueio/state` on Linux. Set `VUEIO_STATE_PATH` for unattended installation.

The selected directory contains:

- `postgres`: the live database (accounts, comments, members, projects and history);
- `app`: app files, attachments and generated previews; and
- `backups`: consistent database backup archives.

Media can be on a different drive and must not overlap the data folder.
Private installation configuration, including credentials and storage mappings,
remains in `VUEIO_HOME`. Protect that directory too. **Settings → Storage** and
`vueioctl data` show the locations; neither moves an existing database.

The database needs a writable local filesystem with normal permissions and
durable writes: ext2/3/4, XFS, Btrfs or ZFS on Linux; APFS or HFS on Mac.
Network shares and FAT/exFAT are not accepted for the database. They can still
hold media. An external data drive must remain connected while Vueio runs.
Stop Vueio before ejecting it. Startup checks its identity and refuses a
missing or replaced drive instead of creating an empty database.

**Existing installations keep their current Docker database volume.** Updating
does not migrate it, rename it or adopt a new data folder. Use `vueioctl data`
to see this distinction. An incomplete new installation retains its data and
configuration for recovery; do not rerun setup over it or remove it blindly.

Use `vueioctl backup` for a consistent database backup and copy the archive and
checksum to another drive. Also back up app files, source media and private
configuration separately. Do not copy a running PostgreSQL data directory as
if it were an ordinary document. Previews can be rebuilt; missing source files
cannot be recovered from a database backup.

On hosts running systemd, the installer also enables the host service for
**Settings → Updates** and **Settings → Storage**. The engine receives only the service's local control
socket. It never mounts the Docker socket, the host root, or an unselected drive.

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

Use `sudo vueioctl setup-info` to show both the browser address and code again.
With a custom installation directory, prefix either command with
`sudo env VUEIO_HOME=/path/to/installation` in place of `sudo`.

## Storage

After creating the first owner account, Vueio opens **Settings → Storage**.
The initial media location is already connected. Choose **Add storage** to
select an additional mounted local drive and its access mode. The picker
offers OS-managed mount locations, excludes system folders and nested mounts,
and does not follow user-controlled mount aliases. Plug in and
unlock the drive on the computer running Vueio, then choose **Check again**.
Devices attached only to the computer viewing the website do not appear.

Only an administrator's browser session can connect drives. Agent API keys,
members, and shared-link visitors cannot grant host access. The host helper
enumerates mounted local filesystems without scanning their media, and checks
the selected device again before registration. It does not offer the operating
system root or Vueio's private application directory. Use a dedicated media
folder for storage on the operating system's disk. The installer provides one
by default.

Adding a drive does not move projects or publish all its files. Choose a
location when creating a project; sharing still uses Vueio's existing access
controls. Connecting or reconnecting storage briefly restarts the media engine
and website, not PostgreSQL. Finish active uploads first. If a request loses
its connection during the restart, check the storage list before retrying.

The host service is required for the picker. Custom Compose installations keep
their existing mappings; Vueio does not rewrite them. For existing folders,
mounted network shares, or installations without the service, authorize
storage with the existing host command:

```bash
sudo vueioctl storage add "Fast projects" /mnt/nvme/projects rw
sudo vueioctl storage add "Studio archive" /mnt/archive/projects ro
sudo vueioctl storage list
```

Vueio sees stable internal paths such as `/storage/root-001`; users see the
labels. Host paths remain installation-specific and never enter the Vueio
application database.

The explicit `install` and `storage add` commands create a small read-only
`.vueio-storage-id` marker when the selected folder does not already have one.
If a valid marker already exists, that explicit command records it instead.
Ordinary startup never creates or silently adopts a marker. The marker lets
`vueioctl doctor` distinguish the intended disk from an empty mount point or a
different disk mounted at the same host path. Do not delete, overwrite, or copy
the marker to another root. Registration does not require hard links, so FAT
and exFAT drives can use the same identity mechanism. The filesystem must
permit this initial identity file, even when Vueio's access mode will be
read-only. Vueio does not format drives or recursively change their permissions.

For network storage, mount the share in Linux before starting Vueio. Stop
active uploads and downloads before ejecting any drive through the operating
system. To take all media services offline first:

```bash
sudo vueioctl stop
# disconnect or remount the drive here
sudo vueioctl start
sudo vueioctl doctor
```

On managed installations, `start` and `restart` keep disconnected locations
in the catalog but omit their bind mounts. The remaining app can start. Its
read-only `/storage` base prevents uploads from falling back to an empty local
mount point. Project records, comments, and history are not deleted when a
drive goes offline. Its source media cannot play or download until it returns.
Custom Compose overrides retain the stricter startup check.

Reconnect the original drive, then use **Reconnect drives** in Settings or:

```bash
sudo vueioctl storage reconnect
```

If a registered whole drive returns at a different mount path, **Add storage**
can recognize its original identity and reconnect it without changing the
storage name or project references. For a registered subfolder, use:

```bash
sudo vueioctl storage reconnect "Fast projects" /mnt/reconnected/projects
```

Vueio checks the original identity before changing the path. It refuses to
replace a still-connected original with a copy. `doctor` continues to report
missing or mismatched drives; update and release checks do not ignore them.
After a host reboot with a drive absent, use `vueioctl start` so the host can
rebuild the available mounts. Docker's restart policy alone cannot do this.

Removing a root does not delete files, but projects using it will be offline:

```bash
sudo vueioctl storage remove "Studio archive"
```

Vueio retains the removed name and mount ID to prevent an unrelated drive
from inheriting old references. Adding the original drive with the same name
restores that identity. Merely unplugging a drive does not require removing it.

The engine runs as `VUEIO_PUID:VUEIO_PGID` and applies `VUEIO_UMASK`.
The installer defaults these IDs to the account that invoked `sudo`. Set them
explicitly when project folders belong to a dedicated storage account. Vueio does
not recursively change permissions on project storage.

### Mac installer preview

The application remains one set of Linux container images on both CPU
architectures. Platform-specific launchers must handle installation, mounted
drive discovery, operating-system file permissions, and Docker file sharing.
They must not add host path handling to application routes or give the web
container access to the Docker socket or every host drive.

The boundary is deliberately small: the host lists eligible drives and issues
selection IDs; an authenticated owner selects an ID; the host rechecks it and
maps only that location to a stable container path. The database and private
application data stay separate from selected media roots. A desktop launcher
must place them on internal storage by default.

The same installer now detects macOS and CPU architecture. The Mac path is
**an experimental Apple Silicon preview, not recommended for production**.
Intel Macs are not supported. Linux AMD64 and ARM64 support is unchanged. An initial
Apple Silicon rehearsal passed installation, USB media upload/playback/download,
channel switching, and database backup/restore. Supported macOS versions,
and the lifecycle checks below still need verification. Use test
data for your first installation. It uses Homebrew and local Docker Desktop.
The installer offers to run Homebrew's official installer if needed, then
install Bash, Python, coreutils, findutils and Docker Desktop. It continues
without asking you to find separate commands. macOS may need your password
or permission approval; password characters are hidden while you type.
Docker Desktop has its own licensing
terms and first-run approvals; Vueio does not accept these on your behalf.

From a release that includes this path, run `sh ./install.sh` **without sudo**
on Mac. Linux asks for administrator approval automatically; existing
`sudo sh ./install.sh` commands also work. Both use the same source,
release tags, channels and container images; no Mac branch is maintained.

Mac private configuration defaults to `~/Library/Application Support/Vueio`,
with a separate selectable data folder (default: `state` inside that directory).
Media defaults to `~/Movies/Vueio projects`. The command is installed in
`~/.local/bin/vueioctl`; an optional global symlink makes `vueioctl` available
in every terminal without modifying shell profiles. The installer opens Docker
Desktop when needed, waits for it, then opens browser onboarding.

The Mac helper runs as the Mac user through a LaunchAgent. It discovers
OS-mounted volumes with `diskutil`. Its authenticated control endpoint binds
only to `127.0.0.1`; only the engine receives its private token file. The
Linux helper keeps its existing Unix socket and root-only configuration.
Neither platform gives the web container the Docker socket or the host root.
If Docker cannot reach the Mac helper, setup reports that failure rather than
exposing the helper on the LAN. Docker must be allowed to access each selected
folder; selecting a drive does not bypass macOS privacy permissions.

Real Apple Silicon installation, Docker file sharing, sleep/wake,
USB unplug/replug, data-drive loss, login startup, updates, channel switching,
and database backup/restore must all be rehearsed before claiming Mac support.
Linux verification or mocked platform calls are not a substitute. CPU remains
the default. Optional Apple Silicon acceleration uses the authenticated native
media helper and Homebrew FFmpeg, not GPU passthrough into Docker. Set
Docker Desktop to start at login if desired; do not assume a sleeping or
logged-out laptop is an always-on server. Windows remains unimplemented.
Internet sharing still needs HTTPS and a reachable, awake computer; installing
Vueio does not create a public tunnel.

The terminal shows one setup step at a time. Enter accepts the default folder;
`?` shows details and `q` cancels before installation. Set `VUEIO_PLAIN=1`
to keep all steps in the terminal transcript without colors or screen clearing.
`NO_COLOR=1` disables colors only. Failed installation steps show the path to
a private diagnostic log in the installation's `logs` folder.

### Preview processing

Open **Settings → Storage & previews → Preview processing**. CPU is the default
for new and existing installations. **Check hardware** runs a short hardware
encode and a separate thumbnail decode check. It does not enable GPU processing.
Select a verified GPU and save to use it for new preview jobs. Running jobs and
existing cached previews stay unchanged. A failed GPU job retries once on CPU;
recent processing shows the processor used and any fallback.

AMD integrated and discrete graphics use VA-API on Linux. NVIDIA graphics,
including capable GTX and RTX cards, use NVENC. Support depends on the card,
codec, driver and FFmpeg build, not the product name. A detected device is not
marked verified until its encode succeeds. This does not add a Windows installer.
Video decoding and scaling can still use CPU with GPU encoding. Hardware
thumbnail decoding is checked separately; unsupported inputs use CPU.

The Linux controller maps available render devices into the engine and adds
their group IDs when Vueio starts. It refreshes generated mappings when devices
change and preserves operator-managed GPU overrides. NVIDIA requires a working
NVIDIA driver and Container Toolkit runtime on the host. Manually managed
installations need a reviewed Compose device configuration; checking hardware
does not change host permissions.
Do not give the engine privileged mode or access to the Docker socket for this.

The Mac installer includes `vueio-media.py`, built from the same media recipe
module as the engine. It uses the existing authenticated loopback helper. Only
registered media and application media folders are readable. Requests cannot
supply shell commands, FFmpeg arguments or output filters. Native output is
staged privately, then copied to the engine's temporary preview directory with
no-follow file descriptors. The engine retains its source-generation checks,
job ownership, cancellation and atomic publication. Native jobs stop if their
engine heartbeat disappears. Source media and the database are never outputs.

An existing Mac installation also needs Homebrew FFmpeg (`brew install ffmpeg`)
and the matching verified helper asset. Without them, CPU processing still works.
Hardware status is a check result, not a live GPU-utilization measurement.

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

## Workspace preview LUTs

Administrators can upload `.cube` files in **Settings → Preview LUTs**. Saved
LUTs appear in **Color preview** for images and videos across the workspace,
including authorized share-link views. Members and share visitors can apply
them but cannot change the library. Choose a LUT that matches the source
media's color encoding.

The library is stored in this installation's database and survives restarts
and updates. It is included in database backups, not shipped with Vueio's
source or images. The limits are 64 LUTs, 32 MiB per file, and 256 MiB total.
Only standalone 3D `.cube` files with 2–65 points per axis are supported.

**Load temporary LUT** in the viewer keeps a file in browser memory until the
page is closed or refreshed. It does not add that file to the saved library.
LUTs affect the preview and captured video frames; original media and downloads
stay unchanged.

For animated image files, LUT mode shows a single frame. Select **Source** to
see the animation.

## Backups and restores

For a guided terminal menu, run `sudo vueioctl` on Linux or `vueioctl` on Mac.
Enter a number or `/help`. The menu reuses the same maintenance commands;
unknown text is never executed as a shell command. Closing the menu does not
stop Vueio. `update` with no version checks the running app for the latest
release on its selected channel, then uses the usual verified update path.
It never installs an older version. The menu confirms updates, restarts and
shutdowns, and offers a database backup destination on a separate drive.

Create a database backup:

```bash
sudo vueioctl backup
sudo vueioctl backups
```

The archive contains a consistent PostgreSQL dump, a manifest identifying its
version and creation time, and internal checksums. The finished archive also
has an adjacent SHA-256 checksum. The controller validates the dump and
checksums before accepting the backup.

**Backups contain the database only.** They do not include application files,
uploads, comment attachments, project files, media, caches, or host
configuration. Those files stay in place during backup, restore, and rollback.
Back up files and host configuration separately with your storage system.
Restoring database records cannot recover a missing file.

Database backups contain private account and project records. Keep them
private; the controller writes archives and checksums with owner-only
permissions.

Restore preserves the current host's paths, storage mounts, database password,
session secret, and application files. An adopted installation can retain a
root-owned `compose.installation.yml` beside its managed Compose files. The
controller applies this file last and keeps it through updates and restores.
It blocks `storage add` and `storage remove` while the override exists, so an
operator must review its storage mapping before making changes.

The engine pauses briefly to create a consistent backup. Restore is
intentionally guarded:

```bash
sudo vueioctl restore /path/to/backups/vueio-20260729T120000Z.tar.gz
```

Restore requires typing `RESTORE`. It validates the archive and available
space before changing the database. It then:

1. stops the engine and creates a fresh database safety backup;
2. restores the selected database in one transaction; and
3. starts Vueio and requires `doctor` to pass.

If a later step fails, Vueio attempts to restore the safety database and prior
image settings. If recovery cannot complete, Vueio stays stopped and prints
the safety-backup path. Application files are never staged, moved, replaced,
or removed by restore.

Older archives that include application files remain usable as database
restore sources. The controller validates their contents but restores only
the database; archived files and configuration are ignored.

Rehearse backup and restore on a disposable installation before relying on
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

Open **Settings → Updates** and choose **Update now** to install the offered
release from your selected channel. Only an administrator signed in to Vueio
can start an update. The progress bar shows completed installation stages;
the description explains the current step. Download time depends on the
connection and backup time depends on database size.

The host service continues the operation while Vueio restarts. The page
reconnects and reloads after the target version passes its health checks.
Refreshing the page resumes the current operation. Only one host maintenance
operation can run at a time; clicking again does not start another update.

The terminal command remains available:

```bash
sudo vueioctl update v0.1.1-alpha.1
```

The command checks the current installation, available space, Docker, release
metadata, and target images before changing anything. It downloads and
checksum-verifies the release files, pulls the versioned images before the
short restart window, creates a validated pre-update database backup, starts the new
release, and requires `doctor` to pass. Progress is written to
`/opt/vueio/logs/update-<timestamp>.log`; the newest ten update logs are kept.

The engine stays paused from the consistent backup through installation.
If an update fails before installation, the existing version can restart.
Once installation begins, failure or interruption requires operator recovery;
Vueio does not automatically restore an older database or retry installation.
Check `sudo vueioctl doctor` and the update log, then follow the release's
recovery instructions. An explicit rollback discards database changes after its backup,
as described below.

Administrators can see the installed version and check for a newer release in
**Settings → Updates**. When a release is available, Vueio also shows a small
update indicator at the bottom of the sidebar. Update requests specify only
the offered release version. The host independently validates the installed
channel and published release before invoking its fixed management command.

### Enable updates on an existing installation

If the installed host controller predates database-only backups, replace it
with the `vueioctl` asset from the selected release after verifying that file
against the release's `SHA256SUMS`. Do this before starting an update from
Settings or the terminal. An older controller uses its previous backup
behavior until it is replaced; downloading new application images does not
change that behavior.

An installation from before the update-service feature then needs one terminal
upgrade to the selected release. Afterward, run:

```bash
sudo vueioctl updater enable
sudo vueioctl updater status
```

`enable` prepares the verified helper and local socket, then installs a
persistent service when systemd is running. New installations enable it
automatically on systemd hosts. To disable
browser updates, run `sudo vueioctl updater disable`; terminal updates remain
available.

On a host with another service manager, configure it to run
`sudo vueioctl updater serve` at boot, restart it on failure, and preserve a
running update process when restarting the service. For a custom installation
directory, set `VUEIO_HOME` to that directory for both commands and the service.
The helper must remain independent of the containers it updates. Its code,
installation directory, and parent directories must be owned by root and not
writable by other users.

The service supports installations managed by the release installer and its
Compose model. A source checkout or custom Compose deployment must first be
adopted into that layout while preserving its database and authorized storage.
The Updates page shows setup instructions until its host service is available.

### Release channels

Stable is the default channel. Stable releases use immutable
`vX.Y.Z-alpha.N` tags and are not GitHub prereleases. Nightly releases are test
builds, use `vX.Y.Z-alpha.N.dev.M` tags, and are marked prerelease.

Administrators can select **Stable** or **Nightly** in **Settings → Updates →
Channel**. Vueio briefly restarts to apply the channel and shows its progress.
This keeps the installed version; use **Update now** to install an offered
release. Install the latest release first if the channel selector is unavailable.

The terminal commands remain available:

```bash
sudo vueioctl channel stable
sudo vueioctl channel nightly
```

Nightly sees both stable and nightly releases; stable sees stable releases
only. Switching from nightly to stable does not downgrade the running app. It
waits for a stable release newer than the installed nightly because database
migrations are one-way.

The public `stable` branch shows the source for the latest Stable release. The
public `nightly` branch shows the source for the latest Nightly release. When a
Nightly becomes Stable, both branches point to the same reviewed source.

The immutable release tag is carried into the engine, UI images, installer,
and update screen, so version numbers do not need to be edited in several
places.

To undo an update that completed successfully, use:

```bash
sudo vueioctl rollback
```

Rollback restores the newest pre-update database backup and repins the
matching application images. The command prints the version and backup time
and requires typing `RESTORE`. **Database changes made after that backup are
discarded.** Application files, uploads, attachments, project files, and media
remain unchanged; they are not restored from the archive. Database migrations
are one-way, so never run an older image against a newer database without
restoring its matching backup.

Every release must be tested in two paths:

1. a completely fresh installation; and
2. an upgrade restored from a copy of an existing Vueio installation.

Every installation should use the published images and release Compose model,
with only its environment and explicitly authorized storage paths differing.
