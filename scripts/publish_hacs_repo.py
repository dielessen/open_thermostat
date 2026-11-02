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
README = """<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="{source_raw}/docs/brand/dark_logo.svg">
    <img src="{source_raw}/docs/brand/logo.svg" alt="OpenThermostat" width="420">
  </picture>
</p>

# OpenThermostat for Home Assistant

OpenThermostat is a self-learning room thermostat for EMS boilers (Nefit, Buderus, Bosch,
Junkers, Worcester). It runs on a **BBQKees Gateway E32 V2** connected to your boiler: every
room gets its own week program, the thermostat learns how each room warms up so it is warm on
time, and it tunes itself to your house. Everything runs locally on your own network, with no
cloud account. This integration brings it into Home Assistant: a thermostat per room, a visual
week planner, boiler values, energy, backups and firmware updates.

> **What you need**
>
> This integration does nothing on its own. It works only together with a **BBQKees Gateway
> E32 V2 that runs the OpenThermostat firmware**.
>
> - A **[BBQKees Gateway E32 V2](https://bbqkees-electronics.nl/product/gateway-e32-v2-ethernet-wifi-edition-v2/)**
>   ([BBQKees wiki](https://bbqkees-electronics.nl/wiki/)), connected to your boiler's EMS bus.
> - The **OpenThermostat firmware** on that gateway, installed once over USB:
>   [install the firmware]({source}/blob/main/docs/INSTALL.md#2-install-the-firmware-on-the-e32-first-time-over-usb).
>   HACS does not install it. The gateway usually comes with EMS-ESP, which this firmware
>   replaces: [make a backup first]({source}/blob/main/docs/FLASHING.md#make-a-full-backup-first).
> - A boiler that speaks **EMS Classic (EMS 1.0)**, directly or through an adapter such as the
>   Bosch EasyControl Adapter. EMS+ (EMS 2.0) boilers are not supported yet (planned for 1.1).
> - An **MQTT broker** (for example the Mosquitto broker add-on) and Home Assistant's
>   **MQTT integration**.
> - **Home Assistant {ha} or newer**.

## Features

- **A week program per room.** Up to 8 rooms, each with its own program at Comfort, Eco and
  Night levels, edited in a visual planner in Home Assistant or on the E32. The E32 runs the
  programs itself, also when Home Assistant is offline.
- **Warm on time.** The thermostat learns how fast each room warms up and cools down, starts
  heating early enough for the next program time, and can use the coolest water that still
  gets the room warm in time.
- **Self-tuning.** It adjusts its own settings (burner rest and run times, when to start and
  stop heating) by at most one small step a day. "What the thermostat learned" explains every
  figure and change in plain language.
- **Presence and away.** House mode Automatic (by presence), At home, Away, or Holiday until
  a date, warm again in time; persons per room.
- **Windows and doors.** Contacts in Home Assistant pause a room while they are open; frost
  protection stays.
- **A thermostat per room** in Home Assistant, with the presets Comfort, Eco, Night and Boost
  and temporary changes that end by themselves.
- **Radiator valves** through Home Assistant climate entities, set to the program's temperature.
- **Bluetooth thermometers** that the E32 receives itself, as a room's sensor or as a fallback.
- **Hot water.** Hot water today, split into tapping and keeping warm, also as gas.
- **Boiler diagnostics.** Water temperatures, pressure, burner starts with a short-cycling
  warning, and the boiler's display code in words. Problems appear under Repairs.
- **Energy and gas.** Optional gas meter, gas price and outdoor temperature: gas for heating
  and for hot water per day, a daily summary, and heating advice that never changes a setting.
- **Backup and restore.** Home Assistant keeps a daily backup of the E32 settings (the last
  7 days) and restores one onto the same or a replacement E32.
- **Firmware updates from Home Assistant.** The E32 firmware appears under Settings → Updates
  and installs with one click; a firmware that does not start properly rolls back by itself.
- **Ready-made dashboard** (optional) and a week planner card; no YAML needed.
- **English, Dutch and Polish** in Home Assistant; the E32's own pages in English and Dutch.

## Screenshots

Rendered with fictitious demonstration data, not captures of a real home.

**Week planner card in Home Assistant**: drag the switch times, tap a block to change it, copy
a day.

![The week planner card with a week program per room]({source_raw}/docs/img/screenshots/ha-week-card-rc2.png)

**What the thermostat has learned** (E32 Home page): per room how fast it warms and cools, the
lowest water temperature that still warms it in time, and when it starts heating.

![What the thermostat has learned, per room and for the house]({source_raw}/docs/img/screenshots/e32-home-learned-rc2.png)

**E32 Overview**: the rooms with their last 24 hours, the boiler and its history.

![E32 Overview with rooms, the boiler and the boiler history]({source_raw}/docs/img/screenshots/e32-overview-rc2.png)

<details>
<summary>More screenshots: Rooms, Boiler and the Overview on a phone</summary>

![E32 Rooms page with a room's week program]({source_raw}/docs/img/screenshots/e32-rooms-rc2.png)

![E32 Boiler page with current values and hot water today]({source_raw}/docs/img/screenshots/e32-boiler-rc2.png)

<img src="{source_raw}/docs/img/screenshots/e32-overview-phone-dark-rc2.png" alt="E32 Overview on a phone, dark theme" width="320">

</details>

## How it fits together

```text
 Boiler  <-- EMS bus -->  BBQKees Gateway E32 V2  <--  Bluetooth thermometers (optional)
                          with OpenThermostat firmware
                              |                  |
                         MQTT | live values      | local HTTP: rooms, week programs,
                              |                  | backups, firmware updates
                         MQTT broker             |
                              |                  |
                              v                  v
                     Home Assistant with this integration
```

The **E32 is the thermostat**. Rooms, week programs, Bluetooth thermometers, learning, frost
protection and the boiler control run on the gateway, also without Home Assistant, and it has
its own web pages (Overview, Rooms, Home, Boiler, System). **Home Assistant adds** temperature
sensors and thermostats you already have as room sources, presence, window contacts, energy
inputs, advice, dashboards, daily backups and one-click firmware updates. Live values travel
over MQTT; settings, backups and updates go directly to the E32 over your local network.

A new E32 that still hears your old thermostat on the boiler bus starts with a **trial run**:
it calculates and compares, but sends nothing to the boiler. It takes over only after a guided
boiler test and your confirmation; see
[the attended switch-over]({source}/blob/main/docs/SWITCHOVER.md).

## Install

**Step 1. The firmware on the E32 (not through HACS).** HACS installs only this Home Assistant
integration. Put the OpenThermostat firmware on the E32 once over USB, connect it to your
Wi-Fi and your MQTT broker:
[installation guide, sections 2 to 8]({source}/blob/main/docs/INSTALL.md#2-install-the-firmware-on-the-e32-first-time-over-usb).
After that, firmware updates come through Home Assistant (Settings → Updates).

**Step 2. The integration with HACS.**

1. In Home Assistant open **HACS**, the three dots at the top right, **Custom repositories**.
2. Repository `https://github.com/dielessen/openthermostat-ha`, type **Integration**, **Add**.
3. Search HACS for **OpenThermostat**, open it and choose **Download**. Restart Home Assistant.

Pre-releases (such as `1.0.0rc2`) are not offered by default. To install one, open the three
dots of **OpenThermostat** in HACS, choose **Download** (or **Redownload**), and pick the
version under **Need a different version?**. To be offered pre-releases as updates, open
**Settings → Devices & services → HACS**, the **OpenThermostat** device, enable its
**Pre-release** switch entity and switch it on.

**Step 3. Add the integration.** **Settings → Devices & services → Add integration →
OpenThermostat**, then **Configure → E32 connection** with the E32's address and password, and
add your rooms. The E32 then leads you through the next step: a trial run beside your old
thermostat when it hears one on the boiler bus, otherwise the guided boiler test.
[Installation guide, sections 9 to 12]({source}/blob/main/docs/INSTALL.md#9-install-the-home-assistant-integration).

## Documentation

- [Installation guide]({source}/blob/main/docs/INSTALL.md): from a new E32 to a working setup
- [User guide]({source}/blob/main/docs/USER-GUIDE.md): where to set what, rooms, away, learning, backups
- [Attended switch-over]({source}/blob/main/docs/SWITCHOVER.md): letting the E32 control the boiler
- [USB backup and recovery]({source}/blob/main/docs/FLASHING.md), including going back to EMS-ESP
- [Home Assistant release notes]({source}/blob/main/docs/modern-thermostat/HA-RELEASE-NOTES.md)
- [The main repository]({source}): the firmware, all documentation and the source

## Support

Questions and problems: [open an issue]({source}/issues) in the main repository. This
repository only carries the integration for HACS. Please add the integration's diagnostics
(**Settings → Devices & services → OpenThermostat → ⋮ → Download diagnostics**) and the E32
firmware version.

OpenThermostat is an independent project; it is not made or supported by BBQKees Electronics.

## Versions and licence

Each version here is exactly the released package `ha-v<version>` of the main repository
(the same files, checked against its SHA-256 list). Release notes: see each release, or
<{source}/blob/main/docs/modern-thermostat/HA-RELEASE-NOTES.md>.

MIT licence (see [LICENSE](LICENSE)). OpenThermostat derives from
[OpenThermostat by Pawel Filipczak / intuibase](https://github.com/intuibase/open_thermostat);
further development and releases by Mark Dielessen.
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
                                                "render_readme": True}, indent=2) + "\n", encoding="utf-8", newline="\n")
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
