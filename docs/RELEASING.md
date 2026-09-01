# Publishing Vueio releases

Publishing is performed from the reviewed, sanitized public repository—not
from the private development repository. The export process places a marker in
that tree; `ops/publish-release.sh` refuses to run without it.

Before beginning, complete the private release checklist, export the exact
reviewed commit, run the independent redacted secret scan, and commit the
sanitized public snapshot on the public `nightly` branch. Configure the
required per-tag repository variables described by the release checklist.
Install and authenticate GitHub CLI with `gh auth login`.

The public repository has two branches. `stable` is the default branch and
shows the latest Stable source. `nightly` shows the latest Nightly source. The
private repository is never a remote and its history is never copied.

Write the GitHub/in-app changelog in a temporary Markdown file using
`docs/RELEASE_NOTES_STYLE.md`. Do not commit a one-off notes file. The release
command chooses the version; operators never enter or increment version
numbers manually.

## Stable

Run:

```bash
ops/publish-release.sh stable --notes-file /tmp/vueio-stable.md
```

The command increments the immutable `vX.Y.Z-alpha.N` version automatically.
The resulting GitHub Release is not marked prerelease, even though the product
is still an alpha. The command advances both `stable` and `nightly` to the same
reviewed commit.

## Nightly

Run:

```bash
ops/publish-release.sh nightly --notes-file /tmp/vueio-nightly.md
```

The command uses the latest published stable release as its base and appends
the UTC date plus a daily sequence, such as
`v0.1.0-alpha.8.dev.2026080501`. CI marks the GitHub Release prerelease, and up
to 99 immutable nightlies can be published each day without reusing a tag. The
command advances only the public `nightly` branch.

To preview the version needed by the per-tag release gates without publishing:

```bash
ops/publish-release.sh --print-version nightly
ops/publish-release.sh --print-version stable
```

## What the command does

The command requires a clean public `nightly` worktree, checks GitHub
authentication, chooses an unused version, and confirms both per-tag release
gates before an immutable tag can be created. It shows the exact
commit/channel/notes and requires typing `PUBLISH`. It atomically pushes the
release tag with the correct public branch pointers. GitHub Actions then runs
verification, builds and scans the AMD64 and ARM64 images, creates checksummed
assets and SBOMs, and publishes the GitHub Release only after every gate
succeeds. The command waits for that workflow and opens the finished release.

If CI fails, the immutable tag remains as evidence of the failed attempt and
no GitHub Release is published. Fix the problem and choose a new version; do
not delete or reuse a tag that reached the public remote.

**Pushing ordinary commits does nothing to installed users. Only publishing a
GitHub Release makes an update visible in Vueio.** The in-app cache refreshes
within about 15 minutes, or immediately when an owner presses **Check Again**.
