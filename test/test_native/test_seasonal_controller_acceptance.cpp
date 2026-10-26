// New acceptance only: existing REAL controller/protocol/fixture, no second model.
#include "SeasonalControllerFixture.h"
namespace {
using namespace heating::control;
TEST(SeasonalControllerAcceptance, SummerAndAllOffStopCannotBeUndoneByNewManualBoost) {
    Fixture f;auto pin=sourceFor();auto safety=safe();
    pin.configDigest=controlTestHash(comfortConfig());bind(f,pin,safety);comfortReady(f);
    auto first=contextObservation(f,1);f.send("ha/observations",first.get());
    auto next=contextObservation(f,2);f.send("ha/observations",next.get());
    auto boost=comfortCommand(f,"boost",1,2300,60000);f.send("ha/user_command",boost.get());
    auto active=f.state();ASSERT_TRUE(cJSON_IsTrue(field(Fixture::row(active),"demand")));outputsFalse(active);
    ++f.now;safety.summer=true; // New dated producer fact.
    auto fresh=contextObservation(f,3);f.send("ha/observations",fresh.get());
    auto summer=f.state();outputsFalse(summer);
    EXPECT_EQ(uintField(Fixture::row(summer),"target_centi_c"),2300u);
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(summer),"demand")));
    EXPECT_NE(losses(summer)&seasonalRestriction(SeasonalRestriction::stop),0u);
    // NEW authenticated boost (not just a duplicate) cannot revoke source summer.
    auto newBoost=comfortCommand(f,"boost",2,2400,60000);f.send("ha/user_command",newBoost.get());
    auto still=f.state();outputsFalse(still);
    EXPECT_EQ(uintField(Fixture::row(still),"target_centi_c"),2400u);
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(still),"demand")));
    EXPECT_STREQ(stringField(Fixture::row(still),"reason").c_str(),"seasonal_summer");
    ++f.now;safety.summer=false;safety.allOff=true;
    auto allOffBoost=comfortCommand(f,"boost",3,2500,60000);f.send("ha/user_command",allOffBoost.get());
    auto stopped=f.state();outputsFalse(stopped);
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(stopped),"demand")));
    EXPECT_NE(losses(stopped)&seasonalRestriction(SeasonalRestriction::stop),0u);
}
TEST(SeasonalControllerAcceptance, ActualTwoZonesAOnlyTogetherBOnlyThenAllOff) {
    Fixture f;auto pin=sourceFor();auto safety=safe();pin.count=2;
    auto& b=pin.zones[1];b=pin.zones[0];b.zoneId="11223344";b.sensorId="room2";b.actuatorId="trv2";
    auto root=parseControlJson(config());const auto aZone=printJson(field(root.get(),"zones")->child);
    auto bZone=parseControlJson(aZone);
    cJSON_SetValuestring(const_cast<cJSON*>(field(bZone.get(),"zone_id")),"11223344");
    cJSON_SetValuestring(const_cast<cJSON*>(field(bZone.get(),"sensor_id")),"room2");
    cJSON_SetValuestring(const_cast<cJSON*>(field(bZone.get(),"actuator_id")),"trv2");
    const auto bytes=config(1,aZone+","+printJson(bZone.get()));
    pin.configDigest=controlTestHash(bytes);bind(f,pin,safety);
    f.start();f.connect();f.heartbeat();auto cfg=f.configuration(bytes);f.send("ha/config",cfg.get());
    ASSERT_EQ(f.store.writes,1u);f.connect();f.heartbeat();
    auto frame=report(f);EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(frame),"demand")));
    const auto check=[&](bool a,bool b) {
        const auto s=f.state();outputsFalse(s);auto list=field(s.get(),"zones");
        ASSERT_EQ(cJSON_GetArraySize(list),2);
        EXPECT_EQ(bool(cJSON_IsTrue(field(list->child,"demand"))),a);
        EXPECT_EQ(bool(cJSON_IsTrue(field(list->child->next,"demand"))),b);
        EXPECT_EQ(bool(cJSON_IsTrue(field(field(s.get(),"supervisor"),"requested_heat"))),a||b);
    };
    report(f);check(true,false); // B has no qualified report; no phantom B request.
    auto obs=f.envelope("room2");
    cJSON_AddStringToObject(obs.get(),"zone_id","11223344");
    cJSON_AddBoolToObject(obs.get(),"source_available",true);
    cJSON_AddNumberToObject(obs.get(),"temperature_c",19);
    cJSON_AddNumberToObject(obs.get(),"source_sample_age_ms",0);
    cJSON_AddStringToObject(obs.get(),"evidence","physical_report");
    f.send("ha/observations",obs.get());check(true,true);
    auto off=f.command("off");f.send("ha/user_command",off.get());check(false,true);
    auto bOff=f.command("off");
    cJSON_SetValuestring(const_cast<cJSON*>(field(bOff.get(),"binding_id")),"11223344");
    f.send("ha/user_command",bOff.get());check(false,false);
}
TEST(SeasonalControllerAcceptance, TinyZoneDutyNeverFabricatesMinimumPulseAcrossThreeCompleteCycles) {
    Fixture f;auto pin=sourceFor();auto safety=safe();
    auto& control=pin.zones[0].control;
    control.mode=ZoneControl::slowBinaryPi;control.kpPermillePerC=1;
    control.kiPermillePerCMinute=0;control.cycleMs=600000;
    control.minimumOnMs=control.minimumOffMs=120000;
    ASSERT_TRUE(control.valid());bind(f,pin,safety);f.ready();
    // Existing first-frame owner-change stop is preserved, not shortcut by a flag.
    auto initial=report(f);EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(initial),"demand")));
    unsigned heartbeat=1,observations=0;
    for(unsigned elapsed=0;elapsed<=1800000;elapsed+=2000) {
        if(elapsed) {f.now+=2000;f.tick();f.syncSession();f.heartbeat(++heartbeat);}
        auto s=report(f);++observations;
        ASSERT_FALSE(f.core->faulted());
        ASSERT_EQ(losses(s),0u); // Proves source/safety/minimum wait isn't the inhibition.
        EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(s),"demand")));
        EXPECT_STREQ(stringField(Fixture::row(s),"reason").c_str(),"shadow_low_load_or_satisfied");
        outputsFalse(s);
    }
    EXPECT_EQ(observations,901u); // 30 SYNTHETIC minutes, not real-house duration.
    EXPECT_EQ(f.store.writes,1u); // No per-sample configuration/persistence write.
}
}
