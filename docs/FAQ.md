# Frequently asked questions

## Is this really free?

The self-hosted software is free under the [PolyForm Perimeter License 1.0.1](../LICENSE.md).
Vue.io does not charge per seat or sell you a cloud-storage allowance for
this edition. You supply hardware, storage, electricity, networking, and backups.

## Is Vue.io open source?

It is **source-available**, not open source under the OSI definition. You can
inspect the source. The license permits use, modification, and distribution
for purposes that do not compete with the software. Read the license for
its terms; free self-hosting does not mean unrestricted commercial reuse.

## How should I think about the Frame.io comparison?

Vue.io is an independent, self-hosted alternative for familiar media review,
version history, feedback, and delivery workflows. It also brings shot
tracking, project pages, files, and selected local storage into the workspace.

It is not Frame.io, is not affiliated with Adobe, and does not promise identical
features, native integrations, enterprise support, or automatic migration.
Check the workflow you need before moving an active project.

## Does version history mean Git?

No. It means revisions of a shot or media item in the review workspace. It
does not merge creative application files or replace source-code version control.

## Can I install it on Mac or Windows?

Linux x86-64 and ARM64 are the primary alpha host platforms. Apple Silicon
has an experimental installer; full sleep/wake, login startup, and upgrade
validation remain incomplete. Intel Mac and native Windows installers are
not supported yet. This is separate from viewing Vue.io in a browser.

[Mac preview requirements →](SELF_HOSTING.md#mac-installer-preview)

## Can I use a NAS or an external SSD?

Yes, for media mounted and explicitly available to the supported host. A NAS
brand or attached USB drive does not automatically mean that device can run
Vue.io. The database has stricter filesystem requirements than media.

[Storage guide →](STORAGE_OPERATIONS.md)

## Is my media copied into someone else's cloud?

The self-hosted engine reads authorized storage and generates local working
files and previews. A review link serves media from your host; it does not
create an independent cloud backup. Remote recipients receive the media
needed for playback or permitted downloads.

## Will a link work when my computer is asleep?

Not if that computer is the host. The host, storage, and network must stay
available. Remote access also needs your HTTPS proxy, VPN, or tunnel.

## Is there a hosted service or one-click public tunnel?

This repository distributes the self-hosted alpha. Managed hosting and a
built-in public tunnel are not included. Setup does not create DNS, HTTPS
certificates, or an external connection for you.

## Is it production-ready?

It is a public alpha, developed through real production use but not verified
for every environment. Begin with trusted users and non-sensitive sample media.
Read current release notes, including security findings, and keep independent
backups before putting important work on it.

## Was it built with AI?

Vue.io uses human-directed, AI-assisted engineering. Release notes
describe changes and limitations; reproducible reports help improve it.
AI-assisted development is not itself a reliability or security guarantee.

## Does the backup include my videos?

No. `vueioctl backup` archives the database only. Back up media, uploads,
attachments, app files, and private configuration separately.

## Where do I ask for help?

Start with [troubleshooting](TROUBLESHOOTING.md), then open a
[GitHub issue](https://github.com/rfxmedia/vueio/issues) with a redacted,
reproducible description. The alpha does not promise a support SLA or private
installation service. Use the [security policy](../SECURITY.md) for vulnerabilities.
