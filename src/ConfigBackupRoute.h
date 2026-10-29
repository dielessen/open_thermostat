#pragma once
#ifdef OPENTHERMOSTAT_E32V2
// POST /config/backup (behind the web sign-in and CSRF gate of REST::route):
//   {"action":"export"[,"passphrase":".."][,"language":"en"|"nl"]} -> the backup file
//   {"action":"validate","backup":{..}[,"passphrase":".."]}      -> the summary + fingerprint
//   {"action":"apply","backup":{..},"fingerprint":".."[,"passphrase"]} -> applied, restart scheduled
// Logic and validation: control/ConfigBackup.h. cJSON allocates in PSRAM (main.cpp hooks).
#include "BoilerDisplay.h"
#include "DeviceAccess.h"
#include "DeviceBluetoothSettings.h"
#include "DeviceNetworkSettings.h"
#include "EmbeddedWebAssets.h"
#include "Network.h"
#include "SetupNetwork.h"
#include "control/BackupCipher.h"
#include "control/ConfigBackup.h"
#include "diagnostics/SupervisorPolicy.h"
#include "update/GitHubUpdate.h"
#include <WebServer.h>
#include <mbedtls/sha256.h>
#include <cstdio>
#include <ctime>
#include <string_view>

namespace heating {
extern bool networkTimeTrusted;
namespace backup_route {
namespace b = control::backup;
static_assert(b::saltBytes == b::cipher::saltBytes && b::nonceBytes == b::cipher::nonceBytes && b::tagBytes == b::cipher::tagBytes);
inline constexpr uint32_t restartDelayMs = 10000;

// UTC "YYYY-MM-DDTHH:MM:SSZ" without new libc time functions; empty before NTP.
inline std::string created() {
    if (!networkTimeTrusted) return {};
    const int64_t now = static_cast<int64_t>(std::time(nullptr));
    if (now < 1704067200) return {};
    int64_t days = now / 86400; const int64_t secs = now % 86400;
    days += 719468; const int64_t era = days / 146097, doe = days - era * 146097;
    const int64_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365, doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    const int64_t mp = (5 * doy + 2) / 153, day = doy - (153 * mp + 2) / 5 + 1, month = mp < 10 ? mp + 3 : mp - 9;
    const int64_t year = yoe + era * 400 + (month <= 2);
    char text[24];
    std::snprintf(text, sizeof text, "%04d-%02d-%02dT%02d:%02d:%02dZ", int(year), int(month), int(day),
                  int(secs / 3600), int(secs / 60 % 60), int(secs % 60));
    return text;
}
inline std::string sha256Hex(const std::string& bytes) {
    unsigned char hash[32];
    if (mbedtls_sha256_ret(reinterpret_cast<const unsigned char*>(bytes.data()), bytes.size(), hash, 0) != 0) return {};
    return b::toHex(std::string_view(reinterpret_cast<const char*>(hash), sizeof hash));
}
template<class Controller> b::DeviceState deviceState(Controller& controller) {
    b::DeviceState s;
    const auto network = readDeviceNetworkSettings();
    s.network.assign(network.c_str(), network.length());
    s.bluetooth = readDeviceBluetoothSettings();
    s.plan = controller.heatingPlanJson();
    s.flow = controller.flowSettingsJson();
    if (const auto model = readBoilerDisplayModel()) s.display = *model;
    config::WiFiConfig wifi;
    if (readSetupWifi(wifi)) s.wifiSsid = wifi.ssid;
    b::cipher::wipe(wifi.password);
    s.modernMode = controller.modernMode();
    s.ethernetUp = ethernetConnected();
    s.boilerClaimed = controller.claimsBoiler() || controller.boilerTestActive() || controller.boilerSettingsActive();
    return s;
}
inline b::Meta meta(const std::string& language) {
    b::Meta m; m.firmware = embedded::version; m.board = "e32v2"; m.created = created(); m.language = language;
    return m;
}
// Writes one section through the same owner as its own API (and its readback).
template<class Controller> struct Target {
    Controller& controller;
    bool save(b::Part part, const std::string& text) {
        switch (part) {
            case b::Part::display: return saveBoilerDisplayModel(text);
            case b::Part::flow: {
                auto root = control::parseNestedJson(text, true, 2);
                return root && !controller.setFlowSettings(root.get());
            }
            case b::Part::plan: {
                // setHeatingPlan only accepts a write on top of the current revision.
                auto root = control::parseNestedJson(text, true, 10);
                auto current = control::parseNestedJson(controller.heatingPlanJson(), true, 10);
                const auto revision = b::item(current.get(), "revision");
                return root && cJSON_IsNumber(revision) && b::put(root.get(), "revision", cJSON_CreateNumber(revision->valuedouble))
                    && !controller.setHeatingPlan(root.get());
            }
            case b::Part::bluetooth:
                controller.stopManagedBle(); // observation stays closed until the restart
                return saveDeviceBluetoothSettings(text);
            case b::Part::network: return saveDeviceNetworkSettings(String(text.c_str()));
        }
        return false;
    }
};
template<class Server> void send(Server& server, int code, const cJSON* root, bool pretty = false) {
    std::unique_ptr<char, decltype(&cJSON_free)> text(root ? (pretty ? cJSON_Print(root) : cJSON_PrintUnformatted(root)) : nullptr, cJSON_free);
    server.sendHeader("Cache-Control", "no-store");
    if (!text) { server.send(503, "application/json", "{\"error\":\"out_of_memory\"}"); return; }
    server.sendView(code, "application/json", std::string_view(text.get()));
}
template<class Server> void fail(Server& server, int code, const char* error, b::Report* report = nullptr, const char* failed = nullptr) {
    control::ControlJson root(cJSON_CreateObject(), cJSON_Delete);
    if (!root) { server.send(503, "application/json", "{\"error\":\"out_of_memory\"}"); return; }
    cJSON_AddStringToObject(root.get(), "error", error);
    if (failed) cJSON_AddStringToObject(root.get(), "failed", failed);
    if (report && report->warnings) cJSON_AddItemToObject(root.get(), "warnings", report->warnings.release());
    send(server, code, root.get());
}
inline int errorCode(const char* e) {
    const std::string_view s(e);
    if (s == "backup_too_large") return 413;
    if (s == "boiler_owned" || s == "settings_changed" || s == "busy") return 409;
    if (s == "out_of_memory" || s == "settings_unavailable") return 503;
    return 400;
}
}

template<class Server, class Controller>
void configBackupRoute(Server& server, Controller& controller) {
    namespace b = control::backup;
    using namespace backup_route;
    if (server.method() != HTTP_POST) { server.send(405, "application/json", "{\"error\":\"method_not_allowed\"}"); return; }
    if (update::busy()) { fail(server, 409, "busy"); return; }
    const auto body = server.arg("plain");
    b::Request request;
    if (const char* e = b::readRequest(body.c_str(), body.length(), request)) { fail(server, errorCode(e), e); return; }
    const auto state = deviceState(controller);
    const auto device = meta(request.language);

    if (request.action == "export") {
        std::string sealedHex;
        if (!request.passphrase.empty()) {
            auto plain = b::secretsDocument(state);
            if (!plain.empty()) {
                std::array<uint8_t, b::saltBytes> salt{}; std::array<uint8_t, b::nonceBytes> nonce{};
                std::string box;
                const bool sealed = deviceAccess.randomBytes(salt.data(), salt.size()) && deviceAccess.randomBytes(nonce.data(), nonce.size())
                    && b::cipher::seal(request.passphrase, plain, salt, nonce, b::kdfIterations, box);
                b::cipher::wipe(plain);
                if (!sealed) { fail(server, 503, "seal_failed"); return; }
                sealedHex = b::toHex(box);
            }
        }
        auto document = b::exportDocument(state, device, sealedHex);
        if (!document) { fail(server, 503, "settings_unavailable"); return; }
        send(server, 200, document.get(), true);
        return;
    }

    b::Report report;
    std::string sealedBox;
    if (const char* e = b::checkEnvelope(request.backup, device, report, sealedBox)) { fail(server, errorCode(e), e, &report); return; }
    b::Secrets secrets;
    if (!sealedBox.empty() && !request.passphrase.empty()) {
        std::string plain;
        if (!b::cipher::open(request.passphrase, sealedBox, b::kdfIterations, plain)) { fail(server, 400, "wrong_passphrase", &report); return; }
        const char* e = b::readSecrets(plain, secrets);
        b::cipher::wipe(plain);
        if (e) { fail(server, 400, e, &report); return; }
    } else if (!sealedBox.empty()) report.warn("secrets_skipped");
    b::Prepared prepared;
    if (const char* e = b::prepare(request.backup, state, secrets, prepared, report)) { fail(server, errorCode(e), e, &report); return; }
    const auto fingerprint = sha256Hex(b::fingerprintInput(state, prepared));
    if (fingerprint.empty()) { fail(server, 503, "out_of_memory"); return; }

    if (request.action == "validate") {
        auto summary = b::summaryJson(report, prepared, fingerprint, !sealedBox.empty(), secrets.present);
        if (!summary) { fail(server, 503, "out_of_memory"); return; }
        send(server, 200, summary.get());
        return;
    }
    // apply: exactly what the owner confirmed, on the device as it was then.
    if (request.fingerprint != fingerprint) { fail(server, 409, "settings_changed"); return; }
    Target<Controller> target{controller};
    std::string failed;
    const auto result = b::apply(state, prepared, target, failed);
    // A Bluetooth write closed observation: only the restart opens it again.
    const bool restart = result == b::Applied::applied ? prepared.restart : !prepared.bluetooth.empty();
    const bool scheduled = restart && update::scheduleControlledRestart(restartDelayMs,
        static_cast<uint8_t>(diagnostics::SupervisorPolicy::Reason::settingsRestore));
    if (result != b::Applied::applied) {
        fail(server, result == b::Applied::restored ? 503 : 500, result == b::Applied::restored ? "save_failed_restored" : "save_partial",
             &report, failed.c_str());
        return;
    }
    control::ControlJson root(cJSON_CreateObject(), cJSON_Delete);
    if (!root) { server.send(201, "application/json", "{\"applied\":true}"); return; }
    cJSON_AddBoolToObject(root.get(), "applied", true);
    cJSON_AddBoolToObject(root.get(), "restart", restart);
    cJSON_AddBoolToObject(root.get(), "restart_scheduled", scheduled);
    if (scheduled) cJSON_AddNumberToObject(root.get(), "restart_in_s", restartDelayMs / 1000);
    if (prepared.language.empty()) cJSON_AddNullToObject(root.get(), "language");
    else cJSON_AddStringToObject(root.get(), "language", prepared.language.c_str());
    cJSON_AddItemToObject(root.get(), "reenter", report.reenter.release());
    send(server, 201, root.get());
}
}
#endif
