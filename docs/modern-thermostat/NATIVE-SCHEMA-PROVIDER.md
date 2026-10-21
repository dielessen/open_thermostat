# Qualified native schema provider — HA2026.10.2 only

The selected supported/tested target is the actual Home Assistant2026.10.2
production API on Python3.14.8. That distribution directly declares
probatio==0.13.0. Its data_entry_flow, config_entries, config_validation and
selectors import probatio and use probatio.Schema. This is stronger evidence
than an extra package happening to import in a test venv.

The existing three project flows deliberately import probatio as vol, matching
that production API. probatio is its own MIT distribution, not the original
voluptuous distribution or Schema. A blind rename to voluptuous is not a fix.
HA's ORIGINAL __init__.py itself calls probatio.compat.install_as_voluptuous for
older consumers. This documented upstream compatibility alias is not injected
by this project or test harness; the three direct imports do not rely on it.

The initial standalone diagnostic imported original voluptuous BEFORE HA, which
triggered HA's upstream import-order warning. That probe is retained as diagnostic,
not a production failure. The final fresh probe follows the actual HA bootstrap
and separately compares the genuine original providers in an isolated pre-HA
subprocess. Neither probe installs a package or patches sys.modules.

Provider selection was already qualified in Stage46, with exact native core/
provider METADATA/RECORD and original MIT license, native entry-form serialization
and real unload/reload/readback. Stage45's original unknown-provider audit remains
immutable and historically reproducible. It was incomplete evidence, not a
demonstrated live import outage. Its policy/receipt/source/archive are not
silently retargeted here. Current source hashes and later policy scopes are
separate. No new runtime import, dependency or schema shim is required.

New bounded acceptance binds installed HA production API source files and provider
files to their actual distribution RECORD SHA256 entries, not merely to filenames
or version labels. All three real module/schema identities are checked. Actual
native FlowManager forms, validation-retained error values, options Store/change
barriers, exact C++ readback, registry invalidation and owner/reload/reconnect
tests retain real production code; only process/MQTT/clock/source qualification
are finite fixture boundaries. No replacement HA/module/schema implementation.

Negative prerequisite evidence: the frozen Stage45 report flags all three unknown
probatio imports, while current audit rejects a missing direct core requirement,
changed dependency ledger or original license. No absence is relabeled as support.
The original Stage46 patch and current supplemental test/doc patch have separate
hash manifests and rollback. No runtime/source-provider correction is fabricated
when the chosen actual API already declares and uses this provider.

Scope limit: this qualifies ONLY HA2026.10.2, not arbitrary older/newer HA, Mark's
unread live installation, a clean install of a different platform, full dependency
license closure or frontend/browser/device acceptance. Unsupported/unmeasured
versions remain OPEN; do not add another provider or fallback to make tests pass.
The manifest need not redeclare a pinned native core dependency as an independently
installed integration requirement. No claim that a different HA version supplies
it. Production version/resolution qualification remains a release/deployment gate.

Reproduce test_native_schema_contract.py plus exact recorded targeted flow/native
peer commands in PROVIDER-QUALIFICATION-RESULT.json. Stage46 source patch:
source-entry-only-core.patch with SOURCE-ENTRY-RESULT.json. No need to repeat broad
build/native/HA suites. This supplemental package changes tests/docs ONLY.

Rollback only this new test/doc commit before dependents; remove no installed
dependency or upstream code. Stage45/46/history/Store/journal/registry/owner/source/
model/Recorder/parent docs and all physical/default locks remain unchanged.
No liveHA/device/login/broker/install/flash/publication/actuation.
