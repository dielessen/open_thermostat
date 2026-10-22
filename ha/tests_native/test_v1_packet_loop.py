"""Opt-in real HA MQTT client + localhost Mosquitto + actual firmware core.

No production configuration, routes or sensors. Broker must be the dedicated
fixture with fw-test/ha-test users and test_therm namespace. The short-lived FW
process is a test peer, NOT the ESP32 socket/radio/flash implementation.
"""
import asyncio
import json
import os
import socket
from types import MappingProxyType

import pytest
from homeassistant.components.mqtt.client import MQTT
from homeassistant.components.mqtt.models import MqttData, DATA_MQTT, DATA_MQTT_AVAILABLE
from homeassistant.config_entries import ConfigEntry

from custom_components.open_thermostat.v1_mqtt import NativeShadowConnection
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from test_v1_native import room, entry, source_profile, physical_state
from test_v1_wire_interop import RUNNER

REAL_CONNECT = socket.socket.connect


@pytest.mark.asyncio
async def test_real_localhost_packet_loop_and_firmware_lwt(hass, monkeypatch):
    setting = os.environ.get("OPENTHERMOSTAT_TEST_MQTT_PORT")
    if not setting:
        pytest.skip("opt-in ephemeral localhost fixture broker not supplied")
    port = int(setting)
    assert 1024 <= port <= 65535

    def loopback_only(sock, address):
        if address != ("127.0.0.1", port):
            raise AssertionError("packet test attempted a non-fixture connection")
        return REAL_CONNECT(sock, address)
    monkeypatch.setattr(socket.socket, "connect", loopback_only)

    conf = {"broker": "127.0.0.1", "port": port, "username": "ha-test",
            "password": "fixture-only", "protocol": "5", "discovery": False,
            "client_id": "opth-ha-packet-test", "birth_message": {}, "will_message": {}}
    broker_entry = ConfigEntry(domain="mqtt", title="isolated packet test", version=1,
        minor_version=1, data=conf, options={}, source="user", unique_id="packet-fixture",
        discovery_keys=MappingProxyType({}), subentries_data=[])
    hass.config_entries._entries[broker_entry.entry_id] = broker_entry
    native = MQTT(hass, broker_entry, conf)
    mqtt_data = MqttData(client=native, config=[])
    hass.data[DATA_MQTT] = mqtt_data
    available = hass.data[DATA_MQTT_AVAILABLE] = hass.loop.create_future()
    process = None
    firmware = None
    reactor = None
    fw_network = None
    runtime = None
    connection = None
    queue = asyncio.Queue(maxsize=64)
    subscribed = asyncio.Event()
    changed = asyncio.Event()
    trace = []
    base = "test_therm/v1/"
    loop = asyncio.get_running_loop()

    async def wait_for(predicate):
        async with asyncio.timeout(12):
            while not predicate():
                changed.clear()
                await changed.wait()

    try:
        # These are real HA/Paho clients, not patched MQTT publish/subscribe.
        await native.async_start(mqtt_data)
        await hass.async_start()
        await native.async_connect(available)
        assert await asyncio.wait_for(available, 5)

        import paho.mqtt.client as paho
        firmware = paho.Client(paho.CallbackAPIVersion.VERSION2,
            client_id="opth-fw-packet-test", reconnect_on_failure=False)
        firmware.username_pw_set("fw-test", "fixture-only")
        firmware.will_set(base + "fw/availability", "offline", qos=0, retain=False)

        def on_connect(client, userdata, flags, reason, properties):
            assert not reason.is_failure
            client.subscribe(base + "ha/#", qos=0)

        def on_subscribe(client, userdata, mid, reasons, properties):
            loop.call_soon_threadsafe(subscribed.set)

        def on_message(client, userdata, message):
            suffix = message.topic.removeprefix(base)
            loop.call_soon_threadsafe(queue.put_nowait, (suffix, message.payload.decode()))

        firmware.on_connect = on_connect
        firmware.on_subscribe = on_subscribe
        firmware.on_message = on_message
        await asyncio.to_thread(firmware.connect, "127.0.0.1", port, 10)

        async def pump_fw_socket():
            # Official external-loop API: no portability socketpair's second
            # TCP listener; every connect remains the declared broker only.
            while True:
                for action in (firmware.loop_read, firmware.loop_write, firmware.loop_misc):
                    if action() != paho.MQTT_ERR_SUCCESS:
                        return
                await asyncio.sleep(0.01)

        fw_network = asyncio.create_task(pump_fw_socket())
        await asyncio.wait_for(subscribed.wait(), 5)

        binding = room(hass)
        parent = entry(hass, enabled=True, room=binding)
        hass.config_entries.async_update_entry(parent, data={**parent.data, "topic_prefix": "test_therm"})
        runtime = ShadowRuntime(hass, parent, [binding])
        runtime.set_report_profile(binding.room_id, source_profile)  # synthetic test reports only
        runtime.add_listener(changed.set)
        await runtime.async_start()
        connection = NativeShadowConnection(runtime)
        await connection.async_start()
        process = await asyncio.create_subprocess_exec(str(RUNNER),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        started = loop.time()

        async def event(op, **extra):
            packet = {"op": op, "now": int((loop.time() - started) * 1000),
                      "utc": 1792368000, **extra}
            process.stdin.write((json.dumps(packet) + "\n").encode())
            await process.stdin.drain()
            while True:
                line = await asyncio.wait_for(process.stdout.readline(), 5)
                assert line, "actual firmware test peer exited"
                result = json.loads(line)
                if result.get("event_done"):
                    return
                trace.append(result)
                firmware.publish(base + result["topic"], json.dumps(result["payload"], separators=(",", ":")), qos=0, retain=False)

        async def react():
            await event("connect")
            firmware.publish(base + "fw/availability", "online", qos=0, retain=False)
            while True:
                try:
                    topic, raw = await asyncio.wait_for(queue.get(), 0.1)
                    await event("receive", topic=topic, raw=raw)
                    queue.task_done()
                except TimeoutError:
                    await event("tick")

        reactor = asyncio.create_task(react())
        await wait_for(lambda: connection.client.ready)
        assert native.connected
        physical_state(hass, binding, key="packet-fixture-1", value="19")
        await wait_for(lambda: binding.room_id in runtime.decisions and runtime.decisions[binding.room_id].demand)
        await runtime.async_set_temperature(binding.room_id, 22)
        await wait_for(lambda: runtime.decisions[binding.room_id].target_centi_c == 2200)
        assert any(p["topic"] == "fw/config_result" and p["payload"]["status"] == "applied" for p in trace)
        assert all(p["payload"].get("boiler_output_enabled") is False and
                   p["payload"].get("actuator_output_enabled") is False
                   for p in trace if p["topic"] == "fw/state/zones")

        # Hard-close only the fixture FW socket: actual broker LWT must withdraw
        # the HA session even while HA's own MQTT connection stays healthy.
        firmware.socket().shutdown(socket.SHUT_RDWR)
        await wait_for(lambda: not connection.client.ready and not runtime.decisions)
        assert native.connected
        assert connection.client.error == "firmware_offline"
    finally:
        if reactor:
            reactor.cancel()
            await asyncio.gather(reactor, return_exceptions=True)
        if runtime:
            await runtime.async_stop()
        if process:
            process.stdin.close()
            await asyncio.wait_for(process.wait(), 5)
        if firmware:
            if fw_network:
                fw_network.cancel()
                await asyncio.gather(fw_network, return_exceptions=True)
            firmware.disconnect()
        if hasattr(native, "_mqttc"):
            await native.async_disconnect()
        native.cleanup()
