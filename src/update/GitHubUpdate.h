#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <atomic>
#include <cstdint>
#include <string>
#include <string_view>
namespace heating::update {
bool busy();
bool staged();
bool mutationBlocked(std::string_view path);
bool checkReleases();
bool installRelease(const std::string &tag);
void firmwareInstalled(); // Only after native validation and boot-slot selection.
bool requestReboot();
bool requestRollback();
std::string status();
std::string availability(); // Cached local summary; never starts network work.
// automaticAllowed: no boiler trial/settings session (also gates the
// controlled restart). supervisorAlive: the supervisor task ran recently
// (confirms a new OTA image, see BootConfirmation). networkProven: since boot
// the device had an IP address and served a request, held an MQTT session or
// got a gateway probe reply (also required for that confirmation).
void loop(bool automaticAllowed,bool supervisorAlive,bool networkProven);
// A restart after delayMs at the first moment without an update, an
// unconfirmed boot or a boiler session; reason: SupervisorPolicy::Reason.
bool scheduleControlledRestart(uint32_t delayMs,uint8_t reason);
bool controlledRestartPending();
bool bootPending();
// An HTTP firmware or filesystem upload (REST /ota, /otafs) is being written:
// set on UPLOAD_FILE_START, cleared on END/ABORTED and by the final reply. The
// supervisor counts it as a running update (still capped at updateMaxMs).
inline std::atomic<bool> httpUploadActive{false};
}
#endif
