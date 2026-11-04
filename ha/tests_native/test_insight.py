"""What the E32 knows, how the boiler responds and what stood out yesterday (insight.py, E32 rc.5).

fw/telemetry/insight joins the summary as "insight" (hub-only; a retained one from firmware that no longer
sends it is dropped); on the product device the sensors "Knowledge" and "Boiler response" (unknown without
the topic, unavailable while the E32 is silent); each insight is a persistent notification (information,
never a Repairs item); the learned overview says the free heat per room and yesterday's insights in words.
The fixtures follow docs/modern-thermostat/RC5-PLAN.md 2.1-2.3 exactly; the report lists them for the
integrator to compare with the firmware's output.
"""
import json
import string
from copy import deepcopy
from types import SimpleNamespace

import pytest
from homeassistant.components import persistent_notification as pn
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.open_thermostat import insight as module
from custom_components.open_thermostat import learned_overview as lo
from custom_components.open_thermostat.heating_link import (
    FLOW_TOPIC, INSIGHT_MISSED_HEARTBEATS, INSIGHT_TOPIC, HeatingHub, decode_insight, decode_learned, hub_only_topic)

STATUS = {"schema": 1, "revision": 5, "mode": "active", "request": {"heat": True, "flow_c": 41, "reason": "heating"},
          "ha_entities": [],
          "rooms": [{"id": "woonkamer", "name": "Woonkamer", "status": "ok", "temperature": 20.6, "setpoint": 21.0,
                     "demand": True},
                    {"id": "slaapkamer", "name": "Slaapkamer", "status": "ok", "temperature": 17.8, "setpoint": 18.0,
                     "demand": False}]}
SUMMARY = {"schema": 1, "learned": {"schema": 1, "applied": True, "status": "learning"}}
# fw/telemetry/insight as RC5-PLAN.md 2.2 writes it: the parts at the top of a schema 1 document.
INSIGHT = {"schema": 1,
           "knowledge": {"pct": 70, "missing": ["warmup:slaapkamer", "arrival:slaapkamer", "boiler_response"], "more": 0},
           "house": {"ua_kw_per_k": 0.21, "kw_per_flow_k": 0.43, "slope": 0.71, "state": "learned"},
           "boiler": {"held": 3, "rest_s": 540, "ceiling_c": 48, "absorbed_kw": 7.4, "kw_per_k": 0.36, "state": "learned",
                      "return": True},
           "insights": [{"kind": "gas_per_dd_up", "pct": 34}, {"kind": "warmup_slower", "pct": 40, "room": "slaapkamer"}]}
# The worst case the plan allows (<= 700 B): 8 missing keys with 30-character room ids, "more", the house, the
# boiler (P1's object with "return") and 4 insights, two of them with a room.
ROOMS = [f"kamer_met_een_lange_naam_nr_{i}xx"[:30] for i in range(6)]
WORST = {"schema": 1,
         "knowledge": {"pct": 42, "missing": [f"warmup:{ROOMS[0]}", f"cooling:{ROOMS[1]}", f"arrival:{ROOMS[2]}",
                                              f"warmup:{ROOMS[3]}", "curve", "boiler_minimum", "boiler_response", "house"],
                       "more": 9},
         "house": {"ua_kw_per_k": 0.214, "kw_per_flow_k": 0.431, "slope": 1.17, "state": "collecting"},
         "boiler": {"held": 12, "rest_s": 1260, "ceiling_c": 57, "absorbed_kw": 11.8, "kw_per_k": 0.412, "state": "learned",
                    "return": True},
         "insights": [{"kind": "gas_per_dd_up", "pct": 134}, {"kind": "starts_up", "pct": 250},
                      {"kind": "warmup_slower", "pct": 45, "room": ROOMS[4]}, {"kind": "warmup_slower", "pct": 61, "room": ROOMS[5]}]}
# fw/telemetry/flow with the rc.5 additions (RC5-PLAN.md 2.1): "ceiling_c", the learned state "held", the
# boiler's response, and the curve's slope from the house model (2.2).
FLOW = {"schema": 1, "flow": {"source": "curve", "rule_flow_c": 44, "applied_flow_c": 48, "ceiling_c": 48,
                              "curve": {"state": "applied", "flow_c": 46, "slope": 0.71, "slope_source": "house", "windows": 2},
                              "learned": {"state": "held", "flow_c": 52}, "optimum_start": "none", "yesterday": None,
                              "boiler": {"held": 1, "rest_s": None, "ceiling_c": None, "absorbed_kw": None, "kw_per_k": None,
                                         "state": "no_return", "return": False}},
        "night_gas": {"last": None}}
# fw/telemetry/learned/<room> with free heat (RC5-PLAN.md 2.3): six 4-hour dayparts from midnight.
FREE_HEAT = {"rate": [0.0, None, 0.2, 0.4, 0.1, None], "n": [9, 0, 6, 7, 3, 0], "applied_min": 12}


def hub(insight=INSIGHT, summary=SUMMARY):
    h = HeatingHub("fixture")
    h.update(STATUS)
    merged = deepcopy(summary)
    if insight is not None:
        merged["insight"] = decode_insight(json.dumps(insight))
    h.update_summary(merged)
    return h


def localized(sensor, language="en"):
    sensor.hass = SimpleNamespace(config=SimpleNamespace(language=language))
    return sensor


# -- the topic ----------------------------------------------------------------------------------------------------


def test_the_insight_topic_is_read_by_the_hub_alone():
    assert INSIGHT_TOPIC == "fw/telemetry/insight" and hub_only_topic(INSIGHT_TOPIC)


def test_the_insight_joins_the_summary_like_the_scoreboard():
    h = HeatingHub("fixture")
    h.receive("fw/telemetry/summary", json.dumps(SUMMARY))
    assert "insight" not in h.summary
    h.receive(INSIGHT_TOPIC, json.dumps(INSIGHT))
    assert h.summary["insight"] == {key: INSIGHT[key] for key in ("knowledge", "house", "boiler", "insights")}
    assert h.summary["learned"] == SUMMARY["learned"] and not h.insight_gone
    # The other parts keep it; the parts may also come in one "insight" object.
    h.receive(FLOW_TOPIC, json.dumps(FLOW))
    assert h.summary["insight"]["knowledge"]["pct"] == 70 and h.summary["flow"]["ceiling_c"] == 48
    h.receive(INSIGHT_TOPIC, json.dumps({"schema": 1, "insight": {"knowledge": {"pct": 80}}}))
    assert h.summary["insight"] == {"knowledge": {"pct": 80}}
    # A broken or emptied topic takes it out again; the rest of the summary stays.
    for bad in ("not json", json.dumps({**INSIGHT, "schema": 2}), json.dumps({"schema": 1, "knowledge": []}), ""):
        h.receive(INSIGHT_TOPIC, json.dumps(INSIGHT))
        h.receive(INSIGHT_TOPIC, bad)
        assert "insight" not in h.summary and h.insight_gone and h.summary["flow"]["source"] == "curve", bad


def test_the_worst_case_insight_fits_and_reads_completely():
    payload = json.dumps(WORST, separators=(",", ":"))
    assert 650 <= len(payload.encode()) <= 700, len(payload.encode())
    h = HeatingHub("fixture")
    h.update(STATUS)
    h.receive("fw/telemetry/summary", json.dumps(SUMMARY))
    h.receive(INSIGHT_TOPIC, payload)
    part = module.knowledge(h.summary)
    sentences, more = module.missing_sentences(part, {}, "en")
    assert len(sentences) == 8 and more == 9
    assert sentences[0] == f"It still has to see how fast {ROOMS[0]} warms up."
    assert [item["kind"] for item in module.insight_items(h.summary)] == ["gas_per_dd_up", "starts_up", "warmup_slower",
                                                                          "warmup_slower"]


def test_a_retained_insight_goes_when_a_live_e32_sends_none():
    """Firmware without the topic (after a downgrade) leaves a retained insight on the broker: once the E32 has
    been heard for 16 minutes without a new one, it is not current any more."""
    h = HeatingHub("fixture")
    h.receive("fw/telemetry/summary", json.dumps(SUMMARY), retained=True)
    h.receive(INSIGHT_TOPIC, json.dumps(INSIGHT), retained=True)
    beat = lambda n: h.receive("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 60 * n}))
    for n in range(1, INSIGHT_MISSED_HEARTBEATS + 1):
        beat(n)
    assert "insight" in h.summary
    h.receive("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 99}), retained=True)  # a retained beat does not count
    assert "insight" in h.summary
    beat(INSIGHT_MISSED_HEARTBEATS + 1)
    assert "insight" not in h.summary and h.insight_gone
    # An E32 that sends it again brings it back; its messages restart the count.
    h.receive(INSIGHT_TOPIC, json.dumps(INSIGHT))
    for n in range(INSIGHT_MISSED_HEARTBEATS):
        beat(100 + n)
        if n % 5 == 4:
            h.receive(INSIGHT_TOPIC, json.dumps(INSIGHT))
    assert "insight" in h.summary and not h.insight_gone


def test_the_boiler_and_the_free_heat_survive_their_documents():
    h = HeatingHub("fixture")
    h.receive("fw/telemetry/summary", json.dumps(SUMMARY))
    beside = {"schema": 1, "flow": FLOW["flow"], "boiler": {"state": "no_return"}}
    h.receive(FLOW_TOPIC, json.dumps(beside))
    assert h.summary["boiler"] == {"state": "no_return"}
    assert module.boiler_response(h.summary) == FLOW["flow"]["boiler"]  # inside "flow" wins over beside it
    h.receive(INSIGHT_TOPIC, json.dumps(INSIGHT))
    assert module.boiler_response(h.summary) == INSIGHT["boiler"]  # and the insight's over both
    # "free_heat" beside "learned" in fw/telemetry/learned/<room> belongs to the room.
    room, plan = decode_learned("slaapkamer", json.dumps({"schema": 1, "id": "slaapkamer", "learned": {"readiness": "ready"},
                                                          "plan": None, "free_heat": FREE_HEAT}))
    assert room["free_heat"] == FREE_HEAT and plan is None
    inside, _ = decode_learned("slaapkamer", json.dumps({"schema": 1, "id": "slaapkamer", "free_heat": {"n": []},
                                                         "learned": {"free_heat": FREE_HEAT}, "plan": None}))
    assert inside["free_heat"] == FREE_HEAT


# -- the sensors --------------------------------------------------------------------------------------------------


def test_knowledge_is_a_percentage_with_what_it_still_learns_in_words():
    sensor = localized(module.KnowledgeSensor(hub()))
    assert sensor.unique_id == "fixture_hub_knowledge" and sensor.translation_key == "knowledge"
    assert sensor.native_unit_of_measurement == "%" and sensor.state_class == SensorStateClass.MEASUREMENT
    assert sensor.device_info["identifiers"] == {("open_thermostat", "fixture")}  # the product device, no new device
    assert sensor.available and sensor.native_value == 70
    assert sensor.extra_state_attributes == {"missing": [
        "It still has to see how fast Slaapkamer warms up.",
        "It still has to check whether Slaapkamer is warm on time.",
        "It is still listening to how your boiler holds its temperature."], "more": 0}
    assert "missing" in sensor._unrecorded_attributes  # the sentences are shown, the percentage is kept


@pytest.mark.parametrize("language, first, last", [
    ("nl", "Hij moet nog zien hoe snel Slaapkamer opwarmt.", "Hij luistert nog hoe je ketel zijn temperatuur vasthoudt."),
    ("pl", "Musi jeszcze zobaczyć, jak szybko nagrzewa się pomieszczenie Slaapkamer.",
     "Wciąż wsłuchuje się, jak Twój kocioł utrzymuje swoją temperaturę.")])
def test_knowledge_speaks_dutch_and_polish(language, first, last):
    missing = localized(module.KnowledgeSensor(hub()), language).extra_state_attributes["missing"]
    assert missing[0] == first and missing[-1] == last


def test_every_missing_key_has_its_sentence_and_unknown_ones_count_as_more():
    insight = deepcopy(INSIGHT)
    insight["knowledge"] = {"pct": 35, "more": 2, "missing": [
        "warmup:woonkamer", "cooling:woonkamer", "arrival:woonkamer", "curve", "boiler_minimum", "boiler_response",
        "house", "valves", "warmup:", "warmup:Bad Id", 7]}
    attributes = localized(module.KnowledgeSensor(hub(insight))).extra_state_attributes
    assert attributes["missing"] == [
        "It still has to see how fast Woonkamer warms up.", "It still has to see how fast Woonkamer cools down.",
        "It still has to check whether Woonkamer is warm on time.",
        "It is still learning how much warmer the water must be when it gets colder outside.",
        "It is still finding out from which water temperature your boiler starts heating.",
        "It is still listening to how your boiler holds its temperature.",
        "It is still working out how fast your house loses heat."]
    assert attributes["more"] == 2 + 4  # the E32's own count, and the four keys this version does not know


def test_firmware_without_the_topic_leaves_both_sensors_unknown_and_silence_makes_them_unavailable():
    h = hub(insight=None)
    knowledge, boiler = (localized(cls(h)) for cls in (module.KnowledgeSensor, module.BoilerResponseSensor))
    for sensor in (knowledge, boiler):
        assert sensor.available and sensor.native_value is None and sensor.extra_state_attributes is None
    h.update(None)  # the E32 is offline or silent
    assert not knowledge.available and not boiler.available
    # Odd figures are left out, never shown as a number.
    odd = deepcopy(INSIGHT)
    odd["knowledge"]["pct"], odd["boiler"] = 140, {"state": "sleeping", "held": -1, "rest_s": "long", "ceiling_c": 200}
    knowledge, boiler = (localized(cls(hub(odd))) for cls in (module.KnowledgeSensor, module.BoilerResponseSensor))
    assert knowledge.native_value is None and boiler.native_value is None
    assert boiler.extra_state_attributes == {"held_today": None, "rest_min": None, "ceiling_c": None, "absorbed_kw": None,
                                             "kw_per_k": None, "return_reported": None, "sentence": None}


def test_the_boiler_response_in_figures_and_one_sentence():
    sensor = localized(module.BoilerResponseSensor(hub()))
    assert sensor.unique_id == "fixture_hub_boiler_response" and sensor.translation_key == "boiler_response"
    assert sensor.device_class == SensorDeviceClass.ENUM and sensor.options == ["collecting", "learned", "no_return", "not_driving"]
    assert sensor.native_value == "learned"
    # The ceiling holds near the target only (a room 1 °C or more below its target gets the full water temperature);
    # the boiler holds about the ceiling + 2 °C (the ceiling is the held request minus 2 °C).
    assert sensor.extra_state_attributes == {
        "held_today": 3, "rest_min": 9.0, "ceiling_c": 48, "absorbed_kw": 7.4, "kw_per_k": 0.36, "return_reported": True,
        "sentence": "Your boiler holds about 50 °C and rests 9 minutes; near the target the E32 asks at most 48 °C."}
    assert {"absorbed_kw", "sentence"} <= sensor._unrecorded_attributes


@pytest.mark.parametrize("boiler, en, nl, pl", [
    ({"state": "learned", "rest_s": 450, "ceiling_c": None},
     "Your boiler rests 8 minutes each time it reaches its temperature.",
     "Je ketel rust 8 minuten telkens als hij zijn temperatuur bereikt.",
     "Twój kocioł odpoczywa 8 minut za każdym razem, gdy osiągnie swoją temperaturę."),
    ({"state": "learned", "rest_s": 75, "ceiling_c": None},
     "Your boiler rests 1 minute each time it reaches its temperature.",
     "Je ketel rust 1 minuut telkens als hij zijn temperatuur bereikt.",
     "Twój kocioł odpoczywa 1 minutę za każdym razem, gdy osiągnie swoją temperaturę."),
    ({"state": "learned", "rest_s": None, "ceiling_c": 52},
     "Your boiler holds about 54 °C; near the target the E32 asks at most 52 °C.",
     "Je ketel houdt ongeveer 54 °C vast; dicht bij de doeltemperatuur vraagt de E32 hoogstens 52 °C.",
     "Twój kocioł utrzymuje około 54 °C; blisko temperatury docelowej E32 zadaje najwyżej 52 °C."),
    ({"state": "learned", "rest_s": 180, "ceiling_c": 41, "return": False},
     "Your boiler holds about 43 °C and rests 3 minutes; near the target the E32 asks at most 41 °C.",
     "Je ketel houdt ongeveer 43 °C vast en rust 3 minuten; dicht bij de doeltemperatuur vraagt de E32 hoogstens 41 °C.",
     "Twój kocioł utrzymuje około 43 °C i odpoczywa 3 minuty; blisko temperatury docelowej E32 zadaje najwyżej 41 °C."),
    ({"state": "learned"}, "The E32 has learned how your boiler holds its temperature.",
     "De E32 heeft geleerd hoe je ketel zijn temperatuur vasthoudt.", "E32 nauczył się, jak Twój kocioł utrzymuje swoją temperaturę."),
    ({"state": "collecting", "held": 1}, "The E32 is still listening to how your boiler holds its temperature.",
     "De E32 luistert nog hoe je ketel zijn temperatuur vasthoudt.",
     "E32 wciąż wsłuchuje się, jak Twój kocioł utrzymuje swoją temperaturę."),
    ({"state": "no_return", "return": False},
     "Your boiler does not report the water coming back, so the E32 cannot see how much heat your house takes; it still "
     "learns how your boiler holds its temperature.",
     "Je ketel meldt het terugkomende water niet, dus de E32 kan niet zien hoeveel warmte je huis opneemt; hij leert wel "
     "hoe je ketel zijn temperatuur vasthoudt.",
     "Twój kocioł nie zgłasza temperatury wody powrotnej, więc E32 nie widzi, ile ciepła pobiera Twój dom; nadal uczy się, "
     "jak Twój kocioł utrzymuje swoją temperaturę."),
    ({"state": "not_driving"}, "The E32 listens to your boiler once it controls the boiler itself.",
     "De E32 luistert naar je ketel zodra hij de ketel zelf regelt.",
     "E32 zacznie wsłuchiwać się w Twój kocioł, gdy sam będzie nim sterował.")])
def test_every_boiler_state_has_its_sentence(boiler, en, nl, pl):
    insight = {**INSIGHT, "boiler": boiler}
    for language, expected in (("en", en), ("nl", nl), ("pl", pl)):
        sensor = localized(module.BoilerResponseSensor(hub(insight)), language)
        assert sensor.native_value == boiler["state"] and sensor.extra_state_attributes["sentence"] == expected, language


@pytest.mark.parametrize("count, en, nl, pl", [(1, "1 minute", "1 minuut", "1 minutę"), (2, "2 minutes", "2 minuten", "2 minuty"),
                                              (5, "5 minutes", "5 minuten", "5 minut"), (12, "12 minutes", "12 minuten", "12 minut"),
                                              (22, "22 minutes", "22 minuten", "22 minuty")])
def test_minutes_in_every_language(count, en, nl, pl):
    assert [module.minutes(count, language) for language in ("en", "nl", "pl")] == [en, nl, pl]


def test_without_the_insight_the_boiler_comes_from_the_flow_document():
    h = HeatingHub("fixture")
    h.receive("fw/telemetry/summary", json.dumps(SUMMARY))
    h.receive(FLOW_TOPIC, json.dumps(FLOW))
    h.update(STATUS)  # the E32 reports (a status of its own parts is assembled elsewhere)
    sensor = localized(module.BoilerResponseSensor(h))
    assert sensor.native_value == "no_return" and sensor.extra_state_attributes["return_reported"] is False
    assert localized(module.KnowledgeSensor(h)).native_value is None  # the knowledge needs the insight itself


@pytest.mark.asyncio
async def test_a_product_entry_gets_exactly_the_two_sensors_on_its_device(hass):
    h = hub()
    added = []
    hass.data.setdefault("open_thermostat", {})["e"] = {}
    entry = SimpleNamespace(entry_id="e", async_on_unload=lambda remove: None)
    await module.async_setup_insight(hass, entry, lambda entities, **options: added.extend(entities), {}, h)
    assert [entity.unique_id for entity in added] == ["fixture_hub_knowledge", "fixture_hub_boiler_response"]
    assert isinstance(hass.data["open_thermostat"]["e"]["insight_notifier"], module.InsightNotifier)
    await hass.async_block_till_done()


# -- the notifications --------------------------------------------------------------------------------------------


def notes(hass):
    return {key: dict(value) for key, value in pn._async_get_or_create_notifications(hass).items()
            if key.startswith("open_thermostat_insight_")}


class Store:
    def __init__(self):
        self.saved = None

    def async_delay_save(self, data, delay):
        self.saved = data()


def notifier(hass, h, dismissed=None, entry_id="e"):
    n = module.InsightNotifier(hass, entry_id, h, dismissed, Store())
    remove = pn.async_register_callback(hass, n.notification_changed)
    return n, remove


@pytest.mark.asyncio
async def test_each_insight_is_a_notification_replaced_when_it_changes_and_dismissed_when_it_is_gone(hass):
    hass.config.language = "en"
    h = hub()
    n, remove = notifier(hass, h)
    n.hub_changed()
    shown = notes(hass)
    assert sorted(shown) == ["open_thermostat_insight_gas_per_dd_up_e", "open_thermostat_insight_warmup_slower_slaapkamer_e"]
    gas = shown["open_thermostat_insight_gas_per_dd_up_e"]
    assert gas["title"] == "OpenThermostat: More gas than usual"
    assert gas["message"] == ("Yesterday used 34 % more gas per degree of cold than usual. A window or door left open, or a "
                              "room set warmer, can cause this.\n\nThe E32 compares each day with your house's own usual "
                              "days, corrected for how cold it was. This is information; you do not need to do anything.")
    assert shown["open_thermostat_insight_warmup_slower_slaapkamer_e"]["title"] == "OpenThermostat: Slaapkamer warmed up more slowly"
    # Information, never a Repairs item.
    from homeassistant.helpers import issue_registry as ir
    assert not [issue for (domain, _), issue in ir.async_get(hass).issues.items() if domain == "open_thermostat"]
    # The same again (every E32 message): nothing changes, not even the time it was created.
    created = gas["created_at"]
    n.hub_changed()
    assert notes(hass)["open_thermostat_insight_gas_per_dd_up_e"]["created_at"] == created
    # Changed: replaced; gone: dismissed.
    changed = deepcopy(INSIGHT)
    changed["insights"] = [{"kind": "gas_per_dd_up", "pct": 51}]
    h.update_summary({**SUMMARY, "insight": decode_insight(json.dumps(changed))})
    n.hub_changed()
    assert list(notes(hass)) == ["open_thermostat_insight_gas_per_dd_up_e"]
    assert notes(hass)["open_thermostat_insight_gas_per_dd_up_e"]["message"].startswith("Yesterday used 51 % more gas")
    # While the E32 is silent nothing changes; once its insight is gone, so are the notifications.
    h.update(None)
    n.hub_changed()
    assert len(notes(hass)) == 1
    h.update(STATUS)
    h.update_summary(SUMMARY)
    n.hub_changed()
    assert len(notes(hass)) == 1  # not known (yet) is not gone
    h.insight_gone = True
    n.hub_changed()
    assert notes(hass) == {}
    remove()


@pytest.mark.asyncio
async def test_a_dismissed_insight_stays_dismissed_until_it_changes_also_after_a_restart(hass):
    hass.config.language = "en"
    h = hub()
    n, remove = notifier(hass, h)
    n.hub_changed()
    pn.async_dismiss(hass, "open_thermostat_insight_gas_per_dd_up_e")  # the owner read it
    await hass.async_block_till_done()
    assert n.dismissed == {"open_thermostat_insight_gas_per_dd_up_e": ["gas_per_dd_up", None, 34]}
    assert n.store.saved == {"dismissed": n.dismissed}
    n.hub_changed()
    assert list(notes(hass)) == ["open_thermostat_insight_warmup_slower_slaapkamer_e"]
    remove()
    # A restart of Home Assistant: the notifications are gone, the store remembers what was dismissed.
    for key in list(notes(hass)):
        pn.async_dismiss(hass, key)
    hass.data.pop("open_thermostat_insight_shown")
    again, remove = notifier(hass, h, dismissed=module._dismissed(n.store.saved))
    again.hub_changed()
    assert list(notes(hass)) == ["open_thermostat_insight_warmup_slower_slaapkamer_e"]
    # Tomorrow's judgement says something else: it shows again, and the old dismissal is forgotten.
    changed = deepcopy(INSIGHT)
    changed["insights"][0]["pct"] = 41
    h.update_summary({**SUMMARY, "insight": decode_insight(json.dumps(changed))})
    again.hub_changed()
    assert "open_thermostat_insight_gas_per_dd_up_e" in notes(hass) and again.dismissed == {}
    remove()


@pytest.mark.asyncio
async def test_the_notifications_follow_the_language_and_the_room_name(hass):
    hass.config.language = "nl"
    h = hub()
    n, remove = notifier(hass, h)
    n.hub_changed()
    slow = notes(hass)["open_thermostat_insight_warmup_slower_slaapkamer_e"]
    assert slow["title"] == "OpenThermostat: Slaapkamer warmde langzamer op"
    assert slow["message"].startswith("Gisteren warmde Slaapkamer 40 % langzamer op dan normaal. Een open raam")
    hass.config.language = "pl"
    renamed = deepcopy(STATUS)
    renamed["rooms"][1]["name"] = "Sypialnia"
    h.update(renamed)
    n.hub_changed()
    slow = notes(hass)["open_thermostat_insight_warmup_slower_slaapkamer_e"]
    assert slow["title"] == "OpenThermostat: Pomieszczenie Sypialnia nagrzewało się wolniej"
    assert "pomieszczenie Sypialnia nagrzewało się o 40 % wolniej" in slow["message"]
    remove()


@pytest.mark.asyncio
async def test_a_removed_installation_takes_its_notifications_along(hass):
    h = hub()
    n, remove = notifier(hass, h, entry_id="gone")
    n.hub_changed()
    assert len(notes(hass)) == 2
    remove()
    await module.async_remove_insight(hass, "gone")
    assert notes(hass) == {}


@pytest.mark.parametrize("kind, pct, room, en, nl, pl", [
    ("gas_per_dd_down", 22, None, "Yesterday used 22 % less gas per degree of cold than usual.",
     "Gisteren ging er 22 % minder gas per graad kou door dan normaal.",
     "Wczoraj zużyto o 22 % mniej gazu na stopień zimna niż zwykle."),
    ("starts_up", 80, None, "Yesterday the burner started 80 % more often per heating hour than usual.",
     "Gisteren startte de brander 80 % vaker per stookuur dan normaal.",
     "Wczoraj palnik uruchamiał się o 80 % częściej na godzinę grzania niż zwykle."),
    ("hours_per_dd_up", 31, None, "Yesterday the heating ran 31 % longer per degree of cold than usual.",
     "Gisteren stookte de verwarming 31 % langer per graad kou dan normaal.",
     "Wczoraj ogrzewanie pracowało o 31 % dłużej na stopień zimna niż zwykle.")])
def test_every_insight_kind_in_words(kind, pct, room, en, nl, pl):
    item = {"kind": kind, "pct": pct, "room": room}
    for language, expected in (("en", en), ("nl", nl), ("pl", pl)):
        title, text, meaning = module.insight_text(item, {}, language)
        assert text == expected and title and meaning, language


def test_odd_insights_are_left_out():
    insight = deepcopy(INSIGHT)
    insight["insights"] = [{"kind": "gas_per_dd_up", "pct": "a lot"}, {"kind": "something_new", "pct": 5},
                           {"kind": "warmup_slower", "pct": 40}, {"kind": "warmup_slower", "pct": 40, "room": "Bad Id"},
                           "nonsense", {"kind": "starts_up", "pct": 33.6}]
    assert module.insight_items({"insight": decode_insight(json.dumps(insight))}) == [
        {"kind": "starts_up", "pct": 34, "room": None}]


# -- the learned overview -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("language, text, meaning", [
    ("en", "In the afternoon this room warms up by itself, about 0.4 °C per hour (sun, cooking or people).",
     "Smart warm-up now starts 12 min later for it, so it does not heat what comes for free."),
    ("nl", "'s Middags warmt deze ruimte vanzelf op, ongeveer 0,4 °C per uur (zon, koken of mensen).",
     "Slim opwarmen begint daardoor nu 12 min later, zodat hij niet verwarmt wat gratis komt."),
    ("pl", "Po południu to pomieszczenie samo się nagrzewa, o około 0,4 °C na godzinę (słońce, gotowanie lub ludzie).",
     "Inteligentne nagrzewanie zaczyna teraz dzięki temu 12 min później, więc nie grzeje tego, co przychodzi za darmo.")])
def test_free_heat_per_room_in_words(language, text, meaning):
    lines = lo.room_overview("Slaapkamer", {"readiness": "learning", "segments": 2, "free_heat": FREE_HEAT}, None, language,
                             str)["lines"]
    assert {"text": text, "meaning": meaning} in lines


def test_a_room_with_free_heat_says_so_and_a_room_without_it_says_nothing():
    """P3: "free_heat" sits in "learned" of fw/telemetry/learned/<room>; it is null before any judged window and
    left out of a message near its 1000 B budget. A room without it gets no line, never an "unknown" one."""
    h = HeatingHub("fixture")
    h.update(STATUS)
    h.update_learned("woonkamer", decode_learned("woonkamer", json.dumps(
        {"schema": 1, "id": "woonkamer", "learned": {"readiness": "learning", "segments": 2}, "plan": None})))
    h.update_learned("slaapkamer", decode_learned("slaapkamer", json.dumps(
        {"schema": 1, "id": "slaapkamer", "learned": {"readiness": "learning", "segments": 3, "free_heat": FREE_HEAT}, "plan": None})))
    sensor = lo.LearnedOverviewSensor(SimpleNamespace(entry_id="e"), h, clock=str)
    sensor.hass = SimpleNamespace(config=SimpleNamespace(language="en"))
    living, bedroom = sensor.extra_state_attributes["rooms"]
    assert not any("by itself" in line["text"] for line in living["lines"])
    assert bedroom["lines"][-1]["text"].startswith("In the afternoon this room warms up by itself")
    h.update_learned("slaapkamer", decode_learned("slaapkamer", json.dumps(
        {"schema": 1, "id": "slaapkamer", "learned": {"readiness": "learning", "segments": 3, "free_heat": None}, "plan": None})))
    assert not any("by itself" in line["text"] for line in sensor.extra_state_attributes["rooms"][1]["lines"])


def test_free_heat_needs_five_windows_and_a_real_rise():
    assert lo.free_heat({"free_heat": FREE_HEAT}) == (3, 0.4, 12)
    morning = {"rate": [None, None, 0.3, None, None, None], "n": [0, 0, 5, 0, 0, 0], "applied_min": 0}
    assert lo.free_heat_line({"free_heat": morning}, None, "en") == (
        "In the morning this room warms up by itself, about 0.3 °C per hour (sun, cooking or people).",
        "Smart warm-up takes this into account when it plans a warm-up at that time of day.")
    assert lo.free_heat_line({}, {"free_heat": morning}, "en")[0].startswith("In the morning")  # carried by the plan
    for odd in ({"rate": [0.5] * 6, "n": [4] * 6}, {"rate": [0.04] * 6, "n": [9] * 6}, {"rate": [0.5] * 5, "n": [9] * 5},
                {"rate": ["0.5"] * 6, "n": [9] * 6}, {"rate": [True] * 6, "n": [9] * 6}, None, []):
        assert lo.free_heat({"free_heat": odd}) is None, odd


@pytest.mark.parametrize("language, status, figure", [
    ("en", "Weather compensation: estimated from your house for now, learning more (2 of 6 steady periods).",
     "Weather compensation, estimated from your house: the water gets about 0.71 °C warmer for every degree colder outside."),
    ("nl", "Weerafhankelijke regeling: voorlopig geschat uit je huis, hij leert nog bij (2 van 6 rustige periodes).",
     "Weerafhankelijke regeling, geschat uit je huis: het water wordt ongeveer 0,71 °C warmer voor elke graad kouder buiten."),
    ("pl", "Kompensacja pogodowa: na razie oszacowana na podstawie Twojego domu, wciąż się uczy (2 z 6 stabilnych okresów).",
     "Kompensacja pogodowa oszacowana na podstawie Twojego domu: woda jest cieplejsza o około 0,71 °C na każdy stopień "
     "zimniej na zewnątrz.")])
def test_a_curve_worked_out_from_the_house_says_so(language, status, figure):
    summary = {**SUMMARY, "flow": FLOW["flow"]}
    texts = [line["text"] for line in lo.house_overview(summary, language)]
    assert texts[0] == status and figure in texts
    # "held": the boiler's own ceiling binds; the boiler sentence says that, not "Coolest water".
    assert not any("Coolest water" in text or "Koelste water" in text for text in texts)
    plain = {"state": "applied", "slope": 0.71, "slope_source": "house"}
    assert lo.curve_status(plain, True, language)[0] == status.split(" (")[0].rstrip(".") + "."


def test_the_learned_overview_lists_yesterdays_insights():
    h = hub()
    sensor = lo.LearnedOverviewSensor(SimpleNamespace(entry_id="e"), h, clock=str)
    sensor.hass = SimpleNamespace(config=SimpleNamespace(language="en"))
    insights = sensor.extra_state_attributes["insights"]
    assert insights == [
        {"text": "Yesterday used 34 % more gas per degree of cold than usual.",
         "meaning": "A window or door left open, or a room set warmer, can cause this."},
        {"text": "Yesterday Slaapkamer warmed up 40 % more slowly than usual.",
         "meaning": "A window left open, a closed radiator valve or furniture in front of the radiator can slow a room down."}]
    assert "insights" in sensor._unrecorded_attributes
    h.update_summary(SUMMARY)  # firmware before rc.5
    assert sensor.extra_state_attributes["insights"] == []


# -- the texts ----------------------------------------------------------------------------------------------------


def fields(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_language_has_every_insight_text_with_the_same_placeholders():
    keys = set(module.TEXT["en"])
    assert {"missing." + key for key in (*module.HOUSE_KEYS, *module.ROOM_KEYS)} <= keys
    assert {f"{part}.{kind}" for part in ("insight", "title", "mean") for kind in module.INSIGHT_KINDS} <= keys
    assert {"boiler." + state for state in module.BOILER_STATES} <= keys
    for language, texts in module.TEXT.items():
        assert set(texts) == keys, language
        for key, text in texts.items():
            assert fields(text) == fields(module.TEXT["en"][key]), (language, key)
            assert text.strip() and (language == "en" or text != module.TEXT["en"][key]), (language, key)
    for key in ("free_heat", "free_heat_applied", "free_heat_mean", "curve_status_house", "curve_status_house_plain",
                "curve_house", *(f"daypart.{n}" for n in range(6))):
        assert all(key in lo.TEXT[language] for language in ("en", "nl", "pl")), key


def test_the_new_entity_and_card_texts_are_in_every_translation():
    from pathlib import Path
    base = Path(module.__file__).parent
    english = json.loads((base / "strings.json").read_text(encoding="utf-8"))["entity"]["sensor"]
    for language in ("en", "nl", "pl"):
        sensor = json.loads((base / "translations" / f"{language}.json").read_text(encoding="utf-8"))["entity"]["sensor"]
        assert sensor["knowledge"]["name"] and sensor["boiler_response"]["name"]
        assert set(sensor["boiler_response"]["state"]) == set(module.BOILER_STATES)
        for path in (("knowledge", "state_attributes", "card", "state"), ("flow_curve", "state_attributes", "chart", "state")):
            words, source = sensor, english
            for key in path:
                words, source = words[key], source[key]
            assert set(words) == set(source), (language, path)
            for key, text in words.items():
                assert fields(text) == fields(source[key]) and text.strip(), (language, key)
