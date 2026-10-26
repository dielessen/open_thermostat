#pragma once

// Fixed EMS-ESP E32V2/E32V2_2 bus/network wiring. Do not infer old E32 pins.
namespace heating::board {
// Persistent settings have their own source-reviewed permission, never a build flag.
constexpr bool emsSettingsTransmitAllowed = false;
constexpr int emsRx = 4;
constexpr int emsTx = 5;
constexpr int phyAddress = 0;
constexpr int phyPower = 15;
constexpr int phyMdc = 23;
constexpr int phyMdio = 18;
#ifdef OPENTHERMOSTAT_E32V2
// No runtime or build-flag opt-in: enabling TX requires a reviewed source change
// after the electrical/timing validation in docs/BBQKEES_E32V2.md.
constexpr bool emsTransmitAllowed = false;
// Separate source-reviewed manual route; never grants legacy TX permission.
constexpr bool emsManualTestTransmitAllowed = false;
constexpr bool auxiliaryGpioAllowed = false;
#else
constexpr bool emsTransmitAllowed = true;
constexpr bool emsManualTestTransmitAllowed = false;
constexpr bool auxiliaryGpioAllowed = true;
#endif
}
