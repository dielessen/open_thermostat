'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const Producer = require('../../integrations/zigbee2mqtt/original-tv02.cjs');
const {decodeMessage} = Producer;
const ieee = '0x00158d0000000002';
const binding = {ieee, model: 'TV02-Zigbee', manufacturer: '_TZE200_hue3yfsn', endpoint: 1};
class Selected extends Producer { get bindings() { return [binding]; } }
const dp = (id, datatype, hex) => ({dp:id, datatype, data:Buffer.from(hex, 'hex')});
function frame(rows = [dp(16,2,'000000d7')]) {
    return {device:{ieeeAddr:ieee, definition:{model:'TV02-Zigbee'}, interviewed:true,
        zh:{modelID:'TS0601', manufacturerName:binding.manufacturer}},
    endpoint:{ID:1}, cluster:'manuSpecificTuya', type:'commandDataReport',
    data:{seq:65535, dpValues:rows}, meta:{zclTransactionSequenceNumber:255}};
}
function fixture(Type=Selected) {
    const emitter=new EventEmitter(), listeners=new Map(), calls=[];
    const eventBus={onDeviceMessage(owner,fn){listeners.set(owner,fn);emitter.on('deviceMessage',fn);},
        removeListeners(owner){if(listeners.has(owner))emitter.off('deviceMessage',listeners.get(owner));listeners.delete(owner);}};
    const mqtt={isConnected:()=>true,publish(topic,payload,options){calls.push({topic,payload:JSON.parse(payload),options});}};
    const forbidden=new Proxy({}, {get(){throw Error('cache/control access');}});
    return {producer:new Type(forbidden,mqtt,forbidden,forbidden,eventBus),emitter,mqtt,calls,listeners};
}

test('golden original datapoints preserve raw bytes and direct property meaning',()=>{
    assert.deepEqual(decodeMessage(frame([dp(16,2,'000000d7'),dp(24,2,'000000c6'),
        dp(2,4,'01'),dp(107,1,'00'),dp(10,1,'01')])),[
        {dp:16,datatype:2,raw_hex:'000000d7',property:'target_centi_c',value:2150},
        {dp:24,datatype:2,raw_hex:'000000c6',property:'local_temperature_centi_c',value:1980},
        {dp:2,datatype:4,raw_hex:'01',property:'preset',value:'manual'},
        {dp:107,datatype:1,raw_hex:'00',property:'heating_stop',value:false},
        {dp:10,datatype:1,raw_hex:'01',property:'frost_protection',value:true},
    ]);
});
test('only properties in this original frame are present; no invented system mode or valve position',()=>{
    const fields=decodeMessage(frame([dp(16,2,'000000d7')]));
    assert.equal(fields.length,1);assert.equal(fields[0].property,'target_centi_c');
    assert(!JSON.stringify(fields).includes('system_mode'));
    assert(!JSON.stringify(fields).includes('position'));
    for(const [raw,expected] of [['00','auto'],['01','manual'],['02','holiday'],['03','holiday']])
        assert.equal(decodeMessage(frame([dp(2,4,raw)]))[0].value,expected);
});
test('target boundaries, half-degree steps, zero temperature and unknown signed encoding',()=>{
    for(const [hex,value] of [['00000032',500],['0000012c',3000]])
        assert.equal(decodeMessage(frame([dp(16,2,hex)]))[0].value,value);
    for(const hex of ['00000000','00000031','0000012d','000000d6','ffffffff'])
        assert.equal(decodeMessage(frame([dp(16,2,hex)])),null);
    assert.equal(decodeMessage(frame([dp(24,2,'00000000')]))[0].value,0);
    assert.equal(decodeMessage(frame([dp(24,2,'00000258')]))[0].value,6000);
    assert.equal(decodeMessage(frame([dp(24,2,'ffffffff')])),null);
});
test('wrong datatype/length, invalid enums/booleans and duplicate datapoints reject whole report',()=>{
    for(const row of [dp(16,4,'d7'),dp(16,2,'0000d7'),dp(24,2,'00000259'),dp(2,4,'04'),
        dp(2,1,'01'),dp(107,4,'00'),dp(107,1,'02'),dp(10,1,'0001')])
        assert.equal(decodeMessage(frame([dp(16,2,'000000d7'),row])),null);
    assert.equal(decodeMessage(frame([dp(16,2,'000000d7'),dp(16,2,'000000dc')])),null);
    assert.equal(decodeMessage(frame([dp(45,2,'00000000'),dp(45,2,'00000000')])),null);
});
test('unknown fields are omitted with strict total byte/row bounds',()=>{
    assert.equal(decodeMessage(frame([dp(45,2,'00000000')])),null);
    assert.equal(decodeMessage(frame([dp(45,2,'00000000'),dp(16,2,'000000d7')])).length,1);
    assert.equal(decodeMessage(frame(Array.from({length:17},(_,i)=>dp(i,0,'00')))),null);
    assert.equal(decodeMessage(frame([dp(45,0,'00'.repeat(65)),dp(16,2,'000000d7')])),null);
    assert.equal(decodeMessage(frame([dp(45,0,'00'.repeat(64)),dp(46,0,'00'.repeat(64)),dp(16,2,'000000d7')])),null);
    const row=dp(16,2,'000000d7');row.data=[0,0,0,215];assert.equal(decodeMessage(frame([row])),null);
});
test('only reviewed TV02 fingerprints and genuine inbound command kinds are accepted',()=>{
    for(const type of ['commandDataReport','commandDataResponse','commandActiveStatusReport','commandActiveStatusReportAlt']){
        const m=frame();m.type=type;assert(decodeMessage(m));
    }
    for(const mutate of [m=>m.type='commandDataRequest',m=>m.type='stateChange',m=>m.cluster='genBasic',
        m=>m.device.definition.model='TS0601_thermostat_3',m=>m.device.zh.manufacturerName='_TZE200_unknown',
        m=>m.device.zh.modelID='OTHER',m=>m.device.interviewed=false,m=>m.endpoint.ID=0,
        m=>m.data={current_heating_setpoint:21.5},m=>m.data.dpValues=[]]){
        const m=frame();mutate(m);assert.equal(decodeMessage(m),null);
    }
    const m=frame();m.device.zh.manufacturerName='_TZE200_lllliz3p';assert(decodeMessage(m));
});
test('default allowlist is empty; selected model/manufacturer/endpoint must all match',async()=>{
    const f=fixture(Producer);await f.producer.start();f.emitter.emit('deviceMessage',frame());
    assert.equal(f.calls.length,0);await f.producer.stop();
    const g=fixture();await g.producer.start();
    for(const mutate of [m=>m.device.ieeeAddr='0x00158d0000000003',m=>m.endpoint.ID=2,
        m=>m.device.zh.manufacturerName='_TZE200_lllliz3p']){
        const m=frame();mutate(m);g.emitter.emit('deviceMessage',m);
    }
    assert.equal(g.calls.length,0);await g.producer.stop();
});
test('producer preserves message provenance without cache read or echo/readiness qualification',async()=>{
    const f=fixture();await f.producer.start();f.emitter.emit('deviceMessage',frame());
    assert.equal(f.calls.length,1);const {topic,payload:p,options}=f.calls[0];
    assert.equal(topic,'bridge/openthermostat/original_tv02');
    assert.equal(p.fields[0].value,2150);assert.equal(p.tuya_sequence,65535);assert.equal(p.zcl_transaction,255);
    assert.equal(p.command_correlated,false);assert.equal(p.valve_ready,false);assert.equal(p.control_qualified,false);
    assert.equal(p.sampled_at_unix_ms,null);assert.equal(p.sequence,1);
    assert.deepEqual(options.clientOptions,{retain:false,qos:0});assert.equal(options.skipLog,true);
    assert(Buffer.byteLength(JSON.stringify(p))<2048);await f.producer.stop();
});
test('busy/offline events do not create a backlog or get replayed after recovery',async()=>{
    const f=fixture();await f.producer.start();f.mqtt.isConnected=()=>false;
    f.emitter.emit('deviceMessage',frame());assert.equal(f.calls.length,0);
    f.mqtt.isConnected=()=>true;let complete;
    f.mqtt.publish=(_t,p)=>{f.calls.push(JSON.parse(p));return new Promise(r=>complete=r);};
    f.emitter.emit('deviceMessage',frame());
    for(let i=0;i<100;i++)f.emitter.emit('deviceMessage',frame());
    assert.equal(f.calls.length,1);complete();await f.producer.pending;
    assert.equal(f.calls.length,1);assert.equal(f.producer.dropped,101);await f.producer.stop();
});
test('stop and concurrent restart cannot mix producer owners or retain listeners',async()=>{
    const f=fixture();await f.producer.start();await f.producer.start();assert.equal(f.listeners.size,1);
    let complete;f.mqtt.publish=()=>new Promise(r=>complete=r);f.emitter.emit('deviceMessage',frame());
    const old=f.producer.run,stopping=f.producer.stop(),restart=f.producer.start();
    assert.equal(f.listeners.size,0);complete();await Promise.all([stopping,restart]);
    assert.notEqual(f.producer.run,old);assert.equal(f.listeners.size,1);
    await f.producer.stop();await f.producer.stop();assert.equal(f.listeners.size,0);
});
test('SDK failures are observed locally, not retried or promoted to successful echo',async()=>{
    const f=fixture();await f.producer.start();
    f.mqtt.publish=()=>{throw Error('private broker error');};f.emitter.emit('deviceMessage',frame());
    f.mqtt.publish=()=>Promise.reject(Error('private broker error'));f.emitter.emit('deviceMessage',frame());
    await f.producer.pending;assert.equal(f.producer.dropped,2);assert.equal(f.calls.length,0);await f.producer.stop();
});
test('full supported report stays bounded and protocol sequence wrap is never an echo ID',async()=>{
    const f=fixture();await f.producer.start();
    for(const sequence of [65535,0,0,undefined]){
        const m=frame([dp(16,2,'0000012c'),dp(24,2,'00000258'),dp(2,4,'03'),dp(107,1,'01'),dp(10,1,'01')]);
        m.data.seq=sequence;f.emitter.emit('deviceMessage',m);await f.producer.pending;
    }
    assert.deepEqual(f.calls.map(c=>c.payload.tuya_sequence),[65535,0,0,null]);
    assert.deepEqual(f.calls.map(c=>c.payload.sequence),[1,2,3,4]);
    assert(f.calls.every(c=>c.payload.fields.length===5&&Buffer.byteLength(JSON.stringify(c.payload))<=2048));
    assert(f.calls.every(c=>c.payload.command_correlated===false&&c.payload.valve_ready===false));
    await f.producer.stop();
});
test('invalid or duplicate binding cannot register any producer listener',async()=>{
    for(const bindings of [[{...binding,manufacturer:'_TZE200_unknown'}],[{...binding,endpoint:0}],
        [{...binding,model:'other'}],[{...binding,ieee:'bad'}],[binding,binding]]){
        class Invalid extends Producer {get bindings(){return bindings;}}
        const f=fixture(Invalid);await assert.rejects(f.producer.start(),/Invalid original TV02 binding/);
        assert.equal(f.listeners.size,0);assert.equal(f.calls.length,0);
    }
});

test('failed listener registration releases owner and permits a clean restart', async () => {
    for (const attachFirst of [false, true]) {
        const f = fixture();
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
    const f = fixture();
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
        const f = fixture();
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
    const f = fixture();
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
    const f = fixture();
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
        const f = fixture();
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
