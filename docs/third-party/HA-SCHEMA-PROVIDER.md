# Pinned native HA schema provider: corrected dependency finding

## Actual supported core, not an undeclared optional module

The tested Home Assistant **2026.10.2** distribution explicitly declares `Requires-Dist: probatio==0.13.0` in its package METADATA. Core `homeassistant/__init__.py` imports it before custom integrations; `data_entry_flow.py`, `config_entries.py` and native configuration validators use its Schema/Marker API. Core itself installs its documented compatibility for older `voluptuous` imports. This integration does NOT install any module alias, shim, injection or compatibility adapter.

The production form imports in `v1_config_flow.py`, `v1_heating_flow.py`, `v1_heating_graph_flow.py` and `native_form.py` therefore use the **declared native core dependency** for this exact supported version. The absence of another requirement in the custom integration manifest is not proof the native dependency is undeclared. Do not blindly rename these imports or add a second dependency to make a test pass. Existing imports and all production bytes are unchanged in this qualification package.

## Reproduction and integrity scope

The initial diagnostic intentionally denied probatio imports in a fresh child process. It failed in Home Assistant core BEFORE loading this integration. This is NOT a regression reproduction in an installed system and cannot support the earlier hypothesis of a custom-integration-only missing provider. That failed diagnostic is retained under native-provider-before in the private review evidence.

A read-only probe checks distribution RECORD SHA256 entries against installed files and cached exact package bytes, separating generated installer metadata/entrypoints (checked against their installation RECORD, not asserted to be cached wheel content). Actual core dependency metadata/source, distribution versions and all checked hashes are frozen in native-provider-dependency-evidence/DEPENDENCY.json. These demonstrate installed/cache consistency, NOT independent upstream-signature or remote authenticity verification.

The native schema tests verify all four real modules share the exact core Schema/Marker types and the native suggested-value helper preserves validation and rejected input. Actual native HA options/subentry/group/graph form flows, Store/review/apply/real C++readback/reconnect/unload lifecycle are exercised separately. No fixture supplies a substitute schema provider. A sanitizer peer is used for the same cases; production Python/C++/settings are byte-identical to the preceding source packet.

## Compatibility and notices

This evidence qualifies only pinned HA2026.10.2 / probatio0.13.0. Older HA or alternative schema APIs remain UNQUALIFIED; no claim of an old-core import fallback. Probatio metadata identifies the MIT license and its own upstream source; Home Assistant/core-managed dependency is not an extra bundled project runtime. This finding does not settle the separate binary SDK source-build/notice closure. Historical Stage44/45 audits remain immutable; their initial provider concern is superseded for this exact core, not silently rewritten.

No production module/import/manifest/requirements, config/journal/registry/Recorder/model data or safety/output behavior changed. Rollback this test/documentation-only commit before dependents; no data migration, runtime reset or installation needed. Actual HA frontend desktop/mobile, final combined image/license/physical gates remain open. Entire PLAN remains in progress.
