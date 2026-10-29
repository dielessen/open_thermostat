"""App-owned web UI, gzip only, in the app image; never embeds config.

Every .html/.js/.css source is compressed here (deterministic gzip, level 9,
mtime 0) into a generated header; only that representation is in the image.
Precompressed .gz sources (third-party dependencies, generated reference data)
are embedded byte for byte through PlatformIO's board_build.embed_files. The
E32 serves every asset with Content-Encoding: gzip; a client that refuses gzip
explicitly (Accept-Encoding: identity only, or gzip;q=0) receives 406. Every
browser and captive-portal web view the UI supports sends gzip.
"""
from pathlib import Path
import hashlib
import gzip
import json
import re
import subprocess

Import("env")
root = Path(env.subst("$PROJECT_DIR"))
build = Path(env.subst("$BUILD_DIR"))
build.mkdir(parents=True, exist_ok=True)
source = root / "data/html"
assets = sorted(p for p in source.rglob("*") if p.is_file())
COMPRESSED_HERE = (".html", ".js", ".css")
unsupported = [str(p.relative_to(source)) for p in assets
               if p.suffix != ".gz" and p.suffix not in COMPRESSED_HERE]
if unsupported:
    raise RuntimeError("Web assets must be .html/.js/.css or precompressed .gz: " + ", ".join(unsupported))
precompressed = [p for p in assets if p.suffix == ".gz"]
names = [str(p.relative_to(root)) for p in precompressed] + ["certs/github-ca-bundle.bin"]
configured = [p.strip() for p in env.GetProjectOption("board_build.embed_files", "").splitlines() if p.strip()]
if configured != names:
    raise RuntimeError("Keep board_build.embed_files equal to the precompressed data/html/**/*.gz assets "
                       "plus the public CA bundle (other web assets are gzipped into the image): "
                       + json.dumps(names))
env.Append(CPPPATH=[str(build)])
release = json.loads((root / "release.json").read_text())
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
web = hashlib.sha256()
for p in assets:
    web.update(str(p.relative_to(source)).encode() + b"\0")
    web.update(hashlib.sha256(p.read_bytes()).digest())
web_hash = web.hexdigest()
out = ['#pragma once', '#include <cstdint>', '#include <cstddef>', '#include <cstring>',
       'namespace heating::embedded {',
       'inline constexpr char version[] = ' + json.dumps(release["version"]) + ';',
       'inline constexpr char source[] = ' + json.dumps(commit) + ';',
       'inline constexpr char webSha[] = ' + json.dumps(web_hash) + ';',
       'inline const char imageMarker[] __attribute__((used)) = ' + json.dumps("OT_E32V2_OTA_V1:"+release["version"]+":"+commit+":"+web_hash+":END") + ';']
compressed = {}
for i, p in enumerate(assets):
    if p.suffix == ".gz":
        symbol = re.sub(r"\W", "_", str(p.relative_to(root)))
        out += [f'extern const uint8_t asset{i}[] asm("_binary_{symbol}_start");',
                f'extern const uint8_t end{i}[] asm("_binary_{symbol}_end");']
        continue
    # Generated from the source on every build, never a stale checked-in mirror.
    packed = gzip.compress(p.read_bytes(), compresslevel=9, mtime=0)
    compressed[i] = packed
    out.append(f'inline const uint8_t asset{i}[] = {{')
    out.extend(','.join(f'0x{v:02x}' for v in packed[start:start+24])+','
               for start in range(0, len(packed), 24))
    out.append('};')
out += ['extern const uint8_t caBundle[] asm("_binary_certs_github_ca_bundle_bin_start");',
        '// One representation per asset: gzip bytes (generated or a stored .gz),',
        '// served with Content-Encoding: gzip; etag = SHA-256 of these bytes.',
        'struct Asset { const char *path; const uint8_t *bytes; size_t size; const char *etag; };',
        'inline const Asset assets[] = {']
for i, p in enumerate(assets):
    packed = compressed.get(i, p.read_bytes())
    size = f'sizeof(asset{i})' if i in compressed else f'size_t(end{i}-asset{i})'
    out += ['{'+json.dumps('/'+str(p.relative_to(source)))+f',asset{i},{size},'
            +json.dumps('"'+hashlib.sha256(packed).hexdigest()+'"')+'},']
out += ['};', 'inline const Asset *find(const char *path) { for(const auto &a:assets) if(!std::strcmp(path,a.path)) return &a; return nullptr; }', '}']
header = build / "EmbeddedWebAssets.h"
text = "\n".join(out) + "\n"
if not header.exists() or header.read_text() != text:
    header.write_text(text)
(build / "embedded-web.json").write_text(json.dumps({"version":release["version"], "source":commit,"web_sha256":web_hash,
    "representation": "gzip-only",
    "assets":{str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in assets},
    "gzip": {str(assets[i].relative_to(source)):
             {"size":len(packed), "sha256":hashlib.sha256(packed).hexdigest()}
             for i,packed in compressed.items()}},indent=2)+"\n")
