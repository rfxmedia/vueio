# Get started

Install Vue.io on the computer that will host your workspace. Your team and
clients use their browsers; they do not each need a server installation.

## 1. Prepare your host

The primary alpha supports x86-64 and ARM64 Linux with:

- Docker Engine and Docker Compose v2;
- Python 3.9 or newer;
- 4 CPU cores and 8 GiB RAM as a practical starting point;
- 40 GiB free local space for the app and working data; and
- separate capacity for media and independent backups.

Large libraries and high-resolution previews need more resources. Check Docker:

```bash
docker --version
docker compose version
```

For Apple Silicon, read the [experimental Mac instructions](SELF_HOSTING.md#mac-installer-preview)
first. There is no supported Intel Mac or native Windows installer yet.

## 2. Install Vue.io

Run this on the host:

```bash
curl -fsSL https://github.com/rfxmedia/vueio/releases/latest/download/install.sh | sh
```

You can also download and inspect `install.sh` from the
[latest release](https://github.com/rfxmedia/vueio/releases/latest), then run
`sh ./install.sh`.

The installer checks prerequisites, asks for storage locations, downloads the
release, and starts Vue.io. Keep the terminal open until it prints the browser
address and one-time setup code.

Choose **two separate locations**:

- **Vue data:** database, app files, previews, and database backups. Use a
  suitable local filesystem, not a network share or FAT/exFAT database drive.
- **Media:** a selected project folder or mounted storage. Media can live
  on local disks, USB storage, or a network share mounted on the host.

The installer does not format drives. Do not run a fresh installation over an
existing workspace; follow the [update guide](STORAGE_OPERATIONS.md#updates).

## 3. Open the workspace

On the host, open the printed address, normally `http://127.0.0.1:9000`.
Enter the setup code and create the first owner account.

For a headless server, open an SSH tunnel from your own computer:

```bash
ssh -L 9000:127.0.0.1:9000 user@vueio-server
```

Leave the tunnel open and visit `http://127.0.0.1:9000` in your browser.
Replace `user@vueio-server` with your server's SSH destination.

Lost the setup instructions? On Linux, run:

```bash
sudo vueioctl setup-info
```

The output contains a private setup code. Do not post it in an issue or screenshot.

## 4. Complete a first review

1. Confirm the selected media location in **Settings → Storage**.
2. Create a small project with non-sensitive sample media.
3. Create a tracker and import a shot or file using the available import options.
4. Open the media and leave a review note.
5. Add a new version to the same shot, then check its version history.

Follow [Review workflow](REVIEW_WORKFLOW.md) for the project-to-delivery process.
Test with a second permitted user or share visitor before relying on the setup.

## 5. Set up remote access

The default loopback address is local to the host. It is not an internet link.
Configure an HTTPS reverse proxy, VPN hostname, or tunnel before inviting
remote collaborators. Vue.io does not create that connection for you.

After your HTTPS endpoint is working, configure Vue.io on Linux:

```bash
sudo vueioctl exposure set https://vue.example.com
```

Replace the example with your HTTPS origin. Do not forward the plain HTTP
port directly to the public internet.

[HTTPS, Caddy, and Cloudflare examples →](SELF_HOSTING.md#internet-exposure)

## Before real production work

Read the release's known issues. Verify login, playback, a review link, and
downloads from the intended network. Make a database backup and separately
back up application files, media, and configuration. The alpha is intended
for trusted users and media; a successful install is not a security audit.
