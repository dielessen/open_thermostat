# Exact source provenance and original notices

Source-only release preparation. No runtime, compressed UI asset, dependency,
compiler flag, partition, default or release version changes.

## Identified UI payloads

`provenance.json` binds the actual gzip bytes and decompressed payloads:

| Local asset | Origin | Evidence and original notice |
| --- | --- | --- |
| bms.min.css.gz, bms.min.js.gz | David Stutz Bootstrap Multiselect 0.9.16 | Exact decompressed cdnjs bytes; tag commit 52833181fce388c9110d5c926f69b93e349d92c5; entire original LICENSE.md retained, including Apache notice and BSD text |
| bs.min.css.gz, bs.bundle.min.js.gz | Bootstrap 4.5.2 | Exact except terminal source-map basename bootstrap → bs; no code/style edits; original MIT text |
| Bootstrap bundle's Popper | Popper.js 1.16.1 | Exact Bootstrap upstream package-lock dependency; original MIT notice; not an invented direct project pin |
| jquery.min.js.gz | jQuery 3.5.1 | Exact decompressed bytes; original MIT text |
| chart.umd.js.gz | Chart.js 4.4.0 chart.umd.js | Exact decompressed bytes, NOT differently minified chart.umd.min.js; original MIT text |

The catalog records hashes and source URLs. Collection reverses only the
specified terminal source-map basename change to verify the upstream hash.
The seven original notice files are unedited upstream bytes, not summaries.

## Arduino SDK — partial closure, release BLOCKED

Installed package: framework-arduinoespressif32@3.20017.241212+sha.dcc1105b.
Arduino source: 2.0.17, tag commit
5e19e086c43d0fa5e5a596497ff8f11a0a43f6c2, consistent with generated
core_version.h. The full esp_arduino_version.h is byte-identical to that
immutable source. ESP-IDF's version header is byte-identical to v4.4.7.
Package suffix dcc1105b is NOT substituted for Arduino source commit 5e19e086.
Metadata and relevant header hashes are recorded separately.

The cache omitted Arduino's root license text. The original upstream LGPL-2.1
text is now retained here. IDF's root Apache text is reference-only, NOT a
universal license for all prebuilt SDK components. Installed notices are also
exported unedited.

**Still BLOCKED:** no complete per-component source/build manifest plus original
notice mapping for the installed prebuilt SDK. Metadata, version headers, root
licenses and exhaustive file hashes do not establish that missing binding.
This package does not assert complete SDK/binary licensing or corresponding-
source closure. Do not mark framework.closure VERIFIED merely because these
tests pass. Independent verification of the exact component source/build/notice
mapping is required. Nothing is published.

## Offline reproduction

From the checkout, with its actual cached E32 environment:

```sh
python3 -B -m unittest discover -s scripts -p test_release_notices.py -v
python3 -B scripts/release_notices.py --core "$PLATFORMIO_CORE_DIR" --output /tmp/ot-notice-evidence --allow-blocked-inventory
```

Use a fresh output directory. The second command permits BLOCKED evidence
export ONLY. Without that flag it exports then exits nonzero while blocked.
The existing package_e32v2_release.py uses the same gate before creating
package outputs, without an override.

Inventory covers all regular files and internal file-symlink targets of the
installed SDK, platform, ESP32 toolchain and selected cached environment's
libraries. Metadata versions/licenses are declarations, not complete provenance.
Git internals, Python caches and bytecode are explicitly excluded.
Notice discovery uses case-insensitive filename prefixes LICENSE, LICENCE,
COPYING, COPYRIGHT and NOTICE. Directory/external/dangling/cyclic symlinks block
completeness. Internal aliases retain relative link identity and target hashes;
exported notice aliases contain the original target text.

This defined discovery scope is not proof that every license uses those
filenames or that every installed component is linked into firmware.
Output includes file/tree/asset/metadata hashes and notice text, not private
absolute cache paths or package-manager credential/spec payloads. Repeated
collection of the same installation must be identical. Missing environments,
changed pins/assets/notices and unsafe paths fail closed.

## Rollback / separate gates

Revert only the bounded provenance/notice commit before dependent release work.
Do not delete cache/model/config/history data. Recorder, DHW, model-resource,
F9 and runtime paths remain unchanged. Image/heap/NVS/eight-zone/physical and
publication acceptance remain separate, OPEN unless independently proven.
