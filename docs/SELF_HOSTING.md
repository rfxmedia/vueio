# Self-hosting Vue.io alpha

[Documentation home](README.md) · [Quick start](GETTING_STARTED.md) · [Troubleshooting](TROUBLESHOOTING.md)

This guide covers **v0.1.0-alpha.13** on an installer-managed host.
Docker Compose runs the website, media engine, and PostgreSQL database on one host.
Read the [release notes](https://github.com/rfxmedia/vueio/releases/latest) before installation or an update.

## Alpha support boundary

The primary host platforms are Linux x86-64 and ARM64.
You need Docker Engine, Docker Compose v2, and Python 3.9 or later.
Use local media storage or network storage already mounted on the host.
Configure HTTPS separately for remote access.

Apple Silicon Mac installation is experimental. See [Mac installer preview](#mac-installer-preview).
Intel Mac and native Windows installers are not supported.
The alpha does not provide Kubernetes, clusters, high availability, Podman support, or a built-in internet tunnel.
Hardware acceleration is optional. CPU processing is the default.

Use trusted users and media. Alpha.13 includes known third-party security advisories described in its release notes.
An installation check does not establish security or reliability in every environment.
Keep independent database and file backups.

## Before you install

Use these values as a starting estimate, not a capacity guarantee:

- 4 CPU cores;
- 8 GiB RAM;
- 40 GiB free local space for the application, database, and working files; and
- separate space for source media and independent backups.

Large libraries and high-resolution previews need more resources.
The upload service also reserves free space on each destination. See [Upload safety limits](#upload-safety-limits).

On Linux, install Docker Engine, Compose v2, Python, and curl before running the installer.
Check the prerequisites:

```bash
docker --version
docker compose version
python3 --version
curl --version
```

Docker must be running. The installer stops if a required prerequisite is missing.
Use the versioned installer from a GitHub release, not the unbuilt source copy of `install.sh`.
The release installer contains its version and download location.

## Install

Run the release installer on the host:

```bash
curl -fsSL https://github.com/rfxmedia/vueio/releases/latest/download/install.sh | sh
```

To inspect it first, download `install.sh` from the release. Then run:

```bash
sh ./install.sh
```

Linux installation requests administrator access.
On Mac, run the installer without `sudo`.
The installer checks the platform, prerequisites, disk space, and web port.
It then asks for data and media locations, creates credentials, and starts the versioned containers.
Keep the terminal open until it prints the browser address and setup code.

The initial update channel follows the downloaded release.
You can change it later in **Settings → Updates**.
Do not run a fresh installation over an existing installation. Use [Updates](#updates).

### Your data folder

Choose a new or empty absolute directory for **Vue data**.
The Linux default is `/opt/vueio/state`.
For unattended installation, `VUEIO_STATE_PATH` selects this directory.
The installer does not format drives.

| Subfolder | Contents |
| --- | --- |
| `postgres` | Live database: accounts, projects, comments, membership, and history. |
| `app` | Application files, attachments, previews, and other working files. |
| `backups` | Database backup archives. |

Media storage must not overlap the data folder.
Private configuration and credentials remain in `VUEIO_HOME`, normally `/opt/vueio` on Linux.
Protect both locations.
Use `vueioctl data` or **Settings → Storage** to inspect the configured locations.
These controls do not move an existing database.

The database needs a writable local filesystem with normal permissions and durable writes.
Accepted types include ext2/3/4, XFS, Btrfs, and ZFS on Linux; APFS and HFS on Mac.
Network shares and FAT/exFAT are not accepted database locations. They can hold media.
An external data drive must stay connected while Vue.io runs.
Stop Vue.io before disconnecting it.
Startup rejects a missing, replaced, or incomplete data folder instead of creating an empty replacement.

Older installations keep their existing Docker database volume.
An update does not migrate that volume into a new data folder.
A failed new installation can leave data and configuration for recovery. Read its error before retrying.
Do not remove those files to bypass a startup check.

### First login

The default browser address is `http://127.0.0.1:9000` on the host.
Use the printed setup code to create the first owner account.
For setup from another computer, keep an SSH tunnel open:

```bash
ssh -L 9000:127.0.0.1:9000 user@vueio-server
```

Replace the example SSH destination. Open `http://127.0.0.1:9000` on your computer.
To recover the setup instructions on Linux:

```bash
sudo vueioctl setup-info
```

`sudo vueioctl setup-token` prints only the setup code.
Both outputs are private. Do not put them in screenshots or public issues.
For a custom installation directory, replace `sudo` with `sudo env VUEIO_HOME=/path/to/installation`.

## Storage

After first setup, Vue.io opens **Settings → Storage**.
The initial media location is already connected.
The browser drive picker needs the host management service.
New Linux installations enable this service automatically when systemd is running.

### Add a local drive

1. Connect, unlock, and mount the drive on the Vue.io host.
2. Open **Settings → Storage → Add storage** as an administrator.
3. If needed, select **Check again**.
4. Select an eligible drive and its access mode.
5. Confirm the registration.
6. Check the storage list after the application reconnects.

The picker offers eligible mounted local drives, not every host path.
It excludes system locations and nested mounts.
A drive attached only to the reviewing computer does not appear.
Only an administrator's browser session can register host storage. Agent keys cannot do this.

Adding storage does not move projects or share all files on the drive.
Choose a storage location when creating a project.
Connecting or reconnecting storage restarts the media engine and website, not PostgreSQL.
Finish active uploads before changing storage mappings.
If the browser disconnects, inspect the storage list before submitting the action again.

### Add a folder or mounted network share

For an existing folder or network mount, use the Linux host command:

```bash
sudo vueioctl storage add "Fast projects" /mnt/nvme/projects rw
sudo vueioctl storage add "Studio archive" /mnt/archive/projects ro
sudo vueioctl storage list
```

Replace the example labels and paths. `rw` permits writes; `ro` gives the engine read-only access.
Mount network storage on the host before registration.
Use a dedicated media folder for storage on the operating-system disk.
The engine uses stable internal paths such as `/storage/root-001`.

Registration creates a `.vueio-storage-id` marker, or records an existing valid marker.
The selected filesystem must permit this initial file even when engine access will be read-only.
Registration does not require hard links, so FAT/exFAT media drives can use it.
Ordinary startup does not create or adopt a missing marker.
Do not delete, replace, or copy a marker to another storage root.

The installer does not recursively change existing project-storage permissions.
The engine uses `VUEIO_PUID`, `VUEIO_PGID`, and `VUEIO_UMASK`.
Linux defaults use the account that invoked `sudo`.
Use an appropriate storage account if the files belong to another user or group.

### Disconnect or reconnect storage

Stop transfers before disconnecting a drive.
To stop the media services before an operating-system unmount:

```bash
sudo vueioctl stop
```

Reconnect and mount the drive, then run:

```bash
sudo vueioctl start
sudo vueioctl doctor
```

On a managed installation, `start` and `restart` omit disconnected media mounts but retain their catalog entries.
The application can start with those locations offline. Their media cannot play or download.
Project records, comments, and history remain in the database.
A missing database drive is different: Vue.io cannot start without its database.
Custom Compose overrides can retain stricter startup checks.

To reconnect registered media without removing its catalog entry, use **Reconnect drives** or:

```bash
sudo vueioctl storage reconnect
```

For a registered subfolder at a new mount path:

```bash
sudo vueioctl storage reconnect "Fast projects" /mnt/reconnected/projects
```

Vue.io checks the original identity before changing the mapping.
For a whole drive at a new path, **Add storage** can recognize and reconnect its original identity.
After a reboot with a drive absent, run `vueioctl start` to rebuild the available mappings.
Docker's restart policy does not rebuild them.
`doctor` and update checks still report missing or mismatched storage.

To remove a registered root:

```bash
sudo vueioctl storage remove "Studio archive"
```

This removes access, not source files. Projects using it become offline.
Vue.io retains the old name and mount ID. Adding the original drive with that name restores its identity.
Unplugging a drive does not require removing its root.

For project-specific moves, see [Change a project folder](STORAGE_OPERATIONS.md#change-a-project-folder).

### Custom installations

The management service supports the release installer and its Compose layout.
A source checkout or custom Compose deployment needs a separate adoption review before host-managed updates or storage changes.

An adopted installation can use a root-owned `compose.installation.yml` override.
The controller applies it last and retains it through updates and restores.
It blocks `storage add` and `storage remove` while this override exists.
Review the custom mapping before changing it.
The standard release does not give the web application the Docker socket or unrestricted host-drive access.

## Mac installer preview

The Apple Silicon installer uses the same Linux container images as the Linux installation.
It uses Homebrew and Docker Desktop for host prerequisites.
The installer offers to install Homebrew, Bash, Python, coreutils, findutils, FFmpeg, and Docker Desktop as needed.
Docker Desktop has separate licensing terms and first-run approvals.
Vue.io does not accept those terms for you.

Run the release installer without `sudo`.
The defaults are:

| Item | Default location |
| --- | --- |
| Private configuration | `~/Library/Application Support/Vueio` |
| Vue data | `state` inside the configuration directory |
| Media | `~/Movies/Vueio projects` |
| Management command | `~/.local/bin/vueioctl` |

Use `vueioctl` without `sudo` for Mac management commands.
The installer can create a global command link without changing shell profiles.
It opens Docker Desktop when needed and opens browser setup when ready.

Allow Docker Desktop to access each selected folder.
Selecting a drive in Vue.io does not bypass macOS privacy or file-sharing permissions.
The host helper runs as the Mac user through a LaunchAgent.
Its authenticated endpoint is local; do not expose it to the network.

Mac support remains experimental in alpha.13.
Sleep/wake, login startup, and the complete upgrade path are unverified.
Do not assume that a sleeping or logged-out laptop remains a server.
Use test media and check USB reconnection, data-drive loss, backup, and restore on your actual Mac.
Intel Macs and native Windows installation are not supported.

Optional Apple Silicon acceleration uses the native helper and Homebrew FFmpeg.
It is not Docker GPU passthrough. An older Mac installation needs the matching helper asset and FFmpeg.
CPU processing remains available when native acceleration is unavailable.

For a plain terminal transcript, set `VUEIO_PLAIN=1` when invoking the installer.
`NO_COLOR=1` disables colors only.
Failed installation stages show the private diagnostic-log location.

## Preview processing

Open **Settings → Storage → Preview processing** as an administrator.
CPU is the default for an installation without a saved GPU selection.
An update retains a saved processing preference; it does not reset a selected GPU to CPU.

1. Select **Check hardware**.
2. Inspect the encode and thumbnail-check results.
3. To enable acceleration, select **GPU** and a verified device.
4. Save the selection.
5. Inspect recent processing results after a new preview job.

The check alone does not enable GPU processing.
The saved selection affects new jobs. It does not rebuild cached previews or change a running job.
A failed GPU job can retry on CPU. Recent processing shows the processor and fallback state.
A canceled job is not a request to retry on CPU.

Linux AMD hardware uses VA-API. NVIDIA uses NVENC and needs a working host driver and NVIDIA Container Toolkit.
Support depends on the device, codec, driver, and FFmpeg build.
A product name or detected GPU is not proof of a successful encode.
Video decoding and scaling can still use CPU. Thumbnail decoding is checked separately.

The Linux controller prepares available render-device mappings when starting Vue.io.
Custom installations need appropriate Compose device mappings.
Do not add privileged mode or mount the Docker socket to enable acceleration.
The displayed hardware result is not a live GPU-utilization meter.

## Voice note transcription

Vue.io transcribes English voice notes inside the media engine with the bundled Moonshine model.
It processes one recording at a time. It does not send the recording to a transcription service.
Transcription can be delayed or fail; check the recording if the text appears wrong.

To disable transcription, set `VUEIO_VOICE_TRANSCRIPTION_ENABLED=false` in the installation's private `.env` file.
Restart the managed application to apply the configuration.
The setting does not remove existing recordings or transcripts.

## Internet exposure

The default loopback HTTP address is not a public link.
Do not forward the plain HTTP port directly to the internet.
First configure an HTTPS reverse proxy, tunnel, or reachable VPN HTTPS hostname.
Then set the exact origin on Linux:

```bash
sudo vueioctl exposure set https://vue.example.com
```

Replace the example origin. This enables secure cookies and disables local bootstrap mode.
Vue.io does not create DNS records, certificates, or the external tunnel.
VPN recipients also need access to that VPN.

For a host-installed Cloudflare Tunnel, point the tunnel to `http://127.0.0.1:9000` and run:

```bash
sudo vueioctl exposure set https://vue.example.com --cloudflare
```

Use `--cloudflare` only when the trusted proxy provides Cloudflare's client-address header.
Cloudflare account and upload limits still apply.
Inside a tunnel container, `127.0.0.1` refers to that container, not the Vue.io host.
Container-based tunnel networking requires separate configuration.

A minimal host-installed Caddy configuration is:

```caddyfile
vue.example.com {
    reverse_proxy 127.0.0.1:9000
}
```

Configure DNS and certificate issuance for that hostname.
Run `exposure set` with the same HTTPS origin.
Keep the upstream on loopback and preserve byte-range requests for media seeking.
Check login, seeking, comments, and downloads through the final HTTPS address.

To return to local testing:

```bash
sudo vueioctl exposure local
sudo vueioctl doctor
```

`exposure set` applies the configuration and runs `doctor`.
`exposure local` does not remove an independently configured proxy or tunnel.
Disable external routing separately when taking the host offline.

## Operations

These examples use Linux's default installation directory.
On Mac, omit `sudo`. For a custom directory, use `sudo env VUEIO_HOME=/path/to/installation vueioctl ...` on Linux.

| Command | Purpose |
| --- | --- |
| `sudo vueioctl start` | Start the managed services with available storage mappings. |
| `sudo vueioctl stop` | Stop the managed services. |
| `sudo vueioctl restart` | Restart with current configuration. |
| `sudo vueioctl status` | Show service status. |
| `sudo vueioctl version` | Show the selected release and application image names. |
| `sudo vueioctl data` | Show data and backup locations. |
| `sudo vueioctl logs` | Read service logs. Logs can contain private information. |
| `sudo vueioctl doctor` | Check configuration, storage, database, application readiness, and exposure. |

Run `sudo vueioctl` without arguments for the guided menu.
Enter a menu number or `/help`. Closing the menu does not stop the application.
Unknown text is not executed as a shell command.

Use `sudo vueioctl doctor --fix` only after reading the diagnosis.
It can remove stale staging directories, reconcile image pins, and restart unhealthy services.
It does not restore a backup or repair missing source files.
Local HTTP produces a warning even when required health checks pass.

## Automatic folder updates

Open project folders, expanded navigation folders, and file pickers watch for visible file changes.
Hidden browser tabs stop watching. Returning to a tab refreshes its folders.

Local Linux storage uses filesystem notifications where available.
Fallback checks run at four-second intervals. Existing entries receive a slower reconciliation at about 30 seconds.
New or changed files can wait until their size and modification time settle.
These intervals are not a guarantee of when every render appears.
The watcher does not recursively scan every subfolder or read all media contents.

Folder refresh does not create shot versions automatically.
Use tracker **Import** or **Add version** to register a revision.
Refresh also does not publish held versions or bypass share permissions.

## Workspace preview LUTs

Administrators upload `.cube` files in **Settings → Preview LUTs**.
Members and authorized share visitors can select saved LUTs but cannot change the library.
See [Color preview](REVIEW_WORKFLOW.md#use-a-color-preview-or-capture-a-frame) for viewer steps.

| Limit | Value |
| --- | --- |
| Saved LUT count | 64 |
| File size | 32 MiB |
| Total library size | 256 MiB |
| Supported format | Standalone 3D `.cube`, 2–65 points per axis |

One-dimensional LUTs and combined shapers are not supported.
Saved LUTs are in the database and included in database backups.
Temporary LUTs stay in the browser until the page closes or refreshes.
LUTs affect preview and captured frames, not original files or source downloads.

## Backups and restores

Create and list database backups on Linux:

```bash
sudo vueioctl backup
sudo vueioctl backups
```

The engine stops while the controller creates a consistent PostgreSQL dump.
Plan for a service interruption; its duration depends on the database.
The archive includes a version manifest and internal checksums.
An adjacent `.sha256` file checks the archive.
Copy both files to independent storage.

**These backups contain the database only.**
They exclude uploads, comment attachments, project media, application files, caches, and host configuration.
Back up those separately. Do not copy a running PostgreSQL directory as an ordinary file backup.
Keep database archives private: they contain account and project records.

To choose a destination file:

```bash
sudo vueioctl backup /path/to/independent-backups/vueio-manual.tar.gz
```

Replace the example with a new filename outside project media and live application data.
The controller refuses to overwrite an existing archive or checksum.

### Restore a database

Rehearse recovery on a disposable installation before using it on important data.
A database restore replaces current records. It cannot recover missing source files.

```bash
sudo vueioctl restore /path/to/backups/vueio-backup.tar.gz
```

Replace the example with the selected archive. Read the prompt before typing `RESTORE`.
The controller validates the archive, stops the engine, and creates a safety database backup.
It restores the selected database in one transaction, starts the services, and requires `doctor` to pass.
If recovery after a failure also fails, Vue.io stays stopped and reports the safety-backup path.

Restore keeps current host paths, credentials, storage mappings, and application files.
Ordinary `restore` does not select the application version from the archive.
Use a compatible release; use `rollback` for the supported pre-update version-and-database recovery.
Do not run older application images against a newer database.

Older archives containing application files can be used as database restore sources.
The controller validates them but ignores their archived files and configuration during restore.

### Backup retention

The controller keeps the five newest archives in its managed backup directory by default.
It also protects the newest pre-update backup.
Set `VUEIO_BACKUP_KEEP` to a positive count when invoking the controller to change this retention.
A manual archive outside the managed backup directory is not included in that pruning.
Database backups are not a complete host backup.

## Upload safety limits

These are alpha.13 defaults for the released Compose configuration.
GiB, MiB, and TiB are binary units.

| Limit | Default |
| --- | --- |
| File size | 100 GiB |
| Session total | 500 GiB |
| Files per normal session | 10,000 |
| Files per public session | 2,000 |
| Free-space reserve | 20 GiB |
| Resumable chunk size | 8 MiB maximum |
| Session expiration | One day, refreshed while active |
| Public allocation per share | 1 TiB |
| Active public sessions per share | 25 |
| Active sessions per visitor per share | 5 |
| Comment attachment size | 256 MiB per file, 500 MiB per comment |

The public allocation includes completed sessions and sessions that are not canceled or expired.
It is not a separate storage allowance for each visitor.

Default public rate limits include 20 session creations per hour and 240 chunk requests per minute.
Comment creation is limited to 60 per hour; comment batch reads to 240 per minute.
Share-password attempts are limited to 30 per minute; tracker-view recording to 120 per minute.
These are request-rate controls, not transfer-speed guarantees.

The release Compose file maps configurable limits from `VUEIO_*` values in the installation's private `.env`.
For example, `VUEIO_UPLOAD_MAX_FILE_BYTES` and `VUEIO_UPLOAD_MAX_SESSION_BYTES` control file and session size.
Read the exact mappings in [compose.release.yml](https://github.com/rfxmedia/vueio/blob/stable/compose.release.yml) before changing them.
The 8 MiB chunk limit is fixed in this release; it is not a configurable `.env` value.
Restart the managed application after a configuration change.
Proxy limits and available disk space can still stop an upload.

## Updates

Read the target release notes and make a database backup first.
Keep separate backups of files and configuration.
On a managed installation, an administrator uses **Settings → Updates → Update now**.
The page shows installation stages and reconnects after the application restarts.
Refreshing the page resumes observation of the current operation; it does not start another update.

The host service continues while the containers restart.
Only one host maintenance operation can run at a time.
Agent keys cannot start this browser-only update action.

For the latest eligible release on the installed channel:

```bash
sudo vueioctl update
```

The command checks release metadata, available space, Docker, and image availability.
It verifies release-file checksums, downloads images, and makes a pre-update database backup.
The engine stays stopped from that backup through installation.
The new release must pass `doctor`.
Update logs are in the installation's `logs` directory; the newest ten update logs are retained.

If failure occurs before installation, the previous release can restart.
Once installation begins, interruption requires recovery review.
Vue.io does not automatically restore the old database or repeat installation.
Read the log and run `sudo vueioctl doctor` before taking another action.

### Enable updates on an existing installation

An old host controller can still use older backup behavior even after new application images are downloaded.
If it predates database-only backups, replace `vueioctl` with the target release asset first.
Verify that file against the release's `SHA256SUMS` before installing it in the host command location.
Do not replace it with an unversioned source file.

An installation that predates the host update service needs one terminal update to the selected release.
Then run:

```bash
sudo vueioctl updater enable
sudo vueioctl updater status
```

Linux `enable` installs a persistent service when systemd is running.
On another service manager, the operator must configure `vueioctl updater serve` as an independent host service.
Its Linux code and parent directories must be root-owned and not writable by other users.
Use the same custom `VUEIO_HOME` for the service and management commands.
Mac installations use their user-owned LaunchAgent instead.

To disable browser updates, run `sudo vueioctl updater disable` on Linux.
Terminal updates remain available. Do not stop a helper while it is applying an update.

### Release channels

**Stable** uses tags such as `vX.Y.Z-alpha.N`.
It is still an alpha channel, not a production-readiness certification.
**Nightly** uses prerelease tags such as `vX.Y.Z-alpha.N.dev.M`.
Nightly can offer both stable and nightly releases; Stable offers stable releases only.

Use **Settings → Updates → Channel** to change channels.
Vue.io restarts to apply the channel but keeps the installed version.
Then use **Update now** if a newer eligible release is offered.
The Linux commands are:

```bash
sudo vueioctl channel stable
sudo vueioctl channel nightly
```

Switching to Stable does not downgrade a newer Nightly database.
It waits for a newer eligible Stable release.
Public branches can receive documentation changes between releases.
Use the immutable release tag when you need the exact source for an installed version.

### Roll back an update

```bash
sudo vueioctl rollback
```

Read the displayed version and backup time before typing `RESTORE`.
Rollback restores the newest pre-update database backup and selects its matching application images.
**Database changes after that backup are lost.**
Current uploads, attachments, application files, and project media remain unchanged.
Rollback does not restore or remove those files.
