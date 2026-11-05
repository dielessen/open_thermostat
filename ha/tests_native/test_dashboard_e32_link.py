"""Diagnostics, "Connection with the E32" (rc.7): whether the E32 and Home Assistant reach each other, in plain words.

The rc.5 outage (P22): Home Assistant stopped sending room values to the E32 about four hours after each start while
everything looked fine; the owner only saw it on the E32's own page. rc.6 added the repair heating_input_lost and the
heat request sensor's ``ha_input`` attribute (heating_link.HeatingInputWatch); this section says on the dashboard what
they know, one line per question with an icon (fine, waiting, a problem, not known, an update): is the E32 heard (the
heat request sensor is unavailable while it is silent and written with every E32 message), do the room values reach
it (yes, none for 15 minutes, or no, with the value it refused last and why and the repair's advice), does Home
Assistant reach the MQTT broker, and the firmware (the update entity). The details sit behind "More". Every template
renders against the states of each case, in English, Dutch and Polish.
"""
from datetime import timedelta

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from custom_components.open_thermostat.dashboard import TEXT, RoomDashboard, _connection_section
from test_dashboard_heating import installation, walk

OK, WAIT, PROBLEM, UNKNOWN, UPDATE = (
    f'<font color="{colour}"><ha-icon icon="{icon}"></ha-icon></font> ' for icon, colour in (
        ("mdi:check-circle-outline", "#4caf50"), ("mdi:clock-alert-outline", "#ffa600"),
        ("mdi:alert-circle-outline", "#db4437"), ("mdi:help-circle-outline", "#9e9e9e"),
        ("mdi:arrow-up-circle-outline", "#039be5")))
HEADINGS = {"en": "Connection with the E32", "nl": "Verbinding met de E32", "pl": "Połączenie z E32"}


def link_installation(hass, language="en", update=True):
    e, rooms, sensors, hub, fields = installation(hass, language)
    product = dr.async_get(hass).async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    firmware = er.async_get(hass).async_get_or_create(
        "update", "open_thermostat", "fixture_e32_firmware", config_entry=e, device_id=product.id,
        suggested_object_id="e32_firmware").entity_id if update else None
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert None not in list(walk(config))
    diagnostics = next(view for view in config["views"] if view["path"] == "diagnostics")
    return diagnostics["sections"][0], hub["heat_request"], firmware


def lines(hass, card):
    """The card's lines as rendered, the details behind "More" as one."""
    text = Template(card["content"], hass).async_render(parse_result=False)
    head, details, tail = text.partition("<details>")
    return [line.strip() for line in head.split("\n\n") if line.strip()] + ([details + tail.strip()] if details else [])


def at(moment, language="en"):
    """As the template's at(): the local time of day, the date in front when it is not today."""
    local = dt_util.as_local(moment)
    clock = f"{local.hour}:{local.minute:02d}"
    if local.date() == dt_util.now().date():
        return clock
    return f"{local.day} {TEXT[language]['months'].split(',')[local.month - 1]} {clock}"


def minute(minutes_ago):
    """An ha_input time: UTC, to the minute (heating_link._iso_minute)."""
    moment = dt_util.utcnow().replace(second=0, microsecond=0) - timedelta(minutes=minutes_ago)
    return moment, moment.isoformat()


def ha_input(state, last_input=None, rejected=None, sent=None, error=None, error_at=None, dropped=0, kind=None):
    return {"state": state, "e32_last_input": last_input, "e32_last_rejected": rejected, "last_sent": sent,
            "last_error": error, "last_error_at": error_at, "last_error_kind": kind, "dropped": dropped}


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "nl", "pl"])
async def test_the_connection_comes_first_on_diagnostics_and_says_all_is_well_in_plain_words(hass, language):
    section, request, firmware = link_installation(hass, language)
    heading, card = section["cards"]
    assert heading == {"type": "heading", "heading": HEADINGS[language], "heading_style": "title",
                       "icon": "mdi:lan-connect"}
    # Always shown: its first line answers whether the E32 is heard also while it is not.
    assert card["type"] == "markdown" and "visibility" not in section and "visibility" not in card
    taken, taken_at = minute(2)
    sent, sent_at = minute(1)
    hass.states.async_set(request, "41", {"ha_input": ha_input("ok", taken_at, sent=sent_at)})
    hass.states.async_set(firmware, "off", {"installed_version": "1.0.0-rc.5", "latest_version": "1.0.0-rc.5"})
    now = at(dt_util.utcnow(), language)
    words = {
        "en": [OK + f"The E32 reports to Home Assistant: yes, last at {now}.",
               OK + f"Room values reach the E32: yes, last at {at(taken)}.",
               OK + "MQTT broker: the E32 and Home Assistant both reach it.",
               OK + "Firmware: 1.0.0-rc.5, up to date.",
               f"<details><summary>More</summary>\n\n- Home Assistant last sent a value at {at(sent)}.\n\n</details>"],
        "nl": [OK + f"De E32 meldt zich bij Home Assistant: ja, het laatst om {now}.",
               OK + f"Ruimtewaarden komen aan bij de E32: ja, het laatst om {at(taken, 'nl')}.",
               OK + "MQTT-broker: de E32 en Home Assistant bereiken hem allebei.",
               OK + "Firmware: 1.0.0-rc.5, actueel.",
               f"<details><summary>Meer</summary>\n\n- Home Assistant stuurde de laatste waarde om {at(sent, 'nl')}."
               "\n\n</details>"],
        "pl": [OK + f"E32 zgłasza się do Home Assistant: tak, ostatnio o {now}.",
               OK + f"Wartości pomieszczeń docierają do E32: tak, ostatnio o {at(taken, 'pl')}.",
               OK + "Broker MQTT: E32 i Home Assistant łączą się z nim.",
               OK + "Oprogramowanie układowe: 1.0.0-rc.5, aktualne.",
               f"<details><summary>Więcej</summary>\n\n- Home Assistant wysłał ostatnią wartość o {at(sent, 'pl')}."
               "\n\n</details>"]}[language]
    assert "\n\n".join(lines(hass, card)) == "\n\n".join(words)


@pytest.mark.asyncio
async def test_room_values_that_do_not_arrive_say_since_when_why_and_what_to_do(hass):
    """The rc.5 outage as the repair heating_input_lost sees it: no values taken since 13:41, the one refused last and
    why, Home Assistant's own send failing, the values it dropped; the repair's advice on the line."""
    section, request, _ = link_installation(hass)
    card = section["cards"][1]
    taken, taken_at = minute(200)
    refused, refused_at = minute(30)
    sent, sent_at = minute(190)
    failed, failed_at = minute(3)
    hass.states.async_set(request, "0", {"ha_input": ha_input(
        "not_received", taken_at, {"reason": "unknown_room", "at": refused_at}, sent_at,
        "50 messages still wait for the MQTT broker", failed_at, dropped=212, kind="waiting")})
    heard, values, broker, more = lines(hass, card)
    assert heard.startswith(OK + "The E32 reports to Home Assistant: yes")
    assert values == (PROBLEM + f"Room values reach the E32: no, not since {at(taken)}. The E32 refused the last value at "
                      f"{at(refused)}: it does not know that room. Until they arrive, the E32 runs the rooms on its own "
                      "sensors and week programs. Home Assistant keeps sending them; if this stays, restart Home "
                      "Assistant.")
    # The kind of failure in words; the raw error (English, from the MQTT client) only behind "More".
    assert broker == (PROBLEM + f"MQTT broker: Home Assistant could not send through it at {at(failed)}: too many "
                      "messages were waiting for the broker.")
    assert more == ("<details><summary>More</summary>\n\n"
                    f"- Home Assistant last sent a value at {at(sent)}.\n"
                    f"- Last send error at {at(failed)}: 50 messages still wait for the MQTT broker.\n"
                    "- Values dropped while the broker did not answer: 212.\n\n</details>")
    # A reason this version does not know is said as the E32 sent it; no time taken yet (none since the E32 started).
    hass.states.async_set(request, "0", {"ha_input": ha_input("not_received", None, {"reason": "busy", "at": refused_at})})
    assert lines(hass, card)[1].startswith(PROBLEM + "Room values reach the E32: no. The E32 refused the last value at "
                                           f"{at(refused)}: busy. Until they arrive")


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "nl", "pl"])
async def test_waiting_unknown_and_an_earlier_refusal(hass, language):
    section, request, _ = link_installation(hass, language, update=False)
    card = section["cards"][1]
    taken, taken_at = minute(17)
    refused, refused_at = minute(60 * 26)  # yesterday: with its date
    hass.states.async_set(request, "41", {"ha_input": ha_input("waiting", taken_at,
                                                               {"reason": "invalid_value", "at": refused_at})})
    heard, values, broker, more = lines(hass, card)
    assert values == WAIT + {"en": f"Room values reach the E32: none in the last 15 minutes; the last at {at(taken)}.",
                             "nl": "Ruimtewaarden komen aan bij de E32: geen in de laatste 15 minuten; de laatste om "
                                   f"{at(taken, 'nl')}.",
                             "pl": "Wartości pomieszczeń docierają do E32: brak w ostatnich 15 minutach; ostatnia o "
                                   f"{at(taken, 'pl')}."}[language]
    assert broker.startswith(OK)
    # A value refused while the others arrive: behind "More", with its date.
    assert at(refused, language)[0].isdigit() and " " in at(refused, language)
    assert more.endswith({"en": f"- The E32 last refused a value at {at(refused)}: the value was outside what it "
                                "accepts.\n\n</details>",
                          "nl": f"- De E32 weigerde het laatst een waarde om {at(refused, 'nl')}: de waarde lag buiten "
                                "wat hij aanneemt.\n\n</details>",
                          "pl": f"- E32 ostatnio odrzucił wartość o {at(refused, 'pl')}: wartość była poza "
                                "dopuszczalnym zakresem.\n\n</details>"}[language])
    # Firmware that does not say whether it takes the values (no ha block): not known; no firmware line without the
    # update entity, and nothing behind "More" without anything to tell.
    hass.states.async_set(request, "41", {"ha_input": ha_input("unknown")})
    assert lines(hass, card)[1:] == [
        UNKNOWN + {"en": "Room values reach the E32: the E32 does not say (older firmware).",
                   "nl": "Ruimtewaarden komen aan bij de E32: de E32 meldt het niet (oudere firmware).",
                   "pl": "Wartości pomieszczeń docierają do E32: E32 tego nie podaje (starsze oprogramowanie)."}[language],
        OK + {"en": "MQTT broker: the E32 and Home Assistant both reach it.",
              "nl": "MQTT-broker: de E32 en Home Assistant bereiken hem allebei.",
              "pl": "Broker MQTT: E32 i Home Assistant łączą się z nim."}[language]]


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "nl", "pl"])
async def test_a_silent_e32_says_since_when_and_what_to_check(hass, language):
    section, request, firmware = link_installation(hass, language)
    card = section["cards"][1]
    hass.states.async_set(firmware, "off", {"installed_version": "1.0.0-rc.5", "latest_version": "1.0.0-rc.5"})
    # Before Home Assistant has a state for it at all.
    assert lines(hass, card)[0] == PROBLEM + {
        "en": "The E32 reports to Home Assistant: not yet. Check that the E32 has power and Wi-Fi and that the MQTT broker "
              "runs. Meanwhile the E32 keeps heating the rooms by itself.",
        "nl": "De E32 meldt zich bij Home Assistant: nog niet. Controleer of de E32 stroom en wifi heeft en of de "
              "MQTT-broker draait. Intussen blijft de E32 de ruimtes zelf verwarmen.",
        "pl": "E32 zgłasza się do Home Assistant: jeszcze nie. Sprawdź, czy E32 ma zasilanie i Wi-Fi oraz czy działa "
              "broker MQTT. W tym czasie E32 sam dalej ogrzewa pomieszczenia."}[language]
    # Silent (three missed heartbeats): unavailable, without attributes; since it went quiet. Only the firmware is known.
    hass.states.async_set(request, "unavailable", {})
    now = at(dt_util.utcnow(), language)
    first, *rest = lines(hass, card)
    assert first.startswith(PROBLEM + {"en": f"The E32 reports to Home Assistant: no, nothing heard since {now}. Check",
                                       "nl": f"De E32 meldt zich bij Home Assistant: nee, niets gehoord sinds {now}. "
                                             "Controleer",
                                       "pl": f"E32 zgłasza się do Home Assistant: nie, cisza od {now}. Sprawdź"}[language])
    assert len(rest) == 1 and rest[0].startswith(OK)


@pytest.mark.asyncio
@pytest.mark.parametrize("state, attributes, line", [
    ("on", {"installed_version": "1.0.0-rc.5", "latest_version": "1.0.0"},
     UPDATE + "Firmware: 1.0.0-rc.5; 1.0.0 is available under Settings → Updates."),
    ("on", {"installed_version": "1.0.0-rc.5", "latest_version": "1.0.0", "in_progress": True},
     UPDATE + "Firmware: installing 1.0.0 now."),
    ("on", {"installed_version": "1.0.0-rc.5", "latest_version": "1.0.0", "in_progress": 40},
     UPDATE + "Firmware: installing 1.0.0 now."),
    ("off", {"installed_version": "1.0.0-rc.5", "latest_version": "1.0.0", "skipped_version": "1.0.0"},
     OK + "Firmware: 1.0.0-rc.5; you skipped 1.0.0."),
    ("off", {"installed_version": "1.0.0-rc.5", "latest_version": "1.0.0-rc.5", "in_progress": False},
     OK + "Firmware: 1.0.0-rc.5, up to date."),
    ("unknown", {}, None)])
async def test_the_firmware_line_follows_the_update_entity(hass, state, attributes, line):
    section, request, firmware = link_installation(hass)
    hass.states.async_set(request, "unavailable", {})
    hass.states.async_set(firmware, state, attributes)
    said = lines(hass, section["cards"][1])
    assert said[1:] == ([line] if line else [])


@pytest.mark.asyncio
async def test_no_connection_section_without_an_e32(hass):
    assert _connection_section(TEXT["en"], None) is None
    from test_v1_native import entry
    e = entry(hass)
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    diagnostics = next(view for view in config["views"] if view["path"] == "diagnostics")
    assert diagnostics["sections"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("language, kind, words", [
    ("nl", "timeout", "MQTT-broker: Home Assistant kon er om {at} niets via versturen: de broker nam de waarde niet op "
                      "tijd aan."),
    ("pl", "unreachable", "Broker MQTT: Home Assistant nie mógł przez niego wysłać o {at}: Home Assistant nie mógł "
                          "połączyć się z brokerem."),
    ("en", None, "MQTT broker: Home Assistant could not send through it at {at}: Connection refused.")])
async def test_a_failing_send_is_said_in_the_viewers_words(hass, language, kind, words):
    """The kind of failure in the language (the error text of the MQTT client is English); an attribute without a
    kind (rc.6) falls back to that text."""
    section, request, _ = link_installation(hass, language, update=False)
    taken, taken_at = minute(1)
    failed, failed_at = minute(0)
    hass.states.async_set(request, "41", {"ha_input": ha_input("ok", taken_at, sent=minute(5)[1],
                                                               error="Connection refused", error_at=failed_at, kind=kind)})
    assert lines(hass, section["cards"][1])[2] == PROBLEM + words.format(at=at(failed, language))
