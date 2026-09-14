# Vue.io documentation

A free, self-hosted alternative to Frame.io. Review versions, track shots,
and deliver files from storage you control.

[Open the documentation site →](https://rfxmedia.github.io/vueio/)

## Start here

- [Get started](GETTING_STARTED.md): host requirements, installation, and first login.
- [Review workflow](REVIEW_WORKFLOW.md): projects, trackers, versions, and feedback.
- [Workspace and team](WORKSPACE.md): accounts, access, dashboards, notifications, and agent keys.
- [Sharing and delivery](SHARING.md): review links, downloads, and file requests.
- [Storage and operations](STORAGE_OPERATIONS.md): media locations, updates, and backups.
- [Troubleshooting](TROUBLESHOOTING.md): practical answers when something stops working.
- [FAQ](FAQ.md): costs, licensing, platforms, and the Frame.io comparison.
- [Administrator reference](SELF_HOSTING.md): the full installation and maintenance guide.

## Version covered

These guides describe **v0.1.0-alpha.13**. Check your installed version in **Settings → Updates**.
Read the release notes if your version differs.

## Before using the alpha

Linux is the primary host platform. Apple Silicon Mac hosting is experimental;
native Windows and Intel Mac installers are not available. Use trusted users
and test media first. Read the [current release notes](https://github.com/rfxmedia/vueio/releases/latest)
and keep independent backups of both the database and files.

## Improve this guide

Each guide is a Markdown file in this directory. Edit the Markdown, not the
generated HTML. Rebuild the static site before committing:

```bash
cd docs
npm ci
npm run build
```

Commit the guide and regenerated site files together. The documentation site
needs no application server, database, analytics service, or third-party fonts.
