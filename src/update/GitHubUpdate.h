#pragma once
#ifdef OPENTHERMOSTAT_E32V2
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
// (confirms a new OTA image, see BootConfirmation).
void loop(bool automaticAllowed,bool supervisorAlive);
// A restart after delayMs at the first moment without an update, an
// unconfirmed boot or a boiler session; reason: SupervisorPolicy::Reason.
bool scheduleControlledRestart(uint32_t delayMs,uint8_t reason);
bool controlledRestartPending();
bool bootPending();
}
#endif
