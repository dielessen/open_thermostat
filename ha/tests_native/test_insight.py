"""What the E32 knows, how the boiler responds and what stood out yesterday (insight.py, E32 rc.5).

fw/telemetry/insight joins the summary as "insight" (hub-only; a retained one from firmware that no longer
sends it is dropped); on the product device the sensors "Knowledge" and "Boiler response" (unknown without
the topic, unavailable while the E32 is silent); each insight is a persistent notification (information,
never a Repairs item; only after a live insight message); the learned overview says the free heat per room
and yesterday's insights in words.

The fixtures have the shapes the rc.5 firmware sends (P14 review): the boiler beside "flow" in the flow
document, free-heat rates null below five windows, and the documents the firmware's own tests print
(test/test_native/test_heating_telemetry.cpp WorstCaseSummaryPartsEachStayWithinTheSoftLimit and
PerRoomLearnedPayloadsStayWithinTheirBudget, test_flow_policy.cpp TheSummaryCurveCarriesItsBaseAndTheDesignFlow)
byte for byte.
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
# fw/telemetry/insight as the firmware sends it (Knowledge.h addInsightJson, published with its schema).
INSIGHT = {"schema": 1,
           "knowledge": {"pct": 70, "missing": ["warmup:slaapkamer", "arrival:slaapkamer", "boiler_response"], "more": 0},
           "house": {"ua_kw_per_k": 0.21, "kw_per_flow_k": 0.43, "slope": 0.71, "state": "learned"},
           "boiler": {"held": 3, "rest_s": 540, "ceiling_c": 48, "absorbed_kw": 7.4, "kw_per_k": 0.36, "state": "learned",
                      "return": True},
           "insights": [{"kind": "gas_per_dd_up", "pct": 34}, {"kind": "warmup_slower", "pct": 40, "room": "slaapkamer"}]}
# The firmware's worst case, byte for byte as test_heating_telemetry.cpp prints it (WorstCaseSummaryParts...):
# eight rooms with 32-character ids and nothing learned (two missing keys fit, "more" counts 26), the house still
# collecting, P1's widest boiler (BoilerResponseWidest.h) and four rooms slower than usual.
WORST_PAYLOAD = (
    '{"schema":1,"knowledge":{"pct":0,"missing":["warmup:woonkamer_aaaaaaaaaaaaaaaaaaaaaa","warmup:keuken_bbbbbbbbbbbbbbbbbbbbbbbbb"],'
    '"more":26},"house":{"ua_kw_per_k":null,"kw_per_flow_k":0.123,"slope":null,"state":"collecting"},"boiler":{"held":65535,'
    '"rest_s":1800,"ceiling_c":null,"absorbed_kw":999.9,"kw_per_k":19.999,"state":"not_driving","return":true},"insights":['
    '{"kind":"warmup_slower","pct":999,"room":"woonkamer_aaaaaaaaaaaaaaaaaaaaaa"},{"kind":"warmup_slower","pct":999,'
    '"room":"keuken_bbbbbbbbbbbbbbbbbbbbbbbbb"},{"kind":"warmup_slower","pct":999,"room":"badkamer_ccccccccccccccccccccccc"},'
    '{"kind":"warmup_slower","pct":999,"room":"slaapkamer_voor_dddddddddddddddd"}]}')
# fw/telemetry/flow as the firmware sends it (TelemetryPublisher: FlowPolicy::addSummary with its schema, the boiler's
# object beside "flow"): the cap in effect ("ceiling_c"), the learned state "held", the curve's own value now
# ("base_c"), its design flow and a slope estimated from the house.
FLOW = {"schema": 1, "flow": {"curve": {"state": "applied", "flow_c": 46, "base_c": 44.6, "slope": 0.71, "slope_source": "house",
                                        "design_flow_c": 55, "windows": 2},
                              "learned": {"state": "held", "flow_c": 52}, "source": "curve", "rule_flow_c": 44, "applied_flow_c": 48,
                              "ceiling_c": 48, "optimum_start": "none", "yesterday": None},
        "night_gas": {"nights": 0, "model_ratio": None, "last": None},
        "boiler": {"held": 1, "rest_s": None, "ceiling_c": None, "absorbed_kw": None, "kw_per_k": None, "state": "no_return",
                   "return": False}}
# The realistic flow summary test_flow_policy.cpp prints (TheSummaryCurveCarriesItsBaseAndTheDesignFlow: a floor room at
# 21 °C, −10 °C outside), byte for byte, with the schema TelemetryPublisher adds.
FLOW_FIRMWARE = (
    '{"schema":1,"flow":{"curve":{"state":"applied","flow_c":47,"base_c":41.7,"slope":0.67,"slope_source":"design",'
    '"design_flow_c":40,"windows":0},"learned":{"state":"not_ready","flow_c":null},"source":"curve","rule_flow_c":40,'
    '"applied_flow_c":47,"ceiling_c":null,"optimum_start":"no_clock","yesterday":null},"night_gas":{"nights":0,'
    '"model_ratio":null,"last":null}}')
# fw/telemetry/learned/<room> with free heat (FreeHeat::addJson): six 4-hour dayparts from midnight, rates in °C per
# hour at 0.1, null below five windows.
FREE_HEAT = {"rate": [0.0, None, 0.2, 0.4, None, None], "n": [9, 0, 6, 7, 3, 0], "applied_min": 12}
# A room's message as test_heating_telemetry.cpp prints it (PerRoomLearnedPayloads..., the widest free heat).
LEARNED_FIRMWARE = (
    '{"schema":1,"id":"woonkamer","learned":{"emitter":"floor","readiness":"ready","readiness_timing":"ready","segments":36,'
    '"periods":36,"loss_per_h":0.0176,"capacity_kwh_per_k":26.42,"advice":[{"shortfall_c":1,"required_c_per_h":0.5,'
    '"flow_c":42,"warmup_h":1.9,"reason":"learned","rule_flow_c":40,"rule_warmup_h":2.2,"rule":"lower_too_slow"}],'
    '"now":{"shortfall_c":-1.5,"required_c_per_h":0,"flow_c":32,"warmup_h":0,"reason":"lowest_learned","rule_flow_c":30,'
    '"rule_warmup_h":null,"rule":"below_learned_range"},"free_heat":{"rate":[1.4,1.4,1.4,1.4,1.4,1.4],"n":[99,99,99,99,99,99],'
    '"applied_min":240}},"plan":{"optimum_start":{"reason":"planned","next_switch":{"utc":1793251800,"target_c":21},'
    '"predicted_start_utc":1793239200,"lead_minutes":210,"flow_c":51,"confidence":"learned","reachable":true,'
    '"start_now":false,"applies":true,"estimate":false},"night":{"reason":"estimated","recommended":"program",'
    '"recommended_night_c":18.5,"saving_m3":0,"saving_eur":null},"arrival":null}}')


def hub(insight=INSIGHT, summary=SUMMARY, flow=None):
    h = HeatingHub("fixture")
    h.update(STATUS)
    merged = deepcopy(summary)
    if insight is not None:
        merged["insight"] = decode_insight(json.dumps(insight))
    if flow is not None:
        merged["flow"] = flow
    h.update_summary(merged)
    return h


def live_hub(insight=INSIGHT, retained=False):
    """A hub that heard the summary and an insight message (live unless retained), and the E32's status."""
    h = HeatingHub("fixture")
    h.receive("fw/telemetry/summary", json.dumps(SUMMARY), retained=retained)
    h.receive(INSIGHT_TOPIC, json.dumps(insight), retained=retained)
    h.update(STATUS)  # the status the parts are assembled into (the test has none of those parts)
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
    """The firmware's own worst case (700 B at most, 650 B at least: it fills the topic) reads in full."""
    assert 650 <= len(WORST_PAYLOAD.encode()) <= 700, len(WORST_PAYLOAD.encode())
    h = HeatingHub("fixture")
    h.update(STATUS)
    h.receive("fw/telemetry/summary", json.dumps(SUMMARY))
    h.receive(INSIGHT_TOPIC, WORST_PAYLOAD)
    part = module.knowledge(h.summary)
    assert part["pct"] == 0
    sentences, more = module.missing_sentences(part, {}, "en")
    assert sentences == ["It still has to see how fast woonkamer_aaaaaaaaaaaaaaaaaaaaaa warms up.",
                         "It still has to see how fast keuken_bbbbbbbbbbbbbbbbbbbbbbbbb warms up."] and more == 26
    assert [(item["kind"], item["pct"], item["room"]) for item in module.insight_items(h.summary)] == [
        ("warmup_slower", 999, room) for room in ("woonkamer_aaaaaaaaaaaaaaaaaaaaaa", "keuken_bbbbbbbbbbbbbbbbbbbbbbbbb",
                                                  "badkamer_ccccccccccccccccccccccc", "slaapkamer_voor_dddddddddddddddd")]
    # The widest boiler: its state and figures; the saturated counters are not shown as figures.
    values = module.boiler_values(module.boiler_response(h.summary))
    assert values == {"state": "not_driving", "rest_s": 1800, "held_today": None, "rest_min": 30.0, "ceiling_c": None,
                      "absorbed_kw": None, "kw_per_k": 20, "return_reported": True}
    assert module.boiler_sentence(values, "en") == "The E32 listens to your boiler once it controls the boiler itself."


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
    h.receive(FLOW_TOPIC, json.dumps(FLOW))  # the boiler's object beside "flow", as the firmware sends it
    assert h.summary["boiler"] == FLOW["boiler"] and module.boiler_response(h.summary) == FLOW["boiler"]
    h.receive(INSIGHT_TOPIC, json.dumps(INSIGHT))
    assert module.boiler_response(h.summary) == INSIGHT["boiler"]  # the insight's wins
    # The firmware's own flow document reads as it is.
    h.receive(FLOW_TOPIC, FLOW_FIRMWARE)
    assert h.summary["flow"]["curve"]["base_c"] == 41.7 and h.summary["flow"]["ceiling_c"] is None
    # A room's message as the firmware prints it: "free_heat" inside "learned"; beside it (never sent) is read too.
    room, plan = decode_learned("woonkamer", LEARNED_FIRMWARE)
    assert room["free_heat"] == {"rate": [1.4] * 6, "n": [99] * 6, "applied_min": 240} and plan["optimum_start"]["applies"]
    room, plan = decode_learned("slaapkamer", json.dumps({"schema": 1, "id": "slaapkamer", "learned": {"readiness": "ready"},
                                                          "plan": None, "free_heat": FREE_HEAT}))
    assert room["free_heat"] == FREE_HEAT and plan is None
    inside, _ = decode_learned("slaapkamer", json.dumps({"schema": 1, "id": "slaapkamer", "free_heat": {"n": []},
                                                         "learned": {"free_heat": FREE_HEAT}, "plan": None}))
    assert inside["free_heat"] == FREE_HEAT


def test_a_message_without_free_heat_keeps_what_the_room_had():
    """The E32 leaves "free_heat" out only when the message would exceed its 1100 B budget (32-character ids), so a
    message without the key keeps the room's free heat; null still means that no window was judged yet."""
    h = HeatingHub("fixture")
    message = lambda learned, room="slaapkamer": json.dumps({"schema": 1, "id": room, "learned": learned, "plan": None})

    def heard(payload, room="slaapkamer"):
        h.receive("fw/telemetry/learned/" + room, payload)
        h.update(STATUS)  # the status the retained parts assemble into (none in this test)
        return h.learned[room]

    assert heard(message({"readiness": "learning", "free_heat": FREE_HEAT}))["free_heat"] == FREE_HEAT
    room = heard(message({"readiness": "ready"}))  # too long for it this time
    assert room["free_heat"] == FREE_HEAT and room["readiness"] == "ready"
    h.update_learned("slaapkamer", decode_learned("slaapkamer", message({"readiness": "ready", "segments": 4})))
    assert h.learned["slaapkamer"]["free_heat"] == FREE_HEAT
    assert heard(message({"readiness": "ready", "free_heat": None}))["free_heat"] is None  # nothing judged (yet)
    assert heard(message({"readiness": "ready"}))["free_heat"] is None
    # Another room never borrows it; a room that never had it has no key.
    assert "free_heat" not in heard(message({"readiness": "ready"}, "woonkamer"), "woonkamer")


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
    sensor = localized(module.BoilerResponseSensor(hub(flow=FLOW["flow"])))
    assert sensor.unique_id == "fixture_hub_boiler_response" and sensor.translation_key == "boiler_response"
    assert sensor.device_class == SensorDeviceClass.ENUM and sensor.options == ["collecting", "learned", "no_return", "not_driving"]
    assert sensor.native_value == "learned"
    # The ceiling in effect (flow.ceiling_c) holds near the target only (a room 1 °C or more below its target gets the
    # full water temperature); the boiler holds about its learned ceiling + 2 °C (the held request minus 2 °C).
    assert sensor.extra_state_attributes == {
        "held_today": 3, "rest_min": 9.0, "ceiling_c": 48, "absorbed_kw": 7.4, "kw_per_k": 0.36, "return_reported": True,
        "sentence": "Your boiler holds about 50 °C and rests 9 minutes; near the target the E32 asks at most 48 °C."}
    assert {"absorbed_kw", "sentence"} <= sensor._unrecorded_attributes
    # No ceiling in effect now (Smart warm-up on but a room warming up, or not known): no "asks at most".
    sensor = localized(module.BoilerResponseSensor(hub()))
    assert sensor.extra_state_attributes["sentence"] == "Your boiler holds about 50 °C and rests 9 minutes."


def with_smart(sensor, on):
    """The E32's Smart warm-up as e32_flow last read it, for the sensor's installation "e"."""
    sensor.hass.data = {"open_thermostat": {"e": {"e32_flow": SimpleNamespace(settings={"apply_learned": on})}}}
    return sensor


@pytest.mark.parametrize("boiler, cap, smart, en, nl, pl", [
    ({"state": "learned", "rest_s": 450, "ceiling_c": None}, None, None,
     "Your boiler rests 8 minutes each time it reaches its temperature.",
     "Je ketel rust 8 minuten telkens als hij zijn temperatuur bereikt.",
     "Twój kocioł odpoczywa 8 minut za każdym razem, gdy osiągnie swoją temperaturę."),
    ({"state": "learned", "rest_s": 75, "ceiling_c": None}, None, False,
     "Your boiler rests 1 minute each time it reaches its temperature.",
     "Je ketel rust 1 minuut telkens als hij zijn temperatuur bereikt.",
     "Twój kocioł odpoczywa 1 minutę za każdym razem, gdy osiągnie swoją temperaturę."),
    ({"state": "learned", "rest_s": None, "ceiling_c": 52}, 52, True,
     "Your boiler holds about 54 °C; near the target the E32 asks at most 52 °C.",
     "Je ketel houdt ongeveer 54 °C vast; dicht bij de doeltemperatuur vraagt de E32 hoogstens 52 °C.",
     "Twój kocioł utrzymuje około 54 °C; blisko temperatury docelowej E32 zadaje najwyżej 52 °C."),
    ({"state": "learned", "rest_s": 180, "ceiling_c": 41, "return": False}, 41, True,
     "Your boiler holds about 43 °C and rests 3 minutes; near the target the E32 asks at most 41 °C.",
     "Je ketel houdt ongeveer 43 °C vast en rust 3 minuten; dicht bij de doeltemperatuur vraagt de E32 hoogstens 41 °C.",
     "Twój kocioł utrzymuje około 43 °C i odpoczywa 3 minuty; blisko temperatury docelowej E32 zadaje najwyżej 41 °C."),
    # The cap in effect is never below the plan's lowest water temperature: that number is what the E32 asks.
    ({"state": "learned", "rest_s": None, "ceiling_c": 38}, 40, True,
     "Your boiler holds about 40 °C; near the target the E32 asks at most 40 °C.",
     "Je ketel houdt ongeveer 40 °C vast; dicht bij de doeltemperatuur vraagt de E32 hoogstens 40 °C.",
     "Twój kocioł utrzymuje około 40 °C; blisko temperatury docelowej E32 zadaje najwyżej 40 °C."),
    # Learned but not in effect now: Smart warm-up on (a room warming up gets the full water temperature) ...
    ({"state": "learned", "rest_s": 540, "ceiling_c": 48}, None, True,
     "Your boiler holds about 50 °C and rests 9 minutes.", "Je ketel houdt ongeveer 50 °C vast en rust 9 minuten.",
     "Twój kocioł utrzymuje około 50 °C i odpoczywa 9 minut."),
    ({"state": "learned", "rest_s": None, "ceiling_c": 52}, None, None,
     "Your boiler holds about 54 °C.", "Je ketel houdt ongeveer 54 °C vast.", "Twój kocioł utrzymuje około 54 °C."),
    # ... or off: the learned ceiling waits for it.
    ({"state": "learned", "rest_s": 540, "ceiling_c": 48}, None, False,
     "Your boiler holds about 50 °C and rests 9 minutes. With Smart warm-up on, the E32 would ask at most 48 °C near the "
     "target.",
     "Je ketel houdt ongeveer 50 °C vast en rust 9 minuten. Met Slim opwarmen aan zou de E32 dicht bij de doeltemperatuur "
     "hoogstens 48 °C vragen.",
     "Twój kocioł utrzymuje około 50 °C i odpoczywa 9 minut. Z włączonym Inteligentnym nagrzewaniem E32 zadawałby blisko "
     "temperatury docelowej najwyżej 48 °C."),
    ({"state": "learned"}, None, None, "The E32 has learned how your boiler holds its temperature.",
     "De E32 heeft geleerd hoe je ketel zijn temperatuur vasthoudt.", "E32 nauczył się, jak Twój kocioł utrzymuje swoją temperaturę."),
    ({"state": "collecting", "held": 1}, None, None, "The E32 is still listening to how your boiler holds its temperature.",
     "De E32 luistert nog hoe je ketel zijn temperatuur vasthoudt.",
     "E32 wciąż wsłuchuje się, jak Twój kocioł utrzymuje swoją temperaturę."),
    # Still collecting, but the emitters' output per K is known (Knowledge counts the boiler as learned then): the
    # owner's recording is in this state for days (P14 review, finding 1).
    ({"state": "collecting", "held": 0, "kw_per_k": 0.25, "return": True}, None, None,
     "Your boiler has not held a water temperature by itself yet; every degree the water is warmer than the rooms gives "
     "your house about 0.25 kW. The E32 keeps listening.",
     "Je ketel heeft nog niet zelf een watertemperatuur vastgehouden; elke graad dat het water warmer is dan de ruimtes, "
     "geeft je huis ongeveer 0,25 kW. De E32 blijft luisteren.",
     "Twój kocioł jeszcze sam nie utrzymał temperatury wody; każdy stopień, o który woda jest cieplejsza od pomieszczeń, "
     "daje Twojemu domowi około 0,25 kW. E32 słucha dalej."),
    ({"state": "no_return", "return": False}, None, None,
     "Your boiler does not report the water coming back, so the E32 cannot see how much heat your house takes; it still "
     "learns how your boiler holds its temperature.",
     "Je ketel meldt het terugkomende water niet, dus de E32 kan niet zien hoeveel warmte je huis opneemt; hij leert wel "
     "hoe je ketel zijn temperatuur vasthoudt.",
     "Twój kocioł nie zgłasza temperatury wody powrotnej, więc E32 nie widzi, ile ciepła pobiera Twój dom; nadal uczy się, "
     "jak Twój kocioł utrzymuje swoją temperaturę."),
    ({"state": "not_driving"}, None, None, "The E32 listens to your boiler once it controls the boiler itself.",
     "De E32 luistert naar je ketel zodra hij de ketel zelf regelt.",
     "E32 zacznie wsłuchiwać się w Twój kocioł, gdy sam będzie nim sterował.")])
def test_every_boiler_state_has_its_sentence(boiler, cap, smart, en, nl, pl):
    insight = {**INSIGHT, "boiler": boiler}
    for language, expected in (("en", en), ("nl", nl), ("pl", pl)):
        sensor = with_smart(localized(module.BoilerResponseSensor(hub(insight, flow={"ceiling_c": cap}), "e"), language), smart)
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
    h = live_hub()
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
    h = live_hub()
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
    h = live_hub()
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
    h = live_hub()
    n, remove = notifier(hass, h, entry_id="gone")
    n.hub_changed()
    assert len(notes(hass)) == 2
    remove()
    await module.async_remove_insight(hass, "gone")
    assert notes(hass) == {}


@pytest.mark.asyncio
async def test_notifications_wait_for_a_live_insight_message(hass):
    """A retained insight alone may be stale (rc.4 never clears the topic after a downgrade): the sensors show it, but
    its notifications wait for a live message in this Home Assistant run, and a dropped insight needs a live one again."""
    hass.config.language = "en"
    h = live_hub(retained=True)
    assert module.knowledge(h.summary)["pct"] == 70 and not h.insight_live
    n, remove = notifier(hass, h)
    n.hub_changed()
    assert notes(hass) == {}  # every Home Assistant restart would bring stale ones back otherwise
    h.receive(INSIGHT_TOPIC, json.dumps(INSIGHT))  # the E32's next one, five minutes later
    h.update(STATUS)
    n.hub_changed()
    assert len(notes(hass)) == 2 and h.insight_live
    h.receive(INSIGHT_TOPIC, json.dumps(INSIGHT), retained=True)  # a reconnect while the E32 sends them: still live
    h.update(STATUS)
    assert h.insight_live
    # The E32 stops sending them (a downgrade): dropped after 16 live heartbeats, the notifications go ...
    for beat in range(1, INSIGHT_MISSED_HEARTBEATS + 2):
        h.receive("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 60 * beat}))
    h.update(STATUS)
    n.hub_changed()
    assert notes(hass) == {} and h.insight_gone and not h.insight_live
    # ... and the stale retained one that comes back on a reconnect shows none.
    h.receive(INSIGHT_TOPIC, json.dumps(INSIGHT), retained=True)
    h.update(STATUS)
    n.hub_changed()
    assert notes(hass) == {} and module.knowledge(h.summary)["pct"] == 70
    remove()


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
     "Its next warm-up starts 12 min later, so Smart warm-up does not heat what comes for free."),
    ("nl", "'s Middags warmt deze ruimte vanzelf op, ongeveer 0,4 °C per uur (zon, koken of mensen).",
     "De volgende opwarming begint daardoor 12 min later, zodat Slim opwarmen niet verwarmt wat gratis komt."),
    ("pl", "Po południu to pomieszczenie samo się nagrzewa, o około 0,4 °C na godzinę (słońce, gotowanie lub ludzie).",
     "Następne nagrzewanie zaczyna się dzięki temu 12 min później, więc Inteligentne nagrzewanie nie grzeje tego, co "
     "przychodzi za darmo.")])
def test_free_heat_per_room_in_words(language, text, meaning):
    """applied_min is what the room's next planned start gains, whatever its daypart (FreeHeat): the minutes belong to
    "its next warm-up", not to the daypart named in the first line (P14 review, finding 10)."""
    lines = lo.room_overview("Slaapkamer", {"readiness": "learning", "segments": 2, "free_heat": FREE_HEAT}, None, language,
                             str)["lines"]
    assert {"text": text, "meaning": meaning} in lines


def test_a_room_with_free_heat_says_so_and_a_room_without_it_says_nothing():
    """P3: "free_heat" sits in "learned" of fw/telemetry/learned/<room>; it is null before any judged window and
    left out of a message near its 1100 B budget. A room without it gets no line, never an "unknown" one."""
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


def test_the_learned_overview_lists_the_free_heat_per_room():
    """rc.5 (the owner's sketch): the Learning view's "Free heat" reads the rooms that get heat for free, by name, from
    an attribute of their own: the room's own line, an empty list while no room has one (so the section hides), and a
    room switched off left out as in ``rooms``."""
    h = HeatingHub("fixture")
    h.update(STATUS)
    sensor = lo.LearnedOverviewSensor(SimpleNamespace(entry_id="e"), h, clock=str)
    sensor.hass = SimpleNamespace(config=SimpleNamespace(language="nl"))
    assert sensor.extra_state_attributes["free_heat"] == []
    for room_id in ("woonkamer", "slaapkamer"):
        h.update_learned(room_id, decode_learned(room_id, json.dumps(
            {"schema": 1, "id": room_id, "learned": {"readiness": "learning", "segments": 3, "free_heat": FREE_HEAT},
             "plan": None})))
    line = {"text": "'s Middags warmt deze ruimte vanzelf op, ongeveer 0,4 °C per uur (zon, koken of mensen).",
            "meaning": "De volgende opwarming begint daardoor 12 min later, zodat Slim opwarmen niet verwarmt wat gratis "
                       "komt."}
    attributes = sensor.extra_state_attributes
    assert attributes["free_heat"] == [{"name": "Woonkamer", **line}, {"name": "Slaapkamer", **line}]
    assert line in attributes["rooms"][1]["lines"]  # the same words as the room's own line
    assert "free_heat" in sensor._unrecorded_attributes  # shown, not kept in the history
    h.update({**STATUS, "rooms": [STATUS["rooms"][0], {**STATUS["rooms"][1], "state": "inactive"}]})
    assert [room["name"] for room in sensor.extra_state_attributes["free_heat"]] == ["Woonkamer"]


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
