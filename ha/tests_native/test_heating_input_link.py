"""P22 (4 Nov 2026): Home Assistant stopped feeding the E32.

On the owner's installation (HA 1.0.0rc5, E32 rc.4) the E32 accepted no ha/heating_input message from
about four hours after Home Assistant's start until Home Assistant restarted; reloading the integration
did not help, the E32's MQTT link never dropped (Diagnose page: no reconnect, no stall).

Cause: the comfort forwarder's five-minute refresh was a plain lambda, so Home Assistant ran it as an
executor job; in that worker thread ``hass.async_create_task`` raises (not thread-safe) after
``publish_input`` (R4-07, new in 1.0.0rc5) had counted the send as pending. The count never came back:
after fifty refreshes (4 h 10 min) every room, energy and comfort value was dropped at debug level, and
the count lived in ``hass.data`` outside the entry, so only a restart cleared it.

These tests drive the production wiring on a real Home Assistant core: the timers run exactly as
``async_track_time_interval`` runs them (a ``HassJob``: a @callback in the event loop, anything else as an
executor job).
"""
import asyncio
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import EntityCategory
from homeassistant.core import HassJob
from homeassistant.util import dt as dt_util

from custom_components.open_thermostat import e32_comfort, e32_setting_device, heating_link, product
from custom_components.open_thermostat.const import DOMAIN
from custom_components.open_thermostat.e32_comfort import CONF_COMFORT
from e32_telemetry import FakeE32

TOPIC = "fixture/v1/ha/heating_input"
STATUS = {"schema": 1, "revision": 5, "mode": "active", "request": {"heat": False, "flow_c": 0, "reason": "idle"},
          "ha_entities": ["climate.woonkamer"],
          "rooms": [{"id": "woonkamer", "name": "Woonkamer", "state": "active", "status": "ok", "source": "a4c138a3e8db",
                     "temperature": 20.4, "setpoint": 20.5, "setpoint_source": "schedule", "demand": False}],
          "ha": {"input_age_s": 3, "broker_connected": True}}


class FakePusher:
    def __init__(self, hass, entry, hub):
        pass

    def start(self):
        return lambda: None


class Installation:
    """One E32 entry wired like Home Assistant does it: the heating link (room and energy values) and the
    E32 thermostats' forwarder (window/door contacts and presence). MQTT is recorded."""

    def __init__(self, hass, monkeypatch):
        self.hass, self.monkeypatch = hass, monkeypatch
        self.callbacks, self.published, self.timers, self.unload = {}, [], [], []

    async def start(self, comfort=None):
        from homeassistant import loader
        from homeassistant.components import mqtt
        hass, monkeypatch = self.hass, self.monkeypatch
        loader.async_setup(hass)  # as in Home Assistant: a misuse report names the integration, then raises
        monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())

        async def subscribe(hass, topic, callback):
            self.callbacks[topic] = callback
            return lambda: None
        monkeypatch.setattr(mqtt, "async_subscribe", subscribe)

        async def publish(hass, topic, payload, qos, retain):
            self.published.append((topic, json.loads(payload)))
        monkeypatch.setattr(mqtt, "async_publish", publish)

        def interval(hass, action, every):
            self.timers.append((action, every))
            return lambda: None
        monkeypatch.setattr(heating_link, "async_track_time_interval", interval)
        monkeypatch.setattr(e32_comfort, "async_track_time_interval", interval)
        hass.data.setdefault(DOMAIN, {})["e"] = {"v1_connection": SimpleNamespace(client=object(), prefix="fixture/v1/")}
        self.entry = SimpleNamespace(entry_id="e", data={"topic_prefix": "fixture"},
                                     options={CONF_COMFORT: comfort} if comfort is not None else {},
                                     async_on_unload=self.unload.append)
        await heating_link.async_setup_heating_link(hass, self.entry, lambda *_a, **_k: None)
        self.hub = hass.data[DOMAIN]["e"]["heating_hub"]
        self.hub.plan = SimpleNamespace(stop=lambda: None)  # a stored E32 connection (the thermostats need one)
        self.e32 = FakeE32(self.callbacks)
        self.e32.status(STATUS)
        with monkeypatch.context() as patch:  # only the thermostats' setup sees a product entry
            patch.setattr(product, "is_product", lambda entry: True)
            patch.setattr(e32_comfort, "track_entities", lambda *_a, **_k: (lambda: None))
            patch.setattr(e32_comfort, "add_options", lambda hass, entry, options=None: {})
            patch.setattr(e32_setting_device, "SettingDevicePusher", FakePusher)
            await e32_comfort.async_setup_e32_climates(hass, self.entry, lambda *_a, **_k: None)
        await hass.async_block_till_done()
        return self

    def refreshes(self, module):
        """The five-minute refreshes the module registered."""
        return [action for action, every in self.timers
                if every == timedelta(minutes=5) and getattr(action, "__module__", module.__name__) == module.__name__]

    async def run_timer(self, action, times=1):
        """As async_track_time_interval runs a due timer (homeassistant.helpers.event._TrackTimeInterval)."""
        failures = []
        for _ in range(times):
            job = self.hass.async_run_hass_job(HassJob(action, "track time interval 300"), dt_util.utcnow(),
                                               background=True)
            await self.hass.async_block_till_done(wait_background_tasks=True)
            if isinstance(job, asyncio.Future) and job.done() and not job.cancelled() and job.exception():
                failures.append(job.exception())
        return failures

    def sent(self, kind=None, entity=None):
        return [p for t, p in self.published if t == TOPIC and (kind is None or p.get("kind") == kind)
                and (entity is None or p.get("entity") == entity)]


@pytest.mark.asyncio
async def test_the_five_minute_comfort_refresh_never_stops_the_room_values(hass, monkeypatch):
    """The incident, end to end: a person in the house, fifty-odd five-minute refreshes (more than four hours),
    then the tado reports a new temperature: the E32 must get it."""
    hass.states.async_set("climate.woonkamer", "heat", {"current_temperature": 20.4, "temperature": 20.5})
    hass.states.async_set("person.anna", "home")
    link = await Installation(hass, monkeypatch).start({"presence_entities": ["person.anna"]})
    assert link.sent(entity="climate.woonkamer")[-1] == {"entity": "climate.woonkamer", "temperature": 20.4,
                                                         "target": 20.5}
    comfort_refresh = link.refreshes(e32_comfort)
    assert len(comfort_refresh) == 1
    presence_before = len(link.sent("presence"))
    failures = await link.run_timer(comfort_refresh[0], 60)  # 5 h of five-minute refreshes
    # The room values still go out: a new tado temperature and the heating link's own refresh.
    hass.states.async_set("climate.woonkamer", "heat", {"current_temperature": 20.2, "temperature": 20.5})
    await hass.async_block_till_done()
    assert link.sent(entity="climate.woonkamer")[-1]["temperature"] == 20.2
    room_refresh = [action for action in link.refreshes(heating_link) if action not in comfort_refresh]
    assert room_refresh
    before = len(link.sent(entity="climate.woonkamer"))
    await link.run_timer(room_refresh[0])
    assert len(link.sent(entity="climate.woonkamer")) == before + 1
    # Every refresh sent the house's presence again (the E32 forgets a report after 15 minutes), in the event loop.
    assert failures == []
    assert len(link.sent("presence")) == presence_before + 60


def _entry(unload=None, prefix="fixture"):
    return SimpleNamespace(entry_id="e", data={"topic_prefix": prefix},
                           async_on_unload=unload.append if unload is not None else (lambda _: None))


def _record_mqtt(monkeypatch, published):
    from homeassistant.components import mqtt

    async def publish(hass, topic, payload, qos, retain):
        published.append((topic, payload))
    monkeypatch.setattr(mqtt, "async_publish", publish)


@pytest.mark.asyncio
async def test_a_value_from_a_worker_thread_goes_out_from_the_event_loop(hass, monkeypatch, caplog):
    """Whatever calls it from a worker thread: the message goes out (in order) and holds no place."""
    import logging
    published = []
    _record_mqtt(monkeypatch, published)
    hass.data.setdefault(DOMAIN, {})["e"] = {}
    link = heating_link.heating_input_link(hass, _entry())
    await hass.async_add_executor_job(lambda: [link.send(json.dumps({"n": n})) for n in range(60)])
    await hass.async_block_till_done()
    assert [json.loads(payload)["n"] for _topic, payload in published] == list(range(60))
    assert {topic for topic, _payload in published} == {TOPIC}
    assert link.pending == 0 and link.dropped == 0 and link.error is None
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "worker thread" in warnings[0]


@pytest.mark.asyncio
async def test_a_broker_that_never_answers_frees_its_places_and_a_reload_starts_afresh(hass, monkeypatch, caplog):
    """Sends that hang time out (each its own deadline) and count as failures; one warning when the places are
    full; unloading the entry cancels what still waits, and the reloaded entry sends at once."""
    import logging
    from homeassistant.components import mqtt
    monkeypatch.setattr(heating_link, "PUBLISH_TIMEOUT_S", 0.05)

    async def hanging(hass, topic, payload, qos, retain):
        await asyncio.Event().wait()
    monkeypatch.setattr(mqtt, "async_publish", hanging)
    unload = []
    hass.data.setdefault(DOMAIN, {})["e"] = {}
    link = heating_link.heating_input_link(hass, _entry(unload))
    for _ in range(heating_link.MAX_PENDING_PUBLISHES + 1):
        link.send("{}")
    assert link.pending == heating_link.MAX_PENDING_PUBLISHES and link.dropped == 1
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "still wait for the MQTT broker" in warnings[0]
    await asyncio.sleep(0.3)
    assert link.pending == 0 and link.failures == heating_link.MAX_PENDING_PUBLISHES
    assert "did not take it within" in link.error and link.failing
    published = []
    _record_mqtt(monkeypatch, published)
    link.send('{"after": "timeout"}')
    await hass.async_block_till_done()
    assert published == [(TOPIC, '{"after": "timeout"}')] and not link.failing and link.sent_at is not None
    # Fifty that never end, then a reload: the old link is closed (its sends cancelled), the new one sends.
    monkeypatch.setattr(heating_link, "PUBLISH_TIMEOUT_S", 3600)
    monkeypatch.setattr(mqtt, "async_publish", hanging)
    for _ in range(heating_link.MAX_PENDING_PUBLISHES):
        link.send("{}")
    assert link.pending == heating_link.MAX_PENDING_PUBLISHES
    for remove in unload:  # async_unload_entry: the entry's unload callbacks, then its data goes
        remove()
    hass.data[DOMAIN].pop("e")
    await hass.async_block_till_done()
    assert link.pending == 0
    _record_mqtt(monkeypatch, published)
    link.send('{"to": "the old link"}')  # closed: nothing goes out any more
    hass.data[DOMAIN]["e"] = {}
    fresh = heating_link.heating_input_link(hass, _entry([]))
    fresh.send('{"value": 51}')
    await hass.async_block_till_done()
    assert fresh is not link and published[-1] == (TOPIC, '{"value": 51}') and len(published) == 2


WALL = dt_util.parse_datetime("2026-11-04T17:00:30+00:00")  # the wall clock at now == 1000 (mid-minute)


def _watch(hass, monkeypatch, now, **link_options):
    from homeassistant.components import mqtt
    clock = lambda: now[0]  # noqa: E731
    hub = heating_link.HeatingHub("fixture", clock=clock)
    hub.base = "fixture/v1/"
    hass.data.setdefault(DOMAIN, {})["e"] = {"heating_hub": hub}
    entry = _entry()
    published = []

    async def publish(hass, topic, payload, qos, retain):
        published.append((topic, payload))
    monkeypatch.setattr(mqtt, "async_publish", publish)
    link = heating_link.HeatingInputLink(hass, entry, hub, clock=clock)
    resent = []
    watch = hub.input_watch = heating_link.HeatingInputWatch(
        hass, entry, hub, link, lambda: resent.append(now[0]), clock=clock,
        wall=lambda: WALL + timedelta(seconds=now[0] - 1000))
    return hub, link, watch, resent, published


def _e32(hub, age, rejected=None, **status):
    ha = {"input_age_s": age, "broker_connected": True, **({"last_rejected": rejected} if rejected else {})}
    hub.update({**STATUS, **status, "ha": ha})


def _since(moment):
    local = dt_util.as_local(moment)
    return local.strftime("%H:%M") if local.date() == dt_util.now().date() else local.strftime("%d-%m %H:%M")


@pytest.mark.asyncio
async def test_the_e32_not_accepting_raises_a_repair_and_sends_everything_again(hass, monkeypatch, caplog):
    """The end-to-end check: Home Assistant keeps sending, the E32's input age passes 15 minutes: one warning, a
    fresh resend through a restarted link, a repair with the facts; all of it clears once the E32 accepts again."""
    import logging
    from homeassistant.helpers import issue_registry as ir
    caplog.set_level(logging.INFO, logger="custom_components.open_thermostat.heating_link")
    await ir.async_load(hass)
    now = [1000.0]
    hub, link, watch, resent, published = _watch(hass, monkeypatch, now)
    _e32(hub, 3)
    link.send("{}")
    await hass.async_block_till_done()
    watch.check()
    assert watch.attributes()["state"] == "ok" and watch.diagnostics()["e32_input_age_s"] == 3
    # The attribute names moments to the minute: a newer E32 message about the same acceptance changes nothing.
    first = watch.attributes()
    assert first["e32_last_input"] == "2026-11-04T17:00:00+00:00" and first["last_sent"].endswith(":00+00:00")
    now[0] += 4
    _e32(hub, 7)
    assert watch.attributes() == first
    now[0] -= 4
    _e32(hub, 3)
    issue_id = "heating_input_lost_e"
    for minute in range(1, 31):  # the E32 accepts nothing more; Home Assistant sends every five minutes
        now[0] = 1000.0 + 60 * minute
        if minute % 5 == 0:
            link.send("{}")
            await hass.async_block_till_done()
        _e32(hub, 3 + 60 * minute)
        watch.check()
        issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
        assert (issue is not None) == (minute >= 15), minute
    assert resent == [1000.0 + 900, 1000.0 + 1800]  # at once, then every 15 minutes while it lasts
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "accepted no room values from Home Assistant for 15 min" in warnings[0]
    # rc.7 (R2-11): since when as a local time (the E32 last took one at 17:00:27 UTC, yesterday here: with the day),
    # and no cause while nothing was refused and every send worked: no "-" and no English error text.
    assert issue.translation_key == "heating_input_lost"
    assert issue.translation_placeholders == {"since": _since(WALL - timedelta(seconds=3)), "cause": ""}
    attributes = watch.attributes()
    assert attributes["state"] == "not_received" and attributes["e32_last_input"] == "2026-11-04T17:00:00+00:00"
    assert attributes["last_sent"] is not None and attributes["last_error"] is None
    diagnostics = watch.diagnostics()
    assert diagnostics["state"] == "not_received" and diagnostics["not_received_for_s"] == 900
    assert diagnostics["e32_input_age_s"] == 1803
    assert diagnostics["e32_ha"] == {"input_age_s": 1803, "broker_connected": True}
    # The E32 accepts again: the repair goes, the state is ok.
    now[0] += 30
    _e32(hub, 2)
    watch.check()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    assert watch.attributes()["state"] == "ok" and "accepts room values from Home Assistant again" in caplog.text


@pytest.mark.asyncio
async def test_no_repair_right_after_a_start_or_without_anything_to_send(hass, monkeypatch, caplog):
    """An E32 age from before Home Assistant started is not judged within 15 minutes, and an E32 that waits for
    nothing (no value to send) is not a problem; a never-accepting E32 (null age) counts from its uptime."""
    import logging
    from homeassistant.helpers import issue_registry as ir
    await ir.async_load(hass)
    now = [0.0]
    hub, link, watch, resent, _published = _watch(hass, monkeypatch, now)
    _e32(hub, 11582)  # three hours without input, as Home Assistant (re)starts
    for minute in range(14):
        now[0] = 60.0 * minute
        watch.check()
    assert resent == [] and watch.attributes()["state"] == "waiting"
    _e32(hub, 1)  # the first value after the start arrived
    watch.check()
    assert watch.attributes()["state"] == "ok"
    # Nothing to send (no plan entity has a value, nothing was sent): the age may grow.
    for minute in range(14, 60):
        now[0] = 60.0 * minute
        _e32(hub, 60 * (minute - 13), ha_entities=["climate.gone"])
        watch.check()
    assert resent == [] and watch.lost_since is None
    # A plan entity with a value that never arrives: lost, also without any send (a forwarder that stopped).
    hass.states.async_set("climate.gone", "heat", {"current_temperature": 20.1, "temperature": 20.5})
    watch.check()
    assert resent == [now[0]] and watch.attributes()["state"] == "not_received"
    # null: nothing accepted since the E32 started; its uptime is the age.
    now[0] += 60
    hub.heartbeat, hub.heartbeat_received = {"schema": 1, "uptime_s": 120}, now[0]
    _e32(hub, None)
    assert heating_link.e32_input_age(hub, now[0] + 30) == 150
    watch.check()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "heating_input_lost_e") is None  # 120 s: not lost
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


@pytest.mark.asyncio
async def test_contacts_and_presence_alone_never_raise_the_repair(hass, monkeypatch):
    """E32 rc.4 does not count contacts and presence in ha.input_age_s: an installation that sends only those
    (Bluetooth rooms, no energy inputs) must not look like a lost route."""
    from homeassistant.helpers import issue_registry as ir
    await ir.async_load(hass)
    now = [1000.0]
    hub, link, watch, resent, published = _watch(hass, monkeypatch, now)
    for minute in range(0, 40):
        now[0] = 1000.0 + 60 * minute
        if minute % 5 == 0:
            link.send('{"kind":"presence","home":true}', watched=False)
            await hass.async_block_till_done()
        _e32(hub, 60 * minute, ha_entities=[])
        watch.check()
    assert len(published) == 8 and link.attempted is None
    assert resent == [] and watch.lost_since is None
    assert ir.async_get(hass).async_get_issue(DOMAIN, "heating_input_lost_e") is None


@pytest.mark.asyncio
async def test_every_value_goes_where_the_e32_reports(hass, monkeypatch, caplog):
    """The comfort forwarder and the room forwarder share one route: the topic where the E32's telemetry
    arrives, also when the entry's own topic changes afterwards (one warning)."""
    import logging
    hass.states.async_set("climate.woonkamer", "heat", {"current_temperature": 20.4, "temperature": 20.5})
    hass.states.async_set("person.anna", "home")
    link = await Installation(hass, monkeypatch).start({"presence_entities": ["person.anna"]})
    state = hass.data[DOMAIN]["e"]
    assert state[heating_link.INPUT_LINK] is heating_link.heating_input_link(hass, link.entry)
    del state["v1_connection"]  # the shadow link stopped; the entry's prefix says another base
    link.entry.data["topic_prefix"] = "elsewhere"
    hass.states.async_set("person.anna", "not_home")
    hass.states.async_set("climate.woonkamer", "heat", {"current_temperature": 20.3, "temperature": 20.5})
    await hass.async_block_till_done()
    assert all(topic == TOPIC for topic, _payload in link.published)
    assert link.sent("presence")[-1] == {"kind": "presence", "home": True}  # still home during the away delay
    assert link.sent(entity="climate.woonkamer")[-1]["temperature"] == 20.3
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "elsewhere/v1/" in warnings[0]


@pytest.mark.asyncio
async def test_the_heat_request_sensor_and_the_diagnostics_show_the_route(hass, monkeypatch):
    """The ha_input attribute (live, not recorded) and the diagnostics block: last send, last error, E32 age."""
    from custom_components.open_thermostat import support_diagnostics
    hass.states.async_set("climate.woonkamer", "heat", {"current_temperature": 20.4, "temperature": 20.5})
    added = []
    link = Installation(hass, monkeypatch)
    real_setup = heating_link.async_setup_heating_link

    async def setup(hass, entry, add, **options):
        return await real_setup(hass, entry, lambda entities, **_k: added.extend(entities), **options)
    monkeypatch.setattr(heating_link, "async_setup_heating_link", setup)
    await link.start()
    sensor = next(e for e in added if isinstance(e, heating_link.HeatRequestSensor))
    assert {"ha_input", "rooms", "revision"} <= sensor._unrecorded_attributes  # every room once a minute: not recorded
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    attributes = sensor.extra_state_attributes["ha_input"]
    assert attributes["state"] == "ok" and attributes["e32_last_input"] is not None and attributes["last_sent"] is not None
    assert attributes["last_error"] is None and attributes["dropped"] == 0 and attributes["e32_last_rejected"] is None
    link.e32.status({**STATUS, "ha": {"input_age_s": 40, "broker_connected": True,
                                      "last_rejected": {"reason": "invalid_json", "age_s": 12}}})
    rejected = sensor.extra_state_attributes["ha_input"]["e32_last_rejected"]
    assert rejected["reason"] == "invalid_json" and rejected["at"].endswith(":00+00:00")
    block = support_diagnostics.inputs(hass, link.entry, link.hub)["heating_input"]
    assert block["state"] == "ok" and block["pending"] == 0 and block["last_sent"] is not None
    assert block["e32_ha"]["last_rejected"]["reason"] == "invalid_json"
    # The timers: the five-minute refreshes and the minute check of the route.
    assert {every for _action, every in link.timers} >= {timedelta(minutes=5), heating_link.INPUT_CHECK}


async def _lost(hass, monkeypatch, language="en"):
    """An E32 that took nothing for 15 minutes while Home Assistant sends: the repair is up."""
    from homeassistant.helpers import issue_registry as ir
    await ir.async_load(hass)
    hass.config.language = language
    now = [1000.0]
    hub, link, watch, resent, published = _watch(hass, monkeypatch, now)
    link.send("{}")
    await hass.async_block_till_done()
    return hub, link, watch, now, ir


async def _sending(hass, link, now, seconds):
    """``seconds`` after the start, Home Assistant sends a value (it sends every five minutes)."""
    now[0] = 1000.0 + seconds
    link.send("{}")
    await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.parametrize("language, cause", [
    ("en", "The E32 refused them: it does not know that room."),
    ("nl", "De E32 weigerde ze: hij kent die ruimte niet."),
    ("pl", "E32 je odrzucił: nie zna tego pomieszczenia.")])
async def test_the_repair_names_a_refusal_as_the_cause_in_the_home_assistant_language(hass, monkeypatch, language,
                                                                                     cause):
    hub, link, watch, now, ir = await _lost(hass, monkeypatch, language)
    await _sending(hass, link, now, 960)
    # The E32 refused a value 2 minutes ago, after it last took one (16 minutes ago).
    _e32(hub, 960, {"reason": "unknown_room", "age_s": 120})
    watch.check()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "heating_input_lost_e")
    assert issue.translation_placeholders["cause"] == cause
    # A reason this version does not know: as the E32 sent it. A refusal from before it last took one: no cause.
    watch.lost_since = None
    _e32(hub, 960, {"reason": "busy", "age_s": 120})
    watch.check()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "heating_input_lost_e").translation_placeholders["cause"].endswith(
        "busy.")
    watch.lost_since = None
    _e32(hub, 960, {"reason": "unknown_room", "age_s": 2000})
    watch.check()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "heating_input_lost_e").translation_placeholders["cause"] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("kind, cause", [("timeout", "De MQTT-broker neemt ze niet op tijd aan."),
                                         ("unreachable", "Home Assistant bereikt de MQTT-broker niet."),
                                         ("waiting", "Er wachten te veel berichten op de MQTT-broker.")])
async def test_the_repair_names_a_failing_send_by_its_kind(hass, monkeypatch, kind, cause):
    hub, link, watch, now, ir = await _lost(hass, monkeypatch, "nl")
    await _sending(hass, link, now, 960)
    link._failed("raw English from the MQTT client", dropped=kind == "waiting", kind=kind)
    assert watch.attributes()["last_error_kind"] == kind
    _e32(hub, 960)
    watch.check()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "heating_input_lost_e")
    assert issue.translation_placeholders["cause"] == cause
    assert "raw English" not in str(issue.translation_placeholders)


@pytest.mark.asyncio
async def test_the_repair_goes_when_the_e32_goes_silent(hass, monkeypatch):
    """The offline problem ("E32 not reporting") takes over; once heard again, the check judges afresh."""
    hub, link, watch, now, ir = await _lost(hass, monkeypatch)
    await _sending(hass, link, now, 960)
    _e32(hub, 960)
    watch.check()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "heating_input_lost_e") is not None
    hub.update(None)  # three missed heartbeats: the hub is not fresh
    watch.check()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "heating_input_lost_e") is None and watch.lost_since is None
    _e32(hub, 30)
    watch.check()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "heating_input_lost_e") is None
    assert watch.attributes()["state"] == "ok"
@pytest.mark.asyncio
async def test_a_restarted_or_returning_e32_gets_the_room_values_at_once(hass, monkeypatch):
    """R2-2 (1.0.0rc7): a restarted E32 has no room reading until Home Assistant sends one; it must not wait up to
    five minutes for the refresh (a tado-only room would ask no heat meanwhile)."""
    hass.states.async_set("climate.woonkamer", "heat", {"current_temperature": 20.4, "temperature": 20.5})
    hass.states.async_set("person.anna", "home")
    link = await Installation(hass, monkeypatch).start({"presence_entities": ["person.anna"]})
    link.e32.heartbeat(uptime=100)  # the thermostats' forwarder sends once on its first E32 message after its setup
    await link.hass.async_block_till_done()
    rooms, presence = len(link.sent(entity="climate.woonkamer")), len(link.sent("presence"))
    # A restart shorter than three heartbeats: only the uptime going down says so (hub.boots).
    link.e32.heartbeat(uptime=40)
    await link.hass.async_block_till_done()
    assert len(link.sent(entity="climate.woonkamer")) == rooms + 1
    assert len(link.sent("presence")) == presence + 1  # the contacts and presence too
    link.e32.heartbeat(uptime=100)  # the next heartbeat of the same run: nothing extra
    await link.hass.async_block_till_done()
    assert len(link.sent(entity="climate.woonkamer")) == rooms + 1
    # Offline (its last will, or a power cut), then back online with its retained state.
    link.e32.message("fw/availability", "offline")
    assert link.hub.status is None
    link.e32.message("fw/availability", "online")
    await link.hass.async_block_till_done()
    assert link.hub.fresh
    assert link.sent(entity="climate.woonkamer")[-1] == {"entity": "climate.woonkamer", "temperature": 20.4,
                                                         "target": 20.5}
    assert len(link.sent(entity="climate.woonkamer")) == rooms + 2


@pytest.mark.asyncio
async def test_a_source_that_froze_is_not_refreshed_as_fresh(hass, monkeypatch):
    """R2-3 (1.0.0rc7): an integration that keeps its last state instead of going unavailable. The five-minute
    refresh no longer sends a source silent for three hours, so the E32 ages it out and uses the next source; a
    setpoint helper is a setting and still goes; a new value goes at once; no "not accepted" repair for it."""
    status = {**STATUS, "ha_entities": ["climate.woonkamer", "sensor.woonkamer", "input_number.woonkamer"]}
    hours_ago = dt_util.utcnow().timestamp() - 4 * 3600
    hass.states.async_set("climate.woonkamer", "heat", {"current_temperature": 20.4, "temperature": 20.5},
                          timestamp=hours_ago)
    hass.states.async_set("sensor.woonkamer", "19.8", {"unit_of_measurement": "°C"}, timestamp=hours_ago)
    hass.states.async_set("input_number.woonkamer", "20.0", {"unit_of_measurement": "°C"}, timestamp=hours_ago)
    link = await Installation(hass, monkeypatch).start()
    link.e32.status(status)
    await hass.async_block_till_done()
    assert link.sent(entity="climate.woonkamer") == [] and link.sent(entity="sensor.woonkamer") == []
    assert link.sent(entity="input_number.woonkamer")[-1]["target"] == 20.0
    room_refresh = link.refreshes(heating_link)[0]
    await link.run_timer(room_refresh)
    assert link.sent(entity="climate.woonkamer") == [] and link.sent(entity="sensor.woonkamer") == []
    # A state that reports again (polled: the same value, a new last_reported) is fresh again.
    hass.states.async_set("sensor.woonkamer", "19.8", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    await link.run_timer(room_refresh)
    assert link.sent(entity="sensor.woonkamer")[-1]["temperature"] == 19.8
    assert link.sent(entity="climate.woonkamer") == []
    # Only frozen sources to send: the E32 accepting nothing is not Home Assistant's values getting lost.
    watch = link.hub.input_watch
    hass.states.async_set("sensor.woonkamer", "19.8", {"unit_of_measurement": "°C"}, timestamp=hours_ago)
    hass.states.async_remove("input_number.woonkamer")
    watch.link.attempted = None
    assert watch._expected(watch.clock()) is False
