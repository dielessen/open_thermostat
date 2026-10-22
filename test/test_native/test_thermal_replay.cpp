#include <gtest/gtest.h>
#include "control/ThermalReplay.h"
#include "control/ZoneRegulator.h"
#include "control/BoundedJson.h"
#include <cmath>
#include <fstream>
#include <cstdlib>
using namespace heating::control;
namespace {
constexpr int64_t epoch=1790812800;
auto scenario(){std::array<uint8_t,32> b{};b[0]=42;return b;}
ReplayProfile profile() {
    ReplayProfile p;p.reviewed=true;p.maximumGapMs=120000;p.minimumComparedMs=3600000;p.minimumOccupiedMs=600000;
    p.maximumDurationMs=UINT64_C(56)*86400000;p.minimumCoverageBp=9000;p.minimumInBandBp=9000;
    p.comfortBandCentiC=50;p.maximumOvershootCentiC=100;p.minimumCompletedBurns=3;p.minimumDeadlines=10;p.minimumDeadlineHitBp=8000;return p;
}
ReplayFrame frame(unsigned minute) {
    ReplayFrame f;f.baselineScenario=f.candidateScenario=scenario();f.monotonicMs=minute*60000ULL;f.utc=epoch+minute*60;
    f.sequence=minute+1;f.scheduleKnown=f.occupied=f.conditionsQualified=f.burnerStatesQualified=true;
    f.targetCentiC=2100;f.baselineTemperatureCentiC=f.candidateTemperatureCentiC=2100;
    f.baselineCv=f.candidateCv=minute%20>=5&&minute%20<15;
    if(minute>=5&&minute<=50&&minute%5==0){f.deadlineId=minute/5;f.deadlineTargetCentiC=2100;}
    return f;
}
void record(const char* name,const ReplayAssessment& r) {
    const char* path=std::getenv("OPENTHERMOSTAT_REPLAY_EVIDENCE");
    if(!path)return;
    ControlJson o(cJSON_CreateObject(),cJSON_Delete);ASSERT_NE(o,nullptr);cJSON_AddStringToObject(o.get(),"scenario",name);
    cJSON_AddStringToObject(o.get(),"scope","offline synthetic paired evaluation, NOT home history/actual fortnight/physical/model-release proof");
    cJSON_AddBoolToObject(o.get(),"accepted",r.accepted);cJSON_AddBoolToObject(o.get(),"comparable",r.comparable);
    cJSON_AddBoolToObject(o.get(),"comfort_noninferior",r.comfortNonInferior);cJSON_AddBoolToObject(o.get(),"cycling_available",r.cyclingAvailable);
    cJSON_AddBoolToObject(o.get(),"cycling_noninferior",r.cyclingNonInferior);cJSON_AddBoolToObject(o.get(),"timing_available",r.timingAvailable);
    cJSON_AddBoolToObject(o.get(),"timing_noninferior",r.timingNonInferior);cJSON_AddBoolToObject(o.get(),"safety_noninferior",r.safetyNonInferior);
    cJSON_AddStringToObject(o.get(),"reason",r.reason);cJSON_AddNumberToObject(o.get(),"total_ms",r.totalMs);
    cJSON_AddNumberToObject(o.get(),"compared_ms",r.comparedMs);cJSON_AddNumberToObject(o.get(),"occupied_compared_ms",r.occupiedComparedMs);
    cJSON_AddNumberToObject(o.get(),"excluded_ms",r.excludedMs);cJSON_AddNumberToObject(o.get(),"deadline_attempts",r.deadlineAttempts);
    cJSON_AddNumberToObject(o.get(),"qualified_deadlines",r.qualifiedDeadlines);
    const auto side=[&](const char* label,const ReplaySideScore& s){
        auto v=cJSON_AddObjectToObject(o.get(),label);
        const auto mae=ThermalReplay::meanAbsoluteErrorCentiC(s,r.occupiedComparedMs),burn=ThermalReplay::meanObservedBurnSec(s);
        if(mae)cJSON_AddNumberToObject(v,"sampled_mae_centi_c",*mae);else cJSON_AddNullToObject(v,"sampled_mae_centi_c");
        if(burn)cJSON_AddNumberToObject(v,"mean_observed_cv_run_sec",*burn);else cJSON_AddNullToObject(v,"mean_observed_cv_run_sec");
        cJSON_AddNumberToObject(v,"in_band_occupied_ms",s.inBandOccupiedMs);cJSON_AddNumberToObject(v,"overshoot_centi_c",s.maximumOvershootCentiC);
        cJSON_AddNumberToObject(v,"observed_cv_starts",s.observedCvStarts);cJSON_AddNumberToObject(v,"observed_cv_ms",s.cvMs);
        cJSON_AddNumberToObject(v,"completed_cv_runs",s.completedBurns);cJSON_AddNumberToObject(v,"deadline_hits",s.deadlineHits);
        cJSON_AddNumberToObject(v,"safety_violations",s.safetyViolations);
    };
    side("baseline",r.baseline);side("candidate",r.candidate);
    char* bytes=cJSON_PrintUnformatted(o.get());ASSERT_NE(bytes,nullptr);
    std::ofstream out(path,std::ios::app);out<<bytes<<"\n";cJSON_free(bytes);ASSERT_TRUE(out.good());
}
TEST(ThermalReplay, FullyPairedTraceHasExactSampledMetricsAndNoCounterfactualImprovementClaim) {
    ThermalReplay replay(profile(),scenario());
    for(unsigned i=0;i<=120;++i){ASSERT_TRUE(replay.add(frame(i)));}
    const auto r=replay.assessment();ASSERT_TRUE(r.accepted);
    EXPECT_EQ(r.totalMs,7200000u);EXPECT_EQ(r.comparedMs,r.totalMs);EXPECT_EQ(r.baseline.cvMs,3600000u);
    EXPECT_EQ(r.baseline.observedCvStarts,6u);EXPECT_EQ(r.baseline.completedBurns,6u);
    EXPECT_EQ(ThermalReplay::meanObservedBurnSec(r.baseline),600.0);
    EXPECT_EQ(ThermalReplay::meanAbsoluteErrorCentiC(r.candidate,r.occupiedComparedMs),0.0);
    EXPECT_EQ(r.deadlineAttempts,10u);EXPECT_EQ(r.candidate.deadlineHits,10u);record("known_identical_score_fixture",r);
}
TEST(ThermalReplay, CandidateInsideBandButWorseMaeIsRejectedNotSoldAsComfortImprovement) {
    ThermalReplay replay(profile(),scenario());
    for(unsigned i=0;i<=120;++i){auto f=frame(i);f.candidateTemperatureCentiC=2090;ASSERT_TRUE(replay.add(f));}
    auto r=replay.assessment();EXPECT_TRUE(r.comparable);EXPECT_FALSE(r.comfortNonInferior);EXPECT_FALSE(r.accepted);
    EXPECT_EQ(ThermalReplay::meanAbsoluteErrorCentiC(r.candidate,r.occupiedComparedMs),10.0);
    EXPECT_EQ(r.candidate.inBandOccupiedMs,r.occupiedComparedMs);record("worse_mae_even_inside_band_rejected",r);
}
TEST(ThermalReplay, ExtraOvershootAndExcessObservedCyclingAreIndependentRejectionGates) {
    for(int reason=0;reason<2;++reason){ThermalReplay replay(profile(),scenario());
        for(unsigned i=0;i<=120;++i){auto f=frame(i);
            if(reason==0)f.candidateTemperatureCentiC=2201;
            if(reason==1)f.candidateCv=i%10>=2&&i%10<7;
            ASSERT_TRUE(replay.add(f));}
        auto r=replay.assessment();EXPECT_FALSE(r.accepted);
        if(reason==0){EXPECT_EQ(r.candidate.maximumOvershootCentiC,101);EXPECT_FALSE(r.comfortNonInferior);}
        else{EXPECT_TRUE(r.comfortNonInferior);EXPECT_TRUE(r.cyclingAvailable);EXPECT_FALSE(r.cyclingNonInferior);
            EXPECT_EQ(r.candidate.observedCvStarts,12u);EXPECT_EQ(ThermalReplay::meanObservedBurnSec(r.candidate),300.0);}
        record(reason==0?"overshoot_rejected":"extra_cv_cycling_rejected",r);}
}
TEST(ThermalReplay, MissingTemperatureAndUnqualifiedDataNeverBecomeZeroOrGoodCoverage) {
    ThermalReplay replay(profile(),scenario());
    for(unsigned i=0;i<=120;++i){auto f=frame(i);if(i>=30&&i<60){f.candidateTemperatureCentiC.reset();f.conditionsQualified=false;}
        ASSERT_TRUE(replay.add(f));}
    auto r=replay.assessment();EXPECT_FALSE(r.comparable);EXPECT_FALSE(r.accepted);EXPECT_GT(r.excludedMs,1800000u);
    EXPECT_EQ(ThermalReplay::meanAbsoluteErrorCentiC({},0),std::nullopt);record("missing_data_not_zero",r);
}
TEST(ThermalReplay, UnknownCombustionKeepsCyclingUnavailableEvenWithGoodTemperature) {
    ThermalReplay replay(profile(),scenario());
    for(unsigned i=0;i<=120;++i){auto f=frame(i);f.burnerStatesQualified=false;ASSERT_TRUE(replay.add(f));}
    auto r=replay.assessment();EXPECT_TRUE(r.comfortNonInferior);EXPECT_FALSE(r.cyclingAvailable);EXPECT_FALSE(r.accepted);
    EXPECT_EQ(ThermalReplay::meanObservedBurnSec(r.candidate),std::nullopt);record("combustion_unknown_not_zero",r);
}
TEST(ThermalReplay, SafetyViolationCannotBeHiddenInAnExcludedFaultSample) {
    ThermalReplay replay(profile(),scenario());
    for(unsigned i=0;i<=120;++i){auto f=frame(i);if(i==70){f.conditionsQualified=false;f.candidateSafetyViolation=true;}
        ASSERT_TRUE(replay.add(f));}
    auto r=replay.assessment();EXPECT_TRUE(r.comparable);EXPECT_EQ(r.candidate.safetyViolations,1u);
    EXPECT_FALSE(r.safetyNonInferior);EXPECT_FALSE(r.accepted);record("fault_sample_violation_not_hidden",r);
}
TEST(ThermalReplay, MissingOrRepeatedDeadlineEvidenceCannotBeUpgradedByLaterCache) {
    ThermalReplay replay(profile(),scenario());
    for(unsigned i=0;i<=120;++i){auto f=frame(i);if(i==25){f.conditionsQualified=false;}
        if(i==26){f.deadlineId=5;f.deadlineTargetCentiC=2100;}
        ASSERT_TRUE(replay.add(f));}
    auto r=replay.assessment();EXPECT_EQ(r.deadlineAttempts,10u);EXPECT_EQ(r.qualifiedDeadlines,9u);
    EXPECT_EQ(r.candidate.deadlineHits,9u);EXPECT_FALSE(r.timingAvailable);EXPECT_FALSE(r.accepted);
    ThermalReplay skipped(profile(),scenario());auto f=frame(0);f.deadlineId=10;f.deadlineTargetCentiC=2100;ASSERT_TRUE(skipped.add(f));
    EXPECT_EQ(skipped.assessment().deadlineAttempts,10u);EXPECT_EQ(skipped.assessment().qualifiedDeadlines,1u);record("missing_deadline_not_recovered_from_cache",r);
}
TEST(ThermalReplay, WorseDeadlineResultIsCountedEvenWhenMostOrdinarySamplesAreWarm) {
    ThermalReplay replay(profile(),scenario());
    for(unsigned i=0;i<=120;++i){auto f=frame(i);if(f.deadlineId&&f.deadlineId<=3)f.candidateTemperatureCentiC=2030;ASSERT_TRUE(replay.add(f));}
    auto r=replay.assessment();EXPECT_TRUE(r.timingAvailable);EXPECT_EQ(r.candidate.deadlineHits,7u);
    EXPECT_FALSE(r.timingNonInferior);EXPECT_FALSE(r.accepted);record("arrival_seven_of_ten_rejected",r);
}
TEST(ThermalReplay, UnpairedClockSequenceOrBudgetFailureLatchesCannotResumeWithGoodData) {
    for(int reason=0;reason<6;++reason){ThermalReplay replay(profile(),scenario());ASSERT_TRUE(replay.add(frame(0)));auto f=frame(1);
        if(reason==0)f.candidateScenario[1]++;
        if(reason==1)f.sequence=1;
        if(reason==2)f.monotonicMs=0;
        if(reason==3)f.utc+=3600;
        if(reason==4)f.monotonicMs=UINT64_C(1)<<63;
        if(reason==5)f.deadlineId=1; //Missing immutable deadline target.
        EXPECT_FALSE(replay.add(f));EXPECT_FALSE(replay.add(frame(2)));
        EXPECT_STREQ(replay.assessment().reason,"replay_invalid_or_unpaired_trace");}
    auto p=profile();p.reviewed=false;ThermalReplay bad(p,scenario());EXPECT_FALSE(bad.add(frame(0)));
}
TEST(ThermalReplay, GapAndSequenceLossExcludeIntervalsAndCannotCompleteInventedBurnRuns) {
    ThermalReplay gap(profile(),scenario());ASSERT_TRUE(gap.add(frame(0)));
    auto f=frame(20);f.sequence=2;ASSERT_TRUE(gap.add(f));EXPECT_EQ(gap.assessment().excludedMs,1200000u);
    ThermalReplay skipped(profile(),scenario());ASSERT_TRUE(skipped.add(frame(0)));f=frame(1);f.sequence=3;ASSERT_TRUE(skipped.add(f));
    EXPECT_EQ(skipped.assessment().excludedMs,60000u);
    ThermalReplay initialHot(profile(),scenario());
    for(unsigned i=0;i<=10;++i){f=frame(i);f.baselineCv=f.candidateCv=i<10;ASSERT_TRUE(initialHot.add(f));}
    auto r=initialHot.assessment();EXPECT_EQ(r.candidate.cvMs,600000u);EXPECT_EQ(r.candidate.observedCvStarts,0u);
    EXPECT_EQ(r.candidate.completedBurns,0u);EXPECT_EQ(ThermalReplay::meanObservedBurnSec(r.candidate),std::nullopt);
}
struct Plant {
    double room=21.0,stored=0;
    int16_t temperature()const{return static_cast<int16_t>(std::lround(room*100));}
    void step(bool heat,double outside,double heatGain){
        // Transparent SYNTHETIC two-state plant, identical exogenous input in
        // both runs. Parameters are NOT fitted/claimed for Mark's installation.
        stored+=((heat?heatGain:0.0)-stored)*.20;
        room+=stored-(room-outside)*.001;
    }
};
TEST(ThermalReplay, ActualRegulatorDisabledAdaptiveDefaultMatchesSamePlantBaselineAcrossWeatherAndFaults) {
    for(int climate=0;climate<2;++climate) {
        ThermalReplay replay(profile(),scenario());ZoneRegulator baseline,candidate;Plant a,b;
        for(unsigned i=0;i<=1440;++i){
            const bool fault=i>=600&&i<610;const double outside=climate==0?5.0:15.0;
            auto f=frame(i);f.deadlineId=0;f.deadlineTargetCentiC.reset();
            //11attempts: fault at600min excludes one; still require10actually
            //qualified arrivals, not a weaker gate or a cached recovery hit.
            if(i>=120&&i<=1320&&i%120==0){f.deadlineId=(i-120)/120+1;f.deadlineTargetCentiC=2100;}
            f.baselineTemperatureCentiC=a.temperature();f.candidateTemperatureCentiC=b.temperature();
            f.conditionsQualified=!fault;
            const auto x=baseline.step(f.monotonicMs,a.temperature(),2100,!fault);
            const auto y=candidate.step(f.monotonicMs,b.temperature(),2100,!fault);
            f.baselineCv=x.demand;f.candidateCv=y.demand;f.baselineSafetyViolation=fault&&x.demand;f.candidateSafetyViolation=fault&&y.demand;
            ASSERT_TRUE(replay.add(f));EXPECT_EQ(x.demand,y.demand);EXPECT_EQ(a.temperature(),b.temperature());
            a.step(x.demand,outside,.08);b.step(y.demand,outside,.08);
        }
        auto r=replay.assessment();EXPECT_TRUE(r.comparable);EXPECT_TRUE(r.safetyNonInferior);EXPECT_TRUE(r.accepted)<<r.reason;
        EXPECT_EQ(r.baseline.absoluteErrorTwiceCentiMs,r.candidate.absoluteErrorTwiceCentiMs);
        EXPECT_EQ(r.baseline.observedCvStarts,r.candidate.observedCvStarts);
        // This is ONLY a default-disabled control equivalence regression.
        // It does not establish adaptive/coast/curve benefit or home-history proof.
        record(climate==0?"actual_regulator_disabled_models_cold_synthetic_plant":"actual_regulator_disabled_models_mild_synthetic_plant",r);
    }
}
TEST(ThermalReplay, ActualRegulatorComparisonRejectsFaultBypassingCandidateOnSameSyntheticPlant) {
    ThermalReplay replay(profile(),scenario());ZoneRegulator baseline,candidate;Plant a,b;
    for(unsigned i=0;i<=180;++i){
        auto f=frame(i);const bool fault=i>=60&&i<65;
        f.baselineTemperatureCentiC=a.temperature();f.candidateTemperatureCentiC=b.temperature();f.conditionsQualified=!fault;
        f.baselineCv=baseline.step(f.monotonicMs,a.temperature(),2100,!fault).demand;
        f.candidateCv=candidate.step(f.monotonicMs,b.temperature(),2100,true).demand||fault; //Deliberately bad test candidate.
        f.candidateSafetyViolation=fault&&f.candidateCv;
        ASSERT_TRUE(replay.add(f));a.step(f.baselineCv,5,.08);b.step(f.candidateCv,5,.08);
    }
    auto r=replay.assessment();EXPECT_GT(r.candidate.safetyViolations,0u);EXPECT_FALSE(r.safetyNonInferior);EXPECT_FALSE(r.accepted);
    const auto candidateMae=ThermalReplay::meanAbsoluteErrorCentiC(r.candidate,r.occupiedComparedMs);
    const auto baselineMae=ThermalReplay::meanAbsoluteErrorCentiC(r.baseline,r.occupiedComparedMs);
    ASSERT_TRUE(candidateMae&&baselineMae);EXPECT_LT(*candidateMae,*baselineMae); //Better MAE is NOT a safety waiver.
    record("actual_regulator_bad_candidate_fault_bypass_rejected",r);
}
}
