#include "control/Measurement.h"
#include "control/UtcSchedule.h"
#include <gtest/gtest.h>
#include <limits>

namespace {
using namespace heating::control;

TEST(SourceSample, PhysicalAgeAndBoundedTransportDelayAreNotResetByArrivalOrReadback) {
    TemperatureProfile p; p.maximumAgeMs=10000;
    TemperatureSample s;
    ASSERT_TRUE(s.observe(20.0,TemperatureUnit::celsius,SampleEvidence::physical_report,3000,2000,10000,p));
    EXPECT_EQ(s.age(10000),5000u);
    EXPECT_EQ(s.value(14999),2000);
    EXPECT_EQ(s.age(14999),9999u);
    EXPECT_FALSE(s.value(15000));
    EXPECT_EQ(s.state(15000),SampleState::stale);
    EXPECT_EQ(s.age(15000),10000u);
}

TEST(SourceSample, ANewEqualPhysicalSampleCanRefreshButCacheAndDeviceSeenCannot) {
    TemperatureProfile p; p.maximumAgeMs=10000;
    TemperatureSample s;
    ASSERT_TRUE(s.observe(20.0,TemperatureUnit::celsius,SampleEvidence::physical_report,0,0,10000,p));
    ASSERT_TRUE(s.observe(20.0,TemperatureUnit::celsius,SampleEvidence::physical_report,0,0,19000,p));
    EXPECT_TRUE(s.value(20000));
    EXPECT_FALSE(s.observe(20.0,TemperatureUnit::celsius,SampleEvidence::cache_read,0,0,20000,p));
    EXPECT_EQ(s.state(20000),SampleState::unverified);
    EXPECT_FALSE(s.value(20000));
    EXPECT_FALSE(s.observe(20.0,TemperatureUnit::celsius,SampleEvidence::device_seen,0,0,21000,p));
}

TEST(SourceSample, RestoredValueAndUnvalidatedIntegrationNeverBecomePhysicalEvidence) {
    TemperatureProfile p; TemperatureSample s;
    EXPECT_FALSE(s.observe(20,TemperatureUnit::celsius,SampleEvidence::physical_report,0,0,100,p,true));
    EXPECT_EQ(s.state(100),SampleState::restored);
    EXPECT_FALSE(s.observe(20,TemperatureUnit::celsius,SampleEvidence::validated_integration_report,0,0,100,p));
    p.acceptsValidatedIntegrationReport=true;
    EXPECT_TRUE(s.observe(20,TemperatureUnit::celsius,SampleEvidence::validated_integration_report,0,0,100,p));
}

TEST(SourceSample, FahrenheitCalibrationAndBadNumericInputsAreHandledExplicitly) {
    TemperatureProfile p; p.calibrationCentiC=100;
    TemperatureSample s;
    ASSERT_TRUE(s.observe(68,TemperatureUnit::fahrenheit,SampleEvidence::physical_report,0,0,100,p));
    EXPECT_EQ(s.value(100),2100);
    EXPECT_FALSE(s.observe(std::numeric_limits<double>::quiet_NaN(),TemperatureUnit::celsius,SampleEvidence::physical_report,0,0,100,p));
    EXPECT_EQ(s.state(100),SampleState::invalid);
    EXPECT_FALSE(s.observe(std::numeric_limits<double>::infinity(),TemperatureUnit::celsius,SampleEvidence::physical_report,0,0,100,p));
    EXPECT_FALSE(s.observe(2000,TemperatureUnit::celsius,SampleEvidence::physical_report,0,0,100,p));
    EXPECT_FALSE(s.observe(20,static_cast<TemperatureUnit>(99),SampleEvidence::physical_report,0,0,100,p));
}

TEST(SourceSample, OldOrOverflowingAgeCannotBeReplayedAsFresh) {
    TemperatureProfile p; TemperatureSample s;
    EXPECT_FALSE(s.observe(20,TemperatureUnit::celsius,SampleEvidence::physical_report,7*3600000,0,100,p));
    EXPECT_EQ(s.state(100),SampleState::stale);
    EXPECT_EQ(s.age(100),7*3600000u);
    EXPECT_FALSE(s.observe(20,TemperatureUnit::celsius,SampleEvidence::physical_report,UINT64_MAX,1,100,p));
    EXPECT_FALSE(s.age(100));
    EXPECT_FALSE(s.value(100));
}

TEST(SourceSample, UnavailableInvalidProfileAndClockResetAreNotHiddenByOtherSamples) {
    TemperatureProfile p; TemperatureSample a,b;
    ASSERT_TRUE(a.observe(20,TemperatureUnit::celsius,SampleEvidence::physical_report,0,0,100,p));
    ASSERT_TRUE(b.observe(21,TemperatureUnit::celsius,SampleEvidence::physical_report,0,0,100,p));
    a.unavailable(); EXPECT_FALSE(a.value(101)); EXPECT_TRUE(b.value(101));
    EXPECT_FALSE(b.value(99));
    EXPECT_FALSE(b.value(100+(1ULL<<32)));
    p.maximumAgeMs=0;
    EXPECT_FALSE(b.observe(21,TemperatureUnit::celsius,SampleEvidence::physical_report,0,0,200,p));
}

TEST(SourceSample, KnownExpiryCannotBeUndoneByAnEarlierReadOfTheSameObservation) {
    TemperatureProfile p;p.maximumAgeMs=1000;TemperatureSample s;
    ASSERT_TRUE(s.observe(20,TemperatureUnit::celsius,SampleEvidence::physical_report,0,0,10000,p));
    ASSERT_TRUE(s.value(10999));EXPECT_FALSE(s.value(11000));
    EXPECT_FALSE(s.value(10999));EXPECT_EQ(s.state(10000),SampleState::stale);
    EXPECT_EQ(s.age(11000),1000u); // Original diagnostic age remains available.
}

TEST(SourceSample, DiagnosticExpiryAndBeforeReceiptClockFailureAlsoRetireTheObservation) {
    for(bool diagnostic:{false,true}) {
        TemperatureProfile p;p.maximumAgeMs=1000;TemperatureSample s;
        ASSERT_TRUE(s.observe(20,TemperatureUnit::celsius,SampleEvidence::physical_report,0,0,10000,p));
        if(diagnostic)EXPECT_EQ(s.age(11000),1000u);
        else EXPECT_FALSE(s.value(9999));
        EXPECT_FALSE(s.value(10000));
        auto copied=s;EXPECT_FALSE(copied.value(10000));
    }
}

TEST(SourceSample, OnlyANewAdmittedObservationCanReplaceRetiredEvidence) {
    TemperatureProfile p;p.maximumAgeMs=1000;TemperatureSample s,independent;
    ASSERT_TRUE(s.observe(20,TemperatureUnit::celsius,SampleEvidence::physical_report,0,0,10000,p));
    ASSERT_TRUE(independent.observe(20,TemperatureUnit::celsius,SampleEvidence::physical_report,0,0,11000,p));
    EXPECT_FALSE(s.value(11000));EXPECT_TRUE(independent.value(11000));
    EXPECT_FALSE(s.observe(20,TemperatureUnit::celsius,SampleEvidence::cache_read,0,0,11000,p));
    EXPECT_FALSE(s.value(11000));
    ASSERT_TRUE(s.observe(20,TemperatureUnit::celsius,SampleEvidence::physical_report,0,0,11001,p));
    EXPECT_EQ(s.value(11001),2000);
}

constexpr int64_t monday=1792368000; // Fixed UTC fixture epoch, not a system clock.
TEST(UtcSchedule, BoundaryAdjacentAndBaseIntervalsUseOneEffectiveTarget) {
    UtcSchedule s;
    const ScheduleTransition t[]{{monday,1600},{monday+6*3600,2000},{monday+7*3600,2100},{monday+8*3600,1600}};
    ASSERT_TRUE(s.configure(monday,monday+86400,1600,t,4));
    EXPECT_EQ(s.target(monday+6*3600-1,true).temperatureCentiC,1600);
    EXPECT_EQ(s.target(monday+6*3600,true).temperatureCentiC,2000);
    EXPECT_EQ(s.target(monday+7*3600,true).temperatureCentiC,2100);
    EXPECT_EQ(s.target(monday+8*3600,true).temperatureCentiC,1600);
    EXPECT_EQ(s.target(monday+6*3600,true).next->atUtc,monday+7*3600);
}

TEST(UtcSchedule, ExpiryOrUnvalidatedTimeCannotInventAnInfiniteFallbackSchedule) {
    UtcSchedule s;
    EXPECT_EQ(s.target(monday,true).state,ScheduleState::not_configured);
    const ScheduleTransition t[]{{monday,2000}};
    ASSERT_TRUE(s.configure(monday,monday+86400,1600,t,1));
    EXPECT_EQ(s.target(monday,false).state,ScheduleState::time_not_valid);
    EXPECT_FALSE(s.target(monday,false).temperatureCentiC);
    EXPECT_EQ(s.target(monday-1,true).state,ScheduleState::not_started);
    EXPECT_EQ(s.target(monday+86400,true).state,ScheduleState::expired);
    EXPECT_FALSE(s.target(monday+86400,true).temperatureCentiC);
}

TEST(UtcSchedule, InvalidCandidateLeavesTheEntireOldScheduleActive) {
    UtcSchedule s;
    const ScheduleTransition good[]{{monday,2000},{monday+60,2100}};
    ASSERT_TRUE(s.configure(monday,monday+86400,1600,good,2));
    const ScheduleTransition bad[]{{monday,3000},{monday,3100}};
    EXPECT_FALSE(s.configure(monday,monday+86400,1700,bad,2));
    EXPECT_EQ(s.baseCentiC(),1600);
    EXPECT_EQ(s.target(monday+60,true).temperatureCentiC,2100);
    EXPECT_FALSE(s.configure(monday,monday+17*86400,1600,good,2));
    EXPECT_FALSE(s.configure(monday,monday+86400,4000,good,2));
    EXPECT_FALSE(s.configure(monday,monday+86400,1600,nullptr,2));
    EXPECT_FALSE(s.configure(monday,monday+86400,1600,good,0));
    EXPECT_FALSE(s.configure(monday,monday+86400,1600,good,129));
}

TEST(UtcSchedule, NtpJumpsReevaluateCurrentTargetWithoutReplayingCommandsOrExtendingLeases) {
    UtcSchedule s;
    const ScheduleTransition t[]{{monday,1600},{monday+3600,2000},{monday+7200,1600}};
    ASSERT_TRUE(s.configure(monday,monday+86400,1600,t,3));
    EXPECT_EQ(s.target(monday+3601,true).temperatureCentiC,2000);
    EXPECT_EQ(s.target(monday+1,true).temperatureCentiC,1600);
    EXPECT_EQ(s.target(monday+7201,true).temperatureCentiC,1600);
    EXPECT_EQ(s.target(monday+3601,true).temperatureCentiC,2000); // pure evaluation, no side effects
}

TEST(UtcSchedule, BothFallFoldsAndTheInterveningBaseGapCanBeMaterializedUnambiguously) {
    // 25Oct2026 Europe/Amsterdam: 02:30CEST, rewind02:00CET,
    // 02:30CET,03:00CET. UTC table, not host-localtime guessing.
    const int64_t day=1792886400;
    const ScheduleTransition t[]{{day,1600},{day+1800,2000},{day+3600,1600},{day+5400,2000},{day+7200,1600}};
    UtcSchedule s; ASSERT_TRUE(s.configure(day,day+86400,1600,t,5));
    EXPECT_EQ(s.target(day+2700,true).temperatureCentiC,2000);
    EXPECT_EQ(s.target(day+4500,true).temperatureCentiC,1600);
    EXPECT_EQ(s.target(day+6300,true).temperatureCentiC,2000);
}
}
