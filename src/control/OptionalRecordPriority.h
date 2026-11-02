#pragma once
#include "control/ControlPartitionBudget.h"
#include "control/ControlTuning.h"
#include "control/LearnedState.h"
#include "control/TakeoverReadiness.h"
#include <cstddef>
namespace heating::control {
// The order among the rc.2 optional NVS records when room is short (the
// `priority` of ControlPartitionBudget::permitsOptionalWrite): the readiness
// counters and the automatic knobs without their log first, then what was
// learned (the globals, then the rooms in plan order), the knobs' log last.
// A priority is the room a more important record still needs: none for a
// record already stored (its entries are counted as used already).
struct OptionalRecordPriority {
    using B = ControlPartitionBudget;
    static constexpr size_t knobsBytes = ControlTuning::maxBytes + 31; // the "autotune" record without its log, with its NUL
    // What was learned leaves room for the knobs and the readiness counters not stored yet.
    static constexpr size_t learned(bool knobsStored, bool readinessStored) {
        return (knobsStored ? 0 : 1 + B::blobEntries(knobsBytes)) + (readinessStored ? 0 : 1 + B::blobEntries(sizeof(TakeoverReadiness::Stored)));
    }
    // The knobs' log leaves room for what was learned and is not stored yet (LearnedStore::pendingEntries).
    static constexpr size_t tuningLog(size_t learnedPendingEntries) { return learnedPendingEntries; }
};
}
