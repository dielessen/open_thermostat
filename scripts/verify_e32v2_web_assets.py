"""Verify generated HTTP representations against source and the actual app image.

The E32 UI is gzip only (scripts/e32v2_web_assets.py): each .html/.js/.css
source is in the image only as its generated gzip stream, each precompressed
.gz source byte for byte. image_sources() lets release checks that only hold
the image (no build header) prove the same from the gzip streams it contains.
"""
import gzip
import hashlib
import json
from pathlib import Path
import re
import zlib

GZIP_MEMBER = b"\x1f\x8b\x08"
MAX_ASSET_BYTES = 4 * 1024 * 1024


def image_sources(image):
    """SHA-256 of the content of every complete gzip stream found in the image."""
    found = set()
    start = image.find(GZIP_MEMBER)
    while start != -1:
        stream = zlib.decompressobj(wbits=31)
        try:
            content = stream.decompress(image[start:start + MAX_ASSET_BYTES], MAX_ASSET_BYTES)
            if stream.eof:
                found.add(hashlib.sha256(content).hexdigest())
        except zlib.error:
            pass
        start = image.find(GZIP_MEMBER, start + 1)
    return found


def source_in_image(name, raw, image, streams):
    """A precompressed .gz source byte for byte; any other source as a gzip stream."""
    if name.endswith(".gz"):
        return raw in image
    return hashlib.sha256(raw).hexdigest() in streams


def verify(root, build):
    root, build = Path(root), Path(build)
    meta = json.loads((build / "embedded-web.json").read_text())
    header = (build / "EmbeddedWebAssets.h").read_text()
    image = (build / "firmware.bin").read_bytes()
    source = root / "data/html"
    files = sorted(p for p in source.rglob("*") if p.is_file())
    assert set(meta["assets"]) == {str(p.relative_to(source)) for p in files}
    assert meta.get("representation") == "gzip-only", "web assets are not gzip-only"
    web = hashlib.sha256()
    packed_total = raw_total = stored_total = 0
    found = set()
    for index, path in enumerate(files):
        name, raw = str(path.relative_to(source)), path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        assert meta["assets"][name] == digest, f"stale asset: {name}"
        web.update(name.encode() + b"\0")
        web.update(bytes.fromhex(digest))
        match = re.search(rf"inline const uint8_t asset{index}\[\] = \{{([^}}]+)\}};", header)
        if path.suffix == ".gz":
            assert not match and name not in meta["gzip"], f"precompressed asset compressed again: {name}"
            assert raw in image, f"precompressed source asset missing from image: {name}"
            gzip.decompress(raw)  # a valid gzip stream, served as Content-Encoding: gzip
            stored_total += len(raw)
            continue
        assert match, f"generated gzip representation missing: {name}"
        found.add(name)
        packed = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-f]{2})", match[1]))
        assert gzip.decompress(packed) == raw, f"stale/corrupt gzip: {name}"
        assert packed in image, f"gzip representation missing from image: {name}"
        assert meta["gzip"].get(name) == {"size": len(packed), "sha256": hashlib.sha256(packed).hexdigest()}
        # No uncompressed duplicate: the source bytes themselves are not shipped.
        assert len(raw) < 64 or raw not in image, f"uncompressed duplicate in image: {name}"
        packed_total += len(packed)
        raw_total += len(raw)
    assert set(meta["gzip"]) == found, "gzip inventory mismatch"
    assert web.hexdigest() == meta["web_sha256"], "source UI identity mismatch"
    return {"status": "PASS", "assets": len(files), "gzip_representations": len(found),
            "raw_bytes": raw_total, "gzip_bytes": packed_total, "precompressed_bytes": stored_total,
            "scope": "Source/image byte integrity; gzip-only HTTP representations; no on-device latency claim."}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(verify(root, root / ".pio/build/e32v2")))
