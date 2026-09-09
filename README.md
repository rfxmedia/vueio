# Vue.io

Vue.io is a self-hosted review and collaboration workspace for media teams. It
keeps project files on storage you control while providing trackers, version
review, comments, share links, file requests, and browser playback.

> **Public alpha:** use backups, test upgrades on a copy first, and do not
> expose Vue.io directly to the internet without HTTPS.

> **Source available:** Vue.io is licensed under the
> [PolyForm Perimeter License 1.0.1](LICENSE.md), which permits use,
> modification, and distribution for purposes that do not compete with the
> software. Vue.io is not open-source software under the OSI definition. The
> project name and brand are covered by the [trademark policy](TRADEMARKS.md).

## AI-forward by design

Vueio is designed for agentic workflows and media-pipeline automation. It uses
human-directed, AI-assisted engineering, with repeated adversarial review from
frontier systems such as Fable 5 and GPT-5.6 Sol. Every release also passes
build checks, security scans, manual release and recovery validation, and human
approval.

## Install on Linux

Before installing, prepare a 64-bit Linux server with Docker Engine and Docker
Compose v2. The practical starting point is 4 CPU cores, 8 GiB of memory, and
40 GiB of free local space. The installer checks the server before changing
anything and explains how to fix a missing or stopped Docker installation.

During installation, Vueio creates and records a unique storage identity marker
in the folder you explicitly select. Normal startup never creates or silently
adopts storage. See the [self-hosting storage guide](docs/SELF_HOSTING.md#storage).

Source media needs its own storage capacity and is not included in the 40 GiB
guideline.

Open Terminal on the Linux computer that will run Vueio. Paste this command
and press Enter. If `sudo` asks for a password, enter your computer's password;
the terminal does not show characters while you type.

```bash
curl -fsSL https://github.com/rfxmedia/vueio/releases/latest/download/install.sh | sh
```

The installer:

1. checks Linux, Docker, disk space, and the local web port;
2. asks for a Vue data folder and a separate media location;
3. downloads and verifies the release;
4. creates private database and session secrets;
5. starts Vueio and runs its safety checks;
6. enables updates and drive management on hosts running systemd; and
7. prints the web address, one-time setup code, and next steps.

Press Enter to accept storage on this computer, then confirm the installation.
The update channel follows the release you downloaded; you can change it later
in Settings. Keep the terminal open until it says **Continue in your browser**.

Vueio receives access only to the project folder selected during setup. By
default it uses `/var/lib/vueio/projects`, binds the web app to
`127.0.0.1:9000`, and installs the small `vueioctl` management command.

Open `http://127.0.0.1:9000` on the server, or use the SSH-tunnel example in
the [self-hosting guide](docs/SELF_HOSTING.md). The browser wizard creates the
first owner account and workspace. Then it shows your connected storage and
an **Open workspace** button. Extra drives are optional; you can add them later
in **Settings → Storage**.

Your chosen Vue data folder holds the database, app files and previews. The
database contains accounts, projects, comments, members and history. Keep
database backups on a separate drive, and protect app files and private
configuration too. Existing installations keep their current database location.
Run `sudo vueioctl` for the guided terminal menu, or `sudo vueioctl data` to
show these locations. See [data storage](docs/SELF_HOSTING.md#your-data-folder).

A [Mac installer preview](docs/SELF_HOSTING.md#mac-installer-preview) for Apple
Silicon uses the same command, code and releases. It guides you through any
missing prerequisites. Intel Macs are not supported. Mac verification is still
required before production use.
Windows installation is not available yet.

Vue.io does not configure DNS, TLS certificates, VPNs, reverse proxies, or
Cloudflare Tunnels. The guide explains how to prepare Vue.io after you configure
one of those yourself.

## Protecting existing installations

Administrators can install the latest release in their selected Nightly or
Stable channel from **Settings → Updates → Update now**. A progress bar shows
each stage, and the page reconnects after the restart. Existing installations
need a one-time [update-service setup](docs/SELF_HOSTING.md#enable-updates-on-an-existing-installation).
Older host controllers must be replaced with the checksum-verified release
controller before their first database-only update; the setup guide explains
this transition.

Application updates use database migrations and are designed to preserve
projects, trackers, accounts, comments, shares, and settings. Update backups
contain the database only. Application files, uploads, attachments, and media
stay in place and are not copied into the backup. Before upgrading a production
installation:

```bash
sudo vueioctl backup
sudo vueioctl doctor
sudo vueioctl update <release-tag>
```

Back up application files and authorized project folders separately on independent storage. See
[Backups and restores](docs/SELF_HOSTING.md#backups-and-restores) for the exact
boundary. Once an update may have run a database migration, Vue.io does not
automatically start older application code. Follow that release's recovery
notes and prefer fixing forward or restoring a tested backup.

Check the installed release and installation health at any time:

```bash
sudo vueioctl version
sudo vueioctl doctor
```

## Release channels

The public `stable` branch contains the latest reviewed Stable source. The
public `nightly` branch contains the latest Nightly source. Stable promotion
brings both branches to the same reviewed commit. Immutable GitHub Releases
provide each version, its downloads, and its release notes.

## Documentation

- [Self-hosting, storage, exposure, backups, and updates](docs/SELF_HOSTING.md)
