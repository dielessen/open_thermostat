'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const Producer = require('../../integrations/zigbee2mqtt/original-temperature.cjs');
const ieee = '0x00158d0000000001';
class Selected extends Producer {
    get bindings() { return [{ieee, model: 'WSDCGQ11LM'}]; }
}
function frame(raw = 2100) {
    return {device: {ieeeAddr: ieee, definition: {model: 'WSDCGQ11LM'},
        zh: {modelID: 'lumi.weather'}, interviewed: true}, endpoint: {ID: 1},
    cluster: 'msTemperatureMeasurement', type: 'attributeReport',
    meta: {zclTransactionSequenceNumber: 19}, data: {measuredValue: raw}};
}
function setup(Type = Selected) {
    const emitter = new EventEmitter();
    const owned = new Map();
    const eventBus = {
        onDeviceMessage(owner, listener) { owned.set(owner, listener); emitter.on('deviceMessage', listener); },
        removeListeners(owner) { if (owned.has(owner)) emitter.off('deviceMessage', owned.get(owner)); owned.delete(owner); },
    };
    const calls = [];
    const mqtt = {isConnected: () => true, publish(topic, payload, options) {
        calls.push({topic, payload: JSON.parse(payload), options});
    }};
    // Any accidental cache/state/command access fails the actual test.
    const forbidden = new Proxy({}, {get() { throw Error('Unexpected control/cache access'); }});
    return {producer: new Type(forbidden, mqtt, forbidden, forbidden, eventBus),
        emitter, calls, mqtt, owned};
}
test('default installation observes no devices and sends nothing', async () => {
    const f = setup(Producer); await f.producer.start();
    f.emitter.emit('deviceMessage', frame());
    assert.equal(f.calls.length, 0); await f.producer.stop();
});
test('original raw property survives concurrent cache merge and unrelated last_seen', async () => {
    const f = setup(); await f.producer.start();
    // The normal receive handler/cache can run before this listener. The raw
    // deviceMessage remains the source; publishEntityState is never consulted.
    const cache = {temperature: 99, last_seen: Date.now()};
    f.emitter.prependListener('deviceMessage', () => { cache.temperature = 88; });
    f.emitter.emit('deviceMessage', frame(2137));
    assert.equal(f.calls.length, 1);
    const {topic, payload: p, options} = f.calls[0];
    assert.equal(topic, 'bridge/openthermostat/original_temperature');
    assert.equal(p.value_centi_c, 2137); assert.equal(p.raw_value, 2137);
    assert.equal(p.message_kind, 'attributeReport'); assert.equal(p.endpoint, 1);
    assert.equal(p.zcl_transaction, 19); assert.equal(p.sequence, 1);
    assert.equal(p.sampled_at_unix_ms, null);
    assert.equal(p.acquisition_age_verified, false); assert.equal(p.control_qualified, false);
    assert.deepEqual(options.clientOptions, {retain: false, qos: 0});
    assert.equal(options.skipLog, true); assert.equal(cache.temperature, 88);
    assert(Number.isSafeInteger(p.received_at_unix_ms));
    assert(Buffer.byteLength(JSON.stringify(p)) < 1024);
    await f.producer.stop();
});
test('readResponse stays distinguishable and never becomes acquisition proof', async () => {
    const f = setup(); await f.producer.start(); const msg = frame(-1200);
    msg.type = 'readResponse'; f.emitter.emit('deviceMessage', msg);
    assert.equal(f.calls[0].payload.message_kind, 'readResponse');
    assert.equal(f.calls[0].payload.control_qualified, false); await f.producer.stop();
});
test('diagnostic sensor, foreign identity, cache objects and unrelated messages cannot produce room reports', async () => {
    const f = setup(); await f.producer.start();
    const mutations = [
        m => { m.device.definition.model = 'RTCGQ11LM'; m.device.zh.modelID = 'lumi.sensor_motion.aq2'; },
        m => { m.device.zh.modelID = 'other'; },
        m => { m.device.ieeeAddr = '0x00158d0000000002'; },
        m => { m.device.interviewed = false; },
        m => { m.type = 'write'; }, m => { m.type = 'read'; },
        m => { m.type = 'stateChange'; }, m => { m.cluster = 'genBasic'; },
        m => { m.data = {temperature: 21, last_seen: Date.now()}; },
        m => { m.data = Object.create({measuredValue: 2100}); },
        m => { m.endpoint.ID = 0; }, m => { m.endpoint.ID = 241; },
        m => { m.endpoint.ID = '1'; }, m => { delete m.device; },
    ];
    for (const mutate of mutations) { const m = frame(); mutate(m); f.emitter.emit('deviceMessage', m); }
    assert.equal(f.calls.length, 0); await f.producer.stop();
});
test('invalid raw values are rejected, zero and valid boundary values preserved', async () => {
    const f = setup(); await f.producer.start();
    for (const raw of [null, true, '2100', 21.5, NaN, Infinity, -6500, 6500, -32768, 32767]) {
        f.emitter.emit('deviceMessage', frame(raw));
    }
    assert.equal(f.calls.length, 0);
    for (const raw of [0, -6499, 6499]) {
        f.emitter.emit('deviceMessage', frame(raw)); await f.producer.pending;
    }
    assert.deepEqual(f.calls.map(c => c.payload.value_centi_c), [0, -6499, 6499]);
    await f.producer.stop();
});
test('offline and busy reports are dropped without later backlog or replay', async () => {
    const f = setup(); await f.producer.start();
    f.mqtt.isConnected = () => false; f.emitter.emit('deviceMessage', frame(1000));
    assert.equal(f.calls.length, 0);
    f.mqtt.isConnected = () => true;
    let complete; f.mqtt.publish = (_t, p) => { f.calls.push(JSON.parse(p)); return new Promise(r => { complete = r; }); };
    f.emitter.emit('deviceMessage', frame(2000));
    for (let i = 0; i < 100; i++) f.emitter.emit('deviceMessage', frame(3000));
    assert.equal(f.calls.length, 1); assert.equal(f.calls[0].dropped_reports, 1);
    complete(); await f.producer.pending;
    assert.equal(f.calls.length, 1); // Nothing buffered.
    f.mqtt.publish = (_t, p) => { f.calls.push(JSON.parse(p)); };
    f.emitter.emit('deviceMessage', frame(4000));
    assert.equal(f.calls[1].sequence, 2); assert.equal(f.calls[1].dropped_reports, 101);
    await f.producer.stop();
});
test('stop drains owned publication, removes listener and restart gets new producer run', async () => {
    const f = setup(); await f.producer.start(); await f.producer.start();
    assert.equal(f.owned.size, 1);
    f.emitter.emit('deviceMessage', frame()); const first = f.calls[0].payload;
    await f.producer.stop(); assert.equal(f.owned.size, 0);
    f.emitter.emit('deviceMessage', frame()); assert.equal(f.calls.length, 1);
    await f.producer.start(); f.emitter.emit('deviceMessage', frame());
    assert.notEqual(f.calls[1].payload.producer_run_id, first.producer_run_id);
    assert.equal(f.calls[1].payload.sequence, 1); await f.producer.stop();
});
test('SDK rejection and synchronous failure do not leak an unhandled promise or retry', async () => {
    const f = setup(); await f.producer.start();
    f.mqtt.publish = () => { throw Error('private broker error'); };
    f.emitter.emit('deviceMessage', frame()); assert.equal(f.producer.dropped, 1);
    f.mqtt.publish = () => Promise.reject(Error('private broker error'));
    f.emitter.emit('deviceMessage', frame()); await f.producer.pending;
    assert.equal(f.producer.dropped, 2); assert.equal(f.calls.length, 0);
    await f.producer.stop();
});
test('restart waits for stopping owner and old cleanup cannot remove its listener', async () => {
    const f = setup(); await f.producer.start(); let complete;
    f.mqtt.publish = () => new Promise(resolve => { complete = resolve; });
    f.emitter.emit('deviceMessage', frame());
    const oldRun = f.producer.run;
    const stopping = f.producer.stop();
    const stoppingAgain = f.producer.stop();
    const restarting = f.producer.start();
    assert.equal(f.owned.size, 0);
    complete(); await Promise.all([stopping, stoppingAgain, restarting]);
    assert.equal(f.owned.size, 1); assert.notEqual(f.producer.run, oldRun);
    assert.equal(f.producer.active, true); assert.equal(f.producer.devices.size, 1);
    await f.producer.stop(); await f.producer.stop();
});
test('transaction wrap, repeats and absent metadata remain reception events, never sample IDs', async () => {
    const f = setup(); await f.producer.start();
    for (const transaction of [255, 0, 0, undefined, -1, 256, '1']) {
        const m = frame(); m.meta.zclTransactionSequenceNumber = transaction;
        f.emitter.emit('deviceMessage', m); await f.producer.pending;
    }
    assert.deepEqual(f.calls.map(c => c.payload.zcl_transaction), [255, 0, 0, null, null, null, null]);
    assert.deepEqual(f.calls.map(c => c.payload.sequence), [1, 2, 3, 4, 5, 6, 7]);
    assert(f.calls.every(c => !c.payload.control_qualified && c.payload.sampled_at_unix_ms === null));
    await f.producer.stop();
});
test('invalid allowlist is rejected before registering a listener', async () => {
    for (const bindings of [[{ieee: '../secret', model: 'WSDCGQ11LM'}],
        [{ieee, model: 'RTCGQ11LM'}], [{ieee, model: 'WSDCGQ11LM'}, {ieee, model: 'WSDCGQ11LM'}]]) {
        class Invalid extends Producer { get bindings() { return bindings; } }
        const f = setup(Invalid);
        await assert.rejects(f.producer.start(), /Invalid original temperature binding/);
        assert.equal(f.owned.size, 0); assert.equal(f.calls.length, 0);
    }
});

test('failed listener registration releases owner and permits a clean restart', async () => {
    for (const attachFirst of [false, true]) {
        const f = setup();
        const bus = f.producer.eventBus;
        const register = bus.onDeviceMessage.bind(bus);
        const failure = Error('registration failed');
        bus.onDeviceMessage = (owner, listener) => {
            if (attachFirst) register(owner, listener);
            throw failure;
        };
        await assert.rejects(f.producer.start(), error => error === failure);
        assert.equal(f.producer.active, false);
        assert.equal(f.producer.run, null);
        assert.equal(f.producer.devices.size, 0);
        assert.equal(f.emitter.listenerCount('deviceMessage'), 0);
        f.emitter.emit('deviceMessage', frame());
        assert.equal(f.calls.length, 0);
        bus.onDeviceMessage = register;
        await f.producer.start();
        assert.equal(f.emitter.listenerCount('deviceMessage'), 1);
        f.emitter.emit('deviceMessage', frame());
        assert.equal(f.calls.length, 1);
        assert.equal(f.calls[0].payload.sequence, 1);
        await f.producer.stop();
        assert.equal(f.emitter.listenerCount('deviceMessage'), 0);
    }
});

test('registration cleanup failure preserves both errors and disables retained callback', async () => {
    const f = setup();
    const bus = f.producer.eventBus;
    const register = bus.onDeviceMessage.bind(bus);
    const remove = bus.removeListeners.bind(bus);
    const failure = Error('registration failed');
    const cleanupFailure = Error('cleanup failed');
    bus.onDeviceMessage = (owner, listener) => { register(owner, listener); throw failure; };
    bus.removeListeners = () => { throw cleanupFailure; };
    await assert.rejects(f.producer.start(), error => {
        assert(error instanceof AggregateError);
        assert.deepEqual(error.errors, [failure, cleanupFailure]);
        return true;
    });
    assert.equal(f.producer.active, false);
    assert.equal(f.producer.run, null);
    assert.equal(f.producer.devices.size, 0);
    f.emitter.emit('deviceMessage', frame());
    assert.equal(f.calls.length, 0);
    // The SDK failed cleanup: do not claim that the listener disappeared.
    assert.equal(f.emitter.listenerCount('deviceMessage'), 1);
    // Restart must first retry cleanup, never add a second listener.
    await assert.rejects(f.producer.start(), error => error === cleanupFailure);
    assert.equal(f.emitter.listenerCount('deviceMessage'), 1);
    bus.removeListeners = remove;
    bus.onDeviceMessage = register;
    await f.producer.start();
    assert.equal(f.emitter.listenerCount('deviceMessage'), 1);
    f.emitter.emit('deviceMessage', frame());
    assert.equal(f.calls.length, 1);
    await f.producer.stop();
    assert.equal(f.emitter.listenerCount('deviceMessage'), 0);
});

test('failed stop cleanup still drains publication and fences a concurrent restart', async () => {
    for (const detachFirst of [false, true]) {
        const f = setup();
        await f.producer.start();
        const oldRun = f.producer.run;
        const bus = f.producer.eventBus;
        const remove = bus.removeListeners.bind(bus);
        const failure = Error('stop cleanup failed');
        bus.removeListeners = owner => {
            if (detachFirst) remove(owner);
            throw failure;
        };
        let complete;
        f.mqtt.publish = () => new Promise(resolve => { complete = resolve; });
        f.emitter.emit('deviceMessage', frame());
        let settled = false;
        const stopping = f.producer.stop();
        const stopped = stopping.then(() => { settled = true; }, error => {
            settled = true;
            assert.equal(error, failure);
        });
        const restarting = f.producer.start();
        const restarted = assert.rejects(restarting, error => error === failure);
        await Promise.resolve();
        assert.equal(settled, false);
        assert.equal(f.producer.active, false);
        assert.equal(f.producer.run, oldRun);
        assert.equal(f.producer.sequence, 1);
        f.emitter.emit('deviceMessage', frame());
        assert.equal(f.producer.sequence, 1);
        complete();
        await Promise.all([stopped, restarted]);
        assert.equal(f.producer.run, null);
        assert.equal(f.producer.devices.size, 0);
        assert.equal(f.producer.pending, null);
        assert.equal(f.producer.cleanupRequired, true);
        await assert.rejects(f.producer.start(), error => error === failure);
        bus.removeListeners = remove;
        await f.producer.stop();
        assert.equal(f.emitter.listenerCount('deviceMessage'), 0);
        await f.producer.start();
        assert.notEqual(f.producer.run, oldRun);
        assert.equal(f.emitter.listenerCount('deviceMessage'), 1);
        assert.equal(f.producer.sequence, 0);
        f.mqtt.publish = () => {};
        f.emitter.emit('deviceMessage', frame());
        assert.equal(f.producer.sequence, 1);
        await f.producer.stop();
    }
});

test('stop cleanup failure without publication is shared and remains recoverable', async () => {
    const f = setup();
    await f.producer.start();
    const bus = f.producer.eventBus;
    const remove = bus.removeListeners.bind(bus);
    const failure = Error('cleanup unavailable');
    let attempts = 0;
    bus.removeListeners = () => { attempts++; throw failure; };
    const results = await Promise.allSettled([
        f.producer.stop(), f.producer.stop(), f.producer.start(),
    ]);
    assert.equal(attempts, 1);
    assert(results.every(result => result.status === 'rejected' && result.reason === failure));
    assert.equal(f.producer.run, null);
    assert.equal(f.producer.devices.size, 0);
    assert.equal(f.producer.active, false);
    f.emitter.emit('deviceMessage', frame());
    assert.equal(f.calls.length, 0);
    bus.removeListeners = remove;
    await f.producer.start();
    assert.equal(f.emitter.listenerCount('deviceMessage'), 1);
    f.emitter.emit('deviceMessage', frame());
    assert.equal(f.calls.length, 1);
    await f.producer.stop();
});

test('reentrant reception during SDK publish cannot exceed one outstanding publication', async () => {
    const f = setup();
    await f.producer.start();
    let calls = 0, complete;
    f.mqtt.publish = () => {
        calls++;
        if (calls === 1) f.emitter.emit('deviceMessage', frame());
        return new Promise(resolve => { complete = resolve; });
    };
    f.emitter.emit('deviceMessage', frame());
    assert.equal(calls, 1);
    assert.equal(f.producer.sequence, 1);
    assert.equal(f.producer.dropped, 1);
    const pending = f.producer.pending;
    complete(); await pending;
    assert.equal(f.producer.pending, null);
    assert.equal(calls, 1);
    await f.producer.stop();
});

test('stop inside SDK publish drains that same publication before a fresh owner starts', async () => {
    for (const rejected of [false, true]) {
        const f = setup();
        await f.producer.start();
        const oldRun = f.producer.run;
        let complete, stopping, restarting, settled = false;
        f.mqtt.publish = () => {
            stopping = f.producer.stop().then(() => { settled = true; });
            restarting = f.producer.start();
            return new Promise((resolve, reject) => {
                complete = () => rejected ? reject(Error('SDK failure')) : resolve();
            });
        };
        f.emitter.emit('deviceMessage', frame());
        await Promise.resolve();
        await Promise.resolve();
        assert.equal(settled, false);
        assert.equal(f.producer.run, oldRun);
        assert.equal(f.producer.active, false);
        complete();
        await Promise.all([stopping, restarting]);
        assert.notEqual(f.producer.run, oldRun);
        assert.equal(f.producer.sequence, 0);
        assert.equal(f.producer.dropped, 0);
        assert.equal(f.producer.pending, null);
        assert.equal(f.emitter.listenerCount('deviceMessage'), 1);
        await f.producer.stop();
    }
});
