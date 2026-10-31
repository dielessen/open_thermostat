// The release decision of beta.22, pinned: only the E32 V2 build may send an
// active heat request; every other board keeps the gate closed. Board.h holds
// only constants, so including it with and without the E32 V2 macro is safe.
#define OPENTHERMOSTAT_E32V2
#include "Board.h"
#undef OPENTHERMOSTAT_E32V2
#include <gtest/gtest.h>

namespace {
static_assert(heating::board::emsActiveHeatAllowed, "beta.22: the E32 V2 build opens the active heat gate");
static_assert(heating::board::emsManualTestTransmitAllowed, "active heat uses the reviewed manual route only");
static_assert(!heating::board::emsTransmitAllowed, "automatic/legacy transmission stays closed");
static_assert(!heating::board::emsSettingsTransmitAllowed, "boiler settings writes stay closed");
TEST(BoardGate, OnlyTheE32V2BuildMaySendAnActiveHeatRequest) { SUCCEED(); }
}
