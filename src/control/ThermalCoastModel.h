#pragma once
#include "ThermalResponseModel.h"
#include <cstdlib>

namespace heating::control {
struct CoastProfile {
    bool reviewed=false;
    uint32_t maximumGapMs=0,minimumHeatSec=0,maximumHeatSec=0,heatDurationRadiusSec=0,observationWindowSec=0,maximumCoastSec=0;
    uint8_t minimumCycles=0,minimumDays=0,minimumComparable=0;
    uint16_t minimumSpanDays=0,maximumAgeDays=0,minimumOutdoorSpanCentiC=0;
    uint16_t outdoorDriftCentiC=0,outdoorRadiusCentiC=0,waterRadiusCentiC=0,roomRadiusCentiC=0;
    uint16_t maximumFallCentiC=0,maximumResidualRiseCentiC=0,maximumRateCentiCPerHour=0;
    uint16_t comfortBandCentiC=0,uncertaintyCentiC=0,maximumOvershootCentiC=0;
    bool valid() const {
        return reviewed && maximumGapMs>=1000 && maximumGapMs<=300000
            && minimumHeatSec>=900 && maximumHeatSec>=minimumHeatSec && maximumHeatSec<=21600
            && heatDurationRadiusSec>=60 && heatDurationRadiusSec<=900
            && observationWindowSec>=900 && observationWindowSec<=7200
            && maximumCoastSec>=60 && maximumCoastSec<=observationWindowSec
            && minimumCycles>=6 && minimumCycles<=16 && minimumDays>=6 && minimumDays<=minimumCycles
            && minimumComparable>=3 && minimumComparable<=minimumCycles
            && minimumSpanDays>=14 && minimumSpanDays<=60
            && maximumAgeDays>=minimumSpanDays+2 && maximumAgeDays<=120
            && minimumOutdoorSpanCentiC>=100 && minimumOutdoorSpanCentiC<=2000
            && outdoorDriftCentiC>=10 && outdoorDriftCentiC<=200
            && outdoorRadiusCentiC>=10 && outdoorRadiusCentiC<=300
            && waterRadiusCentiC>=10 && waterRadiusCentiC<=500
            && roomRadiusCentiC>=10 && roomRadiusCentiC<=100
            && maximumFallCentiC>=10 && maximumFallCentiC<=500
            && maximumResidualRiseCentiC>=10 && maximumResidualRiseCentiC<=200
            && maximumRateCentiCPerHour>=10 && maximumRateCentiCPerHour<=3000
            && comfortBandCentiC<=50 && uncertaintyCentiC>=5 && uncertaintyCentiC<=50
            && maximumOvershootCentiC>=10 && maximumOvershootCentiC<=100;
    }
};
struct CoastRun {
    uint32_t startUtc=0,endUtc=0,durationSec=0,heatedDurationSec=0;
    int16_t stopTemperatureCentiC=0,outdoorCentiC=0,waterCentiC=0;
    int16_t minimumRelativeCentiC=0,maximumRelativeCentiC=0,endRelativeCentiC=0;
};
struct CoastSnapshot {
    static constexpr size_t capacity=16;
    uint8_t algorithmVersion=1,count=0;
    std::array<uint8_t,32> bindingDigest{};
    std::array<CoastRun,capacity> runs{};
};
struct CoastAdvisory {
    bool coastNow=false; // Advisory only: NEVER a hydraulic/boiler/actuator command.
    uint32_t horizonSec=0,observedCoolingCentiCPerHour=0;
    uint16_t samplingUncertaintyCentiC=0;
    uint8_t eligibleCycles=0,comparableCycles=0,distinctDays=0;
    uint16_t coveredDays=0;
    std::optional<int16_t> worstLowerCentiC,worstUpperCentiC;
    const char *reason="coast_disabled";
};
class ThermalCoastModel {
public:
    ThermalCoastModel(CoastProfile profile,std::array<uint8_t,32> binding):profile_(profile) {data_.bindingDigest=binding;}
    void setMode(LearningMode mode) {
        mode_=(mode==LearningMode::shadow||mode==LearningMode::frozen)?mode:LearningMode::disabled;
        invalidateAdmission();
    }
    LearningMode mode() const{return mode_;}
    const char* status() const{return status_;}
    void invalidateAdmission(){haveReport_=liveOk_=heatKnown_=collecting_=false;}
    void reset(){auto binding=data_.bindingDigest;data_={};data_.bindingDigest=binding;invalidateAdmission();status_="coast_reset";}
    void storageFault(){storageHealthy_=false;mode_=LearningMode::disabled;invalidateAdmission();status_="coast_storage_fault";}
    CoastSnapshot snapshot() const{return data_;}
    bool restore(const CoastSnapshot& data) {
        if(!profileValid()||data.algorithmVersion!=1||data.bindingDigest!=data_.bindingDigest||data.count>data.capacity)return false;
        for(size_t i=0;i<data.count;++i)
            if(!validRun(data.runs[i])||(i&&data.runs[i].startUtc<=data.runs[i-1].endUtc))return false;
        data_=data;storageHealthy_=true;mode_=LearningMode::disabled;invalidateAdmission();status_="coast_restored_no_admission";return true;
    }
    bool observe(const ThermalObservation& in) {
        if(!profileValid()||!storageHealthy_||mode_==LearningMode::disabled) {
            invalidateAdmission();status_=!storageHealthy_?"coast_storage_fault":"coast_disabled";return false;
        }
        if(!usable(in)){invalidateAdmission();status_="coast_conditions_unverified";return false;}
        if(highestEpoch_&&(in.admissionEpoch<highestEpoch_||
            (in.admissionEpoch==highestEpoch_&&in.reportSequence<=highestSequence_))) {
            invalidateAdmission();status_="coast_cached_or_old_observation";return false;
        }
        if(in.admissionEpoch!=highestEpoch_){invalidateAdmission();highestSequence_=0;}
        highestEpoch_=in.admissionEpoch;highestSequence_=in.reportSequence;
        if(haveReport_) {
            bool bad=in.monotonicMs<=last_.monotonicMs;
            const auto elapsed=bad?0:in.monotonicMs-last_.monotonicMs;
            if(elapsed>profile_.maximumGapMs||in.targetGeneration!=last_.targetGeneration)bad=true;
            if(!bad) {
                const int64_t clockError=(in.utc-last_.utc)*1000-static_cast<int64_t>(elapsed);
                const int64_t delta=*in.temperatureCentiC-*last_.temperatureCentiC;
                if(clockError < -2000||clockError>2000
                    ||std::abs(delta)*3600000>static_cast<int64_t>(profile_.maximumRateCentiCPerHour)*static_cast<int64_t>(elapsed))bad=true;
            }
            if(bad){invalidateAdmission();last_=in;haveReport_=true;status_="coast_discontinuity";return false;}
        }
        liveOk_=true;freshAt_=in.monotonicMs;bool accepted=false;
        if(in.deliveredHeat) {
            if(!heatKnown_){heatKnown_=true;heatAt_=in.monotonicMs;}
            collecting_=false;status_=mode_==LearningMode::frozen?"coast_frozen":"coast_known_heat";
        } else if(mode_==LearningMode::frozen) {
            heatKnown_=collecting_=false;status_="coast_frozen";
        } else {
            if(heatKnown_&&haveReport_&&last_.monotonicMs>=heatAt_
                &&last_.monotonicMs-heatAt_>=static_cast<uint64_t>(profile_.minimumHeatSec)*1000
                &&last_.monotonicMs-heatAt_<=static_cast<uint64_t>(profile_.maximumHeatSec)*1000) {
                collecting_=true;offAt_=in.monotonicMs;run_={};
                run_.startUtc=static_cast<uint32_t>(in.utc);run_.stopTemperatureCentiC=*in.temperatureCentiC;
                run_.heatedDurationSec=static_cast<uint32_t>((last_.monotonicMs-heatAt_)/1000);
                run_.waterCentiC=*last_.waterCentiC;minimumOutdoor_=maximumOutdoor_=*in.outdoorCentiC;
                outdoorIntegral_=0;status_="coast_observing_off";
            }
            heatKnown_=false;
            if(collecting_) {
                const auto elapsed=in.monotonicMs-offAt_;
                const auto delta=static_cast<int16_t>(*in.temperatureCentiC-run_.stopTemperatureCentiC);
                run_.minimumRelativeCentiC=std::min(run_.minimumRelativeCentiC,delta);
                run_.maximumRelativeCentiC=std::max(run_.maximumRelativeCentiC,delta);
                minimumOutdoor_=std::min(minimumOutdoor_,*in.outdoorCentiC);maximumOutdoor_=std::max(maximumOutdoor_,*in.outdoorCentiC);
                if(elapsed)outdoorIntegral_+=static_cast<int64_t>(*last_.outdoorCentiC)*static_cast<int64_t>(in.monotonicMs-last_.monotonicMs);
                if(maximumOutdoor_-minimumOutdoor_>profile_.outdoorDriftCentiC
                    ||delta < -profile_.maximumFallCentiC||delta>profile_.maximumResidualRiseCentiC) {
                    collecting_=false;status_="coast_window_rejected";
                } else if(elapsed>=static_cast<uint64_t>(profile_.observationWindowSec)*1000) {
                    run_.endUtc=static_cast<uint32_t>(in.utc);run_.durationSec=static_cast<uint32_t>(elapsed/1000);
                    run_.endRelativeCentiC=delta;run_.outdoorCentiC=static_cast<int16_t>(outdoorIntegral_/static_cast<int64_t>(elapsed));
                    if(elapsed%1000==0&&validRun(run_)&&(!data_.count||run_.startUtc>data_.runs[data_.count-1].endUtc)) {
                        if(data_.count==data_.capacity){for(size_t i=1;i<data_.capacity;++i)data_.runs[i-1]=data_.runs[i];--data_.count;}
                        data_.runs[data_.count++]=run_;accepted=true;status_="coast_complete_window";
                    } else status_="coast_window_rejected";
                    collecting_=false;
                }
            }
        }
        last_=in;haveReport_=true;return accepted;
    }
    // startModelQualified is supplied by SAME reviewed owner/binding/model epoch,
    // never directly from a user/API flag. No active caller exists in api1.
    CoastAdvisory propose(uint64_t now,int64_t utc,const ScheduleTarget& schedule,bool startModelQualified=false) const {
        CoastAdvisory r;
        if(mode_==LearningMode::disabled||!profileValid()||!storageHealthy_)return r;
        if(!startModelQualified){r.reason="coast_start_model_not_qualified";return r;}
        if(!liveOk_||!haveReport_||now<freshAt_||now-freshAt_>=profile_.maximumGapMs){r.reason="coast_source_not_fresh";return r;}
        if(utc<UtcSchedule::minimumUtcSecond||utc>=UtcSchedule::maximumUtcSecond){r.reason="coast_time_invalid";return r;}
        const auto clockError=(utc-last_.utc)*1000-static_cast<int64_t>(now-last_.monotonicMs);
        if(clockError < -2000||clockError>2000){r.reason="coast_time_invalid";return r;}
        if(!last_.deliveredHeat||!last_.waterCentiC||!heatKnown_||last_.monotonicMs<heatAt_
            ||last_.monotonicMs-heatAt_<uint64_t(profile_.minimumHeatSec)*1000
            ||last_.monotonicMs-heatAt_>uint64_t(profile_.maximumHeatSec)*1000) {
            r.reason="coast_no_comparable_current_heat_period";return r;
        }
        const auto heatedSec=(last_.monotonicMs-heatAt_)/1000;
        if(schedule.state!=ScheduleState::active||!schedule.temperatureCentiC||!schedule.next
            ||!UtcSchedule::validTemperature(*schedule.temperatureCentiC)||!UtcSchedule::validTemperature(schedule.next->temperatureCentiC)
            ||schedule.next->temperatureCentiC>=*schedule.temperatureCentiC||schedule.next->atUtc<=utc
            ||schedule.next->atUtc>=UtcSchedule::maximumUtcSecond||schedule.next->atUtc-utc>profile_.maximumCoastSec) {
            r.reason="coast_no_imminent_lower_transition";return r;
        }
        std::array<uint32_t,CoastSnapshot::capacity> days{},rates{};
        uint32_t earliest=UINT32_MAX,latest=0;int16_t outdoorMin=6000,outdoorMax=-6000,worstMin=0,worstMax=0;
        for(size_t i=0;i<data_.count;++i) {
            const auto& rec=data_.runs[i];
            if(utc<rec.endUtc||utc-rec.endUtc>int64_t(profile_.maximumAgeDays)*86400)continue;
            ++r.eligibleCycles;earliest=std::min(earliest,rec.startUtc);latest=std::max(latest,rec.endUtc);
            outdoorMin=std::min(outdoorMin,rec.outdoorCentiC);outdoorMax=std::max(outdoorMax,rec.outdoorCentiC);
            const auto day=rec.startUtc/86400;
            if(std::find(days.begin(),days.begin()+r.distinctDays,day)==days.begin()+r.distinctDays)days[r.distinctDays++]=day;
            if(std::abs(int32_t(rec.outdoorCentiC)-*last_.outdoorCentiC)>profile_.outdoorRadiusCentiC
                ||std::abs(int32_t(rec.waterCentiC)-*last_.waterCentiC)>profile_.waterRadiusCentiC
                ||std::abs(int32_t(rec.stopTemperatureCentiC)-*last_.temperatureCentiC)>profile_.roomRadiusCentiC
                ||std::abs(int64_t(rec.heatedDurationSec)-static_cast<int64_t>(heatedSec))>profile_.heatDurationRadiusSec
                ||schedule.next->atUtc-utc>rec.durationSec)continue;
            // Whole-window worst bounds, no optimistic sub-window extrapolation.
            worstMin=std::min(worstMin,rec.minimumRelativeCentiC);worstMax=std::max(worstMax,rec.maximumRelativeCentiC);
            rates[r.comparableCycles++]=rec.endRelativeCentiC<0?
                static_cast<uint32_t>((-int64_t(rec.endRelativeCentiC)*3600+rec.durationSec-1)/rec.durationSec):0;
        }
        if(r.eligibleCycles)r.coveredDays=static_cast<uint16_t>((latest-earliest)/86400);
        if(r.eligibleCycles<profile_.minimumCycles||r.distinctDays<profile_.minimumDays||r.coveredDays<profile_.minimumSpanDays
            ||outdoorMax-outdoorMin<profile_.minimumOutdoorSpanCentiC||r.comparableCycles<profile_.minimumComparable) {
            r.reason="coast_insufficient_evidence";return r;
        }
        std::sort(rates.begin(),rates.begin()+r.comparableCycles);r.observedCoolingCentiCPerHour=rates[r.comparableCycles/2];
        // Conservative profile-bound allowance for transition timing AND missed
        // between-report extrema. An empirical reviewed rate, not physical proof.
        r.samplingUncertaintyCentiC=static_cast<uint16_t>((uint64_t(profile_.maximumRateCentiCPerHour)
            *2*profile_.maximumGapMs+3599999)/3600000);
        const int32_t allowance=profile_.uncertaintyCentiC+r.samplingUncertaintyCentiC;
        r.worstLowerCentiC=static_cast<int16_t>(*last_.temperatureCentiC+worstMin-allowance);
        r.worstUpperCentiC=static_cast<int16_t>(*last_.temperatureCentiC+worstMax+allowance);
        if(*r.worstLowerCentiC<*schedule.temperatureCentiC-profile_.comfortBandCentiC
            ||*r.worstUpperCentiC>*schedule.temperatureCentiC+profile_.maximumOvershootCentiC) {
            r.reason="coast_comfort_bound_not_met";return r;
        }
        r.horizonSec=static_cast<uint32_t>(schedule.next->atUtc-utc);r.coastNow=true;r.reason="shadow_coast_advisory";return r;
    }
    bool validRun(const CoastRun& r) const {
        return r.startUtc>=UtcSchedule::minimumUtcSecond&&r.endUtc<UtcSchedule::maximumUtcSecond&&r.endUtc>r.startUtc
            &&r.endUtc-r.startUtc==r.durationSec&&r.durationSec>=profile_.observationWindowSec
            &&r.durationSec<=profile_.observationWindowSec+(profile_.maximumGapMs+999)/1000
            &&r.heatedDurationSec>=profile_.minimumHeatSec&&r.heatedDurationSec<=profile_.maximumHeatSec
            &&r.stopTemperatureCentiC>=500&&r.stopTemperatureCentiC<=3500&&r.outdoorCentiC>=-6000&&r.outdoorCentiC<=6000
            &&r.waterCentiC>=500&&r.waterCentiC<=9000&&r.minimumRelativeCentiC<=0
            &&r.minimumRelativeCentiC>=-profile_.maximumFallCentiC&&r.maximumRelativeCentiC>=0
            &&r.maximumRelativeCentiC<=profile_.maximumResidualRiseCentiC
            &&r.endRelativeCentiC>=r.minimumRelativeCentiC&&r.endRelativeCentiC<=r.maximumRelativeCentiC
            &&r.stopTemperatureCentiC+r.minimumRelativeCentiC>=500&&r.stopTemperatureCentiC+r.maximumRelativeCentiC<=3500
            &&std::abs(int64_t(r.endRelativeCentiC))*3600<=int64_t(profile_.maximumRateCentiCPerHour)*r.durationSec;
    }
private:
    bool profileValid() const{return profile_.valid()&&std::any_of(data_.bindingDigest.begin(),data_.bindingDigest.end(),[](auto b){return b!=0;});}
    static bool usable(const ThermalObservation& in) {
        return in.profileQualified&&in.sourceVerified&&in.conditionsKnown&&in.deliveryKnown&&in.clockTrusted&&in.normalControl
            &&!in.dhw&&!in.windowOpen&&!in.fault&&!in.manualTest&&!in.unexplainedGain&&in.admissionEpoch&&in.reportSequence&&in.targetGeneration
            &&in.utc>=UtcSchedule::minimumUtcSecond&&in.utc<UtcSchedule::maximumUtcSecond
            &&in.temperatureCentiC&&*in.temperatureCentiC>=500&&*in.temperatureCentiC<=3500
            &&in.outdoorCentiC&&*in.outdoorCentiC>=-6000&&*in.outdoorCentiC<=6000
            &&(!in.deliveredHeat||(in.waterCentiC&&*in.waterCentiC>=500&&*in.waterCentiC<=9000));
    }
    CoastProfile profile_;CoastSnapshot data_;ThermalObservation last_;CoastRun run_;
    LearningMode mode_=LearningMode::disabled;
    bool storageHealthy_=true,haveReport_=false,liveOk_=false,heatKnown_=false,collecting_=false;
    uint32_t highestEpoch_=0,highestSequence_=0;
    uint64_t freshAt_=0,heatAt_=0,offAt_=0;
    int16_t minimumOutdoor_=0,maximumOutdoor_=0;int64_t outdoorIntegral_=0;
    const char* status_="coast_disabled";
};
}
