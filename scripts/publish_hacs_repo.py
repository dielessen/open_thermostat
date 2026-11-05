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

Before anything is written the script checks that the folder is a clone of the HACS repository: its origin is
HACS_REMOTE, it is on main without uncommitted changes, and it is not a project worktree (platformio.ini, ha/config
or src/ would mean the main repository, whose README and files this script must never replace). A new folder is
created with that origin.

The commits end with a Co-Authored-By line only when --co-author "Name <email>" (or OT_CO_AUTHOR) is given. The
front page shows the version being published as its example of a test version, and the screenshots of the newest
complete sets in docs/img/screenshots: the E32 pages with the week card (--screenshots) and the dashboard
(--dashboard-screenshots, the ha-dashboard-*.png pictures of tools/dev/ha-demo); --example-version overrides the version.

Usage: python -I scripts/publish_hacs_repo.py <version, e.g. 1.0.0rc1> <path of the HACS repo clone> [--push]
           [--co-author "Name <email>"] [--screenshots rc4] [--dashboard-screenshots rc5] [--example-version 1.0.0rc1]
       python -I scripts/publish_hacs_repo.py --readme-only <path of the HACS repo clone> [--push] [same options]
"""
import argparse
import hashlib
import io
import json
import os
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
PROJECT_MARKERS = ("platformio.ini", "ha/config", "src")  # present in the main repository, never in the HACS one
SCREENSHOTS = ("ha-week-card", "e32-home-learned", "e32-overview", "e32-rooms", "e32-boiler", "e32-overview-phone-dark")
# The generated Home Assistant dashboard (rc.5), photographed in a real Home Assistant by tools/dev/ha-demo; its own
# set, because the E32 pages above and the dashboard are renewed at different times.
DASHBOARD = ("ha-dashboard", "ha-dashboard-boiler", "ha-dashboard-learning", "ha-dashboard-phone-dark")

# The front page of the HACS repository. Images and links are absolute (the main repository's main
# branch), so they work on GitHub and inside HACS. {source}, {source_raw} (raw files on main) and
# {ha}, {example} (the version of a test release), {shots} (the screenshot set of the E32 pages and the week card,
# e.g. rc4) and {dash} (the dashboard set, e.g. rc5) are filled in by str.format: write a literal brace as {{ or }}.
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

![The OpenThermostat dashboard in Home Assistant: the house card, the rooms, today and the house]({source_raw}/docs/img/screenshots/ha-dashboard-{dash}.png)

![The week planner card in Home Assistant]({source_raw}/docs/img/screenshots/ha-week-card-{shots}.png)

![What the thermostat has learned, per room]({source_raw}/docs/img/screenshots/e32-home-learned-{shots}.png)

<details>
<summary>More screenshots</summary>

![The Boiler tab: what the boiler does now, then what you need first]({source_raw}/docs/img/screenshots/ha-dashboard-boiler-{dash}.png)

![The Learning tab: what the E32 knows, the heating curve and yesterday in figures]({source_raw}/docs/img/screenshots/ha-dashboard-learning-{dash}.png)

![The E32 Overview with rooms and the boiler]({source_raw}/docs/img/screenshots/e32-overview-{shots}.png)

![A room with its week program on the E32]({source_raw}/docs/img/screenshots/e32-rooms-{shots}.png)

![The E32 Boiler page]({source_raw}/docs/img/screenshots/e32-boiler-{shots}.png)

<img src="{source_raw}/docs/img/screenshots/ha-dashboard-phone-dark-{dash}.png" alt="The dashboard on a phone in the dark theme" width="320">
<img src="{source_raw}/docs/img/screenshots/e32-overview-phone-dark-{shots}.png" alt="The E32 Overview on a phone in the dark theme" width="320">

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

**Test versions** (such as `{example}`) are not shown by default. To install one,
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


def normal_remote(url):
    return re.sub(r"(\.git)?/*$", "", url.strip()).lower()


def check_clone(repo, remote=HACS_REMOTE):
    """R5-16: refuse anything that is not a clean clone of the HACS repository on main, before any write.

    `git add -A`, a tag and a push in the wrong folder would replace the README of a project worktree (there are
    dozens) or publish unrelated changes."""
    repo = Path(repo)
    try:
        origin = git(repo, "remote", "get-url", "origin")
    except subprocess.CalledProcessError:
        sys.exit(f"{repo} has no origin remote; expected a clone of {remote}")
    if normal_remote(origin) != normal_remote(remote):
        sys.exit(f"{repo}: origin is {origin}, not {remote}: this is not the HACS repository clone")
    present = [marker for marker in PROJECT_MARKERS if (repo / marker).exists()]
    if present:
        sys.exit(f"{repo} contains {', '.join(present)}: that is the main project, not the HACS repository")
    if git(repo, "rev-parse", "--abbrev-ref", "HEAD") != "main":
        sys.exit(f"{repo} is not on its main branch")
    if git(repo, "status", "--porcelain"):
        sys.exit(f"{repo} has uncommitted changes; commit or discard them first (the script stages everything)")


def co_author_trailer(value):
    """R5-17: the trailer of the commits comes from the session, not from this script. None: no trailer."""
    if not value:
        return ""
    if not re.fullmatch(r"[^<>\r\n]+ <[^<>\s@]+@[^<>\s]+>", value.strip()):
        sys.exit(f"--co-author needs the form 'Name <email>', not {value!r}")
    return "\n\nCo-Authored-By: " + value.strip()


def screenshot_sets(directory, names=SCREENSHOTS):
    """The suffixes (rc2, rc4 ...) for which every screenshot in `names` exists in `directory`."""
    directory = Path(directory)
    found = []
    for path in directory.glob(f"{names[0]}-*.png"):
        suffix = path.stem[len(names[0]) + 1:]
        if all((directory / f"{name}-{suffix}.png").exists() for name in names):
            found.append(suffix)

    def order(suffix):
        match = re.fullmatch(r"(alpha|beta|rc)(\d+)", suffix)
        return (("alpha", "beta", "rc").index(match.group(1)), int(match.group(2))) if match else (-1, 0)
    return sorted(found, key=order)


def default_screenshots(names=SCREENSHOTS, option="--screenshots"):
    sets = screenshot_sets(Path(__file__).resolve().parents[1] / "docs" / "img" / "screenshots", names)
    if not sets:
        sys.exit(f"no complete screenshot set {names[0]}-*.png in docs/img/screenshots; give {option}")
    return sets[-1]


def write_front_page(repo, example_version, screenshots, dashboard):
    """README.md and hacs.json: the files HACS and GitHub show for the repository."""
    (repo / "hacs.json").write_text(json.dumps({"name": "OpenThermostat", "homeassistant": MINIMUM_HA,
                                                "render_readme": True,
                                                "hide_default_branch": True}, indent=2) + "\n", encoding="utf-8", newline="\n")
    readme = README.format(source=SOURCE, source_raw=SOURCE.replace("https://github.com/", "https://raw.githubusercontent.com/") + "/main",
                           ha=MINIMUM_HA, example=example_version, shots=screenshots, dash=dashboard)
    (repo / "README.md").write_text(readme, encoding="utf-8", newline="\n")


def readme_only(repo, push, trailer, example_version=None, screenshots=None, dashboard=None):
    if not (repo / ".git").exists():
        sys.exit(f"{repo} is not a clone of the HACS repository")
    check_clone(repo)
    if example_version is None:
        try:
            example_version = json.loads((repo / "custom_components" / DOMAIN / "manifest.json").read_text(encoding="utf-8"))["version"]
        except (OSError, ValueError, KeyError):
            sys.exit("the clone has no released package to take the example version from; give --example-version")
    write_front_page(repo, example_version, screenshots or default_screenshots(),
                     dashboard or default_screenshots(DASHBOARD, "--dashboard-screenshots"))
    git(repo, "add", "--", "README.md", "hacs.json")
    if git(repo, "diff", "--cached", "--name-only"):
        git(repo, "commit", "-q", "-m", "README: refresh the front page from the main repository\n\n"
            "Requirements (the BBQKees Gateway E32 V2 with the OpenThermostat firmware), features,\n"
            "screenshots, how it fits together and the install steps." + trailer, "--", "README.md", "hacs.json")
        print(f"README: {git(repo, 'rev-parse', '--short', 'HEAD')}")
    else:
        print("README: unchanged, nothing committed")
    if push:
        git(repo, "push", "-q", "origin", "main")
        print("pushed main")


def publish(version, repo, push, trailer, example_version=None, screenshots=None, download=fetch, dashboard=None):
    base = f"{SOURCE}/releases/download/ha-v{version}"
    name = f"OpenThermostat-HA-{version}.zip"
    package = download(f"{base}/{name}")
    sums = dict(line.split()[::-1] for line in download(f"{base}/HA-SHA256SUMS.txt").decode().splitlines() if line.strip())
    digest = hashlib.sha256(package).hexdigest()
    if sums.get(name) != digest:
        sys.exit(f"{name}: SHA-256 {digest} does not match HA-SHA256SUMS.txt")
    archive = zipfile.ZipFile(io.BytesIO(package))
    manifest = json.loads(archive.read(f"custom_components/{DOMAIN}/manifest.json"))
    if manifest["version"] != version:
        sys.exit(f"manifest version {manifest['version']} is not {version}")
    screenshots = screenshots or default_screenshots()
    dashboard = dashboard or default_screenshots(DASHBOARD, "--dashboard-screenshots")
    if (repo / ".git").exists():
        check_clone(repo)
    elif repo.exists() and any(repo.iterdir()):
        sys.exit(f"{repo} exists and is not a clone of the HACS repository; give a new or empty folder")
    else:
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
    write_front_page(repo, example_version or version, screenshots, dashboard)
    workflow = repo / ".github" / "workflows" / "release.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(WORKFLOW, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    if git(repo, "status", "--porcelain"):
        git(repo, "commit", "-q", "-m", f"OpenThermostat {version} (ha-v{version}, package SHA-256 {digest})" + trailer)
    if version not in git(repo, "tag", "--list", version).split():
        git(repo, "tag", version)
    print(f"{version}: {git(repo, 'rev-parse', '--short', 'HEAD')}, package {digest}")
    if push:
        git(repo, "push", "-q", "origin", "main")
        git(repo, "push", "-q", "origin", version)
        print("pushed main and tag", version)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("arguments", nargs="+", metavar="version clone | clone", help="see the usage lines above")
    parser.add_argument("--readme-only", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--co-author", default=os.environ.get("OT_CO_AUTHOR"), help='"Name <email>" for the commits (or OT_CO_AUTHOR)')
    parser.add_argument("--screenshots", help="the screenshot set of the E32 pages and the week card, e.g. rc4 (default: the newest complete set)")
    parser.add_argument("--dashboard-screenshots", help="the screenshot set of the dashboard (ha-dashboard-*), e.g. rc5 (default: the newest complete set)")
    parser.add_argument("--example-version", help="the test version the front page names as an example (default: the published version)")
    args = parser.parse_args(argv)
    trailer = co_author_trailer(args.co_author)
    if args.readme_only:
        if len(args.arguments) != 1:
            sys.exit(__doc__)
        return readme_only(Path(args.arguments[0]), args.push, trailer, args.example_version, args.screenshots, args.dashboard_screenshots)
    if len(args.arguments) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+((a|b|rc)\d+)?", args.arguments[0]):
        sys.exit(__doc__)
    return publish(args.arguments[0], Path(args.arguments[1]), args.push, trailer, args.example_version, args.screenshots,
                   dashboard=args.dashboard_screenshots)


if __name__ == "__main__":
    main()
