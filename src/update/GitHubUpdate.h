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
bool requestReboot();
bool requestRollback();
std::string status();
void loop();
}
#endif
