#pragma once
#include "GroupWaterPolicy.h"
#include "ThermalResponseModel.h"
#include <cstdlib>

namespace heating::control {
struct CurveProfile {
    bool reviewed=false;
    uint32_t configGeneration=0,maximumGapMs=0,windowSec=0,maximumOutsideAgeMs=0,maximumRoomAgeMs=0;
    uint8_t zoneCount=0,minimumWindows=0,minimumDays=0,minimumComparable=0;
    std::array<uint32_t,8> zoneIds{},sourceIds{};
    uint16_t minimumSpanDays=0,maximumAgeDays=0,outdoorDriftCentiC=0,outdoorRadiusCentiC=0;
    uint16_t minimumWeatherSpanCentiC=0,errorDeadbandCentiC=0,maximumErrorCentiC=0,maximumErrorSpreadCentiC=0;
    uint16_t waterTrackingToleranceCentiC=0,stepCentiC=0,maximumRoomRateCentiCPerHour=0;
    bool valid()const {
        if(!reviewed||!configGeneration||zoneCount<2||zoneCount>zoneIds.size()
            ||maximumGapMs<1000||maximumGapMs>300000||windowSec<14400||windowSec>43200
            ||maximumRoomAgeMs<60000||maximumRoomAgeMs>300000
            ||maximumOutsideAgeMs<60000||maximumOutsideAgeMs>3600000
            ||minimumWindows<6||minimumWindows>16||minimumDays<6||minimumDays>minimumWindows
            ||minimumComparable<3||minimumComparable>minimumWindows
            ||minimumSpanDays<14||minimumSpanDays>60||maximumAgeDays<minimumSpanDays+2||maximumAgeDays>120
            ||outdoorDriftCentiC<10||outdoorDriftCentiC>100||outdoorRadiusCentiC<10||outdoorRadiusCentiC>100
            ||minimumWeatherSpanCentiC<1000||minimumWeatherSpanCentiC>4000
            ||errorDeadbandCentiC<10||errorDeadbandCentiC>50||maximumErrorCentiC<errorDeadbandCentiC||maximumErrorCentiC>150
            ||maximumErrorSpreadCentiC<5||maximumErrorSpreadCentiC>50
            ||maximumRoomRateCentiCPerHour<100||maximumRoomRateCentiCPerHour>3000
            ||waterTrackingToleranceCentiC<10||waterTrackingToleranceCentiC>100||stepCentiC<1||stepCentiC>25)return false;
        for(size_t i=0;i<zoneCount;++i)
            for(size_t j=0;j<i;++j)if(zoneIds[i]==zoneIds[j]||sourceIds[i]==sourceIds[j])return false;
        return true;
    }
};
struct CurveZoneObservation {
    uint32_t zoneId=0,sourceId=0,reportSequence=0,sourceAgeMs=0;
    bool sourceVerified=false,deliveryVerified=false,actuatorReady=false,windowOpen=false;
    std::optional<int16_t> temperatureCentiC,targetCentiC;
};
struct CurveObservation {
    uint64_t monotonicMs=0;int64_t utc=0;
    uint32_t admissionEpoch=0,reportSequence=0,configGeneration=0,targetGeneration=0,outsideAgeMs=0,outsideReportSequence=0;
    bool profileQualified=false,clockTrusted=false,normalAutomatic=false,outsideQualified=false;
    bool floorSensorFresh=false;std::optional<int16_t> floorCentiC;
    bool independentLimitsHealthy=false,waterTrackingVerified=false,dhw=false,fault=false,manualTest=false,externalGain=false;
    std::optional<int16_t> outdoorCentiC,reportedWaterCentiC,requestedWaterCentiC;
    uint8_t zoneCount=0;std::array<CurveZoneObservation,8> zones{};
};
struct CurveWindow {
    uint32_t startUtc=0,endUtc=0,durationSec=0;
    int16_t outdoorCentiC=0,minimumZoneErrorCentiC=0,maximumZoneErrorCentiC=0;
};
struct CurveSnapshot {
    static constexpr size_t capacity=16;
    uint8_t algorithmVersion=1,count=0;
    std::array<uint8_t,32> bindingDigest{};
    std::array<int16_t,9> baseCurve{};
    std::array<CurveWindow,capacity> windows{};
};
struct CurveAdvisory {
    bool proposed=false;uint8_t knot=0,eligibleWindows=0,comparableWindows=0,distinctDays=0;
    uint16_t coveredDays=0;
    int16_t oldKnotCentiC=0,newKnotCentiC=0;
    uint32_t firstEvidenceUtc=0,lastEvidenceUtc=0;
    std::array<int16_t,9> oldCurve{},newCurve{};
    const char* reason="curve_learning_disabled";
};
class CurveAdaptation {
public:
    CurveAdaptation(CurveProfile profile,GroupWaterProfile group,std::array<uint8_t,32> binding):profile_(profile),group_(group) {
        data_.bindingDigest=binding;data_.baseCurve=group.curveCentiC;
    }
    LearningMode mode()const{return mode_;}
    void setMode(LearningMode mode){mode_=(mode==LearningMode::shadow||mode==LearningMode::frozen)?mode:LearningMode::disabled;invalidateAdmission();}
    void invalidateAdmission(){haveReport_=windowActive_=liveOk_=completeThisAdmission_=false;}
    void reset(){auto binding=data_.bindingDigest;data_={};data_.bindingDigest=binding;data_.baseCurve=group_.curveCentiC;invalidateAdmission();status_="curve_model_reset";}
    void storageFault(){storageHealthy_=false;mode_=LearningMode::disabled;invalidateAdmission();status_="curve_storage_fault";}
    const char* status()const{return status_;}
    CurveSnapshot snapshot()const{return data_;}
    bool validWindow(const CurveWindow& w)const {
        return w.startUtc>=UtcSchedule::minimumUtcSecond&&w.endUtc<UtcSchedule::maximumUtcSecond&&w.endUtc>w.startUtc
            &&w.endUtc-w.startUtc==w.durationSec&&w.durationSec>=profile_.windowSec
            &&w.durationSec<=profile_.windowSec+(profile_.maximumGapMs+999)/1000
            &&w.outdoorCentiC>=-6000&&w.outdoorCentiC<=6000
            &&w.minimumZoneErrorCentiC>=-profile_.maximumErrorCentiC&&w.maximumZoneErrorCentiC<=profile_.maximumErrorCentiC
            &&w.minimumZoneErrorCentiC<=w.maximumZoneErrorCentiC
            &&w.maximumZoneErrorCentiC-w.minimumZoneErrorCentiC<=profile_.maximumErrorSpreadCentiC;
    }
    bool restore(const CurveSnapshot& d) {
        if(!profileValid()||d.algorithmVersion!=1||d.count>d.capacity||d.bindingDigest!=data_.bindingDigest||d.baseCurve!=data_.baseCurve)return false;
        for(size_t i=0;i<d.count;++i)if(!validWindow(d.windows[i])||(i&&d.windows[i].startUtc<d.windows[i-1].endUtc))return false;
        data_=d;storageHealthy_=true;mode_=LearningMode::disabled;invalidateAdmission();status_="curve_restored_no_admission";return true;
    }
    bool observe(const CurveObservation& in) {
        if(!profileValid()||!storageHealthy_||mode_==LearningMode::disabled){invalidateAdmission();return false;}
        if(!in.admissionEpoch||!in.reportSequence||(highestEpoch_&&(in.admissionEpoch<highestEpoch_
            ||(in.admissionEpoch==highestEpoch_&&in.reportSequence<=highestSequence_)))) {
            invalidateAdmission();status_="curve_cached_or_old_report";return false;
        }
        if(in.admissionEpoch!=highestEpoch_){invalidateAdmission();zoneHighwater_={};outsideHighwater_=0;}
        highestEpoch_=in.admissionEpoch;highestSequence_=in.reportSequence;
        if(in.zoneCount!=profile_.zoneCount){invalidateAdmission();status_="curve_zone_quorum";return false;}
        for(size_t i=0;i<in.zoneCount;++i) {
            if(in.zones[i].zoneId!=profile_.zoneIds[i]||in.zones[i].sourceId!=profile_.sourceIds[i]||!in.zones[i].reportSequence||in.zones[i].reportSequence<=zoneHighwater_[i]) {
                invalidateAdmission();status_="curve_cached_or_wrong_zone";return false;
            }
            zoneHighwater_[i]=in.zones[i].reportSequence;
        }
        if(!admitOutside(in)||!usable(in)){invalidateAdmission();status_="curve_conditions_unverified";return false;}
        if(haveReport_) {
            const bool backwards=in.monotonicMs<=last_.monotonicMs;
            const auto dt=backwards?0:in.monotonicMs-last_.monotonicMs;
            bool bad=backwards||dt>profile_.maximumGapMs||in.targetGeneration!=last_.targetGeneration;
            if(!bad) {
                const auto error=(in.utc-last_.utc)*1000-static_cast<int64_t>(dt);bad=error < -2000||error>2000;
                for(size_t i=0;i<in.zoneCount;++i) {
                    const int64_t change=int32_t(*in.zones[i].temperatureCentiC)-*last_.zones[i].temperatureCentiC;
                    if(in.zones[i].targetCentiC!=last_.zones[i].targetCentiC
                        ||std::abs(change)*3600000>int64_t(profile_.maximumRoomRateCentiCPerHour)*static_cast<int64_t>(dt))bad=true;
                }
            }
            if(bad){invalidateAdmission();last_=in;haveReport_=true;status_="curve_discontinuity";return false;}
        }
        liveOk_=true;freshAt_=in.monotonicMs;bool accepted=false;
        if(!windowActive_)beginWindow(in);
        else {
            const auto dt=in.monotonicMs-last_.monotonicMs;
            for(size_t i=0;i<in.zoneCount;++i)errors_[i]+=int64_t(*last_.zones[i].targetCentiC-*last_.zones[i].temperatureCentiC)*static_cast<int64_t>(dt);
            outdoorIntegral_+=int64_t(*last_.outdoorCentiC)*static_cast<int64_t>(dt);
            minimumOutdoor_=std::min(minimumOutdoor_,*in.outdoorCentiC);maximumOutdoor_=std::max(maximumOutdoor_,*in.outdoorCentiC);
            if(maximumOutdoor_-minimumOutdoor_>profile_.outdoorDriftCentiC){invalidateAdmission();status_="curve_outdoor_drift";}
            else if(in.monotonicMs-windowAt_>=uint64_t(profile_.windowSec)*1000) {
                const auto elapsed=in.monotonicMs-windowAt_;
                CurveWindow w{static_cast<uint32_t>(windowUtc_),static_cast<uint32_t>(in.utc),static_cast<uint32_t>(elapsed/1000),
                    static_cast<int16_t>(outdoorIntegral_/static_cast<int64_t>(elapsed)),INT16_MAX,INT16_MIN};
                for(size_t i=0;i<in.zoneCount;++i) {
                    const auto mean=static_cast<int16_t>(errors_[i]/static_cast<int64_t>(elapsed));
                    w.minimumZoneErrorCentiC=std::min(w.minimumZoneErrorCentiC,mean);w.maximumZoneErrorCentiC=std::max(w.maximumZoneErrorCentiC,mean);
                }
                if(elapsed%1000==0&&validWindow(w)&&(!data_.count||w.startUtc>=data_.windows[data_.count-1].endUtc)) {
                    completeThisAdmission_=true;
                    if(mode_==LearningMode::shadow) {
                        if(data_.count==data_.capacity){for(size_t i=1;i<data_.capacity;++i)data_.windows[i-1]=data_.windows[i];--data_.count;}
                        data_.windows[data_.count++]=w;accepted=true;
                    }
                    status_="curve_complete_qualified_window";
                }else {completeThisAdmission_=false;status_="curve_window_rejected";}
                beginWindow(in);
            }
        }
        last_=in;haveReport_=true;return accepted;
    }
    // Defaultfalse: only the SAME reviewed model/config owner can establish this,
    // never a wire flag. No active api1 caller, no water target application.
    CurveAdvisory propose(uint64_t now,int64_t utc,bool modelsQualified=false)const {
        CurveAdvisory r;r.oldCurve=r.newCurve=data_.baseCurve;
        if(mode_==LearningMode::disabled||!profileValid()||!storageHealthy_)return r;
        if(!modelsQualified){r.reason="curve_prerequisite_models_unqualified";return r;}
        if(!liveOk_||!completeThisAdmission_||!haveReport_||now<freshAt_||now-freshAt_>=profile_.maximumGapMs){r.reason="curve_no_fresh_complete_window";return r;}
        if(utc<UtcSchedule::minimumUtcSecond||utc>=UtcSchedule::maximumUtcSecond){r.reason="curve_time_invalid";return r;}
        const auto clockError=(utc-last_.utc)*1000-static_cast<int64_t>(now-last_.monotonicMs);
        if(clockError < -2000||clockError>2000){r.reason="curve_time_invalid";return r;}
        const int32_t outside=*last_.outdoorCentiC;
        const int32_t knot=(2000-outside+250)/500;
        if(knot<1||knot>7||std::abs((2000-knot*500)-outside)>profile_.outdoorRadiusCentiC){r.reason="curve_no_observed_interior_knot";return r;}
        const int32_t center=2000-knot*500,lower=center-500,upper=center+500;
        std::array<uint32_t,CurveSnapshot::capacity> days{};
        uint32_t earliest=UINT32_MAX,latest=0;int16_t weatherMin=6000,weatherMax=-6000;
        bool lowerEvidence=false,upperEvidence=false,allUp=true,allDown=true;uint8_t influence=0;
        for(size_t i=0;i<data_.count;++i) {
            const auto& w=data_.windows[i];
            if(utc<w.endUtc||utc-w.endUtc>int64_t(profile_.maximumAgeDays)*86400)continue;
            ++r.eligibleWindows;earliest=std::min(earliest,w.startUtc);latest=std::max(latest,w.endUtc);
            weatherMin=std::min(weatherMin,w.outdoorCentiC);weatherMax=std::max(weatherMax,w.outdoorCentiC);
            const auto day=w.startUtc/86400;
            if(std::find(days.begin(),days.begin()+r.distinctDays,day)==days.begin()+r.distinctDays)days[r.distinctDays++]=day;
            if(std::abs(w.outdoorCentiC-center)<=profile_.outdoorRadiusCentiC)++r.comparableWindows;
            lowerEvidence=lowerEvidence||std::abs(w.outdoorCentiC-lower)<=profile_.outdoorRadiusCentiC;
            upperEvidence=upperEvidence||std::abs(w.outdoorCentiC-upper)<=profile_.outdoorRadiusCentiC;
            if(w.outdoorCentiC>=lower-profile_.outdoorRadiusCentiC&&w.outdoorCentiC<=upper+profile_.outdoorRadiusCentiC) {
                ++influence;allUp=allUp&&w.minimumZoneErrorCentiC>=profile_.errorDeadbandCentiC;
                allDown=allDown&&w.maximumZoneErrorCentiC<=-profile_.errorDeadbandCentiC;
            }
        }
        if(r.eligibleWindows)r.coveredDays=static_cast<uint16_t>((latest-earliest)/86400);
        if(r.eligibleWindows<profile_.minimumWindows||r.distinctDays<profile_.minimumDays||r.coveredDays<profile_.minimumSpanDays
            ||weatherMax-weatherMin<profile_.minimumWeatherSpanCentiC||!lowerEvidence||!upperEvidence
            ||r.comparableWindows<profile_.minimumComparable||influence<profile_.minimumWindows) {
            r.reason="curve_insufficient_comparable_neighbor_coverage";return r;
        }
        if(allUp==allDown){r.reason="curve_no_consistent_group_error";return r;}
        r.knot=static_cast<uint8_t>(knot);r.oldKnotCentiC=data_.baseCurve[r.knot];
        const int32_t changed=r.oldKnotCentiC+(allUp?profile_.stepCentiC:-profile_.stepCentiC);
        if(changed<group_.minimumCentiC||changed>group_.maximumCentiC
            ||changed<data_.baseCurve[r.knot-1]||changed>data_.baseCurve[r.knot+1]){r.reason="curve_hard_or_monotonic_limit";return r;}
        r.newKnotCentiC=static_cast<int16_t>(changed);r.newCurve[r.knot]=r.newKnotCentiC;
        auto candidate=group_;candidate.curveCentiC=r.newCurve;if(!candidate.valid()){r.reason="curve_profile_invalid";return r;}
        r.firstEvidenceUtc=earliest;r.lastEvidenceUtc=latest;r.proposed=true;r.reason="shadow_curve_knot_advisory";return r;
    }
private:
    bool profileValid()const{return profile_.valid()&&group_.valid()&&std::any_of(data_.bindingDigest.begin(),data_.bindingDigest.end(),[](auto b){return b!=0;});}
    bool usable(const CurveObservation& in)const {
        if(!in.profileQualified||!in.clockTrusted||!in.normalAutomatic||!in.outsideQualified||!in.independentLimitsHealthy||!in.waterTrackingVerified
            ||in.dhw||in.fault||in.manualTest||in.externalGain||in.configGeneration!=profile_.configGeneration||!in.targetGeneration
            ||in.utc<UtcSchedule::minimumUtcSecond||in.utc>=UtcSchedule::maximumUtcSecond||in.outsideAgeMs>=profile_.maximumOutsideAgeMs
            ||!in.outdoorCentiC||*in.outdoorCentiC < -6000||*in.outdoorCentiC>6000
            ||!in.reportedWaterCentiC||!in.requestedWaterCentiC||*in.requestedWaterCentiC<group_.minimumCentiC||*in.requestedWaterCentiC>group_.maximumCentiC
            ||*in.reportedWaterCentiC<group_.minimumCentiC||*in.reportedWaterCentiC>group_.maximumCentiC
            ||std::abs(*in.reportedWaterCentiC-*in.requestedWaterCentiC)>profile_.waterTrackingToleranceCentiC)return false;
        int16_t minimum=INT16_MAX,maximum=INT16_MIN;
        for(size_t i=0;i<in.zoneCount;++i) {
            const auto& z=in.zones[i];
            if(z.sourceAgeMs>=profile_.maximumRoomAgeMs||!z.sourceVerified||!z.deliveryVerified||!z.actuatorReady||z.windowOpen||!z.temperatureCentiC||!z.targetCentiC
                ||!UtcSchedule::validTemperature(*z.temperatureCentiC)||!UtcSchedule::validTemperature(*z.targetCentiC))return false;
            const int32_t error=*z.targetCentiC-*z.temperatureCentiC;
            if(std::abs(error)>profile_.maximumErrorCentiC)return false;
            minimum=std::min(minimum,static_cast<int16_t>(error));maximum=std::max(maximum,static_cast<int16_t>(error));
        }
        if(maximum-minimum>profile_.maximumErrorSpreadCentiC)return false;
        // Refuse learning if another group overrides this group's curve target.
        // Reuse actual existing target/safety function, not a second curve rule.
        GroupWaterInput water;water.demand=water.sourceValid=water.deliveryAvailable=true;
        water.independentLimitHealthy=in.independentLimitsHealthy;water.outdoorFresh=in.outsideQualified;
        water.outdoorCentiC=in.outdoorCentiC;water.roomErrorCentiC=maximum;
        water.floorSensorFresh=in.floorSensorFresh;water.floorCentiC=in.floorCentiC;
        const auto expected=groupWaterTarget(group_,water);
        return expected.target&&!expected.safetyInhibit&&*expected.target==*in.requestedWaterCentiC;
    }
    bool admitOutside(const CurveObservation& in) {
        if(!in.outdoorCentiC||!in.outsideReportSequence||!in.outsideQualified
            ||in.outsideAgeMs>=profile_.maximumOutsideAgeMs||in.outsideReportSequence<outsideHighwater_)return false;
        if(in.outsideReportSequence==outsideHighwater_) {
            if(*in.outdoorCentiC!=outsideValue_||in.monotonicMs<outsideAt_)return false;
            const auto elapsed=in.monotonicMs-outsideAt_;
            if(elapsed>=profile_.maximumOutsideAgeMs||outsideBaseAge_>=profile_.maximumOutsideAgeMs-elapsed
                ||in.outsideAgeMs<outsideBaseAge_+elapsed)return false; // Cache read cannot reset age.
        } else {
            outsideHighwater_=in.outsideReportSequence;outsideAt_=in.monotonicMs;
            outsideBaseAge_=in.outsideAgeMs;outsideValue_=*in.outdoorCentiC;
        }
        return true;
    }
    void beginWindow(const CurveObservation& in) {
        windowActive_=true;windowAt_=in.monotonicMs;windowUtc_=in.utc;errors_={};outdoorIntegral_=0;
        minimumOutdoor_=maximumOutdoor_=*in.outdoorCentiC;
    }
    CurveProfile profile_;GroupWaterProfile group_;CurveSnapshot data_;CurveObservation last_;
    LearningMode mode_=LearningMode::disabled;
    bool storageHealthy_=true,haveReport_=false,windowActive_=false,liveOk_=false,completeThisAdmission_=false;
    uint32_t highestEpoch_=0,highestSequence_=0,outsideHighwater_=0,outsideBaseAge_=0;
    uint64_t outsideAt_=0;int16_t outsideValue_=0;std::array<uint32_t,8> zoneHighwater_{};
    uint64_t freshAt_=0,windowAt_=0;int64_t windowUtc_=0,outdoorIntegral_=0;
    std::array<int64_t,8> errors_{};int16_t minimumOutdoor_=0,maximumOutdoor_=0;
    const char* status_="curve_learning_disabled";
};
}
