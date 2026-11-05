"""What the thermostat learned (learned_overview.py): the plain-language overview sensor, its texts in
English, Dutch and Polish, the change log kept over restarts and the fw/telemetry/tuning topic."""
import json
from types import SimpleNamespace

import pytest

from custom_components.open_thermostat import learned_overview as lo
from custom_components.open_thermostat.heating_link import HeatingHub, SCOREBOARD_TOPIC, TUNING_TOPIC

STATUS = {"schema": 1, "revision": 4, "mode": "active", "request": {"heat": True, "flow_c": 36, "reason": "heating"},
          "ha_entities": ["climate.woonkamer"],
          "rooms": [{"id": "woonkamer", "name": "Woonkamer", "state": "active", "temperature": 20.5, "setpoint": 21},
                    {"id": "slaapkamer", "name": "Slaapkamer", "state": "active", "temperature": 18, "setpoint": 18},
                    {"id": "zolder", "name": "Zolder", "state": "inactive"}]}
LEARNED = {"emitter": "floor", "readiness": "ready", "segments": 9, "periods": 4, "loss_per_h": 0.02,
           "advice": [{"shortfall_c": 1, "flow_c": 34, "warmup_h": 1.5, "reason": "learned", "rule_flow_c": 40, "rule_warmup_h": 1.25}]}
PLAN = {"optimum_start": {"reason": "planned", "predicted_start_utc": 1793257800, "next_switch": {"utc": 1793262600, "target_c": 21},
                          "confidence": "learned", "start_now": False},
        "night": {"reason": "estimated", "recommended": "hold_0_5", "recommended_night_c": 19, "saving_m3": 0.12, "saving_eur": 0.15}}
TUNING = {"state": "active", "values": {"min_on_s": 300, "min_off_s": 600, "heat_start_c": 0.2, "heat_stop_c": 0.15,
                                        "flow_per_degree_c": 10, "curve_correction_pct": 50, "floor_lead_min_per_c": 90,
                                        "radiator_lead_min_per_c": 45, "learned_accept_pct": 100, "night_saving_min_pct": 2},
          "manual": ["min_off_s"], "yesterday": {"starts": 59, "heating_h": 14, "burns": 58, "burn_s": 420},
          "today": {"starts": 3, "heating_h": 2}, "would": [],
          "log": [[1793232000, "heat_stop_c", 0.2, 0.15, "overshoot", 0.6, "woonkamer"],
                  [1793145600, "min_off_s", 450, 600, "many_starts", 59, ""]]}
SUMMARY = {"schema": 1, "learned": {"schema": 1, "applied": True, "status": "learning"},
           "flow": {"curve": {"state": "applied", "slope": 0.62, "slope_source": "learned"}}, "tuning": TUNING}
CLOCK = {1793257800: "07:30", 1793262600: "08:50"}


def hub():
    h = HeatingHub("fixture")
    h.update(STATUS)
    h.update_learned("woonkamer", ({**LEARNED, "id": "woonkamer"}, {**PLAN, "id": "woonkamer"}))
    h.update_learned("slaapkamer", ({"emitter": "radiator", "readiness": "learning", "segments": 3, "id": "slaapkamer"}, None))
    h.update_summary(json.loads(json.dumps(SUMMARY)))
    return h


def sensor(language="en"):
    s = lo.LearnedOverviewSensor(SimpleNamespace(entry_id="e"), hub(), clock=CLOCK.get)
    s.hass = SimpleNamespace(config=SimpleNamespace(language=language))
    s._hub_changed()
    return s


def test_the_overview_in_plain_english():
    s = sensor()
    assert s.unique_id == "fixture_hub_learned_overview" and s.translation_key == "learned_overview" and s.available
    assert s.native_value == "Woonkamer got 0.6 °C warmer than its target; the thermostat now stops heating a little earlier."
    a = s.extra_state_attributes
    assert a["explanation"] == "The thermostat adjusts its settings itself, at most one small step a day."
    living, bedroom = a["rooms"]  # the inactive attic is left out
    assert living["name"] == "Woonkamer" and living["progress"] == "Learned" and living["room_id"] == "woonkamer"
    assert living["summary"] == "warms about 1 °C in 1 h 15 min with water of 40 °C"  # the Learning tab's progress
    assert [line["text"] for line in living["lines"]] == [
        "Warms about 1 °C in 1 h 15 min with water of 40 °C.",
        "The lowest water temperature that still warms it in time: 34 °C.",
        "Loses about 0.3 °C per hour at 5 °C outside.",
        "Smart warm-up: starts at 07:30 so it is 21 °C at 08:50.",
        "Keeping it at 19 °C at night is cheaper than letting it cool down: about 0.12 m³ gas (0.15) a night."]
    assert all(line["meaning"] for line in living["lines"])  # every figure says what it means
    assert bedroom["progress"] == "Learning: 3 of 6 warm-ups seen"
    assert bedroom["lines"] == [{"text": "It learns from every warm-up while the heating runs.", "meaning": "Until then it uses safe standard times."}]
    # Weather compensation once (rc7): what it uses and how steep its line is, in one line.
    assert [line["text"] for line in a["house"]] == [
        "Weather compensation: learned for your house. The water gets about 0.62 °C warmer for every degree colder outside.",
        "Yesterday the burner started 59 times for heating; a burn lasted 7 min on average."]
    assert a["house"][1]["meaning"].startswith("That is often.")
    assert [c["text"] for c in a["changes"]] == [
        "Woonkamer got 0.6 °C warmer than its target; the thermostat now stops heating a little earlier.",
        "The burner now rests at least 10 min before it starts again, because it started 59 times yesterday. Fewer starts are gentler on the boiler."]
    assert a["changes"][0]["time"] == "2026-10-29T00:00:00+00:00"
    assert a["settings"]["Burner rest between starts"] == "10 min (set by you)"
    assert a["settings"]["Stop heating when the room is this much above its target"] == "0.15 °C (automatic)"
    assert a["settings"]["Warm-up time for floor heating"] == "1 h 30 min per °C (automatic)"
    assert a["settings"]["Room correction on weather compensation"] == "50 % (standard value)"


@pytest.mark.parametrize("language", ["nl", "pl", "nl-NL", "pl-PL"])
def test_dutch_and_polish_render_completely(language):
    a = sensor(language).extra_state_attributes
    texts = [a["explanation"]] + [line["text"] for room in a["rooms"] for line in room["lines"]] \
        + [line["meaning"] for room in a["rooms"] for line in room["lines"]] + [line["text"] for line in a["house"]] \
        + [c["text"] for c in a["changes"]] + list(a["settings"]) + list(a["settings"].values())
    assert all(t and "{" not in t and "None" not in t for t in texts), texts
    english = sensor().extra_state_attributes
    assert a["rooms"][0]["lines"][0]["text"] != english["rooms"][0]["lines"][0]["text"]
    if language.startswith("nl"):
        assert a["rooms"][0]["lines"][0]["text"] == "Warmt ongeveer 1 °C op in 1 u 15 min met water van 40 °C."
        assert a["settings"]["Rust van de brander tussen starts"] == "10 min (door jou ingesteld)"
    else:
        assert a["rooms"][0]["progress"] == "Wyuczone"


def test_every_language_has_every_text_with_the_same_placeholders():
    import string
    keys = set(lo.TEXT["en"])
    for lang, texts in lo.TEXT.items():
        assert set(texts) == keys, lang
        for key, text in texts.items():
            fields = {f for _, f, _, _ in string.Formatter().parse(text) if f}
            assert fields == {f for _, f, _, _ in string.Formatter().parse(lo.TEXT["en"][key]) if f}, (lang, key)
    assert {"why." + r for r in ("many_starts", "cold_during_rest", "short_burns", "overshoot", "overshoot_gain", "settled",
                                 "hovering", "few_starts", "learned_warmup", "boiler_cycling")} <= keys


def test_changes_in_words():
    names = {"woonkamer": "Woonkamer"}
    assert lo.change_text(["min_off_s", 300, 450, "many_starts", 72, ""], names, "en").startswith("The burner now rests at least 7.5 min ")
    assert lo.change_text(["flow_per_degree_c", 10, 11, "room_response", 180, "woonkamer"], names, "en") == \
        "Woonkamer warms about 1 °C in 3 h; the thermostat now reacts a little more strongly to a cold room."
    assert lo.change_text(["flow_per_degree_c", 10, 9, "room_response", 20, ""], names, "en") == \
        "A typical room warms about 1 °C in 20 min; the thermostat now reacts a little more gently to a cold room."
    assert lo.change_text(["heat_start_c", 0.2, 0.25, "hovering", 143, ""], names, "nl") == (
        "Het verwarmen start nu als een ruimte 0,25 °C onder de gewenste temperatuur is, omdat het gisteren 143 keer startte "
        "voor kleine dalingen. Minder starts zijn beter voor de ketel.")
    # Not understood: left out, never half a sentence.
    for bad in (["x", 1, 2, "many_starts", 1, ""], ["min_on_s", 1, 2, "why", 1, ""], ["min_on_s", "1", 2, "short_burns", 1, ""], [1, 2], None):
        assert lo.change_text(bad, names, "en") is None


def test_the_log_is_kept_over_restarts_and_merged_with_the_newest_four():
    s = sensor()
    assert len(s.log) == 2
    stored = s.extra_restore_state_data.as_dict()
    # The E32 sends only its newest four; older ones stay here, at most ten, newest first, without doubles.
    older = [[1792000000 + i * 86400, "min_off_s", 300, 450, "many_starts", 60 + i, ""] for i in range(12)]
    merged = lo.merge_changes(older, TUNING["log"] + [TUNING["log"][0]])
    assert len(merged) == lo.LOG_KEPT and merged[0] == TUNING["log"][0] and merged[1] == TUNING["log"][1]
    assert [c[0] for c in merged] == sorted((c[0] for c in merged), reverse=True)
    assert lo.merge_changes(stored["log"], []) == TUNING["log"]
    # A reset on the E32 sends an empty log: what was shown stays as history here.
    s.hub.update_summary({**SUMMARY, "tuning": {**TUNING, "log": [], "state": "waiting"}})
    s._hub_changed()
    assert len(s.log) == 2 and s.extra_state_attributes["explanation"].startswith("After a restart or a change")


def test_shadow_mode_shows_what_it_would_change_and_older_firmware_shows_what_there_is():
    s = sensor()
    s.log = []
    s.hub.update_summary({**SUMMARY, "tuning": {**TUNING, "state": "shadow", "log": [], "would": [["min_off_s", 300, 450, "many_starts", 72, ""]]}})
    s._hub_changed()
    a = s.extra_state_attributes
    # A proposal says what it would set and why, never "now rests" (rc7, R1-16); it has no time, so the dashboard's
    # "Latest change" never shows it.
    assert a["changes"][0] == {"time": None, "text": "Would set “Burner rest between starts” to 7.5 min, because the burner "
                                                    "started 72 times yesterday."}
    assert s.native_value == ("Your current thermostat or the boiler's own control is still in charge, so the E32 only shows "
                              "what it would change.")
    # Firmware before rc.2: no tuning, no next switch in the plan; the rest still reads.
    s.hub.update_summary({k: v for k, v in SUMMARY.items() if k != "tuning"})
    s.hub.update_learned("woonkamer", ({**LEARNED, "id": "woonkamer"},
                                       {"id": "woonkamer", "optimum_start": {k: v for k, v in PLAN["optimum_start"].items() if k != "next_switch"}}))
    s._hub_changed()
    a = s.extra_state_attributes
    assert s.native_value == "The E32 has not reported what it learned yet."
    assert a["changes"] == [{"time": None, "text": "Nothing changed yet: the start values still fit, or there is not enough to go on."}]
    assert "Starts heating at 07:30 for the next program step." in [line["text"] for line in a["rooms"][0]["lines"]]
    assert a["settings"] == {} and len(a["house"]) == 1  # the curve: its status and its figure in one line


def test_the_tuning_topic_joins_the_summary():
    h = HeatingHub("fixture")
    h.receive("fw/telemetry/summary", json.dumps({"schema": 1, "learned": {"schema": 1}}))
    h.receive(TUNING_TOPIC, json.dumps({"schema": 1, "tuning": TUNING}))
    assert h.summary["tuning"] == TUNING and h.summary["learned"] == {"schema": 1}
    h.receive("fw/telemetry/flow", json.dumps({"schema": 1, "flow": {"source": "rule"}}))
    assert h.summary["tuning"] == TUNING and h.summary["flow"] == {"source": "rule"}
    for bad in ("", "{}", json.dumps({"schema": 1, "tuning": []}), "not json"):
        h.receive(TUNING_TOPIC, bad)
        assert "tuning" not in h.summary


BOARD = {"yesterday": {"day": "2026-11-03", "heating_h": 9, "heating_starts_per_h": 2.1, "short_cycle_h": 0, "heating_kwh": 31.2,
                       "degree_days": 10.5, "rooms": [{"id": "woonkamer", "on_time_min": -5, "overshoot_c": 0.3}]},
         "today": {"day": "2026-11-04", "heating_h": 3, "heating_starts_per_h": 1.7, "short_cycle_h": 0, "heating_kwh": 8.1,
                   "degree_days": 11}}


def test_the_scoreboard_topic_joins_the_summary():
    """E32 rc.4: the scoreboard left fw/telemetry/summary for its own topic (eight rooms pushed the summary over
    the 1.5 KB limit, where the E32 drops it); merged back as "scoreboard", so scoreboard.py reads it as before."""
    h = HeatingHub("fixture")
    h.receive("fw/telemetry/summary", json.dumps({"schema": 1, "learned": {"schema": 1}}))
    assert "scoreboard" not in h.summary
    h.receive(SCOREBOARD_TOPIC, json.dumps({"schema": 1, "scoreboard": BOARD}))
    assert h.summary["scoreboard"] == BOARD and h.summary["learned"] == {"schema": 1}
    h.receive(TUNING_TOPIC, json.dumps({"schema": 1, "tuning": TUNING}))
    h.receive("fw/telemetry/flow", json.dumps({"schema": 1, "flow": {"source": "rule"}}))
    assert h.summary["scoreboard"] == BOARD and h.summary["tuning"] == TUNING and h.summary["flow"] == {"source": "rule"}
    from custom_components.open_thermostat.scoreboard import scoreboard
    assert scoreboard(h.summary) == BOARD
    # A summary that still carries the scoreboard itself (rc.4 preview firmware): the topic wins while it is there.
    inside = {**BOARD, "today": None}
    h.receive("fw/telemetry/summary", json.dumps({"schema": 1, "learned": {"schema": 1}, "scoreboard": inside}))
    assert h.summary["scoreboard"] == BOARD
    for bad in ("", "{}", json.dumps({"schema": 1, "scoreboard": []}), json.dumps({"schema": 2, "scoreboard": BOARD}), "not json"):
        h.receive(SCOREBOARD_TOPIC, bad)
        assert h.summary["scoreboard"] == inside, bad  # the topic dropped: the summary's own again
    h.receive("fw/telemetry/summary", json.dumps({"schema": 1, "learned": {"schema": 1}}))
    assert "scoreboard" not in h.summary
    h.receive(SCOREBOARD_TOPIC, json.dumps({"schema": 1, "scoreboard": BOARD}))
    assert h.summary["scoreboard"] == BOARD


def test_the_learning_view_sums_it_up_and_shows_the_house_and_its_changes():
    """What it learned is the "Learning and settings" view: how far each room is and the latest change, the house and
    boiler, and what it changed by itself. What it learned per room is in that room's section of the Rooms view."""
    from custom_components.open_thermostat import dashboard
    entity = "sensor.what_the_thermostat_learned"
    shown = [{"condition": "state", "entity": entity, "state_not": "unavailable"}]
    summary, house, changes = dashboard._learned_sections(dashboard.TEXT["en"], entity)
    assert [s["cards"][0]["heading"] for s in (summary, house, changes)] == [
        "What the thermostat has learned", "House and boiler", "What it changed by itself"]
    # The latest change is one the thermostat made (with a time): never a trial-run proposal or "Nothing changed yet".
    assert "room.progress" in summary["cards"][1]["content"] and "room.summary" in summary["cards"][1]["content"]
    assert "'changes') or []) | selectattr('time') | list)[:1]" in summary["cards"][1]["content"]
    assert "room.lines" not in summary["cards"][1]["content"]  # the lines are in the rooms
    assert "'explanation'" in summary["cards"][1]["content"] and "<details>" in summary["cards"][1]["content"]
    assert "'house'" in house["cards"][1]["content"] and "'changes'" in changes["cards"][1]["content"]
    assert "Configure → Heating and boiler → Comfort and boiler care" in changes["cards"][2]["content"]  # the rc4 menu path
    assert all(s["visibility"] == shown for s in (summary, house, changes))
    assert dashboard._learned_sections(dashboard.TEXT["nl"], None) == []
    assert dashboard._learned_sections(dashboard.TEXT["nl"], "sensor.x")[0]["cards"][0]["heading"] == "Wat de thermostaat heeft geleerd"


BOILER_MINIMUM = {
    "en": ("Your boiler only starts heating from about 40 °C water; the thermostat asks at least that much.",
           "It learned this when the boiler did not start for cooler water."),
    "nl": ("Je ketel begint pas te verwarmen vanaf water van ongeveer 40 °C; de thermostaat vraagt minstens zoveel.",
           "Dat leerde hij toen de ketel voor koeler water niet aansloeg."),
    "pl": ("Twój kocioł zaczyna grzać dopiero od wody o temperaturze około 40 °C; termostat żąda co najmniej tyle.",
           "Nauczył się tego, gdy kocioł nie uruchamiał się przy chłodniejszej wodzie."),
}


@pytest.mark.parametrize("language", ["en", "nl", "pl"])
def test_the_boiler_minimum_flow_is_a_house_line_and_an_attribute_once_learned(language):
    """E32 rc.2 learns the lowest water temperature the boiler fires at (learned.boiler_minimum_flow_c of the
    summary, only once learned): a house line in the E32 page's words and an attribute; absent, nothing."""
    s = sensor(language)
    before = s.extra_state_attributes
    assert "boiler_minimum_flow_c" not in before
    assert all("40" not in line["text"] for line in before["house"]) and len(before["house"]) == 2
    s.hub.update_summary({**SUMMARY, "learned": {**SUMMARY["learned"], "boiler_minimum_flow_c": 40}})
    s._hub_changed()
    a = s.extra_state_attributes
    assert a["boiler_minimum_flow_c"] == 40
    assert a["house"][:2] == before["house"]  # after the curve and the burner, as on the E32 page
    assert a["house"][2] == {"text": BOILER_MINIMUM[language][0], "meaning": BOILER_MINIMUM[language][1]}
    # Alone it still shows (no "nothing yet").
    alone = lo.house_overview({"schema": 1, "learned": {"boiler_minimum_flow_c": 40}}, language)
    assert alone == [a["house"][2]]
    # Not understood or implausible: left out, never half a sentence.
    for bad in (None, "40", True, float("nan"), 5, 120):
        summary = {**SUMMARY, "learned": {**SUMMARY["learned"], "boiler_minimum_flow_c": bad}}
        assert lo.boiler_minimum_flow(summary) is None
        assert len(lo.house_overview(summary, language)) == 2
    assert lo.boiler_minimum_flow(None) is None and lo.boiler_minimum_flow({"learned": None}) is None


def test_the_dashboard_house_section_shows_the_boiler_minimum_line():
    """The Learned subview's house section lists the sensor's 'house' lines, so the new line needs no card of its own."""
    from custom_components.open_thermostat import dashboard
    s = sensor()
    s.hub.update_summary({**SUMMARY, "learned": {**SUMMARY["learned"], "boiler_minimum_flow_c": 41}})
    s._hub_changed()
    house = dashboard._learned_sections(dashboard.TEXT["en"], "sensor.x")[1]["cards"][1]["content"]
    assert "'house'" in house and "line.text" in house and "line.meaning" in house
    assert s.extra_state_attributes["house"][-1]["text"].startswith("Your boiler only starts heating from about 41 °C water")


# E32 rc.3 Smart warm-up: a time in the week program means "warm at that time"; one line per room says what
# the next program step means (the same words as the E32 page, index.html smartWarmupLine).
START = {"reason": "planned", "predicted_start_utc": 1793257800, "next_switch": {"utc": 1793262600, "target_c": 21},
         "lead_minutes": 80, "confidence": "learned", "reachable": True, "start_now": False, "applies": True}


@pytest.mark.parametrize("change,on,english,dutch", [
    ({}, True, "Smart warm-up: starts at 07:30 so it is 21 °C at 08:50.",
     "Slim opwarmen: begint om 07:30, zodat het om 08:50 21 °C is."),
    ({}, None, "Smart warm-up: starts at 07:30 so it is 21 °C at 08:50.",       # not read yet: on by default
     "Slim opwarmen: begint om 07:30, zodat het om 08:50 21 °C is."),
    ({"start_now": True}, True, "Smart warm-up: heating now so it is 21 °C at 08:50.",
     "Slim opwarmen: verwarmt nu, zodat het om 08:50 21 °C is."),
    ({"start_now": True, "reachable": False}, True, "Smart warm-up: heating now; 21 °C may come a little after 08:50.",
     "Slim opwarmen: verwarmt nu; 21 °C wordt misschien pas iets na 08:50 gehaald."),
    ({"lead_minutes": 0, "predicted_start_utc": 1793262600}, True,
     "Smart warm-up: warm enough for 21 °C at 08:50, no early start needed.",
     "Slim opwarmen: warm genoeg voor 21 °C om 08:50, eerder beginnen is niet nodig."),
    ({"applies": False, "confidence": "default"}, True,
     "Smart warm-up is still learning: for now heating starts at 08:50 (estimate: from 07:30 it would be 21 °C on time).",
     "Slim opwarmen leert nog: voorlopig begint verwarmen om 08:50 (schatting: vanaf 07:30 zou het op tijd 21 °C zijn)."),
    ({"applies": False}, True,                                                   # warm-up learned, cooling not yet
     "Smart warm-up is still learning: for now heating starts at 08:50 (estimate: from 07:30 it would be 21 °C on time).",
     "Slim opwarmen leert nog: voorlopig begint verwarmen om 08:50 (schatting: vanaf 07:30 zou het op tijd 21 °C zijn)."),
    ({}, False, "Smart warm-up is off: heating starts at 08:50.", "Slim opwarmen staat uit: verwarmen begint om 08:50."),
])
def test_smart_warm_up_says_what_the_next_program_step_means(change, on, english, dutch):
    start = {**START, **change}
    clock = {1793257800: "07:30", 1793262600: "08:50"}.get
    text, meaning = lo.smart_warm_up_line(start, on, "en", clock)
    assert text == english and meaning
    assert lo.smart_warm_up_line(start, on, "nl", clock)[0] == dutch
    polish = lo.smart_warm_up_line(start, on, "pl", clock)[0]
    assert polish.startswith("Inteligentne nagrzewanie") and "08:50" in polish
    # Older firmware (no "applies"): a learned warm-up counts as applied, a default estimate does not.
    older = {k: v for k, v in start.items() if k != "applies"}
    if "applies" not in change or start["confidence"] == "default":
        assert lo.smart_warm_up_line(older, on, "en", clock)[0] == english


def test_smart_warm_up_needs_a_planned_next_switch():
    clock = {1793257800: "07:30", 1793262600: "08:50"}.get
    for start in (None, {}, {**START, "reason": "no_rise_within_24h"}, {k: v for k, v in START.items() if k != "next_switch"}):
        assert lo.smart_warm_up_line(start, True, "en", clock) is None


def test_the_overview_follows_the_smart_warm_up_switch():
    s = sensor()
    s.hass = SimpleNamespace(config=SimpleNamespace(language="en"),
                             data={"open_thermostat": {"e": {"e32_flow": SimpleNamespace(settings={"apply_learned": False})}}})
    living = s.extra_state_attributes["rooms"][0]
    assert {"text": "Smart warm-up is off: heating starts at 08:50.", "meaning": "Turn Smart warm-up on to be warm on time."} in living["lines"]


# E32 rc.3: the heating curve is on by default and the E32 decides itself when its own curve is good enough;
# the overview says plainly what it uses now, and the same for the learned coolest water.
@pytest.mark.parametrize("curve,on,english,dutch", [
    ({"state": "applied", "slope_source": "design", "windows": 2}, True,
     "Weather compensation: standard for now, learning from your house (2 of 6 steady periods).",
     "Weerafhankelijke regeling: voorlopig standaard, hij leert van je huis (2 van 6 rustige periodes)."),
    ({"state": "applied", "slope_source": "design"}, None,                       # older firmware: no count
     "Weather compensation: standard for now, learning from your house.", "Weerafhankelijke regeling: voorlopig standaard, hij leert van je huis."),
    ({"state": "applied", "slope_source": "learned", "windows": 9}, True,
     "Weather compensation: learned for your house.", "Weerafhankelijke regeling: geleerd voor je huis."),
    ({"state": "no_outdoor", "slope_source": "design", "windows": 0}, True,
     "Weather compensation: no outdoor temperature right now, so the water temperature follows the rooms only.",
     "Weerafhankelijke regeling: nu geen buitentemperatuur, dus de watertemperatuur volgt alleen de ruimtes."),
    ({"state": "advice", "slope_source": "learned", "windows": 7}, False,
     "Weather compensation: off, the water temperature follows the rooms only.",
     "Weerafhankelijke regeling: uit, de watertemperatuur volgt alleen de ruimtes."),
])
def test_the_curve_says_what_it_uses_now(curve, on, english, dutch):
    assert lo.curve_status(curve, on, "en")[0] == english
    assert lo.curve_status(curve, on, "nl")[0] == dutch
    assert lo.curve_status(curve, on, "pl")[0].startswith("Kompensacja pogodowa: ")
    assert lo.curve_status({"state": "no_room"}, on, "en") is None and lo.curve_status(None, on, "en") is None


def test_the_learned_water_says_whether_it_is_ready():
    assert lo.learned_flow_status({"state": "not_ready"}, True, "en")[0] == "Coolest water: still learning from each warm-up."
    assert lo.learned_flow_status({"state": "applied", "flow_c": 34}, True, "en")[0] == "Coolest water: learned for your house."
    assert lo.learned_flow_status({"state": "holding", "flow_c": 34}, None, "nl")[0] == "Koelste water: geleerd voor je huis."
    assert lo.learned_flow_status({"state": "advice", "flow_c": 34}, False, "en")[0] == "Coolest water: learned; used when Smart warm-up is on."
    assert lo.learned_flow_status({"state": "no_room"}, True, "en") is None and lo.learned_flow_status(None, True, "en") is None
    s = sensor()
    s.hub.update_summary({**SUMMARY, "flow": {"curve": {"state": "applied", "slope": 1.17, "slope_source": "design", "windows": 2},
                                              "learned": {"state": "not_ready", "flow_c": None}}})
    s.hass = SimpleNamespace(config=SimpleNamespace(language="en"),
                             data={"open_thermostat": {"e": {"e32_flow": SimpleNamespace(settings={"weather_curve": True, "apply_learned": True})}}})
    assert [line["text"] for line in s.extra_state_attributes["house"]][:2] == [
        "Weather compensation: standard for now, learning from your house (2 of 6 steady periods). The water gets about "
        "1.17 °C warmer for every degree colder outside.", "Coolest water: still learning from each warm-up."]


# E32 rc.4: a start from the standard warm-up time is applied too ("estimate"), the warm-up time can be learned
# before the coolest water ("readiness_timing") and every morning is checked ("arrival").
def test_an_estimated_start_says_so():
    clock = {1793257800: "07:30", 1793262600: "08:50"}.get
    start = {**START, "confidence": "default", "estimate": True}
    assert lo.smart_warm_up_line(start, True, "en", clock)[0] == (
        "Smart warm-up: starts at 07:30 (estimate; it learns from every morning) so it is 21 °C at 08:50.")
    assert lo.smart_warm_up_line(start, True, "nl", clock)[0] == (
        "Slim opwarmen: begint om 07:30 (schatting; hij leert van elke ochtend), zodat het om 08:50 21 °C is.")
    assert lo.smart_warm_up_line(start, True, "pl", clock)[0].startswith("Inteligentne nagrzewanie: start o 07:30 (")
    # Heating now on an estimate: "estimate" too, as the E32 page says it (index.html smartWarmupLine, rc7).
    assert lo.smart_warm_up_line({**start, "start_now": True}, True, "en", clock)[0] == (
        "Smart warm-up: heating now (estimate; it learns from every morning) so it is 21 °C at 08:50.")
    assert lo.smart_warm_up_line({**start, "start_now": True}, True, "nl", clock)[0] == (
        "Slim opwarmen: verwarmt nu (schatting; hij leert van elke ochtend), zodat het om 08:50 21 °C is.")
    assert lo.smart_warm_up_line({**start, "start_now": True}, True, "pl", clock)[0] == (
        "Inteligentne nagrzewanie: grzeje teraz (szacunek; uczy się z każdego poranka), aby o 08:50 było 21 °C.")
    # A learned start heating now, or off: the same words as before; firmware without "estimate" too.
    assert lo.smart_warm_up_line({**start, "start_now": True, "estimate": False}, True, "en", clock)[0] == (
        "Smart warm-up: heating now so it is 21 °C at 08:50.")
    assert lo.smart_warm_up_line(start, False, "en", clock)[0] == "Smart warm-up is off: heating starts at 08:50."
    assert lo.smart_warm_up_line({**start, "estimate": False}, True, "en", clock)[0] == (
        "Smart warm-up: starts at 07:30 so it is 21 °C at 08:50.")


def test_the_warm_up_time_can_be_learned_before_the_coolest_water():
    learned = {"emitter": "floor", "readiness": "learning", "readiness_timing": "ready", "segments": 3}
    room = lo.room_overview("Woonkamer", learned, None, "en", CLOCK.get)
    assert room["lines"][0] == {
        "text": "The warm-up time is learned; the coolest water is still being learned.",
        "meaning": "Smart warm-up already plans with it; the coolest water needs a few more warm-ups at other "
                   "water temperatures."}
    assert lo.room_overview("Woonkamer", learned, None, "nl", CLOCK.get)["lines"][0]["text"] == (
        "De opwarmtijd is geleerd; het koelste water leert hij nog.")
    # Not yet (or firmware without it): the learning line as before; fully learned: no learning line at all.
    for timing in ("learning", "collecting", None):
        lines = lo.room_overview("Woonkamer", {**learned, "readiness_timing": timing}, None, "en", CLOCK.get)["lines"]
        assert lines[0]["text"] == "It learns from every warm-up while the heating runs.", timing
    ready = lo.room_overview("Woonkamer", {**LEARNED, "readiness_timing": "ready"}, None, "en", CLOCK.get)
    assert "warm-up time is learned" not in str(ready["lines"])


# rc7: the owner's card said "Learning: 6 of 6 warm-ups seen", which reads as finished; the E32 also needs warm-ups
# in 3 heating periods and at 2 water temperatures (FlowLearner readiness). Then the progress says what is missing.
@pytest.mark.parametrize("language,seen,timing,fine", [
    ("en", "Learning: 14 warm-ups seen; it still needs warm-ups on other days or at another water temperature",
     "Warm-up time learned; the coolest water is still being learned", "Learning: 5 of 6 warm-ups seen"),
    ("nl", "Aan het leren: 14 keer opwarmen gezien; hij moet nog opwarmen zien op andere dagen of bij een andere "
           "watertemperatuur",
     "Opwarmtijd geleerd; het koelste water leert hij nog", "Aan het leren: 5 van 6 keer opwarmen gezien"),
    ("pl", "Uczy się: widziano 14 nagrzewań; potrzebuje jeszcze nagrzewań w inne dni lub przy innej temperaturze wody",
     "Czas nagrzewania wyuczony; najchłodniejszej wody wciąż się uczy", "Uczy się: widziano 5 z 6 nagrzewań"),
])
def test_the_progress_never_reads_as_finished_before_the_room_is_learned(language, seen, timing, fine):
    progress = lambda **learned: lo.room_overview(  # noqa: E731
        "Woonkamer", {"emitter": "floor", "readiness": "learning", **learned}, None, language, CLOCK.get)["progress"]
    # Six or more warm-ups but not learned: the count goes on and it says what is still missing, never "6 of 6".
    assert progress(segments=14, periods=2) == seen
    assert progress(segments=6, periods=2) == seen.replace("14", "6")
    assert "6 " + {"en": "of", "nl": "van", "pl": "z"}[language] + " 6" not in progress(segments=6)
    # The warm-up time learned from one water temperature (E32 rc.4): that is what it says, whatever the count.
    assert progress(segments=3, readiness_timing="ready") == timing
    assert progress(segments=9, readiness_timing="ready") == timing
    # Fewer than six: the count as before; learned: "Learned" (the Rooms tab's badge says the same, strings.json).
    assert progress(segments=5) == fine
    assert progress(segments=0) == fine.replace("5", "0", 1)
    assert lo.room_overview("Woonkamer", {**LEARNED, "readiness_timing": "ready"}, None, language, CLOCK.get)[
        "progress"] == lo.TEXT[language]["learned"]
    # The line under the room says the same thing in a whole sentence.
    lines = lo.room_overview("Woonkamer", {"readiness": "learning", "segments": 14}, None, language, CLOCK.get)["lines"]
    assert lines[0]["text"] == lo.TEXT[language]["learning_more"]


# The firmware (ArrivalLearner::resolve) sends the program's switch time as last_at_utc and the minutes the
# room was late as last_error_min: the room was warm at last_at_utc + last_error_min (09:12 in every case
# here, the only moment the clock below knows), as the E32's Home page shows it.
@pytest.mark.parametrize("arrival,english,dutch", [
    ({"factor": 1.1, "events": 3, "last_error_min": 12, "last_at_utc": 1793265120 - 12 * 60},
     "Yesterday warm at 09:12 (12 min late); next time it starts a little earlier.",
     "Gisteren warm om 09:12 (12 min te laat); de volgende keer begint het iets eerder."),
    ({"factor": 0.92, "events": 4, "last_error_min": -25, "last_at_utc": 1793265120 + 25 * 60},
     "Yesterday warm at 09:12 (25 min early); next time it starts a little later.",
     "Gisteren warm om 09:12 (25 min te vroeg); de volgende keer begint het iets later."),
    ({"factor": 1.0, "events": 1, "last_error_min": 0.4, "last_at_utc": 1793265120},
     "Yesterday warm at 09:12 (on time).", "Gisteren warm om 09:12 (op tijd)."),
    # rc7 (R1-19): the next change follows from this morning with the E32's thresholds, not from the factor, which is
    # the product of every morning so far: after two late mornings (1.21) an early one (1.11) starts later, an on-time
    # one changes nothing, and at the E32's limit (2.0) a late one cannot start earlier.
    ({"factor": 1.11, "events": 3, "last_error_min": -20, "last_at_utc": 1793265120 + 20 * 60},
     "Yesterday warm at 09:12 (20 min early); next time it starts a little later.",
     "Gisteren warm om 09:12 (20 min te vroeg); de volgende keer begint het iets later."),
    ({"factor": 1.21, "events": 3, "last_error_min": 5, "last_at_utc": 1793265120 - 5 * 60},
     "Yesterday warm at 09:12 (5 min late).", "Gisteren warm om 09:12 (5 min te laat)."),
    ({"factor": 2.0, "events": 9, "last_error_min": 30, "last_at_utc": 1793265120 - 30 * 60},
     "Yesterday warm at 09:12 (30 min late).", "Gisteren warm om 09:12 (30 min te laat)."),
    # R1-24: an hour or more in hours and minutes.
    ({"factor": 1.1, "events": 3, "last_error_min": 95, "last_at_utc": 1793265120 - 95 * 60},
     "Yesterday warm at 09:12 (1 h 35 min late); next time it starts a little earlier.",
     "Gisteren warm om 09:12 (1 u 35 min te laat); de volgende keer begint het iets eerder."),
    # R1-6: never warm within 3 hours counts as 3 hours late on the E32; the line names the switch time instead.
    ({"factor": 1.1, "events": 3, "last_error_min": 180, "last_at_utc": 1793265120},
     "Yesterday not warm within 3 hours after 09:12; next time it starts a little earlier.",
     "Gisteren niet warm binnen 3 uur na 09:12; de volgende keer begint het iets eerder."),
])
def test_every_morning_is_checked(arrival, english, dutch):
    from datetime import date, timedelta
    clock = {1793265120: "09:12"}.get

    def day(utc):
        return date(2026, 10, 29) if abs(utc - 1793265120) <= 4 * 3600 else None
    text, meaning = lo.arrival_line(arrival, "en", clock, day, date(2026, 10, 30))
    assert text == english
    assert meaning == "It checks every morning whether the room was warm on time and adjusts its warm-up time."
    assert lo.arrival_line(arrival, "nl", clock, day, date(2026, 10, 30))[0] == dutch
    assert lo.arrival_line(arrival, "pl", clock, day, date(2026, 10, 30))[0].startswith("Wczoraj ")
    assert lo.arrival_line(arrival, "en", clock, day, date(2026, 10, 29))[0] == english.replace("Yesterday", "Today")
    assert lo.arrival_line(arrival, "en", clock, day, date(2026, 10, 29) + timedelta(days=5))[0] == english.replace(
        "Yesterday", "On 29 Oct")
    assert lo.arrival_line(arrival, "nl", clock, day, date(2026, 11, 3))[0] == dutch.replace("Gisteren", "Op 29 okt")


def test_no_arrival_line_without_a_checked_morning():
    def clock(utc):
        return "09:12"
    for arrival in (None, {}, {"factor": 1.0, "events": 0, "last_error_min": None, "last_at_utc": None},
                    {"factor": 1.1, "events": 2, "last_error_min": 12, "last_at_utc": 0},
                    {"factor": 1.1, "events": 2, "last_error_min": 9999, "last_at_utc": 1793265120}):
        assert lo.arrival_line(arrival, "en", clock) is None, arrival


def test_the_room_lines_end_with_how_the_morning_went():
    from datetime import date
    # The switch time was 09:00 (last_at_utc); the room was warm 12 min later, at 09:12.
    plan = {**PLAN, "arrival": {"factor": 1.1, "events": 3, "last_error_min": 12, "last_at_utc": 1793265120 - 12 * 60},
            "optimum_start": {**PLAN["optimum_start"], "applies": True, "estimate": True}}
    clock = {**CLOCK, 1793265120: "09:12"}.get
    room = lo.room_overview("Woonkamer", LEARNED, plan, "en", clock, True,
                            lambda utc: date(2026, 10, 29), date(2026, 10, 30))
    texts = [line["text"] for line in room["lines"]]
    assert texts[3:5] == [
        "Smart warm-up: starts at 07:30 (estimate; it learns from every morning) so it is 21 °C at 08:50.",
        "Yesterday warm at 09:12 (12 min late); next time it starts a little earlier."]
    s = sensor()
    s.hub.update_learned("woonkamer", ({**LEARNED, "id": "woonkamer"}, {**plan, "id": "woonkamer"}))
    s._clock = clock
    assert any(line["text"].endswith("warm at 09:12 (12 min late); next time it starts a little earlier.")
               for line in s.extra_state_attributes["rooms"][0]["lines"])


def test_the_learned_entities_carry_the_rc4_fields():
    """The learning status names the learned warm-up time; the predicted start says whether it is an estimate."""
    from custom_components.open_thermostat.heating_link import RoomHeatingStartSensor, RoomLearningSensor
    h = HeatingHub("fixture")
    h.update(STATUS)
    room = STATUS["rooms"][0]
    start = {"reason": "planned", "predicted_start_utc": 1793257800, "lead_minutes": 80, "confidence": "default",
             "applies": True, "estimate": True}
    h.update_learned("woonkamer", ({"id": "woonkamer", "readiness": "learning", "readiness_timing": "ready"},
                                   {"id": "woonkamer", "optimum_start": start}))
    assert RoomLearningSensor(h, room).extra_state_attributes["timing"] == "ready"
    assert RoomHeatingStartSensor(h, room).extra_state_attributes["estimate"] is True
    # Firmware before rc.4: the attributes are as before.
    h.update_learned("woonkamer", ({"id": "woonkamer", "readiness": "learning"},
                                   {"id": "woonkamer", "optimum_start": {k: v for k, v in start.items() if k != "estimate"}}))
    assert "timing" not in RoomLearningSensor(h, room).extra_state_attributes
    assert "estimate" not in RoomHeatingStartSensor(h, room).extra_state_attributes


# rc7: the sentences review (R1). Every case below is one the reviewer worked out from the firmware.
TRIAL = {
    "en": ("Smart warm-up in the trial run: it would start at 07:30 so it is 21 °C at 08:50.",
           "Smart warm-up in the trial run: it would be heating now so it is 21 °C at 08:50."),
    "nl": ("Slim opwarmen in de proefperiode: het zou om 07:30 beginnen, zodat het om 08:50 21 °C is.",
           "Slim opwarmen in de proefperiode: het zou nu verwarmen, zodat het om 08:50 21 °C is."),
    "pl": ("Inteligentne nagrzewanie w okresie próbnym: start byłby o 07:30, aby o 08:50 było 21 °C.",
           "Inteligentne nagrzewanie w okresie próbnym: grzałoby teraz, aby o 08:50 było 21 °C."),
}


@pytest.mark.parametrize("language", ["en", "nl", "pl"])
def test_the_trial_run_says_what_smart_warm_up_would_do(language):
    """R1-3: in the trial run the E32 heats nothing early (the old thermostat is in charge): "would"."""
    clock = {1793257800: "07:30", 1793262600: "08:50"}.get
    planned, now = TRIAL[language]
    assert lo.smart_warm_up_line(START, True, language, clock, trial=True) == (planned, lo.TEXT[language]["state.shadow"])
    assert lo.smart_warm_up_line({**START, "start_now": True}, True, language, clock, trial=True)[0] == now
    # Off, or still learning, says the same as outside the trial run.
    assert lo.smart_warm_up_line(START, False, language, clock, trial=True) == lo.smart_warm_up_line(START, False, language, clock)
    # The sensor follows the E32's mode.
    s = sensor(language)
    s.hub.update({**STATUS, "mode": "shadow"})
    texts = [line["text"] for line in s.extra_state_attributes["rooms"][0]["lines"]]
    assert planned in texts
    # R4-13: before the takeover is confirmed the E32 heats nothing early either (the house card's driving()).
    s.hub.update({**STATUS, "mode": "active", "active": {"state": "awaiting_confirmation"}})
    texts = [line["text"] for line in s.extra_state_attributes["rooms"][0]["lines"]]
    assert planned in texts
    assert lo.trial_run({"mode": "active", "active": {"state": "active"}}) is False and lo.trial_run(None) is False


FREE = {"rate": [None, 0.3, None, None, None, None], "n": [0, 6, 0, 0, 0, 0], "applied_min": 20}


def test_free_heat_moves_the_start_later_and_says_so_after_it():
    """R1-2: the E32 starts later by what the free heat gives (FreeHeat::shorten); the telemetry's start is without it.
    The start shown is the later one, the free-heat line follows it and says how much later; with Smart warm-up off
    nothing starts later."""
    clock = {1793257800: "07:30", 1793259000: "07:50", 1793262600: "08:50"}.get
    plan = {**PLAN, "optimum_start": {**START}, "free_heat": FREE}
    room = lo.room_overview("Woonkamer", LEARNED, plan, "en", clock, True)
    texts = [(line["text"], line["meaning"]) for line in room["lines"]]
    smart = next(i for i, (text, _) in enumerate(texts) if text.startswith("Smart warm-up"))
    assert texts[smart][0] == "Smart warm-up: starts at 07:50 so it is 21 °C at 08:50."
    assert texts[smart + 1] == ("Early in the morning this room warms up by itself, about 0.3 °C per hour (sun, cooking or "
                                "people).", "So the warm-up starts 20 min later than without the free heat.")
    assert lo.room_overview("Woonkamer", LEARNED, plan, "nl", clock, True)["lines"][smart + 1]["meaning"] == (
        "Daardoor begint het opwarmen 20 min later dan zonder de gratis warmte.")
    # The E32 says "start now" for the start without the free heat: not yet heating before the later start.
    early = {**plan, "optimum_start": {**START, "start_now": True}}
    assert lo.smart_warm_up_line(early["optimum_start"], True, "en", clock, later_min=20, now=1793258400)[0] == (
        "Smart warm-up: starts at 07:50 so it is 21 °C at 08:50.")
    assert lo.smart_warm_up_line(early["optimum_start"], True, "en", clock, later_min=20, now=1793259000)[0] == (
        "Smart warm-up: heating now so it is 21 °C at 08:50.")
    # Smart warm-up off: heating starts at the program time, and the free heat moves nothing.
    off = [(line["text"], line["meaning"]) for line in lo.room_overview("Woonkamer", LEARNED, plan, "en", clock, False)["lines"]]
    assert ("Smart warm-up is off: heating starts at 08:50.", "Turn Smart warm-up on to be warm on time.") in off
    assert off[smart + 1][1] == "Smart warm-up takes this into account when it plans a warm-up at that time of day."
    # The Learning tab's free-heat list: its own sentence while on, the plain meaning while off.
    assert lo.free_heat_lines([("Woonkamer", LEARNED, plan)], "en")[0]["meaning"].startswith("Its next warm-up starts 20 min")
    assert lo.free_heat_lines([("Woonkamer", LEARNED, plan)], "en", False)[0]["meaning"] == lo.TEXT["en"]["free_heat_mean"]


def test_the_heating_start_sensor_names_the_start_the_e32_uses():
    """The "Smart warm-up start" sensor: later by the free heat (rc7), and not "start now" before that later start."""
    from datetime import datetime, timedelta, timezone
    from custom_components.open_thermostat.heating_link import RoomHeatingStartSensor
    h = HeatingHub("fixture")
    h.update(STATUS)
    room = STATUS["rooms"][0]
    soon = int(datetime.now(timezone.utc).timestamp()) + 600
    start = {**START, "predicted_start_utc": soon, "start_now": True}
    h.update_learned("woonkamer", ({**LEARNED, "id": "woonkamer", "free_heat": FREE},
                                   {"id": "woonkamer", "optimum_start": start}))
    sensor_ = RoomHeatingStartSensor(h, room)
    assert sensor_.native_value == datetime.fromtimestamp(soon, timezone.utc) + timedelta(minutes=20)
    assert sensor_.extra_state_attributes["free_heat_min"] == 20 and sensor_.extra_state_attributes["start_now"] is False
    h.update_learned("woonkamer", ({**LEARNED, "id": "woonkamer", "free_heat": {**FREE, "applied_min": 0}},
                                   {"id": "woonkamer", "optimum_start": start}))
    assert sensor_.native_value == datetime.fromtimestamp(soon, timezone.utc)
    assert "free_heat_min" not in sensor_.extra_state_attributes and sensor_.extra_state_attributes["start_now"] is True


def test_a_free_heat_morning_is_never_late():
    """R4-2: the E32's reachable is for the start without the free heat, so once that earlier start has passed it is
    false every free-heat morning (WarmupPlanner::lead), while FreeHeat::shorten keeps the target in time. The sensor
    drops it and the Rooms line never says "may come a little after"."""
    from datetime import datetime, timedelta, timezone
    from custom_components.open_thermostat.heating_link import RoomHeatingStartSensor
    clock = {1793257800: "07:30", 1793259000: "07:50", 1793262600: "08:50"}.get
    late = {**START, "start_now": True, "reachable": False}
    before = lo.smart_warm_up_line(late, True, "en", clock, later_min=20, now=1793258400)[0]
    after = lo.smart_warm_up_line(late, True, "en", clock, later_min=20, now=1793259000)[0]
    assert before == "Smart warm-up: starts at 07:50 so it is 21 °C at 08:50."
    assert after == "Smart warm-up: heating now so it is 21 °C at 08:50."
    # Without free heat the flag still counts: the start could not reach the target in time.
    assert "may come a little after" in lo.smart_warm_up_line(late, True, "en", clock, now=1793259000)[0]
    h = HeatingHub("fixture")
    h.update(STATUS)
    passed = int(datetime.now(timezone.utc).timestamp()) - 1800  # the start without free heat, half an hour ago
    h.update_learned("woonkamer", ({**LEARNED, "id": "woonkamer", "free_heat": FREE},
                                   {"id": "woonkamer", "optimum_start": {**late, "predicted_start_utc": passed}}))
    sensor_ = RoomHeatingStartSensor(h, STATUS["rooms"][0])
    assert sensor_.native_value == datetime.fromtimestamp(passed, timezone.utc) + timedelta(minutes=20)
    attributes = sensor_.extra_state_attributes
    assert attributes["reachable"] is None and attributes["start_now"] is True and attributes["free_heat_min"] == 20
    h.update_learned("woonkamer", ({**LEARNED, "id": "woonkamer", "free_heat": {**FREE, "applied_min": 0}},
                                   {"id": "woonkamer", "optimum_start": {**late, "predicted_start_utc": passed}}))
    assert sensor_.extra_state_attributes["reachable"] is False  # no free heat: the E32's own flag


@pytest.mark.parametrize("comfort", [{"mode": "away"}, {"mode": "presence_away"}, {"mode": "window_open"},
                                     {"mode": "program", "window": "open"}])
def test_away_or_an_open_window_has_no_smart_warm_up_line(comfort):
    """R1-1: away, nobody home or an open window hold the week program on the E32 (no early start), although the
    telemetry plan still says "planned": no Smart warm-up line then."""
    plan = {**PLAN, "optimum_start": {**START}}
    lines = lo.room_overview("Woonkamer", LEARNED, plan, "en", CLOCK.get, True, comfort=comfort)["lines"]
    assert not any(line["text"].startswith("Smart warm-up") for line in lines)
    home = lo.room_overview("Woonkamer", LEARNED, plan, "en", CLOCK.get, True, comfort={"mode": "program"})["lines"]
    assert any(line["text"].startswith("Smart warm-up: starts at 07:30") for line in home)


@pytest.mark.parametrize("language,currency,amount", [
    ("en", "EUR", "€0.15"), ("nl", "EUR", "€ 0,15"), ("pl", "EUR", "0,15 €"), ("pl", "PLN", "0,15 zł"),
    ("en", "GBP", "£0.15"), ("en", "CHF", "0.15 CHF"), ("en", None, "0.15")])
def test_the_night_advice_has_its_currency_with_two_decimals(language, currency, amount):
    """R1-18: the money in Home Assistant's currency, always two decimals (0.10, not 0.1)."""
    assert lo.money(0.15, language, currency) == amount
    assert lo.money(0.1, "en", "EUR") == "€0.10"
    room = lo.room_overview("Woonkamer", LEARNED, PLAN, language, CLOCK.get, True, currency=currency)
    assert amount in room["lines"][-1]["text"]


def test_a_setback_that_is_not_the_night_says_until_when():
    """R1-18: the advice is for the setback before the next step up; an afternoon setback is not "at night"."""
    clock = {1793257800: "13:30", 1793262600: "17:00"}.get
    lines = lo.room_overview("Woonkamer", LEARNED, PLAN, "en", clock, True, currency="EUR")["lines"]
    assert lines[-1]["text"] == ("Keeping it at 19 °C until 17:00 is cheaper than letting it cool down: about 0.12 m³ gas "
                                 "(€0.15).")
    nl = lo.room_overview("Woonkamer", LEARNED, PLAN, "nl", clock, True, currency="EUR")["lines"][-1]["text"]
    assert nl == "Tot 17:00 op 19 °C houden is goedkoper dan laten afkoelen: ongeveer 0,12 m³ gas (€ 0,15)."
    program = {**PLAN, "night": {**PLAN["night"], "recommended": "program"}}
    assert lo.room_overview("Woonkamer", LEARNED, program, "en", clock, True)["lines"][-1]["text"] == (
        "Letting it cool down until 17:00, as your program does, is the cheapest.")
    # A morning step up ends a night: "at night", "a night".
    night = lo.room_overview("Woonkamer", LEARNED, PLAN, "en", CLOCK.get, True, currency="EUR")["lines"][-1]["text"]
    assert night == ("Keeping it at 19 °C at night is cheaper than letting it cool down: about 0.12 m³ gas (€0.15) a "
                     "night.")


@pytest.mark.parametrize("starts,burns,english,dutch,polish", [
    (1, 1, "Yesterday the burner started once for heating; the burn lasted 10 min.",
     "Gisteren startte de brander 1 keer voor verwarmen; hij brandde 10 min.",
     "Wczoraj palnik uruchomił się 1 raz do ogrzewania; praca trwała 10 min."),
    (1, None, "Yesterday the burner started once for heating.", "Gisteren startte de brander 1 keer voor verwarmen.",
     "Wczoraj palnik uruchomił się 1 raz do ogrzewania."),
    (0, 0, "Yesterday the burner did not start for heating.", "Gisteren startte de brander niet voor verwarmen.",
     "Wczoraj palnik nie uruchomił się do ogrzewania."),
    (2, 2, "Yesterday the burner started 2 times for heating; a burn lasted 10 min on average.",
     "Gisteren startte de brander 2 keer voor verwarmen; hij brandde gemiddeld 10 min.",
     "Wczoraj palnik uruchomił się 2 razy do ogrzewania; praca trwała średnio 10 min."),
])
def test_one_burner_start_and_none(starts, burns, english, dutch, polish):
    """R1-23: "started once", never "1 times"; no start: "did not start"."""
    yesterday = {"starts": starts, "heating_h": 1, "burn_s": 600, **({"burns": burns} if burns is not None else {})}
    for language, text in (("en", english), ("nl", dutch), ("pl", polish)):
        house = lo.house_overview({"schema": 1, "tuning": {"yesterday": yesterday}}, language)
        assert house[0]["text"] == text, language


def test_a_polish_room_name_stands_after_pomieszczenie():
    """R1-20: a neuter past tense after "Salon" or "Kuchnia" is wrong; after "pomieszczenie" it is right."""
    names = {"salon": "Salon"}
    assert lo.change_text(["heat_stop_c", 0.2, 0.15, "overshoot", 0.6, "salon"], names, "pl").startswith(
        "Pomieszczenie Salon nagrzało się o 0,6 °C")
    assert "bo pomieszczenie Salon ochłodziło się o 0,5 °C" in lo.change_text(
        ["min_off_s", 600, 450, "cold_during_rest", 0.5, "salon"], names, "pl")
    assert "bo przeciętne pomieszczenie ochłodziło się" in lo.change_text(
        ["min_off_s", 600, 450, "cold_during_rest", 0.5, ""], names, "pl")
    assert lo.change_text(["heat_stop_c", 0.2, 0.15, "overshoot_gain", 0.6, ""], names, "pl").startswith(
        "Przeciętne pomieszczenie wciąż nagrzało się")
    # English and Dutch keep the name itself; a typical room in the middle of a sentence is lower case.
    assert lo.change_text(["heat_stop_c", 0.2, 0.15, "overshoot", 0.6, "salon"], names, "en").startswith("Salon got 0.6 °C")
    assert "because a typical room cooled 0.5 °C" in lo.change_text(["min_off_s", 600, 450, "cold_during_rest", 0.5, ""],
                                                                    names, "en")


def test_one_start_and_proposals_in_every_language():
    """R1-23 "with only 1 start"; R1-16 a proposal says what it would set, in every language."""
    assert "with only 1 start yesterday" in lo.change_text(["heat_start_c", 0.25, 0.2, "few_starts", 1, ""], {}, "en")
    assert "met maar 1 start gisteren" in lo.change_text(["heat_start_c", 0.25, 0.2, "few_starts", 1, ""], {}, "nl")
    assert "przy zaledwie 1 uruchomieniu" in lo.change_text(["heat_start_c", 0.25, 0.2, "few_starts", 1, ""], {}, "pl")
    change = ["heat_stop_c", 0.2, 0.15, "overshoot", 0.6, "woonkamer"]
    names = {"woonkamer": "Woonkamer"}
    assert lo.change_text(change, names, "en", proposal=True) == (
        "Would set “Stop heating when the room is this much above its target” to 0.15 °C, because Woonkamer got 0.6 °C "
        "warmer than its target.")
    assert lo.change_text(change, names, "nl", proposal=True).startswith("Zou ‘")
    assert lo.change_text(change, names, "pl", proposal=True).endswith(
        "bo pomieszczenie Woonkamer nagrzało się o 0,6 °C powyżej zadanej temperatury.")
    for reason in ("many_starts", "cold_during_rest", "short_burns", "boiler_cycling", "overshoot", "overshoot_gain",
                   "settled", "hovering", "few_starts", "learned_warmup"):
        for language in ("en", "nl", "pl"):
            text = lo.change_text(["min_off_s", 300, 450, reason, 3, "woonkamer"], names, language, proposal=True)
            assert text and "{" not in text and "now" not in text.split(",")[0], (reason, language)


def test_a_room_that_hardly_cools_has_no_cooling_line():
    """R1-26: "Loses about 0 °C per hour" says nothing."""
    texts = lambda loss: [line["text"] for line in lo.room_overview(  # noqa: E731
        "Woonkamer", {**LEARNED, "loss_per_h": loss}, None, "en", CLOCK.get)["lines"]]
    assert not any(text.startswith("Loses") for text in texts(0.0001))
    assert not any(text.startswith("Loses") for text in texts(-0.01))
    assert "Loses about 0.3 °C per hour at 5 °C outside." in texts(0.02)


def test_six_steady_periods_never_read_as_six_of_six():
    """A2's leftovers: the learned line follows from 6 steady periods; a count of 6 or more without it (a moment's
    race in one summary) says the plain sentence, never "6 of 6"."""
    curve = {"state": "applied", "slope_source": "design", "windows": 6}
    assert lo.curve_status(curve, True, "en")[0] == "Weather compensation: standard for now, learning from your house."
    assert lo.curve_status({**curve, "windows": 5}, True, "en")[0].endswith("(5 of 6 steady periods).")
