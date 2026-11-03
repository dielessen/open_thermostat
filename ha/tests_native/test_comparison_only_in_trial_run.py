"""The comparison with the thermostat on the boiler bus exists only in the trial run (rc.3).

The owner's E32 controls the boiler (mode active) with no thermostat on the bus, yet the dashboard
kept "E32 compared with your thermostat" and the agreement sensor stayed as a restored, unavailable
record. Now the dashboard follows the E32's live mode, and the comparison records of this entry go
once the E32 controls the boiler and hears no thermostat for a while (untouched ones only); back in
a trial run with a thermostat on the bus they come again.
"""
import json
import logging
from datetime import timedelta

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat import native_entity_cleanup
from custom_components.open_thermostat.dashboard import RoomDashboard
from custom_components.open_thermostat.native_entity_cleanup import (
    RETIRED_GRACE_S, cleanup_stale_entities, comparison_over, note_heating_status)
from test_dashboard_heating import STATUS, installation
from test_heating_link import FULL, TODAY, TODAY_KEYS, _setup
from test_retired_entities import Clock, records
from test_product_flow import product
from test_v1_native import entry, room

SHADOW_IDS = [f"fixture_hub_shadow_{key}" for key in TODAY_KEYS]
ALONE = {**TODAY, "tado_unknown_s": TODAY["s"], "tado": {"heat_s": 0, "starts": 0, "flow_min_c": None,
         "flow_max_c": None, "flow_mean_c": None}}


def known(entity_id, also=()):
    return [{"condition": "state", "entity": entity_id, "state_not": ["unavailable", "unknown", *also]}]


def readiness_record(hass, e):
    return er.async_get(hass).async_get_or_create(
        "sensor", "open_thermostat", "fixture_hub_takeover_readiness", config_entry=e,
        suggested_object_id="fixture_hub_takeover_readiness").entity_id


def now_cards(config):
    return config["views"][0]["sections"][0]["cards"]


# -- the dashboard -------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_active_mode_has_no_comparison_link_or_subview(hass):
    e, rooms, sensors, hub, fields = installation(hass)
    readiness = readiness_record(hass, e)
    hass.data["open_thermostat"][e.entry_id]["heating_hub"].update({**STATUS, "mode": "active"})
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert [v["path"] for v in config["views"]] == ["heating", "boiler", "diagnostics"]
    text = json.dumps(config)
    assert "compared with your thermostat" not in text and "/comparison" not in text
    for key in ("shadow_agreement_today", "shadow_tado_heating_time_today", "shadow_tado_starts_today"):
        assert hub[key] not in text
    # The readiness tile stays (it hides itself on not_applicable) but leads to no missing subview.
    tile = next(c for c in now_cards(config) if c.get("entity") == readiness)
    assert tile["visibility"] == known(readiness, ("not_applicable",)) and "tap_action" not in tile
    # The loose Bluetooth sensor is not lost with the subview: it is on the Heating view.
    headings = [s["cards"][0]["heading"] for s in config["views"][0]["sections"]]
    assert headings[-1] == "Bluetooth sensors"
    assert sensors["temperature"] in json.dumps(config["views"][0])


@pytest.mark.asyncio
@pytest.mark.parametrize("language, link, compare", [("en", "E32 compared with your thermostat", "E32 and thermostat"),
                                                     ("nl", "E32 vergeleken met je thermostaat",
                                                      "E32 en thermostaat vergeleken")])
async def test_trial_run_with_a_thermostat_shows_the_link_and_the_subview(hass, language, link, compare):
    e, rooms, sensors, hub, fields = installation(hass, language)
    readiness = readiness_record(hass, e)
    dashboard = RoomDashboard(hass, "fixture", e.entry_id)
    config = dashboard._dashboard_config()
    sub_path = "/" + dashboard.path + "/comparison"
    card = next(c for c in now_cards(config) if c.get("heading") == link)
    assert card["tap_action"] == {"action": "navigate", "navigation_path": sub_path}
    assert card["visibility"] == known(hub["shadow_agreement_today"])
    # The readiness tile still opens the subview, which starts with the check.
    tile = next(c for c in now_cards(config) if c.get("entity") == readiness)
    assert tile["tap_action"] == {"action": "navigate", "navigation_path": sub_path}
    subview = next(v for v in config["views"] if v["path"] == "comparison")
    headings = [s["cards"][0]["heading"] for s in subview["sections"]]
    assert headings[:2] == [{"en": "Ready to take over?", "nl": "Klaar om over te nemen?"}[language], compare]
    # The comparison cards only while a thermostat is heard: no "Unavailable" tiles without one.
    for section in subview["sections"][1:3]:
        assert all(c["visibility"] == known(hub["shadow_agreement_today"]) for c in section["cards"])


@pytest.mark.asyncio
async def test_trial_run_without_a_thermostat_keeps_the_readiness_check_reachable(hass):
    e, rooms, sensors, hub, fields = installation(hass)
    entities = er.async_get(hass)
    for key in [k for k in hub if k.startswith("shadow_")]:
        entities.async_remove(hub.pop(key))
    readiness = readiness_record(hass, e)
    dashboard = RoomDashboard(hass, "fixture", e.entry_id)
    config = dashboard._dashboard_config()
    assert not any(c.get("heading") == "E32 compared with your thermostat" for c in now_cards(config))
    tile = next(c for c in now_cards(config) if c.get("entity") == readiness)
    assert tile["tap_action"]["navigation_path"] == "/" + dashboard.path + "/comparison"
    subview = next(v for v in config["views"] if v["path"] == "comparison")
    assert [s["cards"][0]["heading"] for s in subview["sections"]] == ["Ready to take over?", "Bluetooth sensors"]


@pytest.mark.asyncio
async def test_the_dashboard_follows_the_mode_without_regenerating_by_hand(hass):
    e, rooms, sensors, hub, fields = installation(hass)
    dashboard = RoomDashboard(hass, "fixture", e.entry_id)
    saved = []

    class Store:
        async def async_load(self, force):
            return saved[-1] if saved else None

        async def async_save(self, config):
            saved.append(config)
    dashboard._store = Store()
    dashboard._watch_hub()
    heating = hass.data["open_thermostat"][e.entry_id]["heating_hub"]
    heating.update(STATUS)
    await hass.async_block_till_done()
    assert "comparison" in [v["path"] for v in saved[-1]["views"]]
    heating.update({**STATUS, "mode": "active"})  # the takeover
    await hass.async_block_till_done()
    assert "comparison" not in [v["path"] for v in saved[-1]["views"]]
    assert "compared with your thermostat" not in json.dumps(saved[-1])
    # A silent E32 keeps its last mode: no subview appears or disappears during an outage.
    heating.update(None)
    await hass.async_block_till_done()
    assert "comparison" not in [v["path"] for v in saved[-1]["views"]]
    heating.update(STATUS)  # given back: a trial run again
    await hass.async_block_till_done()
    assert "comparison" in [v["path"] for v in saved[-1]["views"]]
    heating.update(None)
    await hass.async_block_till_done()
    assert "comparison" in [v["path"] for v in saved[-1]["views"]]
    dashboard._unwatch_hub()


# -- the registry records ------------------------------------------------------------------------------------

def statuses(hass, p, status, clock, seconds):
    """Heating statuses arriving for this long (heating_link calls note_heating_status on each)."""
    hass.data.setdefault("open_thermostat", {}).setdefault(p.entry_id, {})
    note_heating_status(hass, p, "fixture", status)
    clock.now += seconds
    note_heating_status(hass, p, "fixture", status)


ACTIVE = {**FULL, "mode": "active"}


def test_the_comparison_is_over_only_in_active_mode_without_a_thermostat():
    assert comparison_over(ACTIVE) and comparison_over({**ACTIVE, "shadow": {"today": ALONE}})
    assert not comparison_over({**ACTIVE, "shadow": {"today": TODAY}})  # a thermostat still heard today
    assert not comparison_over(FULL) and not comparison_over({**FULL, "shadow": {"today": ALONE}})  # trial run
    assert not comparison_over(None)


@pytest.mark.asyncio
async def test_untouched_comparison_records_go_after_the_grace_in_active_mode(hass, caplog, monkeypatch):
    p = product(hass, room(hass))
    registry, record = records(hass, p)
    shadow = [record(uid) for uid in SHADOW_IDS]
    named = record("fixture_hub_shadow_agreement_today_x")  # not a comparison identity
    foreign = [record(SHADOW_IDS[0], platform="other_integration"),
               record(SHADOW_IDS[1], config_entry=entry(hass), platform="open_thermostat_other")]
    clock = Clock(monkeypatch)
    # Never at setup.
    assert cleanup_stale_entities(hass, p, "fixture") == []
    assert all(registry.async_get(entity_id) for entity_id in shadow)
    # Not in a trial run, nor while a thermostat is still heard today.
    statuses(hass, p, {**FULL, "shadow": {"today": ALONE}}, clock, RETIRED_GRACE_S + 1)
    statuses(hass, p, {**ACTIVE, "shadow": {"today": TODAY}}, clock, RETIRED_GRACE_S + 1)
    assert all(registry.async_get(entity_id) for entity_id in shadow)
    # Active without a thermostat, not yet long enough.
    statuses(hass, p, ACTIVE, clock, RETIRED_GRACE_S - 1)
    assert all(registry.async_get(entity_id) for entity_id in shadow)
    with caplog.at_level(logging.INFO):
        clock.now += 1
        note_heating_status(hass, p, "fixture", ACTIVE)
    assert not any(registry.async_get(entity_id) for entity_id in shadow)
    assert all(registry.async_get(entity_id) for entity_id in [named, *foreign])
    assert "history and long-term statistics are kept" in caplog.text and shadow[0] in caplog.text


@pytest.mark.asyncio
async def test_the_grace_starts_over_when_the_trial_run_comes_back(hass, monkeypatch):
    p = product(hass, room(hass))
    registry, record = records(hass, p)
    agreement = record(SHADOW_IDS[-1])
    clock = Clock(monkeypatch)
    statuses(hass, p, ACTIVE, clock, RETIRED_GRACE_S - 10)
    statuses(hass, p, FULL, clock, 20)  # back to the trial run for a moment
    statuses(hass, p, ACTIVE, clock, RETIRED_GRACE_S - 10)
    assert registry.async_get(agreement) is not None
    clock.now += 10
    note_heating_status(hass, p, "fixture", ACTIVE)
    assert registry.async_get(agreement) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("choice", [{"name": "Overeenstemming"}, {"icon": "mdi:compare"}, {"area_id": "woonkamer"},
                                    {"disabled_by": er.RegistryEntryDisabler.USER},
                                    {"hidden_by": er.RegistryEntryHider.USER}])
async def test_a_customised_comparison_record_is_kept(hass, choice, monkeypatch):
    p = product(hass, room(hass))
    registry, record = records(hass, p)
    customised = record(SHADOW_IDS[-1], **choice)
    plain = record(SHADOW_IDS[0])
    statuses(hass, p, ACTIVE, Clock(monkeypatch), RETIRED_GRACE_S + 1)
    assert registry.async_get(customised) is not None and registry.async_get(plain) is None


@pytest.mark.asyncio
async def test_the_heating_link_notes_every_status(hass, monkeypatch):
    seen = []
    monkeypatch.setattr(native_entity_cleanup, "note_heating_status",
                        lambda hass, entry, prefix, status: seen.append((entry.entry_id, prefix, status["mode"])))
    entry_, hub, added, send = await _setup(hass, monkeypatch)
    send(ACTIVE)
    assert seen and seen[-1] == ("e", "fixture", "active")


@pytest.mark.asyncio
async def test_the_comparison_comes_back_in_a_trial_run_with_a_thermostat(hass, monkeypatch):
    """Removed in active mode, created again (same entity IDs) once a trial run hears a thermostat."""
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers.entity_platform import EntityPlatform
    from custom_components.open_thermostat import heating_link as module
    config_entry = entry(hass)
    entities = er.async_get(hass)
    dr.async_get(hass).async_get_or_create(config_entry_id=config_entry.entry_id,
                                           identifiers={("open_thermostat", "fixture")})
    _, hub, _, send = await _setup(hass, monkeypatch)
    hass.data["open_thermostat"][config_entry.entry_id] = {"heating_hub": hub}
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain="sensor",
                              platform_name="open_thermostat", platform=None,
                              scan_interval=timedelta(seconds=30), entity_namespace=None)
    platform.config_entry = config_entry
    created = []

    def add(new, **_):
        created.extend(new)
        hass.async_create_task(platform.async_add_entities(new))

    def entity_ids():
        return [entities.async_get_entity_id("sensor", "open_thermostat", uid) for uid in SHADOW_IDS]
    clock = Clock(monkeypatch)
    stop = module.track_entities(hub, add, {}, module.wanted_sensors)
    remove = hub.add_listener(lambda: note_heating_status(hass, config_entry, "fixture", hub.status))
    try:
        send({**FULL, "shadow": {"today": TODAY}})
        await hass.async_block_till_done()
        first = entity_ids()
        assert None not in first and len([e for e in created if isinstance(e, module.ShadowSensor)]) == 5
        # The takeover: no thermostat any more. Kept during the grace, then removed with their entities.
        send({**ACTIVE, "shadow": {"today": ALONE}})
        clock.now += RETIRED_GRACE_S + 1
        send({**ACTIVE, "shadow": {"today": ALONE}})
        await hass.async_block_till_done()
        assert entity_ids() == [None] * 5 and all(hass.states.get(entity_id) is None for entity_id in first)
        send(ACTIVE)
        await hass.async_block_till_done()
        assert entity_ids() == [None] * 5  # not created again in active mode
        # Given back to the thermostat: a trial run that hears it creates them again.
        send({**FULL, "shadow": {"today": TODAY}})
        await hass.async_block_till_done()
        assert entity_ids() == first
        assert len([e for e in created if isinstance(e, module.ShadowSensor)]) == 10
        assert all(hass.states.get(entity_id) is not None for entity_id in first)
    finally:
        remove()
        stop()
        await platform.async_reset()
