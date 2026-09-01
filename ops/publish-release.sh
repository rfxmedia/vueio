#!/usr/bin/env bash
set -Eeuo pipefail

PROGRAM=${0##*/}
STABLE_PATTERN='^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-alpha\.(0|[1-9][0-9]*)$'
NIGHTLY_PATTERN='^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-alpha\.(0|[1-9][0-9]*)\.dev\.(0|[1-9][0-9]*)$'
RELEASE_SERIES=${VUEIO_RELEASE_SERIES:-v0.1.0-alpha}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<EOF
Usage:
  $PROGRAM stable --notes-file <notes.md> [--yes]
  $PROGRAM nightly --notes-file <notes.md> [--yes]
  $PROGRAM --print-version <stable|nightly>

Vueio chooses the next unused version automatically. Nightly versions use the
current UTC date plus a sequence number, so more than one can ship each day.
The public nightly branch advances for every release. A Stable release advances
both public branches to the same reviewed commit.
EOF
}

root=$(git rev-parse --show-toplevel 2>/dev/null) || die "Run this inside the sanitized public Vueio repository"
cd "$root"
[[ -f .vueio-public-release-root && ! -e AGENTS.md ]] ||
  die "This command runs only in a reviewed public export, never in the private development repository"

command -v gh >/dev/null 2>&1 || die "GitHub CLI (gh) is required"
command -v git >/dev/null 2>&1 || die "Git is required"

channel=''
notes_file=''
assume_yes=false
print_version=false
while (($#)); do
  case $1 in
    stable|nightly)
      [[ -z $channel ]] || die "Choose exactly one release channel"
      channel=$1
      ;;
    --notes-file)
      shift
      notes_file=${1:-}
      ;;
    --yes) assume_yes=true ;;
    --print-version) print_version=true ;;
    -h|--help) usage; exit 0 ;;
    -*) die "Unknown option: $1" ;;
    *) die "Choose 'stable' or 'nightly'; version numbers are automatic" ;;
  esac
  shift || true
done

[[ $channel == stable || $channel == nightly ]] || {
  usage >&2
  die "Choose the stable or nightly channel"
}
if [[ $RELEASE_SERIES.0 =~ $STABLE_PATTERN ]]; then
  series_major=${BASH_REMATCH[1]}
  series_minor=${BASH_REMATCH[2]}
  series_patch=${BASH_REMATCH[3]}
else
  die "VUEIO_RELEASE_SERIES must look like v0.1.0-alpha"
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  die "Commit or discard all changes before publishing"
fi
[[ -n $(git remote get-url origin 2>/dev/null) ]] || die "The public repository needs an origin remote"
gh auth status >/dev/null 2>&1 || die "Sign in first with: gh auth login"
git fetch --quiet origin --tags
git rev-parse --verify HEAD >/dev/null
[[ $(git branch --show-current) == nightly ]] ||
  die "Publish from the public nightly branch. Stable is a release pointer, not a work branch"
for public_branch in stable nightly; do
  git ls-remote --exit-code --heads origin "refs/heads/$public_branch" >/dev/null 2>&1 ||
    die "The public $public_branch branch is missing"
done

tag_alpha_for_series() {
  local tag=$1
  if [[ $tag =~ $STABLE_PATTERN ]]; then
    :
  elif [[ $tag =~ $NIGHTLY_PATTERN ]]; then
    :
  else
    return 1
  fi
  [[ ${BASH_REMATCH[1]} == "$series_major" &&
     ${BASH_REMATCH[2]} == "$series_minor" &&
     ${BASH_REMATCH[3]} == "$series_patch" ]] || return 1
  printf '%s\n' "${BASH_REMATCH[4]}"
}

next_stable_tag() {
  local tag alpha highest=0
  while IFS= read -r tag; do
    alpha=$(tag_alpha_for_series "$tag") || continue
    ((alpha > highest)) && highest=$alpha
  done < <(git tag --list)
  printf '%s.%s\n' "$RELEASE_SERIES" "$((highest + 1))"
}

next_nightly_tag() {
  local releases tag alpha highest_stable=0 nightly_number date_prefix sequence highest_sequence=0
  releases=$(gh release list --limit 1000 --json tagName,isDraft,isPrerelease \
    --jq '.[] | select(.isDraft == false and .isPrerelease == false) | .tagName') ||
    die "Could not inspect existing stable releases"
  while IFS= read -r tag; do
    [[ -n $tag && $tag =~ $STABLE_PATTERN ]] || continue
    alpha=$(tag_alpha_for_series "$tag") || continue
    ((alpha > highest_stable)) && highest_stable=$alpha
  done <<<"$releases"

  date_prefix=$(date -u +%Y%m%d)
  while IFS= read -r tag; do
    [[ $tag =~ $NIGHTLY_PATTERN ]] || continue
    [[ ${BASH_REMATCH[1]} == "$series_major" &&
       ${BASH_REMATCH[2]} == "$series_minor" &&
       ${BASH_REMATCH[3]} == "$series_patch" &&
       ${BASH_REMATCH[4]} == "$highest_stable" ]] || continue
    nightly_number=${BASH_REMATCH[5]}
    [[ $nightly_number == "$date_prefix"* ]] || continue
    sequence=${nightly_number#"$date_prefix"}
    if [[ -z $sequence ]]; then
      sequence=0
    elif [[ $sequence =~ ^[0-9]{2}$ ]]; then
      sequence=$((10#$sequence))
    else
      continue
    fi
    ((sequence > highest_sequence)) && highest_sequence=$sequence
  done < <(git tag --list)
  ((highest_sequence < 99)) || die "The daily nightly sequence is exhausted; try again tomorrow"
  printf '%s.%s.dev.%s%02d\n' \
    "$RELEASE_SERIES" "$highest_stable" "$date_prefix" "$((highest_sequence + 1))"
}

if [[ $channel == stable ]]; then
  release_tag=$(next_stable_tag)
else
  release_tag=$(next_nightly_tag)
fi

if [[ $print_version == true ]]; then
  [[ -z $notes_file && $assume_yes == false ]] ||
    die "--print-version cannot be combined with publishing options"
  printf '%s\n' "$release_tag"
  exit 0
fi

[[ -f $notes_file && -s $notes_file ]] || die "--notes-file must name a non-empty Markdown file"
grep -Eq '^## (New|Improved|Fixed|Before you update)$' "$notes_file" ||
  die "Release notes need at least one standard heading from docs/RELEASE_NOTES_STYLE.md"

if git rev-parse --verify --quiet "refs/tags/$release_tag" >/dev/null; then
  die "Tag $release_tag already exists and will never be overwritten"
fi
if git ls-remote --exit-code --tags origin "refs/tags/$release_tag" >/dev/null 2>&1; then
  die "Remote tag $release_tag already exists and will never be overwritten"
fi
if gh release view "$release_tag" >/dev/null 2>&1; then
  die "GitHub Release $release_tag already exists"
fi
for gate in VUEIO_DISTRIBUTION_REVIEWED_TAG VUEIO_PRIVATE_CREDENTIALS_ROTATED_TAG; do
  gate_value=$(gh variable get "$gate" --json value --jq .value 2>/dev/null || true)
  [[ $gate_value == "$release_tag" ]] ||
    die "Repository release gate $gate must equal $release_tag before publication"
done

printf 'Release: %s\n' "$release_tag"
printf 'Commit:  %s\n' "$(git rev-parse --short=12 HEAD)"
printf 'Channel: %s\n' "${channel^}"
printf 'Notes:   %s\n\n' "$notes_file"
if [[ $channel == stable ]]; then
  printf 'Branches: Stable and Nightly will point to this commit.\n'
else
  printf 'Branch:   Nightly will point to this commit.\n'
fi
printf 'CI will run the full verification, build and scan both architectures, then publish the release.\n'
if [[ $assume_yes != true ]]; then
  printf 'Type PUBLISH to create and push the immutable tag: '
  read -r confirmation
  [[ $confirmation == PUBLISH ]] || die "Publication cancelled; nothing was changed"
fi

git tag --annotate --cleanup=verbatim "$release_tag" --file "$notes_file"
push_refs=("HEAD:refs/heads/nightly" "refs/tags/$release_tag")
if [[ $channel == stable ]]; then
  push_refs=("HEAD:refs/heads/stable" "HEAD:refs/heads/nightly" "refs/tags/$release_tag")
fi
if ! git push --atomic origin "${push_refs[@]}"; then
  git tag --delete "$release_tag" >/dev/null 2>&1 || true
  die "The public branch and tag were not changed; the local tag was removed"
fi

printf 'Tag pushed. Waiting for the release workflow to appear...\n'
run_id=''
for _ in {1..30}; do
  run_id=$(gh run list \
    --workflow release-images.yml \
    --branch "$release_tag" \
    --limit 1 \
    --json databaseId \
    --jq '.[0].databaseId // empty')
  [[ -z $run_id ]] || break
  sleep 2
done
[[ -n $run_id ]] || die "The tag is pushed, but no release workflow appeared. Inspect GitHub Actions before doing anything else"
gh run watch "$run_id" --exit-status
gh release view "$release_tag" --web
printf 'Published %s. Vueio installations will see it within about 15 minutes or after a manual refresh.\n' "$release_tag"
