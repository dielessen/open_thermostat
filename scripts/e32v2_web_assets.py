"""App-owned web UI via PlatformIO's native binary embedding; never embeds config."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

Import("env")
root = Path(env.subst("$PROJECT_DIR"))
build = Path(env.subst("$BUILD_DIR"))
build.mkdir(parents=True, exist_ok=True)
assets = sorted(p for p in (root / "data/html").rglob("*") if p.is_file())
names = [str(p.relative_to(root)) for p in assets] + ["certs/github-ca-bundle.bin"]
configured = [p.strip() for p in env.GetProjectOption("board_build.embed_files", "").splitlines() if p.strip()]
if configured != names:
    raise RuntimeError("Keep board_build.embed_files equal to all data/html assets plus the public CA bundle")
env.Append(CPPPATH=[str(build)])
release = json.loads((root / "release.json").read_text())
source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
web = hashlib.sha256()
for p in assets:
    web.update(str(p.relative_to(root / "data/html")).encode() + b"\0")
    web.update(hashlib.sha256(p.read_bytes()).digest())
web_hash = web.hexdigest()
out = ['#pragma once', '#include <cstdint>', '#include <cstddef>', '#include <cstring>',
       'namespace heating::embedded {',
       'inline constexpr char version[] = ' + json.dumps(release["version"]) + ';',
       'inline constexpr char source[] = ' + json.dumps(source) + ';',
       'inline constexpr char webSha[] = ' + json.dumps(web_hash) + ';',
       'inline const char imageMarker[] __attribute__((used)) = ' + json.dumps("OT_E32V2_OTA_V1:"+release["version"]+":"+source+":"+web_hash+":END") + ';']
for i, p in enumerate(assets):
    symbol = re.sub(r"\W", "_", str(p.relative_to(root)))
    out += [f'extern const uint8_t asset{i}[] asm("_binary_{symbol}_start");',
            f'extern const uint8_t end{i}[] asm("_binary_{symbol}_end");']
out += ['extern const uint8_t caBundle[] asm("_binary_certs_github_ca_bundle_bin_start");',
        'struct Asset { const char *path; const uint8_t *bytes; size_t size; };',
        'inline const Asset assets[] = {']
for i, p in enumerate(assets):
    out += ['{'+json.dumps('/'+str(p.relative_to(root / 'data/html')))+f',asset{i},size_t(end{i}-asset{i})'+'},']
out += ['};', 'inline const Asset *find(const char *path) { for(const auto &a:assets) if(!std::strcmp(path,a.path)) return &a; return nullptr; }', '}']
header = build / "EmbeddedWebAssets.h"
text = "\n".join(out) + "\n"
if not header.exists() or header.read_text() != text:
    header.write_text(text)
(build / "embedded-web.json").write_text(json.dumps({"version":release["version"], "source":source,"web_sha256":web_hash,"assets":{str(p.relative_to(root / 'data/html')):hashlib.sha256(p.read_bytes()).hexdigest() for p in assets}},indent=2)+"\n")
