// Enabled MODEL ADVICE is consumed only by this finite test reference policy.
// No production caller, IO, admission owner, physical output or saved profile.
#include <gtest/gtest.h>
#include "control/ThermalResponseModel.h"
#include "control/ThermalCoastModel.h"
#include "control/CurveAdaptation.h"
#include "control/ThermalReplay.h"
#include "control/ZoneRegulator.h"
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <sstream>
#include "ControlTestHash.h"

using namespace heating::control;
namespace enabled_replay {
constexpr int64_t epoch=1790812800;
auto binding(){std::array<uint8_t,32>b{};b[0]=71;return b;}
GroupWaterProfile group() {
    GroupWaterProfile p;p.qualified=p.independentHighLimit=true;p.minimumCentiC=2000;p.maximumCentiC=7500;
    p.curveCentiC={3000,3500,4000,4500,5000,5500,6000,6500,7000};return p;
}
ThermalModelProfile warmProfile() {
    ThermalModelProfile p;p.reviewed=true;p.maximumGapMs=120000;p.minimumOffSec=1800;
    p.minimumRunSec=900;p.maximumRunSec=7200;p.minimumRiseCentiC=50;p.maximumRiseCentiC=500;
    p.minimumRateCentiCPerHour=10;p.maximumRateCentiCPerHour=3000;p.outdoorDriftCentiC=50;p.waterDriftCentiC=100;
    p.minimumStarts=6;p.minimumDistinctDays=6;p.minimumSpanDays=14;p.maximumAgeDays=60;p.minimumComparableStarts=3;
    p.comparableOutdoorRadiusCentiC=100;p.comparableWaterRadiusCentiC=100;p.comparableRoomRadiusCentiC=100;
    p.minimumOutdoorSpanCentiC=200;p.maximumLeadSec=7200;return p;
}
CoastProfile coastProfile() {
    CoastProfile p;p.reviewed=true;p.maximumGapMs=60000;p.minimumHeatSec=900;p.maximumHeatSec=7200;
    p.heatDurationRadiusSec=300;p.observationWindowSec=1800;p.maximumCoastSec=1800;
    p.minimumCycles=6;p.minimumDays=6;p.minimumComparable=3;p.minimumSpanDays=14;p.maximumAgeDays=60;
    p.minimumOutdoorSpanCentiC=200;p.outdoorDriftCentiC=50;p.outdoorRadiusCentiC=100;p.waterRadiusCentiC=100;
    p.roomRadiusCentiC=25;p.maximumFallCentiC=100;p.maximumResidualRiseCentiC=100;p.maximumRateCentiCPerHour=600;
    p.comfortBandCentiC=50;p.uncertaintyCentiC=10;p.maximumOvershootCentiC=50;return p;
}
CurveProfile curveProfile() {
    CurveProfile p;p.reviewed=true;p.configGeneration=1;p.maximumGapMs=120000;p.windowSec=14400;
    p.maximumOutsideAgeMs=3600000;p.maximumRoomAgeMs=120000;p.zoneCount=2;
    p.zoneIds[0]=1;p.zoneIds[1]=2;p.sourceIds[0]=11;p.sourceIds[1]=12;
    p.minimumWindows=6;p.minimumDays=6;p.minimumComparable=3;p.minimumSpanDays=14;p.maximumAgeDays=60;
    p.minimumWeatherSpanCentiC=1000;p.outdoorDriftCentiC=50;p.outdoorRadiusCentiC=100;
    p.errorDeadbandCentiC=20;p.maximumErrorCentiC=100;p.maximumErrorSpreadCentiC=30;
    p.waterTrackingToleranceCentiC=50;p.stepCentiC=20;p.maximumRoomRateCentiCPerHour=600;return p;
}
ThermalObservation observation(uint64_t ms,int64_t utc,uint32_t seq,uint32_t admission,
        int16_t room,int16_t outside,int16_t water,bool delivered) {
    ThermalObservation x;x.profileQualified=x.sourceVerified=x.conditionsKnown=x.deliveryKnown=true;
    x.clockTrusted=x.normalControl=true;x.monotonicMs=ms;x.utc=utc;x.reportSequence=seq;x.admissionEpoch=admission;
    x.targetGeneration=1;x.temperatureCentiC=room;x.outdoorCentiC=outside;x.waterCentiC=water;x.deliveredHeat=delivered;
    return x;
}
struct Calibrated {
    ThermalResponseModel warm{warmProfile(),binding()};
    ThermalCoastModel coast{coastProfile(),binding()};
    CurveAdaptation curve{curveProfile(),group(),binding()};
    uint32_t seq=0;
    int16_t outside,water;
    bool trained=true;
    explicit Calibrated(int16_t weather):outside(weather),water(interpolateWaterCurve(weather,group().curveCentiC)) {
        warm.setMode(LearningMode::shadow);coast.setMode(LearningMode::shadow);curve.setMode(LearningMode::shadow);
        // Independent SYNTHETIC calibration episodes, not actual home history
        // or training from the holdout plant. Both comparisons see this same
        // declared prehistory. Coverage calendar is compressed test time.
        for(unsigned day=0;day<6;++day) {
            const auto base=uint64_t(day)*3*86400000;
            const auto utc=epoch+day*3*86400;
            const int16_t weatherNow=outside+(day<3?0:200);
            for(unsigned minute=0;minute<=71;++minute) {
                const bool heat=minute>=31&&minute<71;
                const int16_t temp=minute<=31?1900:1900+int16_t(std::min(minute-31,40u))*10;
                auto x=observation(base+minute*60000,utc+minute*60,++seq,day+1,temp,weatherNow,water,heat);
                warm.observe(x);
            }
            for(unsigned minute=0;minute<=61;++minute) {
                const bool heat=minute<=30;
                int16_t temp=2100;
                if(minute>31) {const int d=int(minute)-31;temp=d<=10?2100+d:2120-d;}
                auto x=observation(base+minute*60000,utc+minute*60,++seq,day+1,temp,weatherNow,water,heat);
                coast.observe(x);
            }
            const int16_t curveWeather=outside+(day==0||day==5?-500:day==1?500:0);
            for(unsigned minute=0;minute<=240;++minute)
                curve.observe(curveObservation(base+minute*60000,utc+minute*60,day+1,curveWeather,++seq));
        }
        trained=warm.snapshot().count==6&&coast.snapshot().count==6&&curve.snapshot().count==6;
        warm.setMode(LearningMode::frozen);coast.setMode(LearningMode::frozen);curve.setMode(LearningMode::frozen);
    }
    CurveObservation curveObservation(uint64_t ms,int64_t utc,uint32_t admission,int16_t weather,uint32_t sequence) {
        CurveObservation x;x.monotonicMs=ms;x.utc=utc;x.admissionEpoch=admission;x.reportSequence=sequence;
        x.configGeneration=x.targetGeneration=1;x.outsideReportSequence=sequence;
        x.profileQualified=x.clockTrusted=x.normalAutomatic=x.outsideQualified=true;
        x.independentLimitsHealthy=x.waterTrackingVerified=true;x.outdoorCentiC=weather;
        x.reportedWaterCentiC=x.requestedWaterCentiC=interpolateWaterCurve(weather,group().curveCentiC);x.zoneCount=2;
        for(unsigned i=0;i<2;++i) {
            auto& z=x.zones[i];z.zoneId=i+1;z.sourceId=i+11;z.reportSequence=sequence;
            z.sourceVerified=z.deliveryVerified=z.actuatorReady=true;z.targetCentiC=2100;z.temperatureCentiC=2070;
        }
        return x;
    }
    CurveAdvisory prospectiveCurve(std::optional<int16_t> liveWeather={}) {
        const int16_t currentWeather=liveWeather.value_or(outside);
        // Actual fresh full four-hour window; prospective configuration ONLY.
        // Not a live owner adoption/commit. New test scenario initial conditions
        // are declared separately; this is not continuous physical telemetry.
        for(unsigned m=0;m<=240;++m)
            curve.observe(curveObservation(16ULL*86400000+m*60000,epoch+16*86400+m*60,10,currentWeather,++seq));
        return curve.propose(16ULL*86400000+14400000,epoch+16*86400+14400,trained);
    }
};
struct Holdout {
    // Fixed exogenous toy parameters, shared byte-for-byte by both trajectories.
    double storeResponse=.20,loss=.001,daytimeGain=0;
    unsigned sensorLossBegin=0,sensorLossEnd=0;
    std::optional<int16_t> calibrationWeather;
    bool windowDhwEvents=false;
    unsigned telemetryGapBegin=0,telemetryGapEnd=0;
};
struct Plant {
    double room=19,stored=0;
    int16_t temperature()const{return static_cast<int16_t>(std::lround(room*100));}
    void step(bool heat,double outside,int16_t water,double power,const Holdout& h,bool gainActive) {
        // Toy low-order plant, not fitted or claimed for Mark's house.
        const auto gain=heat?.08*power*std::max(0.0,(water/100.0-20)/25):0;
        stored+=(gain-stored)*h.storeResponse;
        room+=stored-(room-outside)*h.loss+(gainActive?h.daytimeGain:0);
    }
};
ReplayProfile scoreProfile() {
    ReplayProfile p;p.reviewed=true;p.maximumGapMs=120000;p.minimumComparedMs=3600000;p.minimumOccupiedMs=600000;
    p.maximumDurationMs=56ULL*86400000;p.minimumCoverageBp=p.minimumInBandBp=9000;
    p.comfortBandCentiC=50;p.maximumOvershootCentiC=100;p.minimumCompletedBurns=3;
    p.minimumDeadlines=10;p.minimumDeadlineHitBp=8000;return p;
}
struct Choice {bool warm=false,coast=false,curve=false,holdWarm=false;};
// TEST reference execution contract, disabled for all immutable legacy rows.
// A newly-qualified start is an adoption event, not an instruction to erase a
// running preheat whenever its moving ROOM temperature leaves start comparability.
struct WarmExecution {
    bool enabled=false,active=false,haveTime=false;
    uint64_t lastMs=0;int64_t lastUtc=0,until=0;
    uint32_t owner=0,generation=0;
    int16_t target=0,automatic=0,outdoor=0,water=0,adoptTemperature=0;
    std::array<uint8_t,32> bindingDigest{};
    explicit WarmExecution(bool enable=false):enabled(enable){}
    void invalidate(){active=false;}
    std::optional<int16_t> step(uint64_t now,int64_t utc,const ScheduleTarget& schedule,
            const StartAdvisory& advice,bool permitted,LearningMode mode,uint32_t epochId,
            uint32_t targetGeneration,const std::array<uint8_t,32>& binding,
            int16_t weather,std::optional<int16_t> plannedWater,std::optional<int16_t> room) {
        const bool clockOk=!haveTime||(now>=lastMs&&utc>=lastUtc
            &&(utc-lastUtc)*1000-static_cast<int64_t>(now-lastMs)>=-2000
            &&(utc-lastUtc)*1000-static_cast<int64_t>(now-lastMs)<=2000);
        haveTime=true;lastMs=now;lastUtc=utc;
        const auto reason=std::string_view(advice.reason);
        const auto profile=warmProfile();
        const bool usable=enabled&&permitted&&mode==LearningMode::frozen&&clockOk
            &&epochId&&targetGeneration&&plannedWater&&room
            &&std::any_of(binding.begin(),binding.end(),[](auto b){return b!=0;})
            &&schedule.state==ScheduleState::active&&schedule.temperatureCentiC&&schedule.next
            &&schedule.next->atUtc>utc&&schedule.next->atUtc-utc<=profile.maximumLeadSec
            &&schedule.next->temperatureCentiC>*schedule.temperatureCentiC
            &&(reason=="shadow_optimum_start_advisory"||reason=="model_insufficient_evidence"
                ||reason=="model_no_warmup_needed");
        if(!usable){invalidate();return {};}
        if(active&&(owner!=epochId||generation!=targetGeneration||bindingDigest!=binding
            ||until!=schedule.next->atUtc||target!=schedule.next->temperatureCentiC
            ||automatic!=*schedule.temperatureCentiC
            ||outdoor!=weather||water!=*plannedWater)){invalidate();return {};}
        const bool stillCovered=advice.eligibleStarts>=profile.minimumStarts
            &&advice.distinctDays>=profile.minimumDistinctDays&&advice.coveredDays>=profile.minimumSpanDays;
        if(active&&reason=="model_insufficient_evidence"&&(!stillCovered||*room<adoptTemperature)) {
            invalidate();return {};
        }
        if(!active&&advice.startNow&&advice.plannedStartUtc&&*advice.plannedStartUtc<=utc
            &&reason=="shadow_optimum_start_advisory"&&stillCovered
            &&advice.comparableStarts>=profile.minimumComparableStarts
            &&advice.leadSec&&advice.leadSec<=profile.maximumLeadSec) {
            active=true;owner=epochId;generation=targetGeneration;bindingDigest=binding;
            until=schedule.next->atUtc;target=schedule.next->temperatureCentiC;
            automatic=*schedule.temperatureCentiC;adoptTemperature=*room;
            outdoor=weather;water=*plannedWater;
        }
        return active?std::optional<int16_t>(target):std::nullopt;
    }
};
struct Outcome {
    ReplayAssessment score;
    unsigned warmUsed=0,coastUsed=0,curveUsed=0,differentDemand=0,differentWater=0;
    unsigned inhibited=0,unsafeModelDecisions=0,sensorMissingMinutes=0,knownGainMinutes=0;
    unsigned warmWindowsBefore=0,warmWindowsAfter=0,coastWindowsBefore=0,coastWindowsAfter=0;
    unsigned curveWindowsBefore=0,curveWindowsAfter=0;
    bool trained=false,curveValid=true,feedAccepted=true;
    unsigned windowMinutes=0,dhwMinutes=0,faultMinutes=0,absentTelemetryMinutes=0,reconnects=0;
    unsigned missingDeadlineObservations=0,lossAdviceProbes=0,staleAdviceAfterLoss=0,curveDroppedOnLoss=0;
    unsigned maxReportedWarmComparable=0,maxReportedCoastComparable=0;
    unsigned heldWarmMinutes=0,traceRows=0,traceDropped=0;
    std::string baselineTraceDigest;
    std::optional<unsigned> reportedCurveComparable;
    std::string scenarioDigest;
};
// Optional bounded diagnostics on THIS existing replay, never a second plant.
struct Trace {
    std::ofstream file;
    Outcome& outcome;
    Choice choice;
    unsigned count=0;
    static constexpr unsigned maximumRows=4096;
    Trace(Outcome& r,Choice c):outcome(r),choice(c) {
        if(const auto path=std::getenv("OPENTHERMOSTAT_F9_TRACE"))file.open(path,std::ios::app);
    }
    void frame(unsigned minute,const char* event,const StartAdvisory& start,
               int16_t a,int16_t b,int16_t target,int16_t effective,bool heatA,bool heatB,bool permitted) {
        if(!file.is_open())return;
        if(count>=maximumRows){++outcome.traceDropped;return;}
        ++count;++outcome.traceRows;
        file<<"{\"scenario_sha256\":\""<<outcome.scenarioDigest<<"\",\"warm\":"<<choice.warm
            <<",\"coast\":"<<choice.coast<<",\"curve\":"<<choice.curve<<",\"hold_warm\":"<<choice.holdWarm<<",\"minute\":"<<minute
            <<",\"event\":\""<<event<<"\",\"baseline_centi_c\":"<<a<<",\"candidate_centi_c\":"<<b
            <<",\"target_centi_c\":"<<target<<",\"effective_centi_c\":"<<effective
            <<",\"warm_reason\":\""<<start.reason<<"\",\"comparable_starts\":"<<unsigned(start.comparableStarts)
            <<",\"lead_sec\":"<<start.leadSec<<",\"start_now\":"<<start.startNow
            <<",\"heat_baseline\":"<<heatA<<",\"heat_candidate\":"<<heatB<<",\"permitted\":"<<permitted<<"}\n";
    }
};
Outcome run(int16_t weather,Choice enabled,bool blocked=false,double holdoutPower=1.0,bool coastEntry=false,Holdout holdout={}) {
    Calibrated models(holdout.calibrationWeather.value_or(weather));Outcome r;r.trained=models.trained;
    r.warmWindowsBefore=models.warm.snapshot().count;r.coastWindowsBefore=models.coast.snapshot().count;r.curveWindowsBefore=models.curve.snapshot().count;
    auto baseGroup=group(),candidateGroup=baseGroup;
    if(enabled.curve&&!blocked) {
        const auto proposal=models.prospectiveCurve(weather);
        r.reportedCurveComparable=proposal.comparableWindows;
        if(proposal.proposed) {candidateGroup.curveCentiC=proposal.newCurve;++r.curveUsed;}
        r.curveValid=candidateGroup.valid();
    }
    // Hash all exogenous scenario switches; model choices are endogenous and
    // intentionally excluded. Real existing OpenSSL SHA provider, not a fake.
    std::ostringstream exogenous;
    exogenous<<std::setprecision(17)<<"toy-plant-v2;heaterGain=.08;duration=20160min;step=60s;"
        <<"targets=19@00,21@06,19@22;fault=600:610;stale=3000:3010;weather="<<weather
        <<";power="<<holdoutPower<<";blocked="<<blocked<<";coastEntry="<<coastEntry
        <<";store="<<holdout.storeResponse<<";loss="<<holdout.loss
        <<";daytimeGain="<<holdout.daytimeGain<<";sensorLoss="<<holdout.sensorLossBegin<<":"<<holdout.sensorLossEnd;
    // Preserve EXACT old default digest/oracle; hash new exogenous switches only
    // when explicitly enabled, never endogenous candidate decisions.
    if(holdout.calibrationWeather)exogenous<<";calibrationWeather="<<*holdout.calibrationWeather;
    if(holdout.windowDhwEvents)exogenous<<";window=1200:1230;dhw=1800:1810";
    if(holdout.telemetryGapEnd>holdout.telemetryGapBegin)
        exogenous<<";absentTelemetry="<<holdout.telemetryGapBegin<<":"<<holdout.telemetryGapEnd<<";freshOwnerOnReconnect=21";
    r.scenarioDigest=controlTestHash(exogenous.str());
    std::array<uint8_t,32> identity{};
    for(unsigned i=0;i<32;++i)
        identity[i]=static_cast<uint8_t>(std::stoul(r.scenarioDigest.substr(i*2,2),nullptr,16));
    r.baselineTraceDigest=controlTestHash("baseline-chain-v1;"+r.scenarioDigest);
    Trace trace(r,enabled);
    ThermalReplay evaluator(scoreProfile(),identity);
    Plant a,b;ZoneRegulator baseline,candidate;
    uint64_t coastUntil=0;WarmExecution warmExecution(enabled.holdWarm);
    const auto modelBinding=models.warm.snapshot().bindingDigest;
    const unsigned offset=coastEntry?1305:0; // declared 21:45 initial episode
    const uint64_t baseMs=17ULL*86400000+offset*60000;
    const int64_t baseUtc=epoch+17*86400+offset*60;
    bool previousCandidateHeat=false,previousBaselineHeat=false,previousWarm=false;
    const char* previousWarmReason="initial";
    if(coastEntry) {
        a.room=b.room=20.9;
        a.stored=b.stored=(20.9-weather/100.0)*.001;
        baseline.step(baseMs-60000,2090,2110,true);
        candidate.step(baseMs-60000,2090,2110,true);
        for(unsigned m=0;m<30;++m) {
            auto prior=observation(baseMs-1800000+m*60000,baseUtc-1800+m*60,
                ++models.seq,20,2090,weather,models.water,true);
            prior.targetGeneration=2;models.coast.observe(prior);
        }
        previousCandidateHeat=true;
    }
    for(unsigned minute=0;minute<=14*1440;++minute) {
        const unsigned day=(minute+offset)/1440,tod=(minute+offset)%1440;
        const bool occupied=tod>=360&&tod<1320;
        const int16_t commonTarget=occupied?2100:1900;
        const bool fault=minute>=600&&minute<610;
        const bool stale=minute>=3000&&minute<3010;
        const bool sensorLost=minute>=holdout.sensorLossBegin&&minute<holdout.sensorLossEnd;
        const bool gainActive=holdout.daytimeGain>0&&tod>=600&&tod<900;
        const bool window=holdout.windowDhwEvents&&minute>=1200&&minute<1230;
        const bool dhw=holdout.windowDhwEvents&&minute>=1800&&minute<1810;
        const bool absent=minute>=holdout.telemetryGapBegin&&minute<holdout.telemetryGapEnd;
        const bool permitted=!(fault||stale||blocked||sensorLost||window||dhw||absent);
        r.windowMinutes+=window?1:0;r.dhwMinutes+=dhw?1:0;r.faultMinutes+=fault?1:0;
        const bool modelPermitted=permitted&&!gainActive;
        r.sensorMissingMinutes+=sensorLost?1:0;r.knownGainMinutes+=gainActive?1:0;
        const auto now=baseMs+minute*60000;
        const auto utc=baseUtc+minute*60;
        const auto nextMinute=day*1440+(tod<360?360:tod<1320?1320:1800);
        const int16_t nextTarget=tod<360||tod>=1320?2100:1900;
        ScheduleTarget schedule{ScheduleState::active,commonTarget,
            ScheduleTransition{epoch+17*86400+nextMinute*60,nextTarget}};
        if(absent) {
            ++r.absentTelemetryMinutes;if(tod==360)++r.missingDeadlineObservations;
            r.baselineTraceDigest=controlTestHash(r.baselineTraceDigest+";"+std::to_string(minute)+";absent_sample");
            if(minute==holdout.telemetryGapBegin) {
                models.warm.invalidateAdmission();models.coast.invalidateAdmission();models.curve.invalidateAdmission();
                const auto warm=models.warm.propose(now,utc,schedule,models.water);
                const auto coast=models.coast.propose(now,utc,schedule,models.trained);
                r.maxReportedCoastComparable=std::max(r.maxReportedCoastComparable,unsigned(coast.comparableCycles));
                const auto curve=models.curve.propose(now,utc,models.trained);
                r.lossAdviceProbes+=3;
                r.staleAdviceAfterLoss+=(warm.plannedStartUtc?1:0)+(coast.coastNow?1:0)+(curve.proposed?1:0);
                if(candidateGroup.curveCentiC!=baseGroup.curveCentiC)++r.curveDroppedOnLoss;
                candidateGroup=baseGroup; // no automatic prospective re-adoption after owner loss
            }
            coastUntil=0;warmExecution.invalidate();++r.inhibited;
            const auto aStop=baseline.step(now,std::nullopt,std::nullopt,false);
            const auto bStop=candidate.step(now,std::nullopt,std::nullopt,false);
            r.unsafeModelDecisions+=(aStop.demand||bStop.demand)?1:0;
            a.step(false,weather/100.0,2000,holdoutPower,holdout,gainActive);
            b.step(false,weather/100.0,2000,holdoutPower,holdout,gainActive);
            previousCandidateHeat=false;
            // No synthetic temperature or CV observation invented in the gap.
            // Next real frame exposes the actual monotonic gap to evaluator.
            continue;
        }
        if(holdout.telemetryGapEnd>holdout.telemetryGapBegin&&minute==holdout.telemetryGapEnd)++r.reconnects;
        GroupWaterInput input;input.demand=true;input.sourceValid=permitted;input.deliveryAvailable=permitted;
        input.independentLimitHealthy=true;input.outdoorFresh=true;input.outdoorCentiC=weather;input.roomErrorCentiC=0;
        const auto wa=groupWaterTarget(baseGroup,input),wb=groupWaterTarget(candidateGroup,input);
        const uint32_t currentOwner=(holdout.telemetryGapEnd>holdout.telemetryGapBegin&&minute>=holdout.telemetryGapEnd)?21:20;
        auto live=observation(now,utc,++models.seq,currentOwner,b.temperature(),weather,wb.target.value_or(models.water),previousCandidateHeat);
        live.targetGeneration=day*2+(occupied?2:1);live.sourceVerified=permitted;live.fault=fault;live.windowOpen=window;live.dhw=dhw;
        live.unexplainedGain=gainActive;if(sensorLost)live.temperatureCentiC.reset();
        models.warm.observe(live);models.coast.observe(live);
        int16_t effective=commonTarget;bool chooseCoast=false;
        const auto start=models.warm.propose(now,utc,schedule,wb.target);
        r.maxReportedWarmComparable=std::max(r.maxReportedWarmComparable,unsigned(start.comparableStarts));
        if(enabled.warm&&modelPermitted&&start.startNow) {effective=nextTarget;++r.warmUsed;}
        if(enabled.holdWarm) {
            const auto adopted=warmExecution.step(now,utc,schedule,start,enabled.warm&&modelPermitted,
                models.warm.mode(),currentOwner,live.targetGeneration,modelBinding,weather,wb.target,live.temperatureCentiC);
            effective=adopted.value_or(commonTarget);
            if(adopted&&!start.startNow)++r.heldWarmMinutes;
        }
        const auto coast=models.coast.propose(now,utc,schedule,models.trained);
        r.maxReportedCoastComparable=std::max(r.maxReportedCoastComparable,unsigned(coast.comparableCycles));
        if(enabled.coast&&modelPermitted&&coast.coastNow) {coastUntil=now+coast.horizonSec*1000;++r.coastUsed;}
        if(!modelPermitted) {coastUntil=0;++r.inhibited;}
        if(enabled.coast&&modelPermitted&&coastUntil>now) chooseCoast=true;
        const auto x=baseline.step(now,a.temperature(),commonTarget,permitted);
        const auto y=candidate.step(now,b.temperature(),effective,permitted);
        const bool heatA=x.demand&&wa.target.has_value();
        const bool heatB=y.demand&&!chooseCoast&&wb.target.has_value();
        const bool warmSelected=effective!=commonTarget;
        const bool reasonChanged=std::string_view(previousWarmReason)!=start.reason;
        if(tod==360||warmSelected!=previousWarm||heatA!=previousBaselineHeat||heatB!=previousCandidateHeat||reasonChanged)
            trace.frame(minute,tod==360?"arrival":previousWarm&&!warmSelected?"warm_withdrawal":warmSelected&&!previousWarm?"warm_start":reasonChanged?"advice_reason":"cv_edge",
                start,a.temperature(),b.temperature(),commonTarget,effective,heatA,heatB,permitted);
        previousWarm=warmSelected;previousWarmReason=start.reason;previousBaselineHeat=heatA;
        r.differentDemand+=heatA!=heatB?1:0;
        r.differentWater+=wa.target&&wb.target&&*wa.target!=*wb.target?1:0;
        if((!permitted&&heatB)||(!modelPermitted&&(effective!=commonTarget||chooseCoast)))++r.unsafeModelDecisions;
        ReplayFrame f;f.baselineScenario=f.candidateScenario=identity;f.monotonicMs=minute*60000;f.utc=utc;
        f.sequence=minute+1;f.scheduleKnown=true;f.occupied=occupied;
        f.conditionsQualified=permitted;f.burnerStatesQualified=permitted;
        f.targetCentiC=commonTarget;f.baselineTemperatureCentiC=a.temperature();f.candidateTemperatureCentiC=b.temperature();
        // CV bits below are SYNTHETIC plant delivery, not boiler/burner evidence.
        f.baselineCv=heatA;f.candidateCv=heatB;
        if(sensorLost){f.baselineTemperatureCentiC.reset();f.candidateTemperatureCentiC.reset();}
        f.baselineSafetyViolation=!permitted&&heatA;f.candidateSafetyViolation=!permitted&&heatB;
        if(tod==360) {f.deadlineId=coastEntry?day:day+1;f.deadlineTargetCentiC=2100;}
        std::ostringstream baselineFrame;
        baselineFrame<<r.baselineTraceDigest<<';'<<f.monotonicMs<<';'<<f.utc<<';'<<f.sequence
            <<';'<<f.occupied<<';'<<f.conditionsQualified<<';'<<f.burnerStatesQualified
            <<';'<<commonTarget<<';'<<f.baselineTemperatureCentiC.value_or(-9999)
            <<';'<<f.baselineCv<<';'<<wa.target.value_or(-9999)<<';'<<f.deadlineId;
        r.baselineTraceDigest=controlTestHash(baselineFrame.str());
        if(!evaluator.add(f)){r.feedAccepted=false;break;}
        a.step(heatA,weather/100.0,wa.target.value_or(2000),holdoutPower,holdout,gainActive);
        b.step(heatB,weather/100.0,wb.target.value_or(2000),holdoutPower,holdout,gainActive);
        previousCandidateHeat=heatB;
    }
    r.score=evaluator.assessment();r.warmWindowsAfter=models.warm.snapshot().count;
    r.coastWindowsAfter=models.coast.snapshot().count;r.curveWindowsAfter=models.curve.snapshot().count;return r;
}
void record(const char* name,const Outcome& r) {
    const auto* path=std::getenv("OPENTHERMOSTAT_ENABLED_REPLAY_EVIDENCE");if(!path)return;
    std::ofstream out(path,std::ios::app);const auto& s=r.score;
    const auto a=ThermalReplay::meanAbsoluteErrorCentiC(s.baseline,s.occupiedComparedMs);
    const auto b=ThermalReplay::meanAbsoluteErrorCentiC(s.candidate,s.occupiedComparedMs);
    out<<std::setprecision(12)<<"{\"scenario\":\""<<name<<"\",\"scope\":\"enabled advice consumed by test-only reference policy; synthetic calibration/plant/CV proxy, not production model owner/home history/14 actual days/heat savings\","
        <<"\"scenario_sha256\":\""<<r.scenarioDigest<<"\",\"trained\":"<<(r.trained?"true":"false")<<",\"accepted\":"<<(s.accepted?"true":"false")
        <<",\"reason\":\""<<s.reason<<"\",\"comparable\":"<<(s.comparable?"true":"false")
        <<",\"warm_uses\":"<<r.warmUsed<<",\"coast_uses\":"<<r.coastUsed<<",\"curve_profile_uses\":"<<r.curveUsed
        <<",\"different_heat_minutes\":"<<r.differentDemand<<",\"different_water_minutes\":"<<r.differentWater
        <<",\"unsafe_model_decisions\":"<<r.unsafeModelDecisions<<",\"baseline_mae_centi_c\":";
    if(a)out<<*a;else out<<"null";out<<",\"candidate_mae_centi_c\":";if(b)out<<*b;else out<<"null";
    out<<",\"baseline_starts\":"<<s.baseline.observedCvStarts<<",\"candidate_starts\":"<<s.candidate.observedCvStarts
        <<",\"baseline_cv_ms\":"<<s.baseline.cvMs<<",\"candidate_cv_ms\":"<<s.candidate.cvMs
        <<",\"deadline_attempts\":"<<s.deadlineAttempts<<",\"qualified_deadlines\":"<<s.qualifiedDeadlines
        <<",\"baseline_hits\":"<<s.baseline.deadlineHits<<",\"candidate_hits\":"<<s.candidate.deadlineHits
        <<",\"baseline_maximum_overshoot_centi_c\":"<<s.baseline.maximumOvershootCentiC
        <<",\"candidate_maximum_overshoot_centi_c\":"<<s.candidate.maximumOvershootCentiC
        <<",\"total_ms\":"<<s.totalMs<<",\"compared_ms\":"<<s.comparedMs
        <<",\"occupied_known_ms\":"<<s.occupiedKnownMs<<",\"occupied_compared_ms\":"<<s.occupiedComparedMs
        <<",\"excluded_ms\":"<<s.excludedMs<<",\"cv_qualified_ms\":"<<s.cvQualifiedMs
        <<",\"baseline_in_band_occupied_ms\":"<<s.baseline.inBandOccupiedMs
        <<",\"candidate_in_band_occupied_ms\":"<<s.candidate.inBandOccupiedMs
        <<",\"sensor_missing_minutes\":"<<r.sensorMissingMinutes<<",\"known_gain_minutes\":"<<r.knownGainMinutes
        <<",\"warm_windows_before\":"<<r.warmWindowsBefore<<",\"warm_windows_after\":"<<r.warmWindowsAfter
        <<",\"coast_windows_before\":"<<r.coastWindowsBefore<<",\"coast_windows_after\":"<<r.coastWindowsAfter
        <<",\"curve_windows_before\":"<<r.curveWindowsBefore<<",\"curve_windows_after\":"<<r.curveWindowsAfter
        <<",\"window_minutes\":"<<r.windowMinutes<<",\"dhw_minutes\":"<<r.dhwMinutes
        <<",\"fault_minutes\":"<<r.faultMinutes<<",\"absent_telemetry_minutes\":"<<r.absentTelemetryMinutes
        <<",\"fresh_reconnect_epochs\":"<<r.reconnects<<",\"missing_deadline_observations\":"<<r.missingDeadlineObservations
        <<",\"owner_loss_advice_probes\":"<<r.lossAdviceProbes<<",\"stale_advice_after_owner_loss\":"<<r.staleAdviceAfterLoss
        <<",\"curve_prospective_cleared_on_owner_loss\":"<<r.curveDroppedOnLoss
        <<",\"max_reported_warm_comparable\":"<<r.maxReportedWarmComparable
        <<",\"max_reported_coast_comparable\":"<<r.maxReportedCoastComparable
        <<",\"reported_curve_comparable\":";
    if(r.reportedCurveComparable)out<<*r.reportedCurveComparable;else out<<"null";
    out<<",\"candidate_safety_violations\":"<<s.candidate.safetyViolations
        <<",\"baseline_completed_burns\":"<<s.baseline.completedBurns<<",\"candidate_completed_burns\":"<<s.candidate.completedBurns
        <<",\"baseline_completed_burn_ms\":"<<s.baseline.completedBurnMs<<",\"candidate_completed_burn_ms\":"<<s.candidate.completedBurnMs
        <<",\"comfort_noninferior\":"<<s.comfortNonInferior<<",\"cycling_available\":"<<s.cyclingAvailable
        <<",\"cycling_noninferior\":"<<s.cyclingNonInferior<<",\"timing_available\":"<<s.timingAvailable
        <<",\"timing_noninferior\":"<<s.timingNonInferior<<",\"safety_noninferior\":"<<s.safetyNonInferior
        <<",\"held_warm_minutes\":"<<r.heldWarmMinutes
        <<",\"baseline_chain_sha256\":\""<<r.baselineTraceDigest<<"\",\"trace_rows\":"<<r.traceRows
        <<",\"trace_dropped\":"<<r.traceDropped<<",\"physical_output\":false}\n";
}
TEST(ThermalEnabledReplay, RealObserveTrainingHasSixIndependentSyntheticEpisodesAndOneBoundedCurveProposal) {
    for(int16_t weather:{500,1500}) {
        Calibrated c(weather);ASSERT_TRUE(c.trained);EXPECT_EQ(c.warm.mode(),LearningMode::frozen);
        EXPECT_EQ(c.coast.mode(),LearningMode::frozen);
        auto proposal=c.prospectiveCurve();ASSERT_TRUE(proposal.proposed);
        unsigned changes=0;for(unsigned i=0;i<9;++i)changes+=proposal.newCurve[i]!=proposal.oldCurve[i]?1:0;
        EXPECT_EQ(changes,1u);EXPECT_EQ(proposal.newKnotCentiC-proposal.oldKnotCentiC,20);
    }
}
TEST(ThermalEnabledReplay, EnabledWarmAndCombinedAdviceReallyChangeSameColdAndMildHoldoutTrajectories) {
    for(int16_t weather:{500,1500})for(bool curve:{false,true}) {
        auto r=run(weather,{true,true,curve});ASSERT_TRUE(r.trained);EXPECT_TRUE(r.feedAccepted);
        EXPECT_TRUE(r.curveValid);EXPECT_GT(r.warmUsed,0u);EXPECT_GT(r.differentDemand,0u);
        if(curve){EXPECT_EQ(r.curveUsed,1u);EXPECT_GT(r.differentWater,0u);}
        EXPECT_EQ(r.unsafeModelDecisions,0u);EXPECT_EQ(r.score.candidate.safetyViolations,0u);
        // This deliberately non-fitted calibration underpredicts warm-up.
        // Lower sampled MAE must not waive arrivals/cycling or turn green.
        EXPECT_FALSE(r.score.accepted);
        EXPECT_EQ(r.score.deadlineAttempts,14u);EXPECT_EQ(r.score.candidate.deadlineHits,0u);
        EXPECT_FALSE(r.score.timingNonInferior);
        const auto baseMae=ThermalReplay::meanAbsoluteErrorCentiC(r.score.baseline,r.score.occupiedComparedMs);
        const auto candidateMae=ThermalReplay::meanAbsoluteErrorCentiC(r.score.candidate,r.score.occupiedComparedMs);
        ASSERT_TRUE(baseMae&&candidateMae);EXPECT_LT(*candidateMae,*baseMae);
        record(weather==500?(curve?"cold_warm_coast_curve":"cold_warm_coast"):(curve?"mild_warm_coast_curve":"mild_warm_coast"),r);
    }
}
TEST(ThermalEnabledReplay, MissingAdmissionCannotBeUpgradedByEnabledFlagOrStoredModels) {
    auto r=run(500,{true,true,true},true);
    EXPECT_EQ(r.warmUsed,0u);EXPECT_EQ(r.coastUsed,0u);EXPECT_EQ(r.curveUsed,0u);EXPECT_EQ(r.differentDemand,0u);
    EXPECT_EQ(r.unsafeModelDecisions,0u);EXPECT_FALSE(r.score.comparable);EXPECT_FALSE(r.score.accepted);
    record("blocked_source_models_cannot_authorize",r);
}
TEST(ThermalEnabledReplay, HoldoutMismatchIsReportedWithoutAlteringCalibrationOrNoninferiorityGates) {
    const auto normal=run(500,{true,true,true});
    const auto mismatch=run(500,{true,true,true},false,.5);
    EXPECT_TRUE(normal.feedAccepted&&mismatch.feedAccepted);
    EXPECT_TRUE(mismatch.trained);EXPECT_EQ(mismatch.score.candidate.safetyViolations,0u);
    EXPECT_NE(normal.score.candidate.absoluteErrorTwiceCentiMs,mismatch.score.candidate.absoluteErrorTwiceCentiMs);
    EXPECT_FALSE(mismatch.score.accepted);
    record("cold_underpowered_holdout_not_tuned_to_pass",mismatch);
}
TEST(ThermalEnabledReplay, CoastOnlyReferencePolicyChangesActualPairedPlantTrajectoryWithoutWarmOrCurve) {
    auto r=run(500,{false,true,false},false,1.0,true);
    EXPECT_TRUE(r.trained&&r.feedAccepted);EXPECT_GT(r.coastUsed,0u);EXPECT_GT(r.differentDemand,0u);
    EXPECT_EQ(r.warmUsed,0u);EXPECT_EQ(r.curveUsed,0u);EXPECT_EQ(r.differentWater,0u);
    EXPECT_EQ(r.score.deadlineAttempts,14u);
    EXPECT_EQ(r.unsafeModelDecisions,0u);EXPECT_EQ(r.score.candidate.safetyViolations,0u);
    record("cold_coast_only_declared_heat_initial_state",r);
}
TEST(ThermalEnabledReplay, CoastAdviceIsConsumedOnlyBeforeLowerTransitionAndPreservesExplicitBounds) {
    Calibrated c(500);ASSERT_TRUE(c.trained);
    // Separate declared synthetic episode with real 30-min delivered heat
    // observation, same model binding and fresh source. Not inferred from intent.
    const auto base=17ULL*86400000;
    for(unsigned m=0;m<=30;++m)
        c.coast.observe(observation(base+m*60000,epoch+17*86400+m*60,++c.seq,20,2090,500,4500,true));
    const auto now=base+1800000;const auto utc=epoch+17*86400+1800;
    ScheduleTarget s{ScheduleState::active,2100,ScheduleTransition{utc+900,1900}};
    auto advice=c.coast.propose(now,utc,s,true);ASSERT_TRUE(advice.coastNow);
    EXPECT_GE(*advice.worstLowerCentiC,2050);EXPECT_LE(*advice.worstUpperCentiC,2150);
    ZoneRegulator baseline,candidate;baseline.step(now-60000,2090,2110,true);candidate.step(now-60000,2090,2110,true);
    const auto a=baseline.step(now,2090,2100,true),b=candidate.step(now,2090,2100,true);
    EXPECT_TRUE(a.demand&&b.demand);
    const bool referenceHeat=b.demand&&!advice.coastNow;EXPECT_FALSE(referenceHeat);
    // Fresh invalidation wins before this reference policy could use a cache.
    auto lost=observation(now+60000,utc+60,++c.seq,20,2090,500,4500,true);lost.sourceVerified=false;
    c.coast.observe(lost);EXPECT_FALSE(c.coast.propose(now+60000,utc+60,s,true).coastNow);
    s.next=ScheduleTransition{utc+900,2200};EXPECT_FALSE(c.coast.propose(now,utc,s,true).coastNow);
}
TEST(ThermalEnabledReplay, SlowFloorHoldoutUsesSameLongStorageDynamicsWithoutChangingCalibration) {
    Holdout h;h.storeResponse=.02;
    const auto normal=run(500,{true,true,true});
    const auto slow=run(500,{true,true,true},false,1.0,false,h);
    ASSERT_TRUE(slow.feedAccepted&&slow.trained);EXPECT_GT(slow.warmUsed,0u);
    EXPECT_NE(normal.scenarioDigest,slow.scenarioDigest);
    EXPECT_NE(normal.score.candidate.absoluteErrorTwiceCentiMs,slow.score.candidate.absoluteErrorTwiceCentiMs);
    EXPECT_EQ(slow.warmWindowsBefore,slow.warmWindowsAfter);EXPECT_EQ(slow.coastWindowsBefore,slow.coastWindowsAfter);
    EXPECT_EQ(slow.unsafeModelDecisions,0u);EXPECT_EQ(slow.score.candidate.safetyViolations,0u);
    record("slow_floor_storage_holdout",slow);
}
TEST(ThermalEnabledReplay, DeclaredExternalGainInhibitsModelAdviceWithoutDisablingNormalThermostat) {
    Holdout h;h.daytimeGain=.015;
    const auto r=run(500,{true,true,false},false,1.0,false,h);
    ASSERT_TRUE(r.feedAccepted&&r.trained);EXPECT_EQ(r.knownGainMinutes,14u*300u);
    EXPECT_EQ(r.unsafeModelDecisions,0u);EXPECT_EQ(r.score.candidate.safetyViolations,0u);
    EXPECT_EQ(r.warmWindowsBefore,r.warmWindowsAfter);EXPECT_EQ(r.coastWindowsBefore,r.coastWindowsAfter);
    record("known_external_gain_holdout",r);
}
TEST(ThermalEnabledReplay, SmallLoadHoldoutRetainsCyclingAndComfortEvidenceRatherThanDeclaringBenefit) {
    Holdout h;h.loss=.00025;
    const auto r=run(1700,{true,true,true},false,.5,false,h);
    ASSERT_TRUE(r.feedAccepted&&r.trained);EXPECT_GT(r.score.baseline.observedCvStarts,0u);
    EXPECT_EQ(r.unsafeModelDecisions,0u);EXPECT_EQ(r.score.candidate.safetyViolations,0u);
    EXPECT_EQ(r.warmWindowsBefore,r.warmWindowsAfter);EXPECT_EQ(r.coastWindowsBefore,r.coastWindowsAfter);
    record("small_load_low_loss_holdout",r);
}
TEST(ThermalEnabledReplay, ExtendedSensorLossRemovesSamplesStopsDemandAndCannotPassCoverage) {
    Holdout h;h.sensorLossBegin=2*1440;h.sensorLossEnd=5*1440;
    const auto r=run(500,{true,true,true},false,1.0,false,h);
    ASSERT_TRUE(r.feedAccepted&&r.trained);EXPECT_EQ(r.sensorMissingMinutes,3u*1440u);
    EXPECT_GE(r.score.excludedMs,uint64_t(r.sensorMissingMinutes)*60000);
    EXPECT_LT(r.score.comparedMs*10000,r.score.totalMs*9000);
    EXPECT_FALSE(r.score.comparable);EXPECT_FALSE(r.score.accepted);
    EXPECT_STREQ(r.score.reason,"replay_insufficient_data");
    EXPECT_EQ(r.unsafeModelDecisions,0u);EXPECT_EQ(r.score.candidate.safetyViolations,0u);
    EXPECT_EQ(r.warmWindowsBefore,r.warmWindowsAfter);EXPECT_EQ(r.coastWindowsBefore,r.coastWindowsAfter);
    record("extended_sensor_loss_no_fabricated_samples",r);
}

TEST(ThermalEnabledReplay, IncomparableWeatherCannotExtrapolateStoredWarmCoastOrCurveAdvice) {
    Holdout h;h.calibrationWeather=500;
    const auto r=run(-2000,{true,true,true},false,1.0,false,h);
    ASSERT_TRUE(r.feedAccepted&&r.trained);
    EXPECT_EQ(r.warmUsed,0u);EXPECT_EQ(r.coastUsed,0u);EXPECT_EQ(r.curveUsed,0u);
    EXPECT_EQ(r.maxReportedWarmComparable,0u);EXPECT_EQ(r.maxReportedCoastComparable,0u);
    ASSERT_TRUE(r.reportedCurveComparable);EXPECT_EQ(*r.reportedCurveComparable,0u);
    EXPECT_EQ(r.differentDemand,0u);EXPECT_EQ(r.differentWater,0u);
    EXPECT_EQ(r.unsafeModelDecisions,0u);EXPECT_FALSE(r.score.accepted);
    record("incomparable_weather_no_extrapolated_advice",r);
}
TEST(ThermalEnabledReplay, WindowAndDhwPreemptEnabledAdviceAlongsideExistingFaults) {
    Holdout h;h.windowDhwEvents=true;const auto r=run(500,{true,true,true},false,1.0,false,h);
    ASSERT_TRUE(r.feedAccepted&&r.trained);EXPECT_EQ(r.windowMinutes,30u);EXPECT_EQ(r.dhwMinutes,10u);
    EXPECT_EQ(r.faultMinutes,10u);EXPECT_GT(r.warmUsed,0u);
    EXPECT_EQ(r.unsafeModelDecisions,0u);EXPECT_EQ(r.score.baseline.safetyViolations,0u);EXPECT_EQ(r.score.candidate.safetyViolations,0u);
    EXPECT_EQ(r.warmWindowsBefore,r.warmWindowsAfter);EXPECT_EQ(r.coastWindowsBefore,r.coastWindowsAfter);
    EXPECT_FALSE(r.score.accepted);record("window_dhw_fault_preempt_enabled_advice",r);
}
TEST(ThermalEnabledReplay, MissingTelemetryGapAndFreshReconnectNeverRestorePriorAdmissionOrProspectiveCurve) {
    Holdout h;h.telemetryGapBegin=5*1440+300;h.telemetryGapEnd=h.telemetryGapBegin+180;
    const auto r=run(500,{true,true,true},false,1.0,false,h);
    ASSERT_TRUE(r.feedAccepted&&r.trained);EXPECT_EQ(r.absentTelemetryMinutes,180u);EXPECT_EQ(r.reconnects,1u);
    EXPECT_EQ(r.missingDeadlineObservations,1u);EXPECT_EQ(r.lossAdviceProbes,3u);EXPECT_EQ(r.staleAdviceAfterLoss,0u);
    EXPECT_EQ(r.curveDroppedOnLoss,1u);EXPECT_GE(r.score.excludedMs,180ULL*60000);
    EXPECT_EQ(r.score.deadlineAttempts,14u); // known schedule still has14; no denominator relaxation
    EXPECT_EQ(r.score.qualifiedDeadlines,13u); // one absent measurement stays unqualified, not zero/hit
    EXPECT_EQ(r.unsafeModelDecisions,0u);EXPECT_EQ(r.score.candidate.safetyViolations,0u);
    EXPECT_EQ(r.warmWindowsBefore,r.warmWindowsAfter);EXPECT_EQ(r.coastWindowsBefore,r.coastWindowsAfter);
    EXPECT_FALSE(r.score.accepted);record("absent_telemetry_fresh_reconnect_no_cached_advice",r);
}

TEST(ThermalEnabledReplay, AdoptedWarmExecutionDoesNotConfuseMovingRoomComparabilityWithSourceLoss) {
    WarmExecution disabled,execution(true);StartAdvisory start;
    start.startNow=true;start.plannedStartUtc=epoch;start.reason="shadow_optimum_start_advisory";
    start.eligibleStarts=6;start.comparableStarts=3;start.distinctDays=6;start.coveredDays=15;start.leadSec=1200;
    ScheduleTarget schedule{ScheduleState::active,1900,ScheduleTransition{epoch+1200,2100}};
    EXPECT_FALSE(disabled.step(0,epoch,schedule,start,true,LearningMode::frozen,1,1,binding(),500,4500,1900));
    ASSERT_EQ(execution.step(0,epoch,schedule,start,true,LearningMode::frozen,1,1,binding(),500,4500,1900),2100);
    start.startNow=false;start.plannedStartUtc.reset();start.reason="model_insufficient_evidence";
    EXPECT_EQ(execution.step(60000,epoch+60,schedule,start,true,LearningMode::frozen,1,1,binding(),500,4500,1900),2100);
    // A new start estimate is unnecessary, but live invalidation always wins.
    start.reason="model_source_not_fresh";
    EXPECT_FALSE(execution.step(120000,epoch+120,schedule,start,true,LearningMode::frozen,1,1,binding(),500,4500,1900));
    start.reason="model_insufficient_evidence";
    EXPECT_FALSE(execution.step(180000,epoch+180,schedule,start,true,LearningMode::frozen,1,1,binding(),500,4500,1900));
}
TEST(ThermalEnabledReplay, AdoptedWarmExecutionFailsClosedOnBindingOwnerTargetClockWaterAndStopChanges) {
    for(unsigned stop=0;stop<17;++stop) {
        WarmExecution execution(true);StartAdvisory start;
        start.startNow=true;start.plannedStartUtc=epoch;start.reason="shadow_optimum_start_advisory";
    start.eligibleStarts=6;start.comparableStarts=3;start.distinctDays=6;start.coveredDays=15;start.leadSec=1200;
        ScheduleTarget schedule{ScheduleState::active,1900,ScheduleTransition{epoch+1200,2100}};
        ASSERT_TRUE(execution.step(0,epoch,schedule,start,true,LearningMode::frozen,1,1,binding(),500,4500,1900));
        start.startNow=false;start.plannedStartUtc.reset();start.reason="model_insufficient_evidence";
        auto b=binding();uint32_t owner=1,generation=1;uint64_t now=60000;int64_t utc=epoch+60;
        bool permitted=true;auto mode=LearningMode::frozen;std::optional<int16_t> water=4500;int16_t weather=500;
        if(stop==0)permitted=false;
        if(stop==1)mode=LearningMode::disabled;
        if(stop==2)owner=2;
        if(stop==3)generation=2;
        if(stop==4)b[0]++;
        if(stop==5)schedule.next->temperatureCentiC=2200;
        if(stop==6)schedule.next->atUtc++;
        if(stop==7)utc+=30;
        if(stop==8)water.reset();
        if(stop==9)weather++;
        if(stop==10){now=1200000;utc=epoch+1200;}
        if(stop==11)water=4501;
        if(stop==12)schedule.temperatureCentiC=1800;
        if(stop==13)start.eligibleStarts=5;
        if(stop==14)start.reason="future_model_reason";
        if(stop==15)utc=epoch-1;
        if(stop==16)mode=LearningMode::shadow;
        // Changed scope must invalidate even if an old start flag is replayed.
        if(stop>=2&&stop<=6){start.startNow=true;start.plannedStartUtc=epoch;start.reason="shadow_optimum_start_advisory";}
        EXPECT_FALSE(execution.step(now,utc,schedule,start,permitted,mode,owner,generation,b,weather,water,1900))<<stop;
    }
}
TEST(ThermalEnabledReplay, BoundedStartConsumptionPairsAllOriginalScenariosWithoutTuningTrainingPlantOrGates) {
    const auto paired=[&](const char* name,int16_t weather,Choice before,bool blocked=false,double power=1.0,bool entry=false,Holdout h=Holdout{}) {
        const auto original=run(weather,before,blocked,power,entry,h);
        auto after=before;after.holdWarm=true;
        const auto fixed=run(weather,after,blocked,power,entry,h);
        EXPECT_EQ(original.scenarioDigest,fixed.scenarioDigest);EXPECT_EQ(original.baselineTraceDigest,fixed.baselineTraceDigest);
        EXPECT_EQ(original.score.totalMs,fixed.score.totalMs);
        EXPECT_EQ(original.score.baseline.absoluteErrorTwiceCentiMs,fixed.score.baseline.absoluteErrorTwiceCentiMs);
        EXPECT_EQ(original.score.baseline.observedCvStarts,fixed.score.baseline.observedCvStarts);
        EXPECT_EQ(original.score.baseline.cvMs,fixed.score.baseline.cvMs);EXPECT_EQ(original.score.baseline.deadlineHits,fixed.score.baseline.deadlineHits);
        EXPECT_EQ(original.warmWindowsBefore,fixed.warmWindowsAfter);EXPECT_EQ(fixed.unsafeModelDecisions,0u);
        EXPECT_EQ(fixed.score.candidate.safetyViolations,0u);EXPECT_FALSE(fixed.score.accepted);
        record(name,fixed);
    };
    paired("cold_warm_coast_bounded_start",500,{true,true,false});
    paired("cold_warm_coast_curve_bounded_start",500,{true,true,true});
    paired("mild_warm_coast_bounded_start",1500,{true,true,false});
    paired("mild_warm_coast_curve_bounded_start",1500,{true,true,true});
    paired("blocked_source_bounded_start",500,{true,true,true},true);
    paired("underpowered_bounded_start",500,{true,true,true},false,.5);
    paired("coast_only_bounded_start",500,{false,true,false},false,1.0,true);
    Holdout floor;floor.storeResponse=.02;paired("slow_floor_bounded_start",500,{true,true,true},false,1.0,false,floor);
    Holdout gain;gain.daytimeGain=.015;paired("external_gain_bounded_start",500,{true,true,false},false,1.0,false,gain);
    Holdout small;small.loss=.00025;paired("small_load_bounded_start",1700,{true,true,true},false,.5,false,small);
    Holdout loss;loss.sensorLossBegin=2*1440;loss.sensorLossEnd=5*1440;paired("sensor_loss_bounded_start",500,{true,true,true},false,1.0,false,loss);
    Holdout bad;bad.calibrationWeather=500;paired("incomparable_weather_bounded_start",-2000,{true,true,true},false,1.0,false,bad);
    Holdout events;events.windowDhwEvents=true;paired("window_dhw_fault_bounded_start",500,{true,true,true},false,1.0,false,events);
    Holdout gap;gap.telemetryGapBegin=5*1440+300;gap.telemetryGapEnd=gap.telemetryGapBegin+180;
    paired("absent_telemetry_bounded_start",500,{true,true,true},false,1.0,false,gap);
}

}
