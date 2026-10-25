#pragma once
#include "UtcSchedule.h"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>

namespace heating::control {

enum class LearningMode { disabled, frozen, shadow };
struct ThermalModelProfile {
    bool reviewed=false;
    uint32_t maximumGapMs=0, minimumOffSec=0, minimumRunSec=0, maximumRunSec=0;
    uint16_t minimumRiseCentiC=0, maximumRiseCentiC=0;
    uint16_t minimumRateCentiCPerHour=0, maximumRateCentiCPerHour=0;
    uint16_t outdoorDriftCentiC=0, waterDriftCentiC=0;
    uint8_t minimumStarts=0, minimumDistinctDays=0, minimumSpanDays=0, maximumAgeDays=0;
    uint8_t minimumComparableStarts=0;
    uint16_t comparableOutdoorRadiusCentiC=0, comparableWaterRadiusCentiC=0, comparableRoomRadiusCentiC=0;
    uint16_t minimumOutdoorSpanCentiC=0;
    uint32_t maximumLeadSec=0, marginSec=0;
    bool valid() const {
        return reviewed && maximumGapMs>=1000 && maximumGapMs<=300000
            && minimumOffSec>=300 && minimumOffSec<=21600
            && minimumRunSec>=900 && maximumRunSec>=minimumRunSec && maximumRunSec<=21600
            && minimumRiseCentiC>=20 && maximumRiseCentiC>=minimumRiseCentiC && maximumRiseCentiC<=1500
            && minimumRateCentiCPerHour>=1 && maximumRateCentiCPerHour>=minimumRateCentiCPerHour
            && maximumRateCentiCPerHour<=3000 && outdoorDriftCentiC>=10 && outdoorDriftCentiC<=500
            && waterDriftCentiC>=10 && waterDriftCentiC<=1000
            && minimumStarts>=6 && minimumStarts<=16 && minimumDistinctDays>=6
            && minimumDistinctDays<=minimumStarts && minimumSpanDays>=14 && minimumSpanDays<=60
            && maximumAgeDays>=minimumSpanDays+2 && maximumAgeDays<=120
            && minimumComparableStarts>=3 && minimumComparableStarts<=minimumStarts
            && comparableOutdoorRadiusCentiC>=10 && comparableOutdoorRadiusCentiC<=500
            && comparableWaterRadiusCentiC>=10 && comparableWaterRadiusCentiC<=1000
            && comparableRoomRadiusCentiC>=10 && comparableRoomRadiusCentiC<=200
            && minimumOutdoorSpanCentiC>=100 && minimumOutdoorSpanCentiC<=2000
            && maximumLeadSec>=60 && maximumLeadSec<=14400 && marginSec<=600;
    }
};
struct ThermalObservation {
    // Supplied only after existing owner provenance/session/sample admission.
    bool profileQualified=false, sourceVerified=false, conditionsKnown=false;
    bool deliveryKnown=false, deliveredHeat=false, clockTrusted=false;
    bool normalControl=false, dhw=false, windowOpen=false, fault=false;
    bool manualTest=false, unexplainedGain=false;
    uint64_t monotonicMs=0;
    int64_t utc=0;
    uint32_t reportSequence=0, admissionEpoch=0, targetGeneration=0;
    std::optional<int16_t> temperatureCentiC,outdoorCentiC,waterCentiC;
};
struct ThermalRun {
    uint32_t startUtc=0,endUtc=0,durationSec=0;
    int16_t riseCentiC=0,outdoorCentiC=0,waterCentiC=0,startTemperatureCentiC=0;
};
struct ThermalModelSnapshot {
    static constexpr size_t capacity=16;
    uint8_t algorithmVersion=1,count=0;
    std::array<uint8_t,32> bindingDigest{};
    std::array<ThermalRun,capacity> runs{};
};
struct StartAdvisory {
    std::optional<int64_t> plannedStartUtc;
    uint32_t leadSec=0;
    uint8_t eligibleStarts=0,comparableStarts=0,distinctDays=0;
    uint16_t coveredDays=0;
    bool startNow=false,lateForTarget=false;
    const char* reason="learning_disabled";
    // NEVER a boiler/actuator enable or an applied control parameter.
};
class ThermalResponseModel {
public:
    ThermalResponseModel(ThermalModelProfile p,std::array<uint8_t,32> binding):profile_(p) {
        data_.bindingDigest=binding;
    }
    void setMode(LearningMode mode) {
        mode_=(mode==LearningMode::shadow || mode==LearningMode::frozen)?mode:LearningMode::disabled;
        invalidateAdmission();
    }
    LearningMode mode() const {return mode_;}
    // Admission loss must NOT erase replay high-water marks. Epoch is an owner-issued
    // monotonically increasing generation; boot-local owner must never reuse it.
    void invalidateAdmission() {haveReport_=liveOk_=offKnown_=warming_=false;}
    void storageFault() {storageHealthy_=false;mode_=LearningMode::disabled;invalidateAdmission();status_="model_storage_fault";}
    void reset() {
        const auto binding=data_.bindingDigest;data_={};data_.bindingDigest=binding;
        invalidateAdmission();status_="model_reset";
    }
    const char* status() const {return status_;}
    ThermalModelSnapshot snapshot() const {return data_;}
    bool restore(const ThermalModelSnapshot& candidate) {
        if (!profileValid() || candidate.algorithmVersion!=1 || candidate.bindingDigest!=data_.bindingDigest
            || candidate.count>candidate.capacity) return false;
        for(size_t i=0;i<candidate.count;++i)
            if (!validRun(candidate.runs[i]) || (i && candidate.runs[i].startUtc<=candidate.runs[i-1].endUtc))
                return false;
        data_=candidate;storageHealthy_=true;mode_=LearningMode::disabled;
        invalidateAdmission();status_="model_restored_no_admission";return true;
    }
    // Returns true ONLY for one complete new qualified warm-up; no IO/automatic save.
    bool observe(const ThermalObservation& in) {
        if (!profileValid() || !storageHealthy_ || mode_==LearningMode::disabled) {
            invalidateAdmission();status_=!storageHealthy_?"model_storage_fault":"learning_disabled";return false;
        }
        if (!usable(in)) {
            invalidateAdmission();status_="learning_conditions_unverified";return false;
        }
        if (highestEpoch_ && (in.admissionEpoch<highestEpoch_
            || (in.admissionEpoch==highestEpoch_ && in.reportSequence<=highestSequence_))) {
            invalidateAdmission();status_="cached_or_old_observation";return false;
        }
        if (in.admissionEpoch!=highestEpoch_) {invalidateAdmission();highestSequence_=0;}
        highestEpoch_=in.admissionEpoch;highestSequence_=in.reportSequence;
        bool discontinuity=false;
        if (haveReport_) {
            if (in.monotonicMs<last_.monotonicMs) discontinuity=true;
            else {
                const auto dt=in.monotonicMs-last_.monotonicMs;
                // Bound unsigned elapsed time BEFORE conversion/multiplication.
                // A corrupt/overflowing source clock must not reach signed rate
                // arithmetic, even though its gap would later be rejected.
                if (dt>profile_.maximumGapMs || in.targetGeneration!=last_.targetGeneration)
                    discontinuity=true;
                else {
                    const auto wallMs=(in.utc-last_.utc)*1000;
                    const auto timingError=wallMs-static_cast<int64_t>(dt);
                    if (timingError < -2000 || timingError>2000) discontinuity=true;
                    const int64_t change=*in.temperatureCentiC-*last_.temperatureCentiC;
                    if ((!dt && change) || (dt && (change>0?change:-change)*3600000
                            >static_cast<int64_t>(profile_.maximumRateCentiCPerHour)*static_cast<int64_t>(dt)))
                        discontinuity=true;
                }
            }
        }
        if (discontinuity) {
            warming_=offKnown_=liveOk_=false;last_=in;haveReport_=true;
            status_="learning_discontinuity";return false;
        }
        liveOk_=true;freshAt_=in.monotonicMs;
        bool accepted=false;
        if (mode_==LearningMode::frozen) {
            warming_=offKnown_=false;status_="learning_frozen";
        } else if (warming_ && !discontinuity) {
            const auto dt=in.monotonicMs-last_.monotonicMs;
            runOutdoorIntegral_+=static_cast<int64_t>(*last_.outdoorCentiC)*static_cast<int64_t>(dt);
            runWaterIntegral_+=static_cast<int64_t>(*last_.waterCentiC)*static_cast<int64_t>(dt);
            minimumOutdoor_=std::min(minimumOutdoor_,*in.outdoorCentiC);
            maximumOutdoor_=std::max(maximumOutdoor_,*in.outdoorCentiC);
            if (in.deliveredHeat) {
                minimumWater_=std::min(minimumWater_,*in.waterCentiC);
                maximumWater_=std::max(maximumWater_,*in.waterCentiC);
            }
            const uint64_t elapsed=in.monotonicMs-runAt_;
            if (maximumOutdoor_-minimumOutdoor_>profile_.outdoorDriftCentiC
                || maximumWater_-minimumWater_>profile_.waterDriftCentiC
                || elapsed>static_cast<uint64_t>(profile_.maximumRunSec)*1000
                || *in.temperatureCentiC<runTemperature_-20) {
                warming_=offKnown_=false;status_="learning_run_rejected";
            } else if (!in.deliveredHeat) {
                ThermalRun record{static_cast<uint32_t>(runUtc_),static_cast<uint32_t>(in.utc),
                    static_cast<uint32_t>(elapsed/1000),
                    static_cast<int16_t>(*in.temperatureCentiC-runTemperature_),
                    static_cast<int16_t>(elapsed?runOutdoorIntegral_/static_cast<int64_t>(elapsed):0),
                    static_cast<int16_t>(elapsed?runWaterIntegral_/static_cast<int64_t>(elapsed):0),runTemperature_};
                if (elapsed%1000==0 && validRun(record)
                    && (!data_.count || record.startUtc>data_.runs[data_.count-1].endUtc)) {
                    if (data_.count==data_.capacity) {
                        for(size_t i=1;i<data_.capacity;++i)data_.runs[i-1]=data_.runs[i];
                        --data_.count;
                    }
                    data_.runs[data_.count++]=record;accepted=true;status_="warmup_observed";
                } else status_="learning_run_rejected";
                warming_=false;offKnown_=true;offAt_=in.monotonicMs;
            }
        } else if (!in.deliveredHeat) {
            if (!offKnown_) {offKnown_=true;offAt_=in.monotonicMs;}
            status_="learning_known_off";
        } else if (offKnown_ && in.monotonicMs>=offAt_
                   && in.monotonicMs-offAt_>=static_cast<uint64_t>(profile_.minimumOffSec)*1000) {
            warming_=true;offKnown_=false;runAt_=in.monotonicMs;runUtc_=in.utc;
            runTemperature_=*in.temperatureCentiC;minimumOutdoor_=maximumOutdoor_=*in.outdoorCentiC;
            minimumWater_=maximumWater_=*in.waterCentiC;
            runOutdoorIntegral_=runWaterIntegral_=0;status_="learning_warmup";
        } else {offKnown_=false;status_="learning_no_independent_start";}
        last_=in;haveReport_=true;return accepted;
    }
    StartAdvisory propose(uint64_t now,int64_t utc,const ScheduleTarget& schedule,
                          std::optional<int16_t> plannedWaterCentiC) const {
        StartAdvisory r;
        if (mode_==LearningMode::disabled || !profileValid() || !storageHealthy_) return r;
        if (utc<UtcSchedule::minimumUtcSecond || utc>=UtcSchedule::maximumUtcSecond) {
            r.reason="model_time_not_valid";return r;
        }
        if (!liveOk_ || !haveReport_ || now<freshAt_ || now-freshAt_>=profile_.maximumGapMs) {
            r.reason="model_source_not_fresh";return r;
        }
        const int64_t timingError=(utc-last_.utc)*1000-static_cast<int64_t>(now-last_.monotonicMs);
        if (timingError < -2000 || timingError>2000 || !last_.clockTrusted) {
            r.reason="model_time_not_valid";return r;
        }
        if (schedule.state!=ScheduleState::active || !schedule.next
            || schedule.next->atUtc<=utc || schedule.next->atUtc>=UtcSchedule::maximumUtcSecond
            || schedule.next->atUtc-utc>profile_.maximumLeadSec
            || !UtcSchedule::validTemperature(schedule.next->temperatureCentiC)) {
            r.reason="model_no_imminent_transition";return r;
        }
        if (!plannedWaterCentiC || *plannedWaterCentiC<500 || *plannedWaterCentiC>9000) {
            r.reason="model_water_conditions_unknown";return r;
        }
        const int32_t deficit=schedule.next->temperatureCentiC-*last_.temperatureCentiC;
        if (deficit<=20) {r.reason="model_no_warmup_needed";return r;}
        std::array<uint32_t,ThermalModelSnapshot::capacity> predictions{},days{};
        uint32_t earliest=UINT32_MAX,latest=0;
        int16_t minimumOutdoor=6000,maximumOutdoor=-6000;
        for(size_t i=0;i<data_.count;++i) {
            const auto& record=data_.runs[i];
            if (utc<record.endUtc || utc-record.endUtc>static_cast<int64_t>(profile_.maximumAgeDays)*86400) continue;
            ++r.eligibleStarts;earliest=std::min(earliest,record.startUtc);latest=std::max(latest,record.endUtc);
            minimumOutdoor=std::min(minimumOutdoor,record.outdoorCentiC);
            maximumOutdoor=std::max(maximumOutdoor,record.outdoorCentiC);
            const uint32_t day=record.startUtc/86400;
            if (std::find(days.begin(),days.begin()+r.distinctDays,day)==days.begin()+r.distinctDays)
                days[r.distinctDays++]=day;
            const int32_t outdoorDifference=record.outdoorCentiC-*last_.outdoorCentiC;
            const int32_t waterDifference=record.waterCentiC-*plannedWaterCentiC;
            const int32_t roomDifference=record.startTemperatureCentiC-*last_.temperatureCentiC;
            if (outdoorDifference < -profile_.comparableOutdoorRadiusCentiC
                || outdoorDifference>profile_.comparableOutdoorRadiusCentiC
                || waterDifference < -profile_.comparableWaterRadiusCentiC
                || waterDifference>profile_.comparableWaterRadiusCentiC
                || roomDifference < -profile_.comparableRoomRadiusCentiC
                || roomDifference>profile_.comparableRoomRadiusCentiC
                || deficit>record.riseCentiC) continue; // no warm-up-range extrapolation
            const uint64_t numerator=static_cast<uint64_t>(deficit)*record.durationSec;
            predictions[r.comparableStarts++]=static_cast<uint32_t>((numerator+record.riseCentiC-1)/record.riseCentiC);
        }
        if (r.eligibleStarts) r.coveredDays=static_cast<uint16_t>((latest-earliest)/86400);
        if (r.eligibleStarts<profile_.minimumStarts || r.distinctDays<profile_.minimumDistinctDays
            || r.coveredDays<profile_.minimumSpanDays
            || maximumOutdoor-minimumOutdoor<profile_.minimumOutdoorSpanCentiC
            || r.comparableStarts<profile_.minimumComparableStarts) {
            r.reason="model_insufficient_evidence";return r;
        }
        std::sort(predictions.begin(),predictions.begin()+r.comparableStarts);
        const uint64_t lead=static_cast<uint64_t>(predictions[r.comparableStarts/2])+profile_.marginSec;
        if (lead>profile_.maximumLeadSec) {r.reason="model_lead_limit_exceeded";return r;}
        r.leadSec=static_cast<uint32_t>(lead);r.plannedStartUtc=schedule.next->atUtc-r.leadSec;
        r.startNow=utc>=*r.plannedStartUtc;r.lateForTarget=utc+r.leadSec>schedule.next->atUtc;
        r.reason="shadow_optimum_start_advisory";return r;
    }
    bool validRun(const ThermalRun& r) const {
        if (r.startUtc<UtcSchedule::minimumUtcSecond || r.endUtc>=UtcSchedule::maximumUtcSecond
            || r.endUtc<=r.startUtc || r.endUtc-r.startUtc!=r.durationSec
            || r.durationSec<profile_.minimumRunSec || r.durationSec>profile_.maximumRunSec
            || r.riseCentiC<profile_.minimumRiseCentiC || r.riseCentiC>profile_.maximumRiseCentiC
            || r.startTemperatureCentiC<500 || r.startTemperatureCentiC>3500
            || r.startTemperatureCentiC+r.riseCentiC>3500
            || r.outdoorCentiC < -6000 || r.outdoorCentiC>6000 || r.waterCentiC<500 || r.waterCentiC>9000)
            return false;
        const int64_t scaled=static_cast<int64_t>(r.riseCentiC)*3600;
        return scaled>=static_cast<int64_t>(profile_.minimumRateCentiCPerHour)*r.durationSec
            && scaled<=static_cast<int64_t>(profile_.maximumRateCentiCPerHour)*r.durationSec;
    }
private:
    bool profileValid() const {
        return profile_.valid() && std::any_of(data_.bindingDigest.begin(),data_.bindingDigest.end(),[](auto b){return b!=0;});
    }
    bool usable(const ThermalObservation& in) const {
        return in.profileQualified && in.sourceVerified && in.conditionsKnown && in.deliveryKnown
            && in.clockTrusted && in.normalControl && !in.dhw && !in.windowOpen && !in.fault
            && !in.manualTest && !in.unexplainedGain && in.reportSequence && in.admissionEpoch
            && in.targetGeneration && in.utc>=UtcSchedule::minimumUtcSecond && in.utc<UtcSchedule::maximumUtcSecond
            && in.temperatureCentiC && *in.temperatureCentiC>=500 && *in.temperatureCentiC<=3500
            && in.outdoorCentiC && *in.outdoorCentiC>=-6000 && *in.outdoorCentiC<=6000
            && (!in.deliveredHeat || (in.waterCentiC && *in.waterCentiC>=500 && *in.waterCentiC<=9000));
    }
    ThermalModelProfile profile_;
    ThermalModelSnapshot data_;
    ThermalObservation last_;
    LearningMode mode_=LearningMode::disabled;
    bool storageHealthy_=true,haveReport_=false,liveOk_=false,offKnown_=false,warming_=false;
    uint32_t highestEpoch_=0,highestSequence_=0;
    uint64_t freshAt_=0,offAt_=0,runAt_=0;
    int64_t runUtc_=0,runOutdoorIntegral_=0,runWaterIntegral_=0;
    int16_t runTemperature_=0,minimumOutdoor_=0,maximumOutdoor_=0,minimumWater_=0,maximumWater_=0;
    const char* status_="learning_disabled";
};
}
