#pragma once
#include "UtcSchedule.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <optional>

namespace heating::control {
// Offline paired-trace evaluation only. NEVER supplies model/source admission,
// heating permission or production transport input.
struct ReplayProfile {
    bool reviewed=false;
    uint32_t maximumGapMs=0;
    uint64_t minimumComparedMs=0,minimumOccupiedMs=0,maximumDurationMs=0;
    uint16_t minimumCoverageBp=0,minimumInBandBp=0,comfortBandCentiC=0,maximumOvershootCentiC=0;
    uint16_t allowedExtraMaeCentiC=0,allowedExtraOvershootCentiC=0,minimumDeadlineHitBp=0;
    uint8_t minimumCompletedBurns=0,minimumDeadlines=0;
    bool valid()const {
        return reviewed&&maximumGapMs>=1000&&maximumGapMs<=300000
            &&minimumComparedMs>=3600000&&minimumOccupiedMs>=60000&&minimumOccupiedMs<=minimumComparedMs
            &&maximumDurationMs>=minimumComparedMs&&maximumDurationMs<=UINT64_C(56)*86400000
            &&minimumCoverageBp>=9000&&minimumCoverageBp<=10000&&minimumInBandBp>=9000&&minimumInBandBp<=10000
            &&comfortBandCentiC>=10&&comfortBandCentiC<=50&&maximumOvershootCentiC>=50&&maximumOvershootCentiC<=100
            &&allowedExtraMaeCentiC<=10&&allowedExtraOvershootCentiC<=10
            &&minimumCompletedBurns>=3&&minimumCompletedBurns<=100&&minimumDeadlines>=10&&minimumDeadlines<=100
            &&minimumDeadlineHitBp>=8000&&minimumDeadlineHitBp<=10000;
    }
};
struct ReplayFrame {
    // Both result streams MUST originate from exactly the same exogenous scenario.
    std::array<uint8_t,32> baselineScenario{},candidateScenario{};
    uint64_t monotonicMs=0;int64_t utc=0;uint32_t sequence=0;
    bool scheduleKnown=false,occupied=false,conditionsQualified=false,burnerStatesQualified=false;
    std::optional<int16_t> targetCentiC,baselineTemperatureCentiC,candidateTemperatureCentiC;
    bool baselineCv=false,candidateCv=false,baselineSafetyViolation=false,candidateSafetyViolation=false;
    // One immutable scheduled arrival event; unknown data at that deadline is NOT a hit.
    uint32_t deadlineId=0;std::optional<int16_t> deadlineTargetCentiC;
};
struct ReplaySideScore {
    uint64_t absoluteErrorTwiceCentiMs=0,inBandOccupiedMs=0,cvMs=0,completedBurnMs=0;
    uint32_t observedCvStarts=0,completedBurns=0,deadlineHits=0,safetyViolations=0;
    uint16_t maximumOvershootCentiC=0;
};
struct ReplayAssessment {
    bool comparable=false,safetyNonInferior=false,comfortNonInferior=false;
    bool cyclingAvailable=false,cyclingNonInferior=false,timingAvailable=false,timingNonInferior=false,accepted=false;
    uint64_t totalMs=0,comparedMs=0,occupiedComparedMs=0,occupiedKnownMs=0,cvQualifiedMs=0,excludedMs=0;
    uint32_t deadlineAttempts=0,qualifiedDeadlines=0;
    ReplaySideScore baseline,candidate;
    const char* reason="replay_insufficient_data";
};
class ThermalReplay {
public:
    ThermalReplay(ReplayProfile profile,std::array<uint8_t,32> scenario):profile_(profile),scenario_(scenario) {
        failed_=!profile_.valid()||!std::any_of(scenario.begin(),scenario.end(),[](auto b){return b!=0;});
    }
    bool add(const ReplayFrame& in) {
        if(failed_)return false;
        if(!in.sequence||in.utc<UtcSchedule::minimumUtcSecond||in.utc>=UtcSchedule::maximumUtcSecond
            ||in.baselineScenario!=scenario_||in.candidateScenario!=scenario_
            ||(bool(in.deadlineId)!=in.deadlineTargetCentiC.has_value())
            ||(in.deadlineTargetCentiC&&!UtcSchedule::validTemperature(*in.deadlineTargetCentiC)))return fail();
        uint64_t dt=0;bool continuous=true;
        if(have_) {
            if(in.monotonicMs<=last_.monotonicMs||in.sequence<=last_.sequence)return fail();
            dt=in.monotonicMs-last_.monotonicMs;
            if(dt>profile_.maximumDurationMs||totalMs_>profile_.maximumDurationMs-dt)return fail();
            const int64_t clockError=(in.utc-last_.utc)*1000-static_cast<int64_t>(dt);
            if(clockError < -2000||clockError>2000)return fail();
            continuous=dt<=profile_.maximumGapMs&&in.sequence-last_.sequence==1;
        }
        // Never hide a safety violation by labelling that sample unqualified.
        baseline_.safetyViolations+=in.baselineSafetyViolation?1:0;
        candidate_.safetyViolations+=in.candidateSafetyViolation?1:0;
        const bool pointQualified=qualified(in);
        if(pointQualified&&in.occupied) {
            observeOvershoot(baseline_,*in.baselineTemperatureCentiC,*in.targetCentiC);
            observeOvershoot(candidate_,*in.candidateTemperatureCentiC,*in.targetCentiC);
        }
        if(in.deadlineId>deadlineHighwater_) {
            deadlineAttempts_+=in.deadlineId-deadlineHighwater_;deadlineHighwater_=in.deadlineId;
            if(pointQualified) {
                ++qualifiedDeadlines_;
                baseline_.deadlineHits+=within(*in.baselineTemperatureCentiC,*in.deadlineTargetCentiC)?1:0;
                candidate_.deadlineHits+=within(*in.candidateTemperatureCentiC,*in.deadlineTargetCentiC)?1:0;
            }
        }
        if(have_) {
            totalMs_+=dt;
            if(last_.scheduleKnown&&in.scheduleKnown&&last_.occupied&&in.occupied)occupiedKnownMs_+=dt;
            const bool comfortInterval=continuous&&pointQualified&&qualified(last_)&&last_.targetCentiC==in.targetCentiC;
            if(comfortInterval) {
                comparedMs_+=dt;
                if(last_.occupied&&in.occupied) {
                    occupiedComparedMs_+=dt;
                    integrateComfort(baseline_,*last_.baselineTemperatureCentiC,*in.baselineTemperatureCentiC,*in.targetCentiC,dt);
                    integrateComfort(candidate_,*last_.candidateTemperatureCentiC,*in.candidateTemperatureCentiC,*in.targetCentiC,dt);
                }
            } else excludedMs_+=dt;
            if(continuous&&last_.burnerStatesQualified&&in.burnerStatesQualified) {
                cvQualifiedMs_+=dt;
                integrateCv(baseline_,0,last_.baselineCv,in.baselineCv,in.monotonicMs,dt);
                integrateCv(candidate_,1,last_.candidateCv,in.candidateCv,in.monotonicMs,dt);
            }else running_={};
        }
        last_=in;have_=true;return true;
    }
    ReplayAssessment assessment()const {
        ReplayAssessment r;
        r.totalMs=totalMs_;r.comparedMs=comparedMs_;r.occupiedComparedMs=occupiedComparedMs_;
        r.occupiedKnownMs=occupiedKnownMs_;r.cvQualifiedMs=cvQualifiedMs_;r.excludedMs=excludedMs_;
        r.deadlineAttempts=deadlineAttempts_;r.qualifiedDeadlines=qualifiedDeadlines_;r.baseline=baseline_;r.candidate=candidate_;
        if(failed_){r.reason="replay_invalid_or_unpaired_trace";return r;}
        if(comparedMs_<profile_.minimumComparedMs||occupiedComparedMs_<profile_.minimumOccupiedMs
            ||!coverage(comparedMs_,totalMs_)||!coverage(occupiedComparedMs_,occupiedKnownMs_))return r;
        r.comparable=true;
        r.safetyNonInferior=baseline_.safetyViolations==0&&candidate_.safetyViolations==0;
        r.comfortNonInferior=atLeast(candidate_.inBandOccupiedMs,occupiedComparedMs_,profile_.minimumInBandBp)
            &&candidate_.inBandOccupiedMs>=baseline_.inBandOccupiedMs
            &&candidate_.absoluteErrorTwiceCentiMs<=baseline_.absoluteErrorTwiceCentiMs
                +UINT64_C(2)*profile_.allowedExtraMaeCentiC*occupiedComparedMs_
            &&candidate_.maximumOvershootCentiC<=profile_.maximumOvershootCentiC
            &&candidate_.maximumOvershootCentiC<=baseline_.maximumOvershootCentiC+profile_.allowedExtraOvershootCentiC;
        r.cyclingAvailable=coverage(cvQualifiedMs_,totalMs_)
            &&baseline_.completedBurns>=profile_.minimumCompletedBurns&&candidate_.completedBurns>=profile_.minimumCompletedBurns
            &&baseline_.cvMs&&candidate_.cvMs;
        if(r.cyclingAvailable) {
            // Compare rates without division or incomparable observation periods.
            r.cyclingNonInferior=uint64_t(candidate_.observedCvStarts)*baseline_.cvMs<=uint64_t(baseline_.observedCvStarts)*candidate_.cvMs
                &&candidate_.completedBurnMs*baseline_.completedBurns>=baseline_.completedBurnMs*candidate_.completedBurns;
        }
        r.timingAvailable=qualifiedDeadlines_>=profile_.minimumDeadlines;
        if(r.timingAvailable)r.timingNonInferior=atLeast(candidate_.deadlineHits,deadlineAttempts_,profile_.minimumDeadlineHitBp)
            &&candidate_.deadlineHits>=baseline_.deadlineHits;
        r.accepted=r.safetyNonInferior&&r.comfortNonInferior&&r.cyclingNonInferior&&r.timingNonInferior;
        r.reason=r.accepted?"replay_paired_noninferiority_pass":!r.safetyNonInferior?"replay_safety_violation":
            !r.comfortNonInferior?"replay_comfort_worse":!r.cyclingAvailable?"replay_cycling_evidence_missing":
            !r.cyclingNonInferior?"replay_cycling_worse":!r.timingAvailable?"replay_deadline_evidence_missing":"replay_deadline_worse";
        return r;
    }
    static std::optional<double> meanAbsoluteErrorCentiC(const ReplaySideScore& side,uint64_t occupiedComparedMs) {
        if(!occupiedComparedMs)return {};
        return static_cast<double>(side.absoluteErrorTwiceCentiMs)/(2.0*static_cast<double>(occupiedComparedMs));
    }
    static std::optional<double> meanObservedBurnSec(const ReplaySideScore& side) {
        if(!side.completedBurns)return {};
        return static_cast<double>(side.completedBurnMs)/(1000.0*side.completedBurns);
    }
private:
    bool fail(){failed_=true;return false;}
    bool within(int16_t temperature,int16_t target)const{return std::abs(int32_t(temperature)-target)<=profile_.comfortBandCentiC;}
    static bool qualified(const ReplayFrame& in) {
        return in.conditionsQualified&&in.scheduleKnown&&in.targetCentiC&&in.baselineTemperatureCentiC&&in.candidateTemperatureCentiC
            &&UtcSchedule::validTemperature(*in.targetCentiC)&&UtcSchedule::validTemperature(*in.baselineTemperatureCentiC)
            &&UtcSchedule::validTemperature(*in.candidateTemperatureCentiC);
    }
    static bool atLeast(uint64_t numerator,uint64_t denominator,uint16_t bp) {
        return denominator&&numerator*10000>=denominator*bp;
    }
    bool coverage(uint64_t valid,uint64_t total)const{return atLeast(valid,total,profile_.minimumCoverageBp);}
    static void observeOvershoot(ReplaySideScore& side,int16_t temperature,int16_t target) {
        if(temperature>target)side.maximumOvershootCentiC=std::max(side.maximumOvershootCentiC,static_cast<uint16_t>(temperature-target));
    }
    void integrateComfort(ReplaySideScore& side,int16_t before,int16_t current,int16_t target,uint64_t dt) {
        // Sampled trapezoidal ABS error (not continuous physical measurement).
        side.absoluteErrorTwiceCentiMs+=uint64_t(std::abs(int32_t(before)-target)+std::abs(int32_t(current)-target))*dt;
        if(within(before,target)&&within(current,target))side.inBandOccupiedMs+=dt;
    }
    void integrateCv(ReplaySideScore& side,size_t index,bool before,bool current,uint64_t now,uint64_t dt) {
        if(before)side.cvMs+=dt;
        if(!before&&current){++side.observedCvStarts;running_[index]=true;runAt_[index]=now;}
        if(before&&!current&&running_[index]){++side.completedBurns;side.completedBurnMs+=now-runAt_[index];running_[index]=false;}
    }
    ReplayProfile profile_;std::array<uint8_t,32> scenario_;ReplayFrame last_;
    ReplaySideScore baseline_,candidate_;
    bool failed_=false,have_=false;std::array<bool,2> running_{};std::array<uint64_t,2>runAt_{};
    uint64_t totalMs_=0,comparedMs_=0,occupiedComparedMs_=0,occupiedKnownMs_=0,cvQualifiedMs_=0,excludedMs_=0;
    uint32_t deadlineHighwater_=0,deadlineAttempts_=0,qualifiedDeadlines_=0;
};
}
