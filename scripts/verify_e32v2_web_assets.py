"""Verify generated HTTP representations against source and the actual app image."""
import gzip
import hashlib
import json
from pathlib import Path
import re


def verify(root, build):
    root, build = Path(root), Path(build)
    meta = json.loads((build / "embedded-web.json").read_text())
    header = (build / "EmbeddedWebAssets.h").read_text()
    image = (build / "firmware.bin").read_bytes()
    source = root / "data/html"
    files = sorted(p for p in source.rglob("*") if p.is_file())
    assert set(meta["assets"]) == {str(p.relative_to(source)) for p in files}
    web = hashlib.sha256()
    packed_total = raw_total = 0
    found = set()
    for index, path in enumerate(files):
        name, raw = str(path.relative_to(source)), path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        assert meta["assets"][name] == digest, f"stale asset: {name}"
        assert raw in image, f"original source asset missing from image: {name}"
        web.update(name.encode() + b"\0")
        web.update(bytes.fromhex(digest))
        match = re.search(rf"inline const uint8_t gzip{index}\[\] = \{{([^}}]+)\}};", header)
        if not match:
            assert name not in meta["gzip"], f"gzip metadata without bytes: {name}"
            continue
        found.add(name)
        packed = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-f]{2})", match[1]))
        assert gzip.decompress(packed) == raw, f"stale/corrupt gzip: {name}"
        assert packed in image, f"gzip representation missing from image: {name}"
        assert meta["gzip"][name] == {"size": len(packed), "sha256": hashlib.sha256(packed).hexdigest()}
        assert len(packed) < len(raw) * 0.9, f"unhelpful compression: {name}"
        packed_total += len(packed)
        raw_total += len(raw)
    assert set(meta["gzip"]) == found, "gzip inventory mismatch"
    assert web.hexdigest() == meta["web_sha256"], "source UI identity mismatch"
    return {"status": "PASS", "assets": len(files), "gzip_representations": len(found),
            "raw_bytes": raw_total, "gzip_bytes": packed_total,
            "scope": "Source/image byte integrity; no on-device latency claim."}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(verify(root, root / ".pio/build/e32v2")))
