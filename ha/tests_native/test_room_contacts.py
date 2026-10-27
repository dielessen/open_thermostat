"""Real room models plus pure source-age/debounce tests; no devices or network."""
from copy import deepcopy
import pytest
from custom_components.open_thermostat.room_contacts import (
    ContactAggregator, ContactPolicy, ContactSample, contacts_from_dict,
)


def sample(value, age=0, token='original'):
    return ContactSample(value, age, token)


def test_multiple_contacts_pause_on_any_open_and_resume_only_after_all_close():
    a=ContactAggregator(ContactPolicy(120000,0,30000))
    assert a.assess(0,(sample(False),sample(True))).open is True
    for now in (1,10000,30000):
        r=a.assess(now,(sample(False,now),sample(False,now-1,'closed')))
        assert r.open is True and r.reason=='contact_close_delay'
    r=a.assess(30001,(sample(False,30001),sample(False,30000,'closed')))
    assert r.open is False and r.age_ms==30001


def test_repeated_assessment_never_renews_original_age():
    a=ContactAggregator(ContactPolicy(10000,0,0))
    for now in (0,1,9999):
        r=a.assess(now,(sample(False,now),))
        assert r.open is False and r.age_ms==now
    assert a.assess(10000,(sample(False,10000),)).open is None


def test_unknown_closed_contact_prevents_resume_but_a_known_open_still_inhibits():
    a=ContactAggregator(ContactPolicy(120000,0,0))
    assert a.assess(0,(sample(False),sample(None))).open is None
    assert a.assess(1,(sample(True),sample(None))).open is True
    assert a.assess(2,(sample(False),sample(None))).open is None
    assert a.assess(3,(sample(False),sample(False))).open is False


def test_open_delay_uses_the_age_of_the_prior_closed_proof():
    a=ContactAggregator(ContactPolicy(120000,10000,0))
    assert a.assess(100,(sample(False),)).open is False
    r=a.assess(200,(sample(True),));assert r.open is False and r.age_ms==100 and r.pending_ms==10000
    r=a.assess(10199,(sample(True,9999),));assert r.open is False and r.age_ms==10099
    assert a.assess(10200,(sample(True,10000),)).open is True


def test_an_opening_delay_cannot_use_a_missing_or_expired_closed_baseline():
    a=ContactAggregator(ContactPolicy(10000,5000,0))
    assert a.assess(0,(sample(True),)).open is None
    assert a.assess(1000,(sample(False),)).open is False
    assert a.assess(10000,(sample(True),)).open is False
    assert a.assess(11000,(sample(True,1000),)).open is None


def test_unknown_drops_the_prior_closed_baseline_and_restarts_close_delay():
    a=ContactAggregator(ContactPolicy(120000,0,1000))
    assert a.assess(0,(sample(False),)).open is None
    assert a.assess(1000,(sample(False,1000),)).open is False
    assert a.assess(1001,(sample(None),)).open is None
    assert a.assess(1002,(sample(False),)).open is None
    assert a.assess(2002,(sample(False,1000),)).open is False


def test_cancelled_debounce_cannot_resume_from_an_old_timer():
    a=ContactAggregator(ContactPolicy(120000,0,1000))
    assert a.assess(0,(sample(True),)).open is True
    assert a.assess(1,(sample(False),)).pending_ms==1000
    assert a.assess(900,(sample(True),)).open is True
    assert a.assess(1001,(sample(False),)).open is True
    assert a.assess(2001,(sample(False,1000),)).open is False


def test_clock_reversal_and_reset_remove_admitted_context():
    a=ContactAggregator(ContactPolicy(120000,0,1000))
    a.assess(1000,(sample(False),));assert a.assess(2000,(sample(False,1000),)).open is False
    assert a.assess(1999,(sample(False,999),)).reason=='contact_clock_reversed'
    assert a.assess(2001,(sample(False,1001),)).open is None
    a.reset();assert a.assess(2002,(sample(False,1002),)).open is None


@pytest.mark.parametrize('value',[True,-1,0,999,86400001,1.0,'120000',None])
def test_policy_rejects_invalid_source_age(value):
    with pytest.raises(ValueError):ContactPolicy.from_dict(dict(maximum_age_ms=value,open_delay_ms=0,close_delay_ms=0))


@pytest.mark.parametrize('key,value',[('open_delay_ms',True),('close_delay_ms',-1),('open_delay_ms',600001),('close_delay_ms',120000)])
def test_policy_rejects_invalid_delays(key,value):
    p=dict(maximum_age_ms=120000,open_delay_ms=0,close_delay_ms=0);p[key]=value
    with pytest.raises(ValueError):ContactPolicy.from_dict(p)


def contact(entity='binary_sensor.window',unique='window',kind='window'):
    return dict(entity=dict(entity_id=entity,platform='mqtt',unique_id=unique),kind=kind)


def test_contacts_keep_permanent_identity_and_kind_without_display_name_binding():
    raw=[contact(),contact('binary_sensor.door','door','door')]
    assert [c.as_dict() for c in contacts_from_dict(raw)]==raw


@pytest.mark.parametrize('fault',['duplicate','identity_alias','domain','kind','extra','empty_id','missing_identity','too_many'])
def test_invalid_contact_inventory_is_rejected(fault):
    c=contact();raw=[c]
    if fault=='duplicate':raw.append(deepcopy(c))
    if fault=='identity_alias':raw.append(contact('binary_sensor.renamed','window'))
    if fault=='domain':c['entity']['entity_id']='switch.not_a_contact'
    if fault=='kind':c['kind']='temperature'
    if fault=='extra':c['trust']=True
    if fault=='empty_id':c['entity']['entity_id']='binary_sensor.'
    if fault=='missing_identity':c['entity']['platform']=None
    if fault=='too_many':raw=[contact(f'binary_sensor.c{i}',str(i)) for i in range(9)]
    with pytest.raises(ValueError):contacts_from_dict(raw)
