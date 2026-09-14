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
hardware check and CPU fallback status in **Settings → Storage → Preview processing**.
A detected GPU is not the same as a verified working encoder.

[Preview processing →](SELF_HOSTING.md#preview-processing)

## A share or upload works locally but fails remotely

Open the exact link in a signed-out browser. Check that the host is awake,
storage is connected, the HTTPS origin matches Vue.io's exposure configuration,
and the share permits the intended action.

Check proxy or tunnel upload limits and timeouts. A working small file does
not prove a large delivery fits the intermediary's limits.

## A version is missing from a share

Check the version menu as a project owner or administrator.
**Awaiting publication** and **Internal** versions are not share-visible.
Publish the intended version, then reload the share in a signed-out browser.
A status change or disabling approval does not publish an existing held version.
See [Version publication](REVIEW_WORKFLOW.md#control-which-versions-appear-in-shares).

## A team member cannot see a project or shot

Check both the account's workspace access and the project's team settings.
For a member without **Manage project content**, check shot assignments and the member's workspace folder.
Read-only storage can prevent changes even when the member has project edit permission.
Do not grant administrator access just to hide a missing-permission problem.
See [Project access](WORKSPACE.md#set-project-access).

## Compare is missing or rejects the pair

Enable **Comparison** in the tracker's **Settings** for the intended audience.
Select two videos or two images from the same shot.
Mixed pairs and PDFs are not supported. Both source files must be available.

## An upload reports a limit or low-space error

Check the file size, total upload size, file count, and free space on the destination.
Defaults include 100 GiB per file, 500 GiB per session, and a 20 GiB free-space reserve.
Public requests also have per-link limits.
A proxy or tunnel can reject a transfer before Vue.io receives it.
See [Upload safety limits](SELF_HOSTING.md#upload-safety-limits).

## A voice note has no transcript

Check that the recording was submitted and can play.
Transcription processes one English recording at a time and can wait behind other recordings.
It can fail if the model, media, or processor is unavailable.
An administrator can disable transcription in host configuration.
Do not delete a valid recording merely because its transcript is missing.

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
