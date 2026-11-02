"""Publish a released Home Assistant package to the HACS repository (dielessen/openthermostat-ha).

The HACS repository holds only the integration, exactly as released: the script downloads the
release ZIP of `ha-v<version>`, checks it against HA-SHA256SUMS.txt, replaces
custom_components/open_thermostat with its content, adds hacs.json, a README and the release
workflow, commits, tags `<version>` and (with --push) pushes. The tag's workflow in that
repository makes the GitHub release that HACS offers (a pre-release for a/b/rc versions).

Usage: python -I scripts/publish_hacs_repo.py <version, e.g. 1.0.0rc1> <path of the HACS repo clone> [--push]
"""
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

SOURCE = "https://github.com/dielessen/open_thermostat"
HACS_REMOTE = "https://github.com/dielessen/openthermostat-ha.git"
DOMAIN = "open_thermostat"
MINIMUM_HA = "2026.10.0"

README = """# OpenThermostat for Home Assistant

The Home Assistant integration of [OpenThermostat]({source}): a self-learning room
thermostat on an E32 V2 board that controls an EMS boiler (Nefit, Buderus, Bosch,
Junkers, Worcester) and radiator valves.

This repository only carries the integration for HACS. The firmware, the documentation
and the issue tracker live in the main repository: <{source}>.

## Install with HACS

1. In Home Assistant open **HACS**, the three dots at the top right, **Custom repositories**.
2. Repository: `https://github.com/dielessen/openthermostat-ha`, type **Integration**, **Add**.
3. Find **OpenThermostat** in HACS, **Download**, and restart Home Assistant.
   Release candidates (for example 1.0.0rc1) are pre-releases: open the three dots of
   **OpenThermostat**, **Download** (or **Redownload**), and pick the version under
   **Need a different version?**. To be offered pre-releases as updates, switch on the
   **Pre-release** switch of the OpenThermostat device under **Settings → Devices &
   services → HACS** (enable the entity first).
4. **Settings → Devices & services → Add integration → OpenThermostat**, and follow
   the steps. The installation guide explains everything: <{source}/blob/main/docs/INSTALL.md>.

Requirements: Home Assistant {ha} or newer, an MQTT broker (the MQTT integration), and an
E32 V2 with the OpenThermostat firmware (see the main repository for the firmware and
how to install it).

## Versions

Each version here is exactly the released package `ha-v<version>` of the main repository
(the same files, checked against its SHA-256 list). Release notes: see each release, or
{source}/blob/main/docs/modern-thermostat/HA-RELEASE-NOTES.md.
"""

WORKFLOW = """name: Release
on:
  push:
    tags: ['*']
permissions:
  contents: write
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: GitHub release for HACS
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ github.ref_name }}
        run: |
          pre=""
          case "$TAG" in *a[0-9]*|*b[0-9]*|*rc[0-9]*) pre="--prerelease";; esac
          awk 'NR > 1 && /^# / { exit } { print }' RELEASE-NOTES.md > notes.md  # this version's section only
          gh release create "$TAG" --title "OpenThermostat $TAG" --notes-file notes.md $pre
"""


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def main():
    if len(sys.argv) < 3 or not re.fullmatch(r"\d+\.\d+\.\d+((a|b|rc)\d+)?", sys.argv[1]):
        sys.exit(__doc__)
    version, repo, push = sys.argv[1], Path(sys.argv[2]), "--push" in sys.argv[3:]
    base = f"{SOURCE}/releases/download/ha-v{version}"
    name = f"OpenThermostat-HA-{version}.zip"
    package = fetch(f"{base}/{name}")
    sums = dict(line.split()[::-1] for line in fetch(f"{base}/HA-SHA256SUMS.txt").decode().splitlines() if line.strip())
    digest = hashlib.sha256(package).hexdigest()
    if sums.get(name) != digest:
        sys.exit(f"{name}: SHA-256 {digest} does not match HA-SHA256SUMS.txt")
    archive = zipfile.ZipFile(io.BytesIO(package))
    manifest = json.loads(archive.read(f"custom_components/{DOMAIN}/manifest.json"))
    if manifest["version"] != version:
        sys.exit(f"manifest version {manifest['version']} is not {version}")
    if not (repo / ".git").exists():
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        git(repo, "remote", "add", "origin", HACS_REMOTE)
    target = repo / "custom_components" / DOMAIN
    if target.exists():
        shutil.rmtree(target)
    for member in archive.namelist():
        if member.endswith("/") or not (member.startswith("custom_components/") or member in ("LICENSE", "RELEASE-NOTES.md", "SOURCE.json")):
            continue
        out = repo / member
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(archive.read(member))
    (repo / "hacs.json").write_text(json.dumps({"name": "OpenThermostat", "homeassistant": MINIMUM_HA,
                                                "render_readme": True}, indent=2) + "\n", encoding="utf-8", newline="\n")
    (repo / "README.md").write_text(README.format(source=SOURCE, ha=MINIMUM_HA), encoding="utf-8", newline="\n")
    workflow = repo / ".github" / "workflows" / "release.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(WORKFLOW, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    if git(repo, "status", "--porcelain"):
        git(repo, "commit", "-q", "-m", f"OpenThermostat {version} (ha-v{version}, package SHA-256 {digest})\n\n"
            "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
    if version not in git(repo, "tag", "--list", version).split():
        git(repo, "tag", version)
    print(f"{version}: {git(repo, 'rev-parse', '--short', 'HEAD')}, package {digest}")
    if push:
        git(repo, "push", "-q", "origin", "main")
        git(repo, "push", "-q", "origin", version)
        print("pushed main and tag", version)


if __name__ == "__main__":
    main()
