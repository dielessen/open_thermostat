'use strict';

const {randomUUID} = require('node:crypto');

// Source-reviewed target: Zigbee2MQTT 2.14.2, converters 26.115.1.
// Populate only explicitly selected IEEE/model bindings before installation.
// This producer is observational; no entry here authorizes heating control.
const DEVICE_BINDINGS = Object.freeze([]);
const TOPIC = 'bridge/openthermostat/original_tv02';

const MANUFACTURERS = new Set(['_TZE200_hue3yfsn', '_TZE200_lllliz3p']);
const KINDS = new Set(['commandDataResponse', 'commandDataReport',
    'commandActiveStatusReport', 'commandActiveStatusReportAlt']);

// Independent interpretation of the pinned TV02 wire facts, not converter code.
// Never combine this message with state/cache or infer omitted properties.
function decodeMessage(message) {
    const device = message?.device;
    if (device?.definition?.model !== 'TV02-Zigbee' || device.interviewed !== true
        || device.zh?.modelID !== 'TS0601' || !MANUFACTURERS.has(device.zh?.manufacturerName)
        || message.cluster !== 'manuSpecificTuya' || !KINDS.has(message.type)
        || !Number.isInteger(message.endpoint?.ID) || message.endpoint.ID < 1 || message.endpoint.ID > 240
        || !Array.isArray(message.data?.dpValues)
        || !message.data.dpValues.length || message.data.dpValues.length > 16) return null;
    const fields = [], ids = new Set(); let bytes = 0;
    for (const row of message.data.dpValues) {
        if (!row || !Number.isInteger(row.dp) || row.dp < 0 || row.dp > 255
            || ids.has(row.dp) || !Number.isInteger(row.datatype) || row.datatype < 0 || row.datatype > 5
            || !Buffer.isBuffer(row.data) || row.data.length > 64) return null;
        ids.add(row.dp); bytes += row.data.length;
        if (bytes > 128) return null;
        let property, value;
        if (row.dp === 16 || row.dp === 24) {
            if (row.datatype !== 2 || row.data.length !== 4) return null;
            const raw = row.data.readUInt32BE();
            if (row.dp === 16) {
                if (raw < 50 || raw > 300 || raw % 5 !== 0) return null;
                property = 'target_centi_c';
            } else {
                if (raw > 600) return null;
                property = 'local_temperature_centi_c';
            }
            value = raw * 10;
        } else if (row.dp === 2) {
            if (row.datatype !== 4 || row.data.length !== 1 || row.data[0] > 3) return null;
            property = 'preset'; value = ['auto', 'manual', 'holiday', 'holiday'][row.data[0]];
        } else if (row.dp === 107 || row.dp === 10) {
            if (row.datatype !== 1 || row.data.length !== 1 || row.data[0] > 1) return null;
            property = row.dp === 107 ? 'heating_stop' : 'frost_protection'; value = row.data[0] === 1;
        } else continue;
        fields.push({dp: row.dp, datatype: row.datatype, raw_hex: row.data.toString('hex'), property, value});
    }
    return fields.length ? fields : null;
}


module.exports = class OpenThermostatOriginalTv02 {
    constructor(_zigbee, mqtt, _state, _publishEntityState, eventBus) {
        this.mqtt = mqtt;
        this.eventBus = eventBus;
        this.active = false;
        this.cleanupRequired = false;
        this.pending = null;
        this.stopping = null;
        this.run = null;
        this.sequence = 0;
        this.dropped = 0;
        this.onMessage = this.onMessage.bind(this);
    }

    get bindings() { return DEVICE_BINDINGS; }

    async start() {
        if (this.stopping) await this.stopping;
        if (this.active) return;
        if (this.cleanupRequired) {
            this.eventBus.removeListeners(this);
            this.cleanupRequired = false;
        }
        const bindings = new Map();
        for (const binding of this.bindings) {
            if (!binding || !/^0x[0-9a-f]{16}$/.test(binding.ieee)
                || binding.model !== 'TV02-Zigbee' || !MANUFACTURERS.has(binding.manufacturer)
                || !Number.isInteger(binding.endpoint) || binding.endpoint < 1 || binding.endpoint > 240
                || bindings.has(binding.ieee)) {
                throw new Error('Invalid original TV02 binding');
            }
            bindings.set(binding.ieee, Object.freeze({...binding}));
        }
        this.devices = bindings;
        this.run = randomUUID();
        this.sequence = 0;
        this.dropped = 0;
        this.active = true;
        try {
            this.eventBus.onDeviceMessage(this, this.onMessage);
        } catch (error) {
            // Registration may throw after attaching the listener. Withdraw
            // ownership first so even a retained callback cannot publish.
            this.active = false;
            this.run = null;
            this.devices.clear();
            this.cleanupRequired = true;
            try {
                this.eventBus.removeListeners(this);
                this.cleanupRequired = false;
            } catch (cleanupError) {
                throw new AggregateError([error, cleanupError],
                    'Original report listener registration and cleanup failed');
            }
            throw error;
        }
    }

    async stop() {
        if (this.stopping) return this.stopping;
        if (!this.active) {
            if (this.cleanupRequired) {
                this.eventBus.removeListeners(this);
                this.cleanupRequired = false;
            }
            return;
        }
        this.active = false;
        // A failed SDK cleanup must not bypass draining the old publication.
        // Retained callbacks are inert until cleanup succeeds on a later call.
        this.cleanupRequired = true;
        let cleanupError;
        try {
            this.eventBus.removeListeners(this);
            this.cleanupRequired = false;
        } catch (error) {
            cleanupError = error;
        }
        const stopping = (async () => {
            // Always yield once so concurrent start/stop sees this owner even
            // when there is no publication to drain.
            await this.pending;
            this.run = null;
            this.devices?.clear();
            if (this.cleanupRequired) throw cleanupError;
        })();
        this.stopping = stopping;
        try { await stopping; }
        finally { if (this.stopping === stopping) this.stopping = null; }
    }

    onMessage(message) {
        if (!this.active) return;
        const receivedAt = Date.now();
        const device = message?.device;
        const binding = this.devices.get(device?.ieeeAddr);
        if (!binding) return;
        const fields = decodeMessage(message);
        if (!fields || !binding || device.zh.manufacturerName !== binding.manufacturer
            || message.endpoint.ID !== binding.endpoint
            || !Number.isSafeInteger(receivedAt) || receivedAt < 0) return;
        // No backlog, retry or replay after reconnect. One existing MQTT-client
        // publication at most; busy/disconnected samples are discarded.
        if (this.pending || !this.mqtt.isConnected()
            || this.sequence >= Number.MAX_SAFE_INTEGER) {
            this.dropped = Math.min(this.dropped + 1, Number.MAX_SAFE_INTEGER);
            return;
        }
        const transaction = message.meta?.zclTransactionSequenceNumber;
        const tuyaSequence = message.data.seq;
        const payload = {
            schema: 1, producer: 'openthermostat.z2m.original_tv02',
            producer_run_id: this.run, sequence: ++this.sequence,
            device_ieee: device.ieeeAddr, model: 'TV02-Zigbee', zigbee_model: 'TS0601',
            manufacturer: device.zh.manufacturerName, endpoint: message.endpoint.ID,
            cluster: message.cluster, message_kind: message.type,
            tuya_sequence: Number.isInteger(tuyaSequence) && tuyaSequence >= 0 && tuyaSequence <= 65535 ? tuyaSequence : null,
            zcl_transaction: Number.isInteger(transaction) && transaction >= 0 && transaction <= 255 ? transaction : null,
            received_at_unix_ms: receivedAt, sampled_at_unix_ms: null,
            command_correlated: false, valve_ready: false, control_qualified: false,
            fields, dropped_reports: this.dropped,
        };
        // Keep this call synchronous up to publish: mqtt.js has queueQoSZero
        // defaults, so an application-level deferred send would risk a later
        // connection. The connection check cannot eliminate a network race;
        // consumers must enforce their own session/challenge and age policy.
        try {
            const raw = JSON.stringify(payload);
            if (Buffer.byteLength(raw) > 2048) {
                this.dropped = Math.min(this.dropped + 1, Number.MAX_SAFE_INTEGER);
                return;
            }
            const result = this.mqtt.publish(TOPIC, raw, {
                clientOptions: {retain: false, qos: 0}, skipLog: true,
            });
            const pending = Promise.resolve(result).catch(() => {
                this.dropped = Math.min(this.dropped + 1, Number.MAX_SAFE_INTEGER);
            });
            this.pending = pending;
            void pending.finally(() => { if (this.pending === pending) this.pending = null; });
        } catch {
            this.dropped = Math.min(this.dropped + 1, Number.MAX_SAFE_INTEGER);
        }
    }
};

module.exports.decodeMessage = decodeMessage;
