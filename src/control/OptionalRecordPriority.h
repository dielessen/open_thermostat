#pragma once
#include "control/ControlPartitionBudget.h"
#include "control/ControlTuning.h"
#include "control/LearnedState.h"
#include "control/TakeoverReadiness.h"
#include <cstddef>
namespace heating::control {
// The order among the rc.2 optional NVS records when room is short (the
// `priority` of ControlPartitionBudget::permitsOptionalWrite): the automatic
// knobs without their log and the readiness counters first, then what was
// learned (the globals, then the rooms in plan order), the knobs' log last.
struct OptionalRecordPriority {
    using B = ControlPartitionBudget;
    static constexpr size_t knobsBytes = ControlTuning::maxBytes + 31; // the "autotune" record without its log, with its NUL
    // A learned frame leaves room for the knobs and the readiness counters.
    static constexpr size_t learned = B::blobEntries(knobsBytes) + B::blobEntries(sizeof(TakeoverReadiness::Stored));
    // The knobs' log leaves room for one learned frame.
    static constexpr size_t tuningLog = B::blobEntries(LearnedState::maxFrame);
};
}
