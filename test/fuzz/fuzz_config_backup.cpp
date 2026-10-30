// Settings restore fuzzer: the POST /config/backup flow of ConfigBackupRoute.h
// without NVS. The request body (validate/apply with a backup document) goes
// through readRequest, checkEnvelope and prepare against a configured E32; a
// sealed box is opened with real Mbed TLS (any passphrase fails or decrypts
// garbage that readSecrets must refuse). Every accepted candidate must be
// valid for the real readers, and apply with failing writes must restore.
//
// Input: [selector byte][request body JSON]. selector bit 0: modern mode,
// bit 1: Ethernet link up, bit 2: fail the network write, bit 3: secrets document instead of a request.
#include "fuzz_common.h"
#include "control/BackupCipher.h"
#include "control/ConfigBackup.h"
#include <cstring>

namespace {
using namespace heating::control;
namespace b = heating::control::backup;
const char* network = R"({"hostname":"heating-home","interface_mode":"wifi","listenPort":80,"emsEnabled":true,)"
    R"("mqtt":{"enabled":true,"modern_shadow":true,"adapter_id":"ha_1","brokerAddress":"192.0.2.10","brokerPort":1883,"username":"e32","password":"x","native_shadow_source":{"a":1}},)"
    R"("openweather":{"enabled":false,"appid":"k","latitude":"1","longitude":"2","interval":120},"bt":{"scanTime":60,"scanInterval":60}})";
const char* bluetooth = R"({"bt":{"devices":{"schema":1,"items":[["5448e68f80a5",1,1,"231d39c1d7cc1ab1aee224cd096db932","Living"]]}}})";
const char* plan = R"({"schema":1,"revision":3,"mode":"shadow","minimum_flow_c":30,"maximum_flow_c":60,"rooms":[]})";
struct Target {
    b::DeviceState& s; bool failNetwork;
    bool save(b::Part part, const std::string& text) {
        if (text.empty()) otfuzz::invariant("empty section written");
        if (part == b::Part::network && failNetwork) { failNetwork = false; return false; } // the rollback write succeeds
        switch (part) {
            case b::Part::display: s.display = text; break;
            case b::Part::flow: s.flow = text; break;
            case b::Part::plan: s.plan = text; break;
            case b::Part::bluetooth: s.bluetooth = text; break;
            case b::Part::network: s.network = text; break;
        }
        return true;
    }
};
ControlJson parsed(const std::string& text) { return parseNestedJson(text.c_str(), text.size(), true, 12); }
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, std::size_t size) {
    otfuzz::Reader in(data, size);
    const uint8_t selector = in.u8();
    const auto body = in.rest();
    if (selector & 8) {
        b::Secrets secrets;
        (void)b::readSecrets(std::string(body), secrets);
        if (secrets.present && secrets.bleKeys.size() > ManagedBleBindings::capacity) otfuzz::invariant("too many keys");
        return 0;
    }
    b::DeviceState state;
    state.network = network; state.bluetooth = bluetooth; state.plan = plan;
    state.flow = FlowSettings{}.json(); state.display = "none";
    state.modernMode = selector & 1; state.ethernetUp = selector & 2;
    b::Meta meta; meta.firmware = "fuzz"; meta.board = "e32v2";
    b::Request request;
    if (b::readRequest(body.data(), body.size(), request) || !request.backup) return 0;
    b::Report report; std::string sealed;
    if (b::checkEnvelope(request.backup, meta, report, sealed)) return 0;
    b::Secrets secrets;
    if (!sealed.empty()) {
        std::string plain;
        if (b::cipher::open("fuzz passphrase", sealed, b::kdfIterations, plain)) (void)b::readSecrets(plain, secrets);
    }
    b::Prepared prepared;
    if (b::prepare(request.backup, state, secrets, prepared, report)) {
        if (!prepared.network.empty() || !prepared.plan.empty()) otfuzz::invariant("refused backup left candidates");
        return 0;
    }
    if (!prepared.network.empty()) {
        auto n = parsed(prepared.network);
        if (!n || !nativeNetworkSettingsBytesFit(prepared.network)) otfuzz::invariant("network candidate invalid");
        if (networkSettingsContainManagedBleBindings(n.get())) otfuzz::invariant("bindings in the network document");
        if (b::text(b::item(n.get(), "interface_mode")) == "ethernet" && !state.ethernetUp) otfuzz::invariant("ethernet without link");
        if (!cJSON_Compare(b::item(n.get(), "listenPort"), cJSON_GetObjectItemCaseSensitive(parsed(state.network).get(), "listenPort"), true))
            otfuzz::invariant("web port changed");
        if (!b::item(b::item(n.get(), "mqtt"), "native_shadow_source")) otfuzz::invariant("device SOURCE profile lost");
    }
    if (!prepared.bluetooth.empty()) {
        auto bindings = std::make_unique<ManagedBleBindings>();
        if (readManagedBleBindings(parsed(prepared.bluetooth).get(), *bindings) != BleSettingsError::none) otfuzz::invariant("bluetooth candidate invalid");
    }
    if (!prepared.plan.empty()) {
        RoomPlan p;
        if (RoomPlan::parse(parsed(prepared.plan).get(), p) || p.mode != RoomPlan::Mode::shadow) otfuzz::invariant("plan candidate invalid");
    }
    if (!prepared.flow.empty()) { FlowSettings f; if (FlowSettings::parse(parsed(prepared.flow).get(), f)) otfuzz::invariant("flow candidate invalid"); }
    const auto before = state;
    const bool failing = (selector & 4) != 0;
    Target target{state, failing};
    std::string failed;
    const auto result = b::apply(before, prepared, target, failed);
    if (failing && !prepared.network.empty()) {
        if (result != b::Applied::restored || state.plan != before.plan || state.bluetooth != before.bluetooth
                || state.flow != before.flow || state.display != before.display || state.network != before.network)
            otfuzz::invariant("failed apply not restored");
    } else if (result != b::Applied::applied) otfuzz::invariant("apply failed without a failing write");
    (void)b::summaryJson(report, prepared, "fingerprint", !sealed.empty(), secrets.present);
    return 0;
}
