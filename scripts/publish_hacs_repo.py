"""Publish a released Home Assistant package to the HACS repository (dielessen/openthermostat-ha).

The HACS repository holds only the integration, exactly as released: the script downloads the
release ZIP of `ha-v<version>`, checks it against HA-SHA256SUMS.txt, replaces
custom_components/open_thermostat with its content, adds hacs.json, the README (the front page
HACS and GitHub show, generated from the README template below) and the release workflow,
commits, tags `<version>` and (with --push) pushes. The tag's workflow in that repository makes
the GitHub release that HACS offers (a pre-release for a/b/rc versions).

--readme-only refreshes just the front page between releases: it rewrites README.md and
hacs.json in the clone (which must be on its main branch), commits them as "README: ..." and,
with --push, pushes main only. No package is downloaded, nothing else changes and no tag is made.
Without --push, nothing leaves the clone: inspect README.md and the commit first.

Usage: python -I scripts/publish_hacs_repo.py <version, e.g. 1.0.0rc1> <path of the HACS repo clone> [--push]
       python -I scripts/publish_hacs_repo.py --readme-only <path of the HACS repo clone> [--push]
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
CO_AUTHOR = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"

# The front page of the HACS repository. Images and links are absolute (the main repository's main
# branch), so they work on GitHub and inside HACS. {source}, {source_raw} (raw files on main) and
# {ha} are filled in by str.format: write a literal brace as {{ or }}.
# One plain <img>: HACS shows <picture>/<source> as text.
README = """<p align="center">
  <img src="{source_raw}/docs/brand/logo.svg" alt="OpenThermostat" width="420">
</p>

# OpenThermostat for Home Assistant

OpenThermostat is a thermostat for your central heating. It runs on a small box
next to your boiler, the BBQKees Gateway E32 V2. Every room gets its own week
program, and the thermostat learns how fast each room warms up, so it is warm
when you want it. Everything stays in your own home, without a cloud account.

This integration brings OpenThermostat into Home Assistant: a thermostat per
room, a week planner card, your boiler's values, energy figures, daily backups
and firmware updates with one click.

## What you need

This integration does not work on its own. You need:

- A **[BBQKees Gateway E32 V2](https://bbqkees-electronics.nl/product/gateway-e32-v2-ethernet-wifi-edition-v2/)**,
  connected to your boiler.
- The **OpenThermostat firmware** on that gateway. You install it once over USB;
  HACS does not do that for you. See
  [installing the firmware]({source}/blob/main/docs/INSTALL.md#2-install-the-firmware-on-the-e32-first-time-over-usb).
  The gateway usually comes with EMS-ESP, which the firmware replaces, so
  [make a backup first]({source}/blob/main/docs/FLASHING.md#make-a-full-backup-first).
- A boiler that speaks **EMS Classic (EMS 1.0)**: most Nefit, Buderus, Bosch,
  Junkers and Worcester boilers. Newer EMS+ boilers are planned for version 1.1.
- An **MQTT broker** (for example the Mosquitto add-on) and the MQTT integration.
- **Home Assistant {ha} or newer.**

## What you get

- A thermostat per room, with Comfort, Eco, Night and Boost.
- A week planner card: drag a time to change it, copy a day to another.
- Away and holiday modes, and automatically lower when everyone has left. Warm again when you come back.
- Window and door contacts that pause a room while a window is open.
- Radiator valves set per room.
- "What the thermostat has learned": per room how fast it warms up and cools
  down, and what it changed by itself, in plain words.
- Your boiler's water temperatures, pressure, burner starts, hot water use and
  display code in words. Problems show up under Repairs.
- Gas use for heating and hot water, if you have a gas meter in Home Assistant.
- A daily backup of all E32 settings, which you can put back on a new E32.
- Firmware updates for the E32 under Settings → Updates.
- A ready-made dashboard, if you want one.
- English, Dutch and Polish.

The E32 is the thermostat itself. It keeps heating your rooms on its own
program when Home Assistant is offline.

## Screenshots

These use made-up example data, not a real home.

![The week planner card in Home Assistant]({source_raw}/docs/img/screenshots/ha-week-card-rc2.png)

![What the thermostat has learned, per room]({source_raw}/docs/img/screenshots/e32-home-learned-rc2.png)

<details>
<summary>More screenshots</summary>

![The E32 Overview with rooms and the boiler]({source_raw}/docs/img/screenshots/e32-overview-rc2.png)

![A room with its week program on the E32]({source_raw}/docs/img/screenshots/e32-rooms-rc2.png)

![The E32 Boiler page]({source_raw}/docs/img/screenshots/e32-boiler-rc2.png)

<img src="{source_raw}/docs/img/screenshots/e32-overview-phone-dark-rc2.png" alt="The E32 Overview on a phone in the dark theme" width="320">

</details>

## Install

1. Put the OpenThermostat firmware on the E32 and connect it to your Wi-Fi and
   your MQTT broker. The
   [installation guide]({source}/blob/main/docs/INSTALL.md#2-install-the-firmware-on-the-e32-first-time-over-usb)
   explains how.
2. In Home Assistant, open **HACS**, the three dots at the top right, then
   **Custom repositories**. Add `https://github.com/dielessen/openthermostat-ha`
   with type **Integration**.
3. Search for **OpenThermostat** in HACS, choose **Download** and restart Home
   Assistant.
4. Go to **Settings → Devices & services → Add integration → OpenThermostat**
   and follow the steps.

The E32 then guides you further. If your old thermostat is still connected, it
first runs beside it for a while without touching the boiler. Otherwise it
starts with a short boiler test. It only controls your boiler after you confirm.

**Test versions** (such as `1.0.0rc2`) are not shown by default. To install one,
open OpenThermostat in HACS, choose **Download** and pick the version under
**Need a different version?**.

## Help and more information

- [Installation guide]({source}/blob/main/docs/INSTALL.md)
- [User guide]({source}/blob/main/docs/USER-GUIDE.md)
- [Switching over from your old thermostat]({source}/blob/main/docs/SWITCHOVER.md)
- [Release notes]({source}/blob/main/docs/modern-thermostat/HA-RELEASE-NOTES.md)
- [The main project]({source}): the firmware, all documentation and the source code

Questions or problems? [Open an issue]({source}/issues) in the main project. It
helps to add the integration's diagnostics (Settings → Devices & services →
OpenThermostat → ⋮ → Download diagnostics) and the E32's firmware version.

OpenThermostat is an independent project. It is not made or supported by
BBQKees Electronics.

## Versions and licence

Each version here is exactly the released package `ha-v<version>` of the main
project, checked against its SHA-256 list.

MIT licence (see [LICENSE](LICENSE)). OpenThermostat started as
[OpenThermostat by Pawel Filipczak / intuibase](https://github.com/intuibase/open_thermostat).
Further development and releases are by Mark Dielessen.
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


def write_front_page(repo):
    """README.md and hacs.json: the files HACS and GitHub show for the repository."""
    (repo / "hacs.json").write_text(json.dumps({"name": "OpenThermostat", "homeassistant": MINIMUM_HA,
                                                "render_readme": True,
                                                "hide_default_branch": True}, indent=2) + "\n", encoding="utf-8", newline="\n")
    readme = README.format(source=SOURCE, source_raw=SOURCE.replace("https://github.com/", "https://raw.githubusercontent.com/") + "/main",
                           ha=MINIMUM_HA)
    (repo / "README.md").write_text(readme, encoding="utf-8", newline="\n")


def readme_only(repo, push):
    if not (repo / ".git").exists():
        sys.exit(f"{repo} is not a clone of the HACS repository")
    if git(repo, "rev-parse", "--abbrev-ref", "HEAD") != "main":
        sys.exit(f"{repo} is not on its main branch")
    write_front_page(repo)
    git(repo, "add", "--", "README.md", "hacs.json")
    if git(repo, "diff", "--cached", "--name-only"):
        git(repo, "commit", "-q", "-m", "README: refresh the front page from the main repository\n\n"
            "Requirements (the BBQKees Gateway E32 V2 with the OpenThermostat firmware), features,\n"
            "screenshots, how it fits together and the install steps.\n\n" + CO_AUTHOR, "--", "README.md", "hacs.json")
        print(f"README: {git(repo, 'rev-parse', '--short', 'HEAD')}")
    else:
        print("README: unchanged, nothing committed")
    if push:
        git(repo, "push", "-q", "origin", "main")
        print("pushed main")


def main():
    flags = {"--push", "--readme-only"}
    args = [a for a in sys.argv[1:] if a not in flags]
    push = "--push" in sys.argv[1:]
    if "--readme-only" in sys.argv[1:]:
        if len(args) != 1:
            sys.exit(__doc__)
        return readme_only(Path(args[0]), push)
    if len(args) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+((a|b|rc)\d+)?", args[0]):
        sys.exit(__doc__)
    version, repo = args[0], Path(args[1])
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
    write_front_page(repo)
    workflow = repo / ".github" / "workflows" / "release.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(WORKFLOW, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    if git(repo, "status", "--porcelain"):
        git(repo, "commit", "-q", "-m", f"OpenThermostat {version} (ha-v{version}, package SHA-256 {digest})\n\n" + CO_AUTHOR)
    if version not in git(repo, "tag", "--list", version).split():
        git(repo, "tag", version)
    print(f"{version}: {git(repo, 'rev-parse', '--short', 'HEAD')}, package {digest}")
    if push:
        git(repo, "push", "-q", "origin", "main")
        git(repo, "push", "-q", "origin", version)
        print("pushed main and tag", version)


if __name__ == "__main__":
    main()
