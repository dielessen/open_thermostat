"""Check prepared source preservation and the single current release checklist.

This checks correspondence, not physical qualification or beta readiness.
Run again after every intentional inventory/source change; never refresh hashes
without reviewing the changed source and its remaining acceptance.
"""
from pathlib import Path
import hashlib
import json
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(root, inventory):
    root = Path(root).resolve()
    require(inventory.get("schema") == 1, "Unknown inventory schema")
    items = inventory["items"]
    ids = [item["id"] for item in items]
    require(len(ids) == len(set(ids)), "Duplicate prepared item")
    require({f"I{i:02}" for i in range(1, 22)} <= set(ids), "A reviewed prepared item was removed")
    files = 0
    for item in items:
        require(item["include_in_beta"] is True, f"Prepared item excluded: {item['id']}")
        require(bool(item["files"]), f"Missing prepared source references: {item['id']}")
        require(bool(item["remaining_acceptance"]), f"Missing acceptance boundary: {item['id']}")
        for source in item["files"]:
            path = (root / source["path"]).resolve()
            require(path.is_relative_to(root), "Source path escapes repository")
            require(path.is_file(), f"Missing prepared source: {source['path']}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            require(digest == source["sha256"], f"Review source/inventory drift: {source['path']}")
            files += 1
    requirements = inventory["requirements"]
    expected = {f"R{i:02}" for i in range(1, 32)}
    require(len(requirements) == 31 and {r["id"] for r in requirements} == expected,
            "Requirements must cover exactly R01–R31")
    covered = {r for item in items for r in item["requirements"]}
    require(covered == expected, "Prepared-source map lost a product requirement")
    require(inventory["phases"] == [f"F{i}" for i in range(11)], "Phase coverage changed")
    require(inventory["work_packages"] == [f"WP{i:02}" for i in range(1, 9)], "Work-package coverage changed")
    board = (root / inventory["authoritative_workboard"]).read_text()
    require(set(re.findall(r"^\| (R\d\d) \|", board, re.M)) == expected,
            "Workboard requirement coverage differs")
    actual = [(id, marker == "x", text) for marker, id, text in
              re.findall(r"^- \[([ x])\] (B\d\d) (.+)$", board, re.M)]
    recorded = [(row["id"], row["complete"], row["description"]) for row in inventory["release_checks"]]
    require(actual == recorded, "Inventory and workboard release checks differ")
    require(len(actual) == 14 and [row[0] for row in actual] == [f"B{i:02}" for i in range(1, 15)],
            "Release checklist must cover B01–B14 exactly once")
    return {"result": "PASS", "prepared_items": len(items), "source_references": files,
            "requirements": 31, "phases": 11, "work_packages": 8, "release_checks": 14,
            "release_state": inventory["release_state"], "physical_qualification_checked": False}


if __name__ == "__main__":
    project = Path(__file__).resolve().parents[1]
    manifest = project / "docs/modern-thermostat/BETA1-RELEASE-INVENTARIS.json"
    print(json.dumps(verify(project, json.loads(manifest.read_text()))))
