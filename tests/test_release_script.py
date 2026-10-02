"""Release gates must stop before publishing an unverified tag."""

import os
import shutil
import subprocess
from pathlib import Path


def _release_checkout(tmp_path, *, with_tests):
    root = tmp_path / "app"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(Path(__file__).resolve().parents[1] / "scripts/release.sh", scripts / "release.sh")
    (root / "pyproject.toml").write_text('version = "1.10.1"\n')
    (root / "CHANGELOG.md").write_text("## [Unreleased]\n\n- Fixed recording.\n")
    plist = "<key>CFBundleVersion</key><string>1.10.1</string>\n<key>CFBundleShortVersionString</key><string>1.10.1</string>\n"
    (root / "setup.sh").write_text(plist)
    build = root / "src/whisper_voice/cli/build.py"
    build.parent.mkdir(parents=True)
    build.write_text(plist)
    mobile = root / "src/flutter/local_whisper"
    keyboard = mobile / "ios/LocalWhisperKeyboard/Info.plist"
    keyboard.parent.mkdir(parents=True)
    keyboard.write_text(
        "<plist><dict><key>CFBundleShortVersionString</key><string>1.0.0</string><key>CFBundleVersion</key><string>1</string></dict></plist>"
    )
    (mobile / "pubspec.yaml").write_text("version: 1.0.0+1\n")
    tap = tmp_path / "tap"
    (tap / ".git").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    trace = tmp_path / "commands.txt"
    git = bin_dir / "git"
    git.write_text("""#!/bin/sh
printf '%s\n' "git $*" >> "$RELEASE_TEST_TRACE"
case "$1 $2" in
  'branch --show-current') echo main ;;
  'rev-parse HEAD'|'rev-parse origin/main') echo abc123 ;;
  rev-parse*) exit 1 ;;
esac
""")
    git.chmod(0o755)
    gh = bin_dir / "gh"
    gh.write_text("""#!/bin/sh
printf '%s\n' "gh $*" >> "$RELEASE_TEST_TRACE"
case "$1 $2" in
  'run list') echo 42 ;;
  *) exit 1 ;;
esac
""")
    gh.chmod(0o755)
    if with_tests:
        python = root / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        python.write_text("#!/bin/sh\nexit 0\n")
        python.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOMEBREW_TAP_DIR": str(tap),
        "RELEASE_TEST_TRACE": str(trace),
    }
    return root, env, trace


def test_missing_test_environment_stops_before_version_mutation(tmp_path):
    root, env, _ = _release_checkout(tmp_path, with_tests=False)

    result = subprocess.run(
        ["bash", "scripts/release.sh", "1.11.0"],
        cwd=root,
        env=env,
        input="n\n",
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert result.returncode != 0
    assert (root / "pyproject.toml").read_text() == 'version = "1.10.1"\n'


def test_failed_branch_ci_does_not_create_or_push_release_tag(tmp_path):
    root, env, trace = _release_checkout(tmp_path, with_tests=True)

    result = subprocess.run(
        ["bash", "scripts/release.sh", "1.11.0"],
        cwd=root,
        env=env,
        input="y\n",
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert result.returncode != 0
    commands = trace.read_text().splitlines()
    assert "git push origin main" in commands
    assert not any(command.startswith("git tag -a") for command in commands)
    assert not any(command.startswith("git push origin v") for command in commands)
    assert not any(command.startswith("gh release create") for command in commands)
