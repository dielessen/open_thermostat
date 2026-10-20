"""Actual HA Store and shared validator; network forbidden by conftest."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers.storage import Store

from custom_components.open_thermostat.graph_shadow_storage import (
    GraphShadowJournal, native_graph_journal, LIMITS, IDENTITY)
from custom_components.open_thermostat.graph_shadow_validation import (
    CAPS, GraphValidationContext, GraphValidationError, canonical, digest)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "test/fixtures/graph-shadow-validation.jsonl").read_text().splitlines()[0])


def documents(revision=1):
    mapping = json.loads(FIXTURE["mapping_raw"])
    mapping["mapping_revision"] = 1
    raw = json.loads(FIXTURE["raw"])
    raw["config"]["revision"] = revision
    raw["config"]["rooms"][0]["base_centi_c"] += revision - 1
    raw["config"]["mapping_revision"] = 1
    raw["config"]["mapping_digest"] = digest(mapping)
    raw["config_digest"] = digest(raw["config"])
    raw["expected_revision"] = raw["config_revision"] = revision - 1
    context = GraphValidationContext(**{**FIXTURE["context"],
        "current_revision": revision - 1, "mapping_revision": 0 if revision == 1 else 1,
        "mapping_digest": "" if revision == 1 else digest(mapping)})
    return raw, mapping, context


def capability(context, config_digest=""):
    return dict(api=2, mode="shadow_graph", capabilities=sorted(CAPS), limits=deepcopy(LIMITS),
        **{key: getattr(context, key) for key in IDENTITY},
        config_revision=context.current_revision, config_digest=config_digest,
        mapping_revision=context.mapping_revision, mapping_digest=context.mapping_digest,
        boiler_output_enabled=False, actuator_output_enabled=False)


def journal(hass, key="test_graph"):
    return GraphShadowJournal(Store(hass, 1, key), FIXTURE["context"]["qualification_digest"], lambda: 100)


async def stage(j, revision=1, accepted_digest=""):
    raw, mapping, context = documents(revision)
    result = await j.async_stage(canonical(raw), canonical(mapping), context,
        capability(context, accepted_digest), 100, retained=False)
    return raw, mapping, context, result


async def reconcile(j, raw, mapping, *, reboot=False):
    context = replace(documents(raw["config"]["revision"])[2],
        current_revision=raw["config"]["revision"], mapping_revision=1, mapping_digest=digest(mapping))
    if reboot:
        context = replace(context, boot_id="new_boot", adapter_session_id="new_session",
            grant_id="new_grant", grant_sequence=2)
    return await j.async_reconcile(raw["config"], context, capability(context, raw["config_digest"]),
        100, retained=False)


@pytest.mark.asyncio
async def test_actual_store_stage_explicit_apply_reconnect_and_disk_restore(hass):
    j = journal(hass)
    raw, mapping, context, result = await stage(j)
    assert result.boiler_output_enabled is result.actuator_output_enabled is False
    assert j.status == "graph_staged_not_applied" and not j.verified
    # A separate HA Store loads the actual file, not the journal object's cache.
    disk = await Store(hass, 1, "test_graph").async_load()
    assert disk == j.state and disk["accepted"] is None
    sends = []
    async def send(topic, payload):
        assert await Store(hass, 1, "test_graph").async_load() == j.state
        sends.append((topic, json.loads(payload)))
    sent = await j.async_apply(send, context, capability(context), 100, 12, retained=False)
    assert sends == [("ha/config", json.loads(sent))]
    assert sends[0][1]["sequence"] == 12
    assert j.status == "awaiting_graph_readback" and not j.verified
    # Simulate process loss/lost ACK; a fresh journal cannot restore admission.
    restored = journal(hass)
    assert not restored.verified
    assert await reconcile(restored, raw, mapping, reboot=True)
    assert restored.state["accepted"]["config"] == raw["config"]
    assert restored.state["staged"] is None
    assert not restored.outputs_enabled
    restored.invalidate()
    assert not restored.verified and restored.status == "awaiting_graph_readback"
    assert await reconcile(restored, raw, mapping, reboot=True)


@pytest.mark.asyncio
async def test_pending_newer_revision_keeps_old_readback_unverified(hass):
    j = journal(hass)
    old, mapping, _, _ = await stage(j)
    await reconcile(j, old, mapping)
    new, _, _, _ = await stage(j, 2, old["config_digest"])
    assert not await reconcile(j, old, mapping)
    assert j.status == "graph_staged_not_applied"
    assert await reconcile(j, new, mapping)
    assert j.state["accepted"]["config"]["revision"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("change,code", [
    (lambda cap: cap.update(api=1), "unsupported_schema"),
    (lambda cap: cap.update(boiler_output_enabled=True), "outputs_not_locked"),
    (lambda cap: cap.update(actuator_output_enabled=True), "outputs_not_locked"),
    (lambda cap: cap.update(boot_id="different_boot"), "identity"),
    (lambda cap: cap["capabilities"].pop(), "unsupported_capability"),
    (lambda cap: cap["limits"].update(rooms=12), "test_layout_limit"),
    (lambda cap: cap.update(config_revision=True), "revision_conflict"),
    (lambda cap: cap.update(extra="unknown"), "schema"),
    (lambda cap: cap.update(config_digest="f"*64), "readback_required"),
])
async def test_capability_gate_prevents_any_store_write(hass, change, code):
    j = journal(hass)
    j.store.async_save = AsyncMock()
    raw, mapping, context = documents()
    cap = capability(context)
    change(cap)
    with pytest.raises(GraphValidationError, match=f"^{code}$"):
        await j.async_stage(canonical(raw), canonical(mapping), context, cap, 100, retained=False)
    j.store.async_save.assert_not_awaited()
    assert not j.verified and not j.outputs_enabled


@pytest.mark.asyncio
@pytest.mark.parametrize("received,retained,code", [
    (100, True, "retained_capability"), (90, False, "stale_capability"),
    (101, False, "stale_capability"), (float("nan"), False, "stale_capability"),
])
async def test_retained_and_stale_capabilities_fail_closed(hass, received, retained, code):
    j = journal(hass)
    raw, mapping, context = documents()
    with pytest.raises(GraphValidationError, match=f"^{code}$"):
        await j.async_stage(canonical(raw), canonical(mapping), context,
            capability(context), received, retained=retained)
    assert j.state is None


@pytest.mark.asyncio
async def test_full_shared_validator_and_immutable_pending_tuple(hass):
    j = journal(hass)
    raw, mapping, context = documents()
    raw["config"]["rooms"][0]["base_centi_c"] = 9999
    raw["config_digest"] = digest(raw["config"])
    with pytest.raises(GraphValidationError):
        await j.async_stage(canonical(raw), canonical(mapping), context,
            capability(context), 100, retained=False)
    assert j.state is None
    await stage(j)
    raw, mapping, context = documents()
    raw["config"]["rooms"][0]["base_centi_c"] += 1
    raw["config_digest"] = digest(raw["config"])
    with pytest.raises(GraphValidationError, match="^pending_conflict$"):
        await j.async_stage(canonical(raw), canonical(mapping), context,
            capability(context), 100, retained=False)
    snapshot = j.state
    snapshot["staged"]["config"]["revision"] = 999
    assert j.state["staged"]["config"]["revision"] == 1


@pytest.mark.asyncio
async def test_send_failure_does_not_accept_retry_or_rollback(hass):
    j = journal(hass)
    _, _, context, _ = await stage(j)
    before = j.state
    send = AsyncMock(side_effect=OSError("uncertain delivery"))
    with pytest.raises(OSError):
        await j.async_apply(send, context, capability(context), 100, 1, retained=False)
    send.assert_awaited_once()
    assert j.state == before
    assert j.status == "graph_send_unconfirmed" and not j.verified


@pytest.mark.asyncio
async def test_unknown_readback_does_not_adopt_or_overwrite_remote(hass):
    j = journal(hass)
    raw, mapping, _, _ = await stage(j)
    before = j.state
    raw["config"]["rooms"][0]["base_centi_c"] += 1
    raw["config_digest"] = digest(raw["config"])
    with pytest.raises(GraphValidationError, match="^mapping_conflict$"):
        await reconcile(j, raw, mapping)
    assert j.state == before and not j.verified


@pytest.mark.asyncio
async def test_no_implicit_legacy_migration_or_corrupt_store_overwrite(hass):
    for key, value in (("legacy", {"accepted": {}, "staged": None}),
                       ("future", {"schema": 9, "accepted": None, "staged": None})):
        j = journal(hass, key)
        await j.store.async_save(value)
        with pytest.raises(GraphValidationError):
            await stage(j)
        assert await Store(hass, 1, key).async_load() == value
        assert not j.verified


@pytest.mark.asyncio
async def test_ambiguous_committed_save_reloads_instead_of_overwriting(hass):
    j = journal(hass)
    save = j.store.async_save
    async def committed_but_failed(value):
        await save(value)
        raise OSError("fsync response lost")
    j.store.async_save = committed_but_failed
    with pytest.raises(GraphValidationError, match="^storage_fault$"):
        await stage(j)
    assert j.state is None and not j.verified
    j.store.async_save = save
    raw, mapping, context = documents()
    raw["config"]["rooms"][0]["base_centi_c"] += 1
    raw["config_digest"] = digest(raw["config"])
    with pytest.raises(GraphValidationError, match="^pending_conflict$"):
        await j.async_stage(canonical(raw), canonical(mapping), context,
            capability(context), 100, retained=False)
    assert j.state["staged"]["config"]["rooms"][0]["base_centi_c"] == 2100


@pytest.mark.asyncio
async def test_apply_requires_fresh_capability_and_durable_stage(hass):
    j = journal(hass)
    _, _, context, _ = await stage(j)
    send = AsyncMock()
    with pytest.raises(GraphValidationError, match="^stale_capability$"):
        await j.async_apply(send, context, capability(context), 90, 1, retained=False)
    await j.store.async_save({"changed": True})
    with pytest.raises(GraphValidationError, match="^storage_fault$"):
        await j.async_apply(send, context, capability(context), 100, 1, retained=False)
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_qualification_anchor_not_self_granted(hass):
    j = journal(hass)
    raw, mapping, context = documents()
    context = replace(context, qualification_digest="f"*64)
    with pytest.raises(GraphValidationError, match="^qualification$"):
        await j.async_stage(canonical(raw), canonical(mapping), context,
            capability(context), 100, retained=False)


@pytest.mark.asyncio
async def test_native_factory_single_lock_separate_namespace_no_runtime(hass):
    entry = SimpleNamespace(entry_id="test_entry")
    anchor = FIXTURE["context"]["qualification_digest"]
    j = native_graph_journal(hass, entry, anchor)
    j.clock = lambda: 100
    assert native_graph_journal(hass, entry, anchor) is j
    with pytest.raises(GraphValidationError, match="^qualification$"):
        native_graph_journal(hass, entry, "f"*64)
    raw, _, _, _ = await stage(j)
    assert (await Store(hass, 1, "open_thermostat.graph_shadow.test_entry").async_load())["staged"]["config"] == raw["config"]
    assert await Store(hass, 1, "open_thermostat.v1.test_entry").async_load() is None
    assert not j.verified and not j.outputs_enabled


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["apply", "reconcile"])
async def test_disconnect_during_store_await_cannot_restore_admission_or_send(hass, phase):
    j = journal(hass)
    raw, mapping, context, _ = await stage(j)
    load = j.store.async_load
    async def disconnected():
        value = await load()
        j.invalidate()
        return value
    j.store.async_load = disconnected
    send = AsyncMock()
    with pytest.raises(GraphValidationError, match="^session_changed$"):
        if phase == "apply":
            await j.async_apply(send, context, capability(context), 100, 1, retained=False)
        else:
            await reconcile(j, raw, mapping)
    send.assert_not_awaited()
    assert not j.verified


@pytest.mark.asyncio
async def test_capability_expiring_during_store_await_never_sends(hass):
    j = journal(hass)
    _, _, context, _ = await stage(j)
    load = j.store.async_load
    async def delayed():
        value = await load()
        j.clock = lambda: 110
        return value
    j.store.async_load = delayed
    send = AsyncMock()
    with pytest.raises(GraphValidationError, match="^stale_capability$"):
        await j.async_apply(send, context, capability(context), 100, 1, retained=False)
    send.assert_not_awaited()
    assert not j.verified


@pytest.mark.asyncio
async def test_parallel_conflicting_stages_have_single_native_transaction_winner(hass):
    import asyncio
    j = journal(hass)
    raw, mapping, context = documents()
    other = deepcopy(raw)
    other["config"]["rooms"][0]["base_centi_c"] += 1
    other["config_digest"] = digest(other["config"])
    async def run(document):
        return await j.async_stage(canonical(document), canonical(mapping), context,
            capability(context), 100, retained=False)
    results = await asyncio.gather(run(raw), run(other), return_exceptions=True)
    assert sum(not isinstance(x, Exception) for x in results) == 1
    assert [x.code for x in results if isinstance(x, GraphValidationError)] == ["pending_conflict"]
    assert j.state["staged"]["config"] == raw["config"]


@pytest.mark.asyncio
async def test_mapping_baseline_cannot_be_invented_beside_known_accepted_tuple(hass):
    j = journal(hass)
    old, mapping, _, _ = await stage(j)
    await reconcile(j, old, mapping)
    raw, mapping, context = documents(2)
    mapping["mapping_revision"] = 3
    raw["config"]["mapping_revision"] = 3
    raw["config"]["mapping_digest"] = digest(mapping)
    raw["config_digest"] = digest(raw["config"])
    context = replace(context, mapping_revision=2, mapping_digest="a"*64)
    with pytest.raises(GraphValidationError, match="^readback_required$"):
        await j.async_stage(canonical(raw), canonical(mapping), context,
            capability(context, old["config_digest"]), 100, retained=False)
    assert j.state["staged"] is None and not j.verified


@pytest.mark.asyncio
async def test_failed_initial_save_cannot_be_applied(hass):
    j = journal(hass)
    j.store.async_save = AsyncMock(side_effect=OSError("read only disk"))
    with pytest.raises(GraphValidationError, match="^storage_fault$"):
        await stage(j)
    context = documents()[2]
    send = AsyncMock()
    with pytest.raises(GraphValidationError, match="^nothing_staged$"):
        await j.async_apply(send, context, capability(context), 100, 1, retained=False)
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_committed_save_cannot_use_cached_previous_state(hass):
    import asyncio
    j = journal(hass)
    save = j.store.async_save
    async def interrupted(value):
        await save(value)
        raise asyncio.CancelledError()
    j.store.async_save = interrupted
    with pytest.raises(asyncio.CancelledError):
        await stage(j)
    assert j.state is None and j.status == "graph_interrupted" and not j.verified
    j.store.async_save = save
    raw, mapping, context = documents()
    raw["config"]["rooms"][0]["base_centi_c"] += 1
    raw["config_digest"] = digest(raw["config"])
    with pytest.raises(GraphValidationError, match="^pending_conflict$"):
        await j.async_stage(canonical(raw), canonical(mapping), context,
            capability(context), 100, retained=False)
