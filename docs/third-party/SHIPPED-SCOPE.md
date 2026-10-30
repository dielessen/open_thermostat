# Local-build shipment scope, notices and unresolved release obligations

This extends provenance.json, not a second catalog or a release approval.
shipped-policy.json binds existing saved receipts and original notice bytes.
No runtime, dependency, version, compiler flag, partition, lock or default changes.

## Exact identity; built is not installed or published

Saved build source: 8b364f21df6923342d24dde070fcc99ac188e76c.

| Environment | Actual raw app | SHA256 | Scope |
| --- | ---: | --- | --- |
| E32 V2 | 2299632 bytes | 0b830c42a4415d83a7a57ea649ae3f13e4cd87a1b845e9d4dd8bd4582914a85b | Saved local app; original dual 3670016-byte slots |
| ESP32-S3 | 1601728 bytes | df3e280d53b041d5537cd12a4035674237ab4adecd64a6a5bac309880b33d74b | Saved local app; original dual 3670016-byte slots |

Both raw app descriptors contain the SHA256 of their exact saved ELF.
Both descriptors report project arduino-lib-builder, version
esp-idf: v4.4.7 38eeba213a, IDF **v4.4.7-dirty**.
A clean v4.4.7 header or Arduino tag is NOT complete corresponding source
for this dirty binary SDK. The exact modifications/build inputs remain unproven.

The E32 embedded manifest has source8b364f21 and web SHA256
e0f985e2698d060fe05378d400cfa76b50d968b37c67755658e3c80a832289a0.
All22 embedded asset bytes and the source/UI/version marker are checked in the
actual app. The literal alpha.6 version is historical metadata, NOT permission
to label these different local bytes as the immutable published alpha.6.
S3 has no E32 embedded-web manifest; a matching S3 filesystem/distribution
receipt is missing and explicitly blocked. No filesystem image is fabricated.

## Retained versus installed, scanned, host-only or not yet packaged

The offline audit validates GNU map output ranges against ELF SHF_ALLOC sections
and counts only nonzero retained input sections within those ranges. LOAD,
archive-member scan lists, discarded sections and non-ALLOC debug sections are
NOT shipment proof. This yields74 retained archives on E32 and72 on S3.
Contribution counts include runtime RAM/NOBITS, not raw-image flash attribution.

Six external project libraries are retained: PubSubClient2.8.0,
ESPPubSubClientWrapper1.0.2, RTClib2.1.4, AdafruitBusIO1.17.4,
NimBLE-Arduino2.5.1 and esp32_utilities1.0.0+sha.9186b65.
Their build-receipt versions, installed-tree hashes, origins and original
copyright/license/NOTICE files are bound in the policy. Arduino core libraries
are identified separately; prebuilt SDK archives are not all relabeled Apache.
Original GCC runtime exception/GPL and newlib collection texts are also retained.

Four cached E32 SDK header versions are explicit, **not** a complete per-archive
binary/source binding: FreeRTOS10.4.3, lwIP2.1.2 with esp/development macros,
cJSON1.7.17 and MbedTLS2.28.7. Exact original license-comment slices and full
header hashes/byte ranges are retained. MbedTLS's header says
Apache-2.0 OR GPL-2.0-or-later; no silent branch choice/source-closure claim.
Other SDK components remain individually unqualified within the pinned package.

OpenSSL, GoogleTest and Unity are NOT retained firmware archives in these two
receipts. They are host-verification or cached test tooling, not shipped device
crypto. Firmware actually retains mbedTLS archives. This does not assert that
a separately installed HA platform never uses OpenSSL transitively.

The HA subtree is a **package-source candidate**, 126 hash-bound files, not a
newly produced/deployed HA release. Its manifest declares native lovelace/MQTT
dependencies and no separate requirements. homeassistant/voluptuous are
platform-provided, not vendored here. Pinned test HA2026.10.2 is not evidence of
production HA version or its full resolved dependency bill.

Stage45 initially flagged probatio as unknown. The follow-up native metadata
lookup resolves that hypothesis: Home Assistant2026.10.2 directly requires
**probatio==0.13.0**, a real MIT-licensed distribution from frenck/probatio.
Native HA itself imports it; it is not an injected alias, shim or newly installed
dependency. Original license/installed METADATA/RECORD hashes are recorded in
native-ha-validator.json, and the license's RECORD digest was verified.
Both actual room forms and native GUI serialization pass without modifying the
three imports. No import defect or live-HA outage was demonstrated. The earlier
frozen Stage45 report remains historical; current audit requires this evidence
before treating probatio as platform-provided. Production HA version/resolution
is still unmeasured, and SDK/CA/source-offer/S3 filesystem blockers remain open.

The embedded public CA bundle has exact PEM/generated-binary hashes and existing
dated curl/Mozilla provenance in certs/README.md. Its exact dated upstream data
revision/applicable original notice binding is still missing. No blanket license
is inferred from a certificate label or from the generator's Apache notice.

## Exact retained SDK → current cache join — still not corresponding source

sdk-linked-archives.json is the hash-pinned extension consumed by the EXISTING
release_shipped audit. It joins the actual retained ELF/map paths to **52 prebuilt
SDK archives per board**, not all74/72 retained archives of every source family.
Both same-basename/different-directory inputs require their own exact identity.
The104 archive paths, two target sdkconfigs and two package metadata files match
the original frozen installed inventory b4e37aad... and current cache bytes.
No repeated full-cache walk, download or rebuild is necessary.

The saved source8b364f21 ELF/map/image hashes are checked before the join. Target
sdkconfig hashes are esp32 a4fe490abd8cd6447874edd79bde1e78d9630af7845bd53f70440a56b3504907
and esp32s3 a70d5c071e68c07e82fe5e71c3225b0854e1021ecd8a902da20523aa3123b476.
Package metadata hashes must equal the original provenance pins. These identify
cached configurations, NOT a reproduced recipe for the dirty prebuilt libraries.

Per archive the audit deliberately reports **null** for matching source commit,
binary build recipe, linker-time archive attestation and qualified applicable
binary notices. A current cache hash and historical linkmap path cannot prove
which archive bytes the historical linker consumed. Header notice references
remain header-only; E32 references are not copied onto S3 binary qualification.
No component is marked VERIFIED using a file name, root license or clean header.
All104 component rows and overall source-offer closure remain BLOCKED.

To check the current installed archive bytes explicitly, add --core <pinned-core>
to the existing release_shipped command. Without --core the evidence report says
NOT_CHECKED_CORE_NOT_SUPPLIED, never an exact-current-bytes PASS. Both branches
remain BLOCKED; only --allow-blocked-report permits an evidence export exit0.
It cannot make native packaging publishable. Unknown schema, missing or duplicate
archive, new retained input, source/ELF/map/target mismatch, cache tamper, metadata
pin mismatch, unsafe path or invented source/license qualification fails closed.
No original notices, especially the whitespace-sensitive original LGPL text,
are reformatted or replaced.

This evidence concerns the older exact saved build receipts only. Later SOURCE
controller/GUI source commits are NOT thereby full-image built or deployed.
Runtime, SDK dependencies, default factories, outputs and all physical gates are
unchanged. Separate actual producer, DATA writer/provisioning, current composed
image and native frontend acceptance gates remain open where unproven.

## Attribution and corresponding-source checklist — incomplete, BLOCKED

| Evidence class | Required distribution material / current result |
| --- | --- |
| Project MIT, MIT/BSD components | Preserve original copyrights, permissions, conditions/disclaimers; original project and identified library/UI notices retained |
| Apache components | Preserve applicable LICENSE and NOTICE texts, attribution, and document modifications where required; NimBLE/Mynewt/TinyCrypt originals retained separately, not flattened into one Apache label |
| Arduino LGPL2.1 | The root license alone is insufficient. For a static-library distribution, qualify the applicable section6 route, matching complete library sources/modifications and usable application object/relink or compliant shared-library materials. Not supplied/verified for these exact SDK bytes; BLOCKED |
| GCC runtime exception | Preserve exact texts and establish applicability to the actual compilation/runtime components; do NOT infer whole-project GPL or automatic blanket exemption. Exact corresponding runtime source/build mapping remains unproven |
| newlib/vendor prebuilt SDK | Preserve component-specific notices and establish actual source/build/license mapping; a generic SDK root notice is not a substitute. BLOCKED |
| CA data and native HA | Exact applicable data notice and qualified runtime dependency resolution remain open; test-environment versions do not close them |
| Matching source/offer | Repository URL, a tag, this documentation or an unverified written offer is NOT an already fulfilled corresponding-source/relink offer. Exact built-source archive/SDK inputs and applicable delivery route require independent verification before distribution |

No universal legal-completeness assertion. All unknown mappings remain in the
machine-readable blocked list. Existing native packaging still refuses release
while the Stage44 SDK closure is unresolved. Evidence-export flags are not
publication overrides.

## Offline verifier and rollback

Use the existing saved receipts, without rebuilding:

    python3 -B -m unittest discover -s scripts -p 'test_release_*.py' -v
    python3 -B scripts/release_shipped.py --receipts <saved composed-release-parent-evidence> --output <fresh report.json> --allow-blocked-report

The second command exports a BLOCKED report only. Without its evidence flag it
still writes the report and exits nonzero. Modified images/ELFs/maps/logs,
UI/HA source changes, unknown retained inputs and missing notices cannot become
a successful complete-closure claim.

F9: all14 corrected candidate assessments remain rejected/insufficient with
0/14 arrival hits. No production model benefit/caller/adoption claim.
Heap/callgraph/eight-zone/NVS-GC/soak, product integration, physical/runtime and
publication gates stay separate and OPEN where not proven. Generic-size belongs
to the existing separate child; it is not fixed or rebuilt by this audit.

Rollback only this bounded source/doc commit before dependent packaging.
Do not erase cache/model/config/Recorder/history or revert parent's documents,
DHW, resource gates, F9, defaults or runtime paths.
