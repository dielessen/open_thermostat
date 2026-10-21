"""Real shared codecs, actual HA Store, real finite C++ core; no network."""
from copy import deepcopy
import json
import pytest
from unittest.mock import AsyncMock

from custom_components.open_thermostat.graph_wire_codec import (
    TRANSPORT, encode_graph_tuple, decode_graph_tuple)
from custom_components.open_thermostat.graph_shadow_validation import (
    canonical, digest, GraphValidationError, validate_graph_shadow)
from test_graph_shadow_storage import documents, capability, journal
from test_graph_firmware_store import firmware, admit, current


def wire_documents():
    message, mapping, context = documents()
    return message, mapping, context, encode_graph_tuple(
        canonical(message), canonical(mapping), context)


def test_exact_canonical_roundtrip_no_extra_nesting_or_unbound_mapping():
    message, mapping, context, wire = wire_documents()
    inner, decoded = decode_graph_tuple(wire)
    assert inner == canonical(message) and decoded == canonical(mapping)
    assert wire == canonical({**message, "mapping": mapping})
    assert len(wire) == len(inner) + len(decoded) + 11
    assert validate_graph_shadow(inner, decoded, context).revision == 1


@pytest.mark.parametrize("kind", [
    "mapping", "root_extra", "private_mapping", "api_bool",
    "api1", "noncanonical", "duplicate", "oversize",
])
def test_decoder_rejects_integrity_shape_canonical_and_aggregate_budget(kind):
    message, mapping, context, wire = wire_documents()
    value = json.loads(wire)
    if kind == "mapping":
        value["mapping"]["channels"][0]["resource_id"] = "f"*64
    elif kind == "root_extra":
        value["aaa"] = "secret"
    elif kind == "private_mapping":
        # Decoder is not semantic admission: a valid digest alone is insufficient.
        value["mapping"]["service"] = "switch.turn_on"
        value["config"]["mapping_digest"] = digest(value["mapping"])
        value["config_digest"] = digest(value["config"])
        inner, decoded = decode_graph_tuple(canonical(value))
        with pytest.raises(GraphValidationError):
            validate_graph_shadow(inner, decoded, context)
        return
    elif kind == "api_bool":
        value["api"] = True
    elif kind == "api1":
        value["api"] = 1
    elif kind == "noncanonical":
        wire = " " + wire
    elif kind == "duplicate":
        wire = wire.replace('"mapping":', '"mapping":{},"mapping":', 1)
    elif kind == "oversize":
        wire = "x"*8193
    if kind not in ("noncanonical", "duplicate", "oversize"):
        wire = canonical(value)
    with pytest.raises(GraphValidationError):
        decode_graph_tuple(wire)


@pytest.mark.parametrize("kind", ["qualification", "service", "outputs", "owner"])
def test_encoder_reuses_full_shared_admission_privacy_contract(kind):
    message, mapping, context, _ = wire_documents()
    if kind == "qualification":
        message["config"]["qualification"]["record_digest"] = "f"*64
    elif kind == "service":
        mapping["service"] = "switch.turn_on"
        message["config"]["mapping_digest"] = digest(mapping)
    elif kind == "outputs":
        message["config"]["qualification"]["outputs_ready"] = True
    elif kind == "owner":
        message["adapter_id"] = "foreign"
    message["config_digest"] = digest(message["config"])
    with pytest.raises(GraphValidationError):
        encode_graph_tuple(canonical(message), canonical(mapping), context)


@pytest.mark.asyncio
async def test_actual_store_to_single_wire_to_actual_firmware_to_readback(hass):
    message, mapping, context, _ = wire_documents()
    j = journal(hass, "atomic_graph_wire")
    await j.async_stage(canonical(message), canonical(mapping), context,
                        capability(context), 100, retained=False)
    sends = []
    async with firmware() as request:
        await admit(request, context)
        async def send(topic, wire):
            assert topic == "ha/config"
            state = await request(op="apply_tuple", raw=wire, now=101)
            sends.append((wire, state))
            assert state["accepted"] and state["writes"] == 1
            assert state["mapping"] == mapping
            assert state["config"] == message["config"]
        sent = await j.async_apply_tuple(send, context, capability(context),
                100, 12, retained=False, transport=TRANSPORT)
        assert len(sends) == 1 and sends[0][0] == sent
        assert json.loads(sent)["sequence"] == 12
        assert j.status == "awaiting_graph_readback" and not j.verified
        state = sends[0][1]
        # A duplicate packet cannot make a second store write.
        again = await request(op="apply_tuple", raw=sent, now=102)
        assert not again["accepted"] and again["writes"] == 1
        ctx = current(context, state)
        assert await j.async_reconcile(state["config"], ctx,
                capability(ctx, state["config_digest"]), 100, retained=False)
        assert j.verified and not j.outputs_enabled


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", [None, "", "api2", "atomic_mapping_tuple.v2", True])
async def test_no_implicit_negotiation_from_api_or_config(hass, transport):
    j = journal(hass, "unnegotiated_tuple")
    message, mapping, context, _ = wire_documents()
    await j.async_stage(canonical(message), canonical(mapping), context,
                        capability(context), 100, retained=False)
    send = AsyncMock()
    with pytest.raises(GraphValidationError, match="^unsupported_transport$"):
        await j.async_apply_tuple(send, context, capability(context), 100, 2,
                                 retained=False, transport=transport)
    send.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["disconnect", "stale", "disk_drift"])
async def test_atomic_form_cannot_bypass_postawait_generation_age_durable_gate(hass, phase):
    j = journal(hass, "atomic_wire_gate")
    message, mapping, context, _ = wire_documents()
    await j.async_stage(canonical(message), canonical(mapping), context,
                        capability(context), 100, retained=False)
    load = j.store.async_load
    async def interrupted():
        value = await load()
        if phase == "disconnect":
            j.invalidate()
        elif phase == "stale":
            j.clock = lambda: 110
        else:
            value = deepcopy(value)
            value["staged"]["mapping"]["mapping_revision"] = 99
        return value
    j.store.async_load = interrupted
    send = AsyncMock()
    with pytest.raises(GraphValidationError):
        await j.async_apply_tuple(send, context, capability(context), 100, 2,
                                 retained=False, transport=TRANSPORT)
    send.assert_not_awaited()
    assert not j.verified


@pytest.mark.asyncio
async def test_corrupt_wire_does_not_consume_core_admission_or_unknown_mapping(hass):
    message, mapping, context, wire = wire_documents()
    async with firmware() as request:
        await admit(request, context)
        bad = json.loads(wire)
        bad["mapping"]["channels"][0]["resource_id"] = "f"*64
        state = await request(op="apply_tuple", raw=canonical(bad), now=101)
        assert not state["accepted"] and state["writes"] == 0
        good = await request(op="apply_tuple", raw=wire, now=102)
        assert good["accepted"] and good["writes"] == 1
