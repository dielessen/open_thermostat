# Existing control NVS graph preflight — source11785

The pinned unchanged E32 table has one20480-byte NVS partition. Neither PSRAM nor
the8192-byte wire ceiling enlarges that partition. Existing control blob maximum
is4096 bytes; network settings maximum2048 bytes remains separately charged.

ControlPartitionBudget is a necessary conservative preflight, not an NVS
implementation/emulator or a successful allocation/commit/contiguous-page proof.
NvsControlStore keeps its default legacy_api1 behavior. ONLY an explicitly
constructed graph_shadow_v2 store checks the actual partition size through public
esp_partition_find_first and actual nvs_get_stats before any read-write open/
set_blob/commit. It rejects unknown enum/partition/stats/budget. No active factory
currently selects this profile and no device NVS calls were made in this task.
No added namespace/key, erase/reset, partition, credential or network change.

The budget charges32-byte entries, conservative chunk/index overhead, two
namespace entries and one126-entry GC-page reserve. Old accepted config,
network and other keys are ALREADY charged to usedEntries. They are NEVER
credited to free space before commit. Required free preflight is264 entries
even for a smaller new config, reserving a future4096B control replacement.
Stats may still lack a suitable contiguous arrangement; actual set/commit and
the EXISTING core readback/ambiguous-failure disable remain authoritative.
SDK documentation explicitly permits REMOVE_FAILED after a value was written:
never infer a failed response means uncommitted or silently restore old memory.

Explicit optional model accounting uses the EXISTING checkpoint ceilings:
warm426B→20 conservative entries, coast554B→24, curve412B→19.
Eight of EACH uses504 entries before config/network/copy/GC reserves and is
REFUSED by the conservative20KiB ledger. That is NOT a measurement proving all
possible compact model layouts impossible; it prevents advertising this unproven
layout. One warm/coast/curve reservation is separately bounded (63entries), NOT
8zone/model qualification. No actual model keys or model-storage caller added.

Tests cover exact thresholds, old bytes not reclaimed, unknown/larger/zero
partition, unreadable/inconsistent/overflow stats, empty/oversized/overflow blob,
out-of-range model counts and unsupported8set reservation. Six focused actual
native C++ tests pass. Actual current main.cpp is checked with the pinned real
Xtensa/Arduino2.0.17/NVS/partition headers, reusing old generated webassets ONLY
for type-check; no image/link or nativeNVS hardware/flash simulation claim.

Legacy graph migration stays failclosed in GraphShadowConfiguration: nonempty
oldAPI1 blobs are not interpreted, erased or overwritten. This preflight does not
change that rule or establish a graph session/profile/source/physical readiness.
Next source increment is the explicit graph owner/handshake/readback/selection
hook. Full8zone graph/model heap/stack/storage profile and physical commissioning
remain separate gates, not silently accepted through this accounting helper.

Rollback reverse the focused source patch/revert before later dependent changes.
No runtime data changed, therefore no device restore action is necessary.
