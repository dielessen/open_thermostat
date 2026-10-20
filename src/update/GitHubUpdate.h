#pragma once
#ifdef OPENTHERMOSTAT_E32V2
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
void loop();
}
#endif
