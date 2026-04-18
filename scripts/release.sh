#!/usr/bin/env bash
# Cut a new local-whisper release end-to-end.
#
# Usage: ./scripts/release.sh X.Y.Z
#
# Does, in order:
#   1. Sanity checks (clean tree, on main, up to date, tag doesn't exist)
#   2. Bumps version in pyproject.toml, setup.sh, src/whisper_voice/cli/build.py
#   3. Rewrites CHANGELOG.md [Unreleased] → [X.Y.Z] - TODAY
#   4. Runs the full test suite
#   5. Shows the diff and waits for confirmation
#   6. Commits, tags vX.Y.Z, pushes main + tag
#   7. Creates the GitHub release with the X.Y.Z CHANGELOG section as notes
#   8. Bumps the homebrew-local-whisper formula tarball url + sha256 and pushes
#
# Requires:
#   - `gh` authed to github.com with push on both repos
#   - homebrew-local-whisper checked out at ../homebrew-local-whisper
#     (override with HOMEBREW_TAP_DIR=/path/to/tap)
#   - .venv with pytest installed for step 4
#
# For dependency-floor bumps (numpy, pynput, pyobjc-*, soundfile, ...) the
# matching `resource` wheel URL + sha256 in the formula still has to be
# refreshed by hand before running this script. Pull from
# https://pypi.org/pypi/<pkg>/json, pick the cp312 macosx_11_0_arm64 wheel.

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "usage: $0 X.Y.Z" >&2
  exit 2
fi

VERSION="$1"
TAG="v${VERSION}"
TODAY="$(date +%Y-%m-%d)"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAP_DIR="${HOMEBREW_TAP_DIR:-${REPO_ROOT}/../homebrew-local-whisper}"

cd "$REPO_ROOT"

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "error: version must be X.Y.Z (got '$VERSION')" >&2
  exit 2
fi

echo "==> Releasing $TAG ($TODAY)"

# 1. Sanity checks
if [ -n "$(git status --porcelain)" ]; then
  echo "error: working tree not clean" >&2
  git status --short
  exit 1
fi

branch="$(git branch --show-current)"
if [ "$branch" != "main" ]; then
  echo "error: must be on main (currently on '$branch')" >&2
  exit 1
fi

git fetch origin --quiet
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
  echo "error: local main is not in sync with origin/main" >&2
  exit 1
fi

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "error: tag $TAG already exists locally" >&2
  exit 1
fi

if git ls-remote --tags origin "refs/tags/$TAG" | grep -q .; then
  echo "error: tag $TAG already exists on origin" >&2
  exit 1
fi

if [ ! -d "$TAP_DIR/.git" ]; then
  echo "error: homebrew tap not found at $TAP_DIR" >&2
  echo "       set HOMEBREW_TAP_DIR or clone gabrimatic/homebrew-local-whisper there" >&2
  exit 1
fi

# 2. Bump version strings
python3 - "$VERSION" <<'PY'
import re, sys, pathlib
version = sys.argv[1]

pyproject = pathlib.Path("pyproject.toml")
text = pyproject.read_text()
text, n = re.subn(r'^version\s*=\s*"[^"]+"', f'version = "{version}"', text, count=1, flags=re.M)
if n != 1:
    raise SystemExit("failed to rewrite pyproject.toml version")
pyproject.write_text(text)

for path in [pathlib.Path("setup.sh"), pathlib.Path("src/whisper_voice/cli/build.py")]:
    t = path.read_text()
    # Replace CFBundleVersion and CFBundleShortVersionString (same shape, both bump)
    t, n = re.subn(
        r'(<key>CFBundle(?:Short)?Version(?:String)?</key>\s*<string>)[0-9]+\.[0-9]+\.[0-9]+(</string>)',
        rf'\g<1>{version}\g<2>',
        t,
    )
    if n < 2:
        raise SystemExit(f"failed to rewrite bundle versions in {path} (replaced {n})")
    path.write_text(t)
PY

# 3. Rewrite CHANGELOG [Unreleased] → [X.Y.Z] - TODAY
python3 - "$VERSION" "$TODAY" <<'PY'
import re, sys, pathlib
version, today = sys.argv[1], sys.argv[2]
path = pathlib.Path("CHANGELOG.md")
text = path.read_text()
if f"## [{version}]" in text:
    print(f"note: CHANGELOG already has a [{version}] section; leaving it alone")
else:
    text, n = re.subn(r"^## \[Unreleased\].*$", f"## [{version}] - {today}", text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit("failed to find [Unreleased] heading in CHANGELOG.md")
    path.write_text(text)
PY

# 4. Full test suite
if [ -x ".venv/bin/python" ]; then
  echo "==> Running tests"
  .venv/bin/python -m pytest tests/ -q
else
  echo "warning: .venv/bin/python not found, skipping test run" >&2
fi

# 5. Confirm
echo
echo "==> Pending changes:"
git --no-pager diff --stat
echo
read -r -p "Proceed with commit + tag + push? [y/N] " reply
if [[ ! "$reply" =~ ^[Yy]$ ]]; then
  echo "aborted"
  exit 1
fi

# 6. Commit, tag, push
git add pyproject.toml setup.sh src/whisper_voice/cli/build.py CHANGELOG.md
git commit -m "chore: release $TAG"
git tag -a "$TAG" -m "$TAG"
git push origin main
git push origin "$TAG"

# 7. GitHub release
notes_file="$(mktemp -t lw-release-notes-XXXX).md"
python3 - "$VERSION" "$notes_file" <<'PY'
import re, sys, pathlib
version, out = sys.argv[1], sys.argv[2]
text = pathlib.Path("CHANGELOG.md").read_text()
m = re.search(rf"## \[{re.escape(version)}\][^\n]*\n(.*?)(?=\n## \[|\Z)", text, re.DOTALL)
if not m:
    raise SystemExit(f"no CHANGELOG section found for {version}")
pathlib.Path(out).write_text(m.group(1).strip() + "\n")
PY
gh release create "$TAG" --title "$TAG" --notes-file "$notes_file"
rm -f "$notes_file"

# 8. Homebrew formula bump
echo "==> Bumping homebrew formula in $TAP_DIR"
tarball_url="https://github.com/gabrimatic/local-whisper/archive/refs/tags/${TAG}.tar.gz"
tmp_tarball="$(mktemp -t lw-tarball-XXXX).tar.gz"
for attempt in 1 2 3 4 5; do
  if curl -fsSL "$tarball_url" -o "$tmp_tarball"; then
    break
  fi
  sleep 3
done
new_sha="$(shasum -a 256 "$tmp_tarball" | awk '{print $1}')"
rm -f "$tmp_tarball"

(
  cd "$TAP_DIR"
  git fetch origin --quiet
  git checkout main
  git pull --ff-only
  python3 - "$tarball_url" "$new_sha" <<'PY'
import os, pathlib, re, sys
new_url, new_sha = sys.argv[1], sys.argv[2]
path = pathlib.Path("Formula/local-whisper.rb")
text = path.read_text()
text, n1 = re.subn(
    r'url "https://github\.com/gabrimatic/local-whisper/archive/refs/tags/v[^"]+"',
    f'url "{new_url}"',
    text, count=1,
)
text, n2 = re.subn(
    r'(url "https://github\.com/gabrimatic/local-whisper/archive/refs/tags/[^"]+"\n\s*sha256 ")[^"]+(")',
    rf'\g<1>{new_sha}\g<2>',
    text, count=1,
)
if n1 != 1 or n2 != 1:
    raise SystemExit(f"unexpected substitution counts: url={n1}, sha={n2}")
path.write_text(text)
PY
  if git diff --quiet; then
    echo "formula already up to date"
  else
    git add Formula/local-whisper.rb
    git commit -m "local-whisper $VERSION"
    git push
  fi
)

echo
echo "==> Done."
echo "    Release: https://github.com/gabrimatic/local-whisper/releases/tag/$TAG"
echo "    Formula: https://github.com/gabrimatic/homebrew-local-whisper/blob/main/Formula/local-whisper.rb"
