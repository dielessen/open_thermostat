'use strict';

const {randomUUID} = require('node:crypto');

// Source-reviewed target: Zigbee2MQTT 2.14.2, converters 26.115.1.
// Populate only explicitly selected IEEE/model bindings before installation.
// This producer is observational; no entry here authorizes heating control.
const DEVICE_BINDINGS = Object.freeze([]);
const TOPIC = 'bridge/openthermostat/original_temperature';

module.exports = class OpenThermostatOriginalTemperature {
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
                || binding.model !== 'WSDCGQ11LM' || bindings.has(binding.ieee)) {
                throw new Error('Invalid original temperature binding');
            }
            bindings.set(binding.ieee, binding.model);
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
        // Capture callback time before any asynchronous operation. This is a
        // Zigbee receive time, NOT a sensor acquisition time or quality proof.
        const receivedAt = Date.now();
        const device = message?.device;
        const ieee = device?.ieeeAddr;
        if (this.devices.get(ieee) !== 'WSDCGQ11LM'
            || device?.definition?.model !== 'WSDCGQ11LM'
            || device.zh?.modelID !== 'lumi.weather'
            || device.interviewed !== true
            || message.cluster !== 'msTemperatureMeasurement'
            || !['attributeReport', 'readResponse'].includes(message.type)
            || !Number.isInteger(message.endpoint?.ID)
            || message.endpoint.ID < 1 || message.endpoint.ID > 240
            || !Object.hasOwn(message.data ?? {}, 'measuredValue')) return;
        const raw = message.data.measuredValue;
        // Same documented model range, without calibrating or rounding cached
        // values. No conversion function, device read, command or state write.
        if (!Number.isInteger(raw) || raw <= -6500 || raw >= 6500
            || !Number.isSafeInteger(receivedAt) || receivedAt < 0) return;
        // No backlog, retry or replay after reconnect. One existing MQTT-client
        // publication at most; busy/disconnected samples are discarded.
        if (this.pending || !this.mqtt.isConnected()
            || this.sequence >= Number.MAX_SAFE_INTEGER) {
            this.dropped = Math.min(this.dropped + 1, Number.MAX_SAFE_INTEGER);
            return;
        }
        const transaction = message.meta?.zclTransactionSequenceNumber;
        const payload = {
            schema: 1, producer: 'openthermostat.z2m.original_temperature',
            producer_run_id: this.run, sequence: ++this.sequence,
            device_ieee: ieee, model: 'WSDCGQ11LM', zigbee_model: 'lumi.weather',
            endpoint: message.endpoint.ID, cluster: message.cluster,
            message_kind: message.type, property: 'temperature',
            raw_value: raw, value_centi_c: raw,
            zcl_transaction: Number.isInteger(transaction) && transaction >= 0 && transaction <= 255 ? transaction : null,
            received_at_unix_ms: receivedAt, sampled_at_unix_ms: null,
            acquisition_age_verified: false, control_qualified: false,
            dropped_reports: this.dropped,
        };
        // Keep this call synchronous up to publish: mqtt.js has queueQoSZero
        // defaults, so an application-level deferred send would risk a later
        // connection. The connection check cannot eliminate a network race;
        // consumers must enforce their own session/challenge and age policy.
        try {
            const result = this.mqtt.publish(TOPIC, JSON.stringify(payload), {
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
