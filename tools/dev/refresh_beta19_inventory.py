"""Refresh the beta19 release inventory and the shipped HA source policy in one repeatable step.

Usage (from anywhere; WSL or Windows Python 3.11+):
  python3 refresh_beta19_inventory.py <repo-root>            # dry run: print the plan, check it in memory
  python3 refresh_beta19_inventory.py <repo-root> --apply    # write both files, then re-verify from disk
  [--base 14d25d9]   files added since this commit (default: the beta18 release commit) join the inventory
  [--quiet]          print only the totals

What it does (re-run after the code freeze and after every late change; it is idempotent):
  docs/modern-thermostat/BETA1-RELEASE-INVENTARIS.json
    - drops entries whose file no longer exists (e.g. src/control/SocketWriteBudget.h),
    - refreshes every drifted sha256 to the working tree,
    - adds files added since --base (tracked or untracked, not ignored) to an item by RULES.
  docs/third-party/shipped-policy.json (section "ha")
    - source_files = every file of the HA component (no __pycache__/.pyc), with its sha256,
    - source_candidate = sha256 of the compact, key-sorted JSON of source_files,
    - source_git_parent = git HEAD.
  The other policy sections (third-party notices, SDK, CA) are only checked and reported, never changed.

Order: release notes, versions and gate files first (write_beta19_gate.py), then this script last,
because the inventory binds the hashes of those files too. A dry run exits 1 when anything would change.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

INVENTORY = "docs/modern-thermostat/BETA1-RELEASE-INVENTARIS.json"
POLICY = "docs/third-party/shipped-policy.json"
HA = "ha/config/custom_components/open_thermostat/"
EXCLUDE = (".vscode/", "node_modules/", "out/", ".pio/", "test/fuzz/corpus/")

# First matching prefix wins; unmatched files go to I01 (project and package).
RULES = [
    ("I02", ["src/control/WebPassword.h", "src/control/WebAuthSession.h", HA + "e32_access.py",
             "test/test_native/test_web_password.cpp", "test/onboarding/include/mbedtls/",
             "test/about-password-browser.cjs"]),
    ("I03", ["docs/modern-thermostat/BETA17-", "docs/modern-thermostat/BETA18-", "docs/modern-thermostat/BETA19-",
             "docs/modern-thermostat/HA-UPDATE-ACCEPTANCE", "docs/modern-thermostat/update-acceptance/",
             HA + "firmware_update.py"]),
    ("I13", ["src/ConfigBackup", "src/control/ConfigBackup.h", "src/control/BackupCipher.h", "data/html/backup.js",
             "test/test_native/test_config_backup.cpp", "test/ble_crypto/backup_cipher.cpp",
             "test/fuzz/fuzz_config_backup.cpp", "test/config-backup-browser.cjs"]),
    ("I07", ["data/html/week-editor.js", HA + "e32_week.py", HA + "frontend/e32-week-card.js",
             HA + "frontend/week-editor.js", "test/week-editor", "ha/tests_native/test_e32_week.py"]),
    ("I06", ["src/DeviceIdentity.h", HA + "e32_room_flow.py", HA + "room_groups.py", HA + "legacy_room",
             HA + "e32_link.py", HA + "repairs.py", HA + "e32_setting_device.py",
             "ha/tests_native/test_e32_setting_device.py", "ha/tests_native/test_e32_room_flow.py",
             "ha/tests_native/test_native_entity_cleanup.py", "ha/tests_native/test_room_groups.py",
             "ha/tests_native/test_legacy_room_migration.py", "ha/tests_native/test_own_name.py",
             "ha/tests_native/test_e32_room_plan_link.py", "ha/tests_native/test_room_plan_link_interop.py"]),
    ("I18", ["src/control/RoomOverrides.h", "src/RoomOverridesStore.h", HA + "e32_comfort.py", HA + "switch.py",
             "test/test_native/test_room_overrides.cpp", "ha/tests_native/test_e32_comfort.py",
             "test/e32-comfort-browser.cjs"]),
    ("I17", ["src/control/HeatingHistory.h", "data/html/history-chart.js", "test/test_native/test_heating_history",
             "test/history-chart-browser.cjs", HA + "energy_use.py", HA + "weekly_summary.py",
             HA + "blueprints/weekly_summary.yaml", "ha/tests_native/test_energy_use.py",
             "ha/tests_native/test_weekly_summary.py"]),
    ("I11", ["src/diagnostics/", "test/test_native/test_atomic_placement", HA + "heating_problem.py",
             HA + "blueprints/", "ha/tests_native/test_heating_problem.py", HA + "support_diagnostics.py",
             "ha/tests_native/test_support_diagnostics.py", "src/control/MqttOutbox.h", "src/control/Telemetry",
             "src/control/HeatingStateTopics.h", "src/control/BoilerStateTelemetry.h",
             "test/test_native/test_mqtt_outbox.cpp", "test/test_native/test_telemetry_publisher.cpp",
             "test/test_native/test_heating_state_topics.cpp", "test/test_native/test_session_cadence.cpp",
             "ha/tests_native/e32_telemetry.py", "ha/tests_native/test_e32_telemetry_topics.py",
             "ha/tests_native/test_session_recovery.py", "test/soak/", "docs/modern-thermostat/TELEMETRIEBUDGET"]),
    ("I05", [HA + "icons.json", "ha/tests_native/test_plain_language.py", "ha/tests_native/test_ux_review_ha.py",
             "ha/tests_native/test_boiler_field_names.py", "ha/tests_native/test_dashboard_heating.py",
             "ha/tests_native/test_polish_translation.py", "docs/img/", "data/html/ui-messages"]),
    ("I12", ["ha/tests_native/test_boiler_catalog_fields.py", "src/EMS/BoilerLimitRead.h", "src/EMS/BoilerProfile",
             "test/test_native/test_boiler_limit_read.cpp", "test/test_native/test_boiler_profile.cpp",
             "ha/tests_native/test_boiler_profile.py", "ha/tests_native/test_boiler_field_twins.py",
             "ha/tests_native/test_boiler_state.py", "ha/tests_native/test_native_entity_cleanup_f28.py",
             "test/boiler-profile-browser.cjs", "docs/modern-thermostat/BOILER-LIMIT-READ",
             "docs/modern-thermostat/BOILER-PROFILE", "docs/modern-thermostat/TADO-ROWS"]),
    ("I19", ["src/control/FlowLearner.h", "src/control/WarmupPlanner.h", "src/control/WeatherCurve.h",
             "src/control/GasCalibration.h", "test/test_native/test_flow_learner", "test/test_native/test_warmup",
             "test/test_native/test_gas_calibration.cpp", HA + "heating_advice.py",
             "ha/tests_native/test_heating_advice.py"]),
    ("I15", ["src/control/", "src/EMS/", "src/FlowSettingsStore.h", "test/test_native/", "test/fixtures/",
             HA + "energy_input.py", HA + "e32_flow.py", "test/heating-flow-browser.cjs", "tools/switchover/",
             "ha/tests_native/"]),
    ("I01", [""]),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


def dump(value, ensure_ascii):
    return (json.dumps(value, indent=2, ensure_ascii=ensure_ascii) + "\n").encode()


def refresh_inventory(root, base, log):
    inventory = json.loads((root / INVENTORY).read_text(encoding="utf-8"))
    removed, refreshed, added = [], [], []
    for item in inventory["items"]:
        kept = []
        for source in item["files"]:
            path = root / source["path"]
            if not path.is_file():
                removed.append((item["id"], source["path"]))
                continue
            digest = sha(path)
            if digest != source["sha256"]:
                refreshed.append((item["id"], source["path"]))
                source["sha256"] = digest
            kept.append(source)
        item["files"] = kept
    empty = [item["id"] for item in inventory["items"] if not item["files"]]
    if empty:
        raise SystemExit(f"inventory items would lose all files: {empty}; review by hand")
    new = git(root, "diff", "--name-only", "--diff-filter=A", base).split("\n")
    new += git(root, "ls-files", "--others", "--exclude-standard").split("\n")
    candidates = sorted({p for p in new if p and not p.startswith(EXCLUDE) and "__pycache__/" not in p
                         and not p.endswith((".pyc", ".pyo")) and (root / p).is_file()})
    items = {item["id"]: item for item in inventory["items"]}
    present = {s["path"] for item in inventory["items"] for s in item["files"]}
    for path in candidates:
        if path in present:
            continue
        item_id = next(i for i, prefixes in RULES if any(path.startswith(p) for p in prefixes))
        items[item_id]["files"].append({"path": path, "sha256": sha(root / path)})
        added.append((item_id, path))
    for label, rows in (("removed", removed), ("refreshed", refreshed), ("added", added)):
        for item_id, path in rows:
            log(f"inventory {label:9} {item_id} {path}")
    return inventory, {"removed": len(removed), "refreshed": len(refreshed), "added": len(added)}


def refresh_policy(root, log):
    policy = json.loads((root / POLICY).read_text(encoding="utf-8"))
    ha = policy["ha"]
    component = (root / ha["manifest"]).parent
    actual = {p.relative_to(root).as_posix(): sha(p) for p in sorted(component.rglob("*"))
              if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo")}
    old = ha["source_files"]
    stats = {"missing": sorted(set(actual) - set(old)), "gone": sorted(set(old) - set(actual)),
             "stale": sorted(p for p in set(old) & set(actual) if old[p] != actual[p])}
    for label in ("missing", "gone", "stale"):
        for path in stats[label]:
            log(f"policy    {label:9} {path}")
    if actual != old:  # a stable re-run after the commit keeps the recorded parent
        ha["source_git_parent"] = git(root, "rev-parse", "HEAD").strip()
    ha["source_files"] = dict(sorted(actual.items()))
    ha["source_candidate"] = "sha256:" + hashlib.sha256(
        json.dumps(ha["source_files"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    # Report-only: hashes of retained third-party notice bytes in the rest of the policy.
    other = []
    for notice in policy.get("original_runtime_notices", []):
        path = root / notice["path"]
        if not path.is_file() or sha(path) != notice["sha256"]:
            other.append(notice["path"])
    for component_row in policy.get("cached_sdk_component_evidence", []):
        path = root / component_row["excerpt_path"]
        if not path.is_file() or sha(path) != component_row["excerpt_sha256"]:
            other.append(component_row["excerpt_path"])
    for key in ("pem", "binary"):
        path = root / policy["ca"][key]
        if not path.is_file() or sha(path) != policy["ca"][key + "_sha256"]:
            other.append(policy["ca"][key])
    for path in other:
        log(f"policy    NOT-HA    {path} (third-party/CA hash differs: review by hand, not changed)")
    return policy, {k: len(v) for k, v in stats.items()} | {"files": len(actual), "third_party_differs": len(other)}


def check(root, inventory, policy):
    """The repository verifiers, run against the refreshed (possibly unwritten) documents."""
    sys.path.insert(0, str(root / "scripts"))
    from verify_beta_release_inventory import verify
    from release_shipped import ha_inventory
    result = verify(root, inventory)
    ha = ha_inventory(root, policy["ha"])
    return {"inventory": result["result"], "source_references": result["source_references"],
            "ha_policy_files": len(ha["source_files"]),
            "ha_unqualified_imports": sorted(ha["unqualified_external_imports"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--base", default="14d25d9")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    log = (lambda line: None) if args.quiet else print
    # The policy first: the inventory binds the policy file's own hash.
    policy, pol_stats = refresh_policy(root, log)
    pol_bytes = dump(policy, True)
    changed = {POLICY: pol_bytes != (root / POLICY).read_bytes()}
    if args.apply and changed[POLICY]:
        (root / POLICY).write_bytes(pol_bytes)
    inventory, inv_stats = refresh_inventory(root, args.base, log)
    if not args.apply and changed[POLICY]:  # dry run: hash the policy as it would be written
        digest = hashlib.sha256(pol_bytes).hexdigest()
        for item in inventory["items"]:
            for source in item["files"]:
                if source["path"] == POLICY:
                    source["sha256"] = digest
    inv_bytes = dump(inventory, False)
    changed[INVENTORY] = inv_bytes != (root / INVENTORY).read_bytes()
    if args.apply:
        if changed[INVENTORY]:
            (root / INVENTORY).write_bytes(inv_bytes)
        inventory = json.loads((root / INVENTORY).read_text(encoding="utf-8"))
        policy = json.loads((root / POLICY).read_text(encoding="utf-8"))
    probe = json.loads(json.dumps(inventory))
    if not args.apply and changed[POLICY]:  # the policy is not written in a dry run: leave its own hash out
        for item in probe["items"]:
            item["files"] = [s for s in item["files"] if s["path"] != POLICY]
    try:
        verified = check(root, probe, policy)
    except Exception as error:  # report the verifier's own message
        verified = {"error": f"{type(error).__name__}: {error}"}
    print(json.dumps({"applied": args.apply, "base": args.base, "inventory": inv_stats, "shipped_policy": pol_stats,
                      "would_change" if not args.apply else "changed": changed, "verify": verified}, indent=1))
    if "error" in verified or (not args.apply and any(changed.values())):
        sys.exit(1)


if __name__ == "__main__":
    main()
