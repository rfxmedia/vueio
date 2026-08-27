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

```bash
curl -fsSL https://github.com/rfxmedia/vueio/releases/download/<release-tag>/install.sh | sudo sh
```

The installer:

1. checks Linux, Docker, disk space, and the local web port;
2. offers a safe local project folder or accepts an existing mounted folder;
3. downloads and verifies the release;
4. creates private database and session secrets;
5. starts Vueio and runs its safety checks; and
6. prints the web address and one-time setup code.

Vueio receives access only to the project folder selected during setup. By
default it uses `/var/lib/vueio/projects`, binds the web app to
`127.0.0.1:9000`, and installs the small `vueioctl` management command.

Open `http://127.0.0.1:9000` on the server, or use the SSH-tunnel example in
the [self-hosting guide](docs/SELF_HOSTING.md). The browser wizard creates the
first owner account and workspace.

Vue.io does not configure DNS, TLS certificates, VPNs, reverse proxies, or
Cloudflare Tunnels. The guide explains how to prepare Vue.io after you configure
one of those yourself.

## Protecting existing installations

Application updates use database migrations and are designed to preserve
projects, trackers, accounts, comments, shares, and settings. Source media is
never copied into a backup automatically. Before upgrading a production
installation:

```bash
sudo vueioctl backup
sudo vueioctl doctor
sudo vueioctl update <release-tag>
```

Keep a separate NAS/storage backup of the authorized project folders. See
[Backups and restores](docs/SELF_HOSTING.md#backups-and-restores) for the exact
boundary. Once an update may have run a database migration, Vue.io does not
automatically start older application code. Follow that release's recovery
notes and prefer fixing forward or restoring a tested backup.

Check the installed release and installation health at any time:

```bash
sudo vueioctl version
sudo vueioctl doctor
```

## Documentation

- [Self-hosting, storage, exposure, backups, and updates](docs/SELF_HOSTING.md)
