# Troubleshooting

Start with the installed release, host platform, and first failing step.
Avoid changing storage or reinstalling until you understand the failure.

## The installer says Docker is missing

Install Docker Engine and Compose v2 on the Linux host, then confirm:

```bash
docker --version
docker compose version
```

Make sure Docker is running. Retry only after the missing prerequisite is
resolved. If an earlier attempt created installation state, read its recovery
output rather than removing the directory.

## The page will not open from another computer

Vue.io listens on the server's loopback address by default. Your computer's
`127.0.0.1` is not that server. Use the [SSH tunnel](GETTING_STARTED.md#3-open-the-workspace)
for setup or configure an [HTTPS endpoint](SELF_HOSTING.md#internet-exposure).

On the Linux host, check:

```bash
sudo vueioctl status
sudo vueioctl doctor
```

Do not expose the raw HTTP port to the internet to solve a connection problem.

## I lost the setup code

Run `sudo vueioctl setup-info` on the Linux host. It shows the browser address
and private setup code. Do not post the output publicly.

## A drive or folder is missing

Confirm the drive is attached and mounted on the host, not only the computer
viewing Vue.io. In **Settings → Storage**, use **Check again** where available.
Confirm the directory and access permissions.

If identity checks fail, reconnect the original drive. Do not remove the
marker, fabricate a replacement, or initialize a new database to silence the error.

## Media will not play or is still processing

Check that the source file is present and nonempty, storage is online, and
the host has free disk space. Large files need time and CPU resources to
create previews. A file extension alone does not guarantee codec support.

CPU processing is the default. If you enabled GPU processing, review its
hardware check and CPU fallback status in **Settings → Storage & previews**.
A detected GPU is not the same as a verified working encoder.

[Preview processing →](SELF_HOSTING.md#preview-processing)

## A share or upload works locally but fails remotely

Open the exact link in a signed-out browser. Check that the host is awake,
storage is connected, the HTTPS origin matches Vue.io's exposure configuration,
and the share permits the intended action.

Check proxy or tunnel upload limits and timeouts. A working small file does
not prove a large delivery fits the intermediary's limits.

## Settings cannot install an update

Confirm you are an administrator on an installer-managed installation. Older
hosts need [one-time updater setup](SELF_HOSTING.md#enable-updates-on-an-existing-installation).
Read the displayed stage and private log before retrying. Do not start a
second maintenance operation while one is active.

## Report a reproducible problem

[Open an issue](https://github.com/rfxmedia/vueio/issues) with:

- the release shown by `vueioctl version`;
- host OS and architecture;
- the action, expected result, and actual result;
- short reproduction steps; and
- a redacted error or synthetic screenshot, if useful.

Review logs before sharing. Remove credentials, setup codes, private paths,
personal information, and client media. Never post database backups.
Report vulnerabilities privately using the [security policy](../SECURITY.md).
