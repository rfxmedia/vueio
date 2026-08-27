# Vueio release notes

The GitHub Release body is also the changelog owners read inside Vueio. Write
for the person running a media workspace, not for the people who authored the
commits.

Use these headings when they apply:

- **New** — capabilities users can now rely on.
- **Improved** — visible workflow, performance, or reliability changes.
- **Fixed** — user-facing problems that are resolved.
- **Before you update** — required preparation, known limitations, migration
  time, or behavior that may surprise an owner.

Keep each item short and concrete. Say what changed and why it matters. Avoid
commit hashes, internal component names, issue-tracker shorthand, marketing
claims, and raw test output. If no preparation is required, write “Nothing —
the updater handles this release automatically.”

Rollback must be described honestly whenever migrations or compatibility are
relevant: `vueioctl rollback` restores the pre-update backup, so Vueio data
created after that backup is lost. Project files and media are not modified.
