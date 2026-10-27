"""HA-zone civil time resolution; never a browser timezone or silent DST fold."""
from datetime import datetime,timezone,timedelta
import pytest
from custom_components.open_thermostat.room_vacation import local_end_candidates

NOW=datetime(2026,10,24,tzinfo=timezone.utc)


def test_normal_local_end_is_explicit_iso_and_same_utc_in_all_clients():
    rows=local_end_candidates('2026-10-30T18:00','Europe/Amsterdam',NOW)
    assert rows==[{'iso':'2026-10-30T18:00:00+01:00','until_utc':int(datetime(2026,10,30,17,tzinfo=timezone.utc).timestamp()),'utc_offset':'+0100'}]
    assert len(local_end_candidates('2026-10-30T18:00','UTC',NOW))==1


@pytest.mark.parametrize('local,zone,offsets',[
    ('2026-10-25T02:30','Europe/Amsterdam',['+0200','+0100']),
    ('2026-10-25T01:30','Europe/London',['+0100','+0000']),
    ('2027-04-04T01:45','Australia/Lord_Howe',['+1100','+1030'])])
def test_ambiguous_clocks_return_both_distinct_ordered_occurrences(local,zone,offsets):
    rows=local_end_candidates(local,zone,NOW)
    assert [r['utc_offset'] for r in rows]==offsets
    assert rows[0]['until_utc']<rows[1]['until_utc']
    assert all(int(datetime.fromisoformat(r['iso']).timestamp())==r['until_utc'] for r in rows)


@pytest.mark.parametrize('local,zone',[
    ('2027-03-28T02:30','Europe/Amsterdam'),('2027-10-03T02:15','Australia/Lord_Howe')])
def test_nonexistent_clock_never_rolls_forward_to_a_different_time(local,zone):
    with pytest.raises(ValueError,match='^vacation_nonexistent_time$'):
        local_end_candidates(local,zone,NOW)


def test_only_remaining_future_fold_is_returned_after_first_occurrence_has_passed():
    rows=local_end_candidates('2026-10-25T02:30','Europe/Amsterdam',datetime(2026,10,25,0,45,tzinfo=timezone.utc))
    assert len(rows)==1 and rows[0]['utc_offset']=='+0100'


@pytest.mark.parametrize('value',[None,True,'2026-10-30','2026-10-30 18:00','2026-10-30T18:00Z',
    '2026-10-30T18:00+01:00','2026-10-30T18:00:00.1','2026-02-30T18:00','0001-01-01T00:00','x'*10000])
def test_invalid_local_inputs_are_bounded_and_never_guessed(value):
    with pytest.raises(ValueError,match='^vacation_date_invalid$'):
        local_end_candidates(value,'Europe/Amsterdam',NOW)


def test_expiry_is_future_and_bounded_in_utc_including_exact_boundary():
    value=(NOW+timedelta(days=366)).strftime('%Y-%m-%dT%H:%M')
    assert local_end_candidates(value,'UTC',NOW)[0]['until_utc']==int(NOW.timestamp())+366*86400
    for value in ['2026-10-24T00:00','2026-10-23T23:59',(NOW+timedelta(days=366,minutes=1)).strftime('%Y-%m-%dT%H:%M')]:
        with pytest.raises(ValueError,match='^vacation_date_range$'):local_end_candidates(value,'UTC',NOW)
    with pytest.raises(ValueError,match='^vacation_timezone_unavailable$'):
        local_end_candidates('2026-10-30T18:00','Unknown/Zone',NOW)
