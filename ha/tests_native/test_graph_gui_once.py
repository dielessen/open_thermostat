"""Native options acceptance gaps; real existing worker/journal/C++ peer, offline IO boundary."""
import asyncio
import json
import os
from pathlib import Path
import pytest
from test_graph_review_flow import native_graph
from test_graph_draft_apply import saved_graph


def evidence(row):
    if path := os.environ.get('OPENTHERMOSTAT_GRAPH_GUI_EVIDENCE'):
        with Path(path).open('a') as f:
            f.write(json.dumps(row, sort_keys=True)+'\n')


@pytest.mark.asyncio
@pytest.mark.parametrize('same_flow', [True, False])
async def test_simultaneous_same_or_two_flow_confirmations_send_config_once(native_graph, same_flow):
    n = native_graph
    await n.stage()
    first = n.flow()
    await first.async_step_graph_review()
    second = first if same_flow else n.flow()
    if not same_flow:
        await second.async_step_graph_review()
    results = await asyncio.gather(first.async_step_graph_review({'confirm_apply': True}),
                                   second.async_step_graph_review({'confirm_apply': True}))
    sent = sum(topic == 'ha/config' for topic, _ in n.publications)
    await n.drain()
    remote = await n.peer.request('status')
    evidence(dict(scenario='same_flow' if same_flow else 'two_flows',
                  config_publications=sent, durable_writes=remote['writes'],
                  readback_verified=n.client.graph_ready,
                  boiler_output_enabled=remote['boiler_output_enabled'],
                  actuator_output_enabled=remote['actuator_output_enabled']))
    assert sent == 1, {'config_publications': sent, 'durable_writes': remote['writes']}
    assert remote['writes'] == 1
    assert n.client.graph_ready and not n.runtime.transport_ready
    assert remote['boiler_output_enabled'] is remote['actuator_output_enabled'] is False
    assert all(result.get('step_id') == 'graph_status' for result in results)


@pytest.mark.asyncio
@pytest.mark.parametrize('saved_graph', [True], indirect=True)
async def test_real_native_options_manager_saved_subentry_prepare_consent_and_exact_readback(saved_graph, hass):
    from homeassistant import loader
    n = saved_graph
    loader.async_setup(hass)
    # Load the actual custom config-flow module through the native loader. The
    # fixture already owns the connection; do not start HTTP/MQTT dependencies.
    component = await loader.async_get_integration(hass, 'open_thermostat')
    await component.async_get_platform('config_flow')
    manager = hass.config_entries.options
    initial = await manager.async_init(n.parent.entry_id)
    assert initial['step_id'] == 'init'
    flow_id = initial['flow_id']
    prepared = await manager.async_configure(flow_id, initial['data_schema']({'graph_action':'prepare'}))
    assert prepared['step_id'] == 'graph_review' and prepared['flow_id'] == flow_id
    assert n.client.journal.status == 'graph_staged_not_applied'
    staged = n.client.journal.state['staged']
    assert staged['config']['rooms'][0]['zone_id'] == n.binding.room_id
    disk = await n.client.journal.store.async_load()
    assert disk['staged'] == staged and disk['accepted'] is None
    assert not n.publications and (await n.peer.request('status'))['writes'] == 0
    pending = await manager.async_configure(flow_id, prepared['data_schema']({'confirm_apply':True}))
    assert pending['step_id'] == 'graph_status' and pending['description_placeholders']['verified'] == 'False'
    assert sum(t == 'ha/config' for t, _ in n.publications) == 1
    from homeassistant.helpers.translation import async_get_translations
    text = await async_get_translations(hass, 'en', 'options', {'open_thermostat'})
    template = text['component.open_thermostat.options.step.graph_status.description']
    rendered = template.format(**pending['description_placeholders'])
    assert 'Device result:not_received' in rendered and 'an ACK is not applied/readback proof' in rendered
    assert 'Current readback verified:False' in rendered
    await n.drain()
    status = await n.peer.request('status')
    accepted = n.client.journal.state['accepted']
    assert status['writes'] == 1 and accepted == staged
    assert n.client.graph_ready and not n.runtime.transport_ready
    assert status['boiler_output_enabled'] is status['actuator_output_enabled'] is False
    evidence(dict(scenario='native_options_manager', prepare='graph_staged_not_applied',
                  pending=pending['description_placeholders'], accepted_revision=accepted['config']['revision'],
                  exact_tuple_persisted_and_readback=True, durable_writes=status['writes'],
                  form_steps=['init','graph_review','graph_status'], english_status_rendered=rendered,
                  physical_outputs_enabled=False))
    done = await manager.async_configure(flow_id, {})
    assert done['reason'] == 'graph_review_complete'
    assert not manager.async_progress()


async def committed_reply(n):
    await n.stage()
    f = n.flow()
    await f.async_step_graph_review()
    await f.async_step_graph_review({'confirm_apply':True})
    topic, raw = n.publications.popleft()
    assert topic == 'ha/config'
    result = await n.peer.request('receive', topic=topic, raw=raw)
    ack = next(frame for frame in result['frames'] if frame['topic']=='fw/config_result')
    return f, result, ack


@pytest.mark.asyncio
async def test_real_cpp_ack_is_visible_but_not_apply_or_readiness_and_contains_no_secrets(native_graph, hass):
    from custom_components.open_thermostat.diagnostics import async_get_config_entry_diagnostics
    n = native_graph
    f, result, ack = await committed_reply(n)
    assert result['writes'] == 1
    before = (n.client.grant_until, n.client.lease_until, n.client._cap_received)
    await n.deliver([ack])
    status = await f.async_step_graph_status()
    assert status['description_placeholders']['device_result'] == 'acknowledged_unverified'
    assert status['description_placeholders']['verified'] == 'False'
    assert status['description_placeholders']['accepted'] == '0'
    assert n.client.journal.state['accepted'] is None and not n.client.graph_ready
    await n.deliver([ack])
    assert (n.client.grant_until, n.client.lease_until, n.client._cap_received) == before
    diagnostic = await async_get_config_entry_diagnostics(hass,n.parent)
    assert diagnostic['graph']['device_result'] == 'acknowledged_unverified'
    public = json.dumps(diagnostic)+json.dumps(status['description_placeholders'])
    for secret in (n.client.session['grant_id'], n.client.session['adapter_session_id'], n.client.profile.qualification_digest):
        assert secret not in public
    evidence(dict(scenario='actual_cpp_ack_only', device_result='acknowledged_unverified',
                  accepted_revision=0,readback_verified=False,deadlines_unchanged=True,
                  diagnostics_redacted=True,physical_outputs_enabled=False))
    await n.deliver([frame for frame in result['frames'] if frame is not ack])
    await n.drain()
    assert n.client.graph_ready and not n.runtime.transport_ready
    assert n.client.journal.state['accepted'] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize('wrong', ['sequence','grant','target_digest','mapping_revision','unknown_status','retained','expired','extra_private'])
async def test_nonmatching_stale_or_malformed_ack_never_looks_applied(native_graph, wrong):
    from types import SimpleNamespace
    n=native_graph
    _, result, ack = await committed_reply(n)
    value=json.loads(ack['raw'])
    if wrong=='sequence':value['sequence']+=1
    if wrong=='grant':value['grant_id']='wrong_grant'
    if wrong=='target_digest':value['config_digest']='0'*64
    if wrong=='mapping_revision':value['mapping_revision']+=1
    if wrong=='unknown_status':value['status']='untrusted_private_status'
    if wrong=='extra_private':value['password']='synthetic-private'
    if wrong=='expired':n.peer.clock[0]+=11
    n.callbacks['message'](SimpleNamespace(topic='fixture/v2/fw/config_result',
        payload=json.dumps(value),retain=wrong=='retained'))
    await n.connection.queue.join()
    assert n.client.graph_status['device_result'] is None
    assert n.client.journal.state['accepted'] is None and not n.client.graph_ready
    assert not n.client.ready and not n.runtime.transport_ready
    evidence(dict(scenario='reject_ack_'+wrong,readback_verified=False,
                  device_result=None,physical_outputs_enabled=False))


@pytest.mark.asyncio
async def test_real_cpp_revision_conflict_is_visible_without_retry_or_remote_adoption(native_graph):
    from custom_components.open_thermostat.graph_shadow_validation import canonical
    n=native_graph
    await n.stage()
    f=n.flow();await f.async_step_graph_review()
    await f.async_step_graph_review({'confirm_apply':True})
    topic,raw=n.publications.popleft()
    bad=json.loads(raw);bad['expected_revision']=7
    result=await n.peer.request('receive',topic=topic,raw=canonical(bad))
    ack=next(frame for frame in result['frames'] if frame['topic']=='fw/config_result')
    assert json.loads(ack['raw'])['status']=='revision_conflict' and result['writes']==0
    await n.deliver([ack])
    status=await f.async_step_graph_status()
    assert status['description_placeholders']['device_result']=='conflict'
    assert status['description_placeholders']['journal_status']=='graph_remote_conflict'
    assert status['description_placeholders']['verified']=='False'
    assert n.client.journal.state['staged'] is not None
    assert n.client.journal.state['accepted'] is None and not n.publications
    assert not n.runtime.transport_ready
    evidence(dict(scenario='actual_cpp_conflict',device_result='conflict',
                  durable_writes=0,readback_verified=False,physical_outputs_enabled=False))


@pytest.mark.asyncio
@pytest.mark.parametrize('completion', ['uncertain','cancelled','grant_rotation','identical_restage'])
async def test_same_tuple_attempt_remains_reserved_across_uncertainty_cancel_grant_and_restage(hass, completion):
    from dataclasses import replace
    from test_graph_shadow_storage import journal,stage,capability
    from custom_components.open_thermostat.graph_shadow_validation import GraphValidationError,canonical
    from custom_components.open_thermostat.graph_wire_codec import TRANSPORT
    j=journal(hass,'attempt_'+completion)
    raw,mapping,ctx,_=await stage(j)
    reviewed=j.review_key(j.state['staged'],ctx)
    sent=[]
    async def send(topic,body):
        sent.append((topic,body))
        if completion=='uncertain':raise RuntimeError('synthetic lost completion')
        if completion=='cancelled':raise asyncio.CancelledError
    async def apply(sequence,context=ctx):
        return await j.async_apply_tuple(send,context,capability(context),100,sequence,
            retained=False,transport=TRANSPORT,reviewed=reviewed)
    if completion in ('uncertain','cancelled'):
        error=RuntimeError if completion=='uncertain' else asyncio.CancelledError
        with pytest.raises(error):await apply(1)
    else:await apply(1)
    if completion=='identical_restage':
        await j.async_stage(canonical(raw),canonical(mapping),ctx,capability(ctx),100,retained=False)
    newer=replace(ctx,grant_id='new_grant',grant_sequence=ctx.grant_sequence+1) if completion=='grant_rotation' else ctx
    with pytest.raises(GraphValidationError,match='^graph_apply_pending$'):
        await apply(2,newer)
    assert len(sent)==1 and not j.verified and not j.outputs_enabled
    assert j.state['accepted'] is None and j.state['staged'] is not None
    evidence(dict(scenario='reserved_'+completion,config_publications=1,
                  readback_verified=False,physical_outputs_enabled=False))


@pytest.mark.asyncio
async def test_lost_uncommitted_send_needs_new_session_and_new_explicit_consent_to_recover(native_graph):
    n=native_graph
    await n.stage()
    old=n.flow();await old.async_step_graph_review()
    await old.async_step_graph_review({'confirm_apply':True})
    topic,_=n.publications.popleft()
    assert topic=='ha/config' and (await n.peer.request('status'))['writes']==0
    n.callbacks['status'](False)
    await n.connection.queue.join()
    await n.connect()
    assert not any(t=='ha/config' for t,_ in n.publications)
    assert n.client.journal.state['staged'] is not None and not n.client.graph_ready
    refused=await old.async_step_graph_review({'confirm_apply':True})
    assert refused['reason']=='graph_review_changed'
    assert not n.publications
    fresh=n.flow();await fresh.async_step_graph_review()
    await fresh.async_step_graph_review({'confirm_apply':True})
    assert sum(t=='ha/config' for t,_ in n.publications)==1
    await n.drain()
    result=await n.peer.request('status')
    assert result['writes']==1 and n.client.graph_ready and not n.runtime.transport_ready
    evidence(dict(scenario='lost_uncommitted_new_consent',new_session_auto_sends=0,
                  new_consent_sends=1,durable_writes=1,readback_verified=True,
                  physical_outputs_enabled=False))
