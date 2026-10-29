#ifdef OPENTHERMOSTAT_E32V2
// POST /config/backup: see ConfigBackupRoute.h. Runs on the loop task (the
// WebServer owner), like every other settings writer. A rare, owner-started
// request: optimized for size, not speed (the image is -O3).
#pragma GCC optimize("Os")
#include "ConfigBackupRoute.h"
#include "BoilerDisplay.h"
#include "DeviceAccess.h"
#include "DeviceBluetoothSettings.h"
#include "DeviceNetworkSettings.h"
#include "Network.h"
#include "control/BackupCipher.h"
#include "control/ConfigBackup.h"
#include "diagnostics/SupervisorPolicy.h"
#include "update/GitHubUpdate.h"
#include <mbedtls/sha256.h>
#include <array>
#include <ctime>

namespace heating {
extern bool networkTimeTrusted; // main.cpp: NTP synchronized this boot
namespace {
namespace b = control::backup;
static_assert(b::saltBytes == b::cipher::saltBytes && b::nonceBytes == b::cipher::nonceBytes && b::tagBytes == b::cipher::tagBytes,
              "one sealed-box layout");
constexpr uint32_t restartDelayMs = 10000;

std::string sha256Hex(const std::string& bytes) {
    unsigned char hash[32];
    if (mbedtls_sha256_ret(reinterpret_cast<const unsigned char*>(bytes.data()), bytes.size(), hash, 0) != 0) return {};
    return b::toHex(std::string_view(reinterpret_cast<const char*>(hash), sizeof hash));
}
b::DeviceState deviceState(ConfigBackupHost& host) {
    b::DeviceState s;
    const auto network = readDeviceNetworkSettings();
    s.network.assign(network.c_str(), network.length());
    s.bluetooth = readDeviceBluetoothSettings();
    s.plan = host.plan();
    s.flow = host.flow();
    if (const auto model = readBoilerDisplayModel()) s.display = *model;
    s.wifiSsid = host.wifiSsid();
    s.modernMode = host.modernMode();
    s.ethernetUp = ethernetConnected();
    s.boilerClaimed = host.boilerClaimed();
    return s;
}
// Writes one section through the owner of its own API (each reads back).
struct Target {
    ConfigBackupHost& host;
    bool save(b::Part part, const std::string& text) {
        switch (part) {
            case b::Part::display: return saveBoilerDisplayModel(text);
            case b::Part::flow: {
                auto root = control::parseNestedJson(text, true, 2);
                return root && !host.setFlow(root.get());
            }
            case b::Part::plan: {
                // setHeatingPlan only accepts a write on top of the current revision.
                auto root = control::parseNestedJson(text, true, 10);
                auto current = control::parseNestedJson(host.plan(), true, 10);
                const auto revision = b::item(current.get(), "revision");
                return root && cJSON_IsNumber(revision) && b::put(root.get(), "revision", cJSON_CreateNumber(revision->valuedouble))
                    && !host.setPlan(root.get());
            }
            case b::Part::bluetooth:
                host.stopBluetooth(); // observation stays closed until the restart
                return saveDeviceBluetoothSettings(text);
            case b::Part::network: return saveDeviceNetworkSettings(String(text.c_str()));
        }
        return false;
    }
};
void reply(ConfigBackupResponse& out, int code, const cJSON* root) {
    out.code = code;
    out.text = root ? cJSON_PrintUnformatted(root) : nullptr;
}
void fail(ConfigBackupResponse& out, int code, const char* error, b::Report* report = nullptr, const char* failed = nullptr) {
    control::ControlJson root(cJSON_CreateObject(), cJSON_Delete);
    if (!root) return;
    cJSON_AddStringToObject(root.get(), "error", error);
    if (failed) cJSON_AddStringToObject(root.get(), "failed", failed);
    if (report && report->warnings) cJSON_AddItemToObject(root.get(), "warnings", report->warnings.release());
    reply(out, code, root.get());
}
int errorCode(const char* e) {
    const std::string_view s(e);
    if (s == "backup_too_large") return 413;
    if (s == "boiler_owned" || s == "settings_changed" || s == "busy") return 409;
    if (s == "out_of_memory" || s == "settings_unavailable") return 503;
    return 400;
}
}

void configBackupRequest(const char* body, std::size_t size, ConfigBackupHost& host, ConfigBackupResponse& out) {
    if (update::busy()) { fail(out, 409, "busy"); return; }
    b::Request request;
    if (const char* e = b::readRequest(body, size, request)) { fail(out, errorCode(e), e); return; }
    const auto state = deviceState(host);
    b::Meta device;
    device.firmware = host.firmware(); device.board = "e32v2"; device.language = request.language;
    if (networkTimeTrusted) device.created = b::utcText(static_cast<int64_t>(std::time(nullptr)));

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
                if (!sealed) { fail(out, 503, "seal_failed"); return; }
                sealedHex = b::toHex(box);
            }
        }
        auto document = b::exportDocument(state, device, sealedHex);
        if (!document) { fail(out, 503, "settings_unavailable"); return; }
        reply(out, 200, document.get()); // the browser saves it indented
        return;
    }

    b::Report report;
    std::string sealedBox;
    if (const char* e = b::checkEnvelope(request.backup, device, report, sealedBox)) { fail(out, errorCode(e), e, &report); return; }
    b::Secrets secrets;
    if (!sealedBox.empty() && !request.passphrase.empty()) {
        std::string plain;
        if (!b::cipher::open(request.passphrase, sealedBox, b::kdfIterations, plain)) { fail(out, 400, "wrong_passphrase", &report); return; }
        const char* e = b::readSecrets(plain, secrets);
        b::cipher::wipe(plain);
        if (e) { fail(out, 400, e, &report); return; }
    } else if (!sealedBox.empty()) report.warn("secrets_skipped");
    b::Prepared prepared;
    if (const char* e = b::prepare(request.backup, state, secrets, prepared, report)) { fail(out, errorCode(e), e, &report); return; }
    const auto fingerprint = sha256Hex(b::fingerprintInput(state, prepared));
    if (fingerprint.empty()) { fail(out, 503, "out_of_memory"); return; }

    if (request.action == "validate") {
        auto summary = b::summaryJson(report, prepared, fingerprint, !sealedBox.empty(), secrets.present);
        if (!summary) { fail(out, 503, "out_of_memory"); return; }
        reply(out, 200, summary.get());
        return;
    }
    // apply: exactly what the owner confirmed, on the device as it was then.
    if (request.fingerprint != fingerprint) { fail(out, 409, "settings_changed"); return; }
    Target target{host};
    std::string failed;
    const auto result = b::apply(state, prepared, target, failed);
    // A Bluetooth write closed observation: only the restart opens it again.
    const bool restart = result == b::Applied::applied ? prepared.restart : !prepared.bluetooth.empty();
    const bool scheduled = restart && update::scheduleControlledRestart(restartDelayMs,
        static_cast<uint8_t>(diagnostics::SupervisorPolicy::Reason::settingsRestore));
    if (result != b::Applied::applied) {
        fail(out, result == b::Applied::restored ? 503 : 500, result == b::Applied::restored ? "save_failed_restored" : "save_partial",
             &report, failed.c_str());
        return;
    }
    out.code = 201; // applied, even when the answer below cannot be built
    control::ControlJson root(cJSON_CreateObject(), cJSON_Delete);
    if (!root) return;
    cJSON_AddBoolToObject(root.get(), "applied", true);
    cJSON_AddBoolToObject(root.get(), "restart", restart);
    cJSON_AddBoolToObject(root.get(), "restart_scheduled", scheduled);
    if (scheduled) cJSON_AddNumberToObject(root.get(), "restart_in_s", restartDelayMs / 1000);
    if (prepared.language.empty()) cJSON_AddNullToObject(root.get(), "language");
    else cJSON_AddStringToObject(root.get(), "language", prepared.language.c_str());
    cJSON_AddItemToObject(root.get(), "reenter", report.reenter.release());
    reply(out, 201, root.get());
}
}
#endif
