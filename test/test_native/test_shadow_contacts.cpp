#include "ShadowControllerFixture.h"
namespace {
std::string contactConfig(const std::string& policy=R"({"maximum_age_ms":10000})") {
    return config(1,R"({"actuator_id":"trv1","base_centi_c":2100,"contacts":)"+policy+
        R"(,"max_age_ms":120000,"report_evidence":"physical_report","schedule":null,"sensor_id":"room1","zone_id":"1234abcd"})");
}
void readyContacts(Fixture& f) {
    f.start();f.connect();f.heartbeat();auto cfg=f.configuration(contactConfig());f.send("ha/config",cfg.get());
    ASSERT_EQ(f.store.writes,1u);f.connect();f.heartbeat();
}
ControlJson contactObservation(Fixture& f,unsigned sequence,int open,unsigned age=0) {
    auto p=f.observation(sequence);
    cJSON_AddItemToObject(p.get(),"window_open",open<0?cJSON_CreateNull():cJSON_CreateBool(open));
    cJSON_AddNumberToObject(p.get(),"window_age_ms",age);
    cJSON_AddNullToObject(p.get(),"presence_away");cJSON_AddNumberToObject(p.get(),"presence_age_ms",86400000);
    return p;
}
TEST(ShadowContacts, InhibitOnlyDoesNotSelectComfortOrChangeOrdinaryTemperatureAndOffControls) {
    Fixture f;readyContacts(f);
    auto closed=contactObservation(f,1,0);f.send("ha/observations",closed.get());auto s=f.state();
    EXPECT_EQ(uintField(Fixture::row(s),"target_centi_c"),2100u);
    EXPECT_EQ(field(Fixture::row(s),"comfort_mode"),nullptr);
    auto open=contactObservation(f,2,1);f.send("ha/observations",open.get());s=f.state();
    EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(s),"target_centi_c")));
    EXPECT_STREQ(stringField(Fixture::row(s),"reason").c_str(),"window_open");
    auto temporary=f.command();f.send("ha/user_command",temporary.get());s=f.state();
    EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(s),"target_centi_c")));
    auto off=f.command("off",2);f.send("ha/user_command",off.get());s=f.state();
    EXPECT_EQ(stringField(Fixture::row(s),"target_source"),"off");
    EXPECT_FALSE(cJSON_IsTrue(field(s.get(),"boiler_output_enabled")));
    EXPECT_FALSE(cJSON_IsTrue(field(s.get(),"actuator_output_enabled")));
}
TEST(ShadowContacts, OriginalContextExpiresEvenWhileTemperatureAndLeaseRemainUsable) {
    Fixture f;readyContacts(f);auto p=contactObservation(f,1,0);f.send("ha/observations",p.get());
    f.now+=9999;f.tick();auto s=f.state();EXPECT_TRUE(cJSON_IsNumber(field(Fixture::row(s),"target_centi_c")));
    ++f.now;f.tick();f.syncSession();
    // Ask for a current state; the normal periodic publisher is rate-limited.
    auto snapshot=f.envelope("snapshot");f.send("ha/snapshot_request",snapshot.get());s=f.state();
    EXPECT_TRUE(cJSON_IsNumber(field(Fixture::row(s),"temperature_centi_c")));
    EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(s),"target_centi_c")));
    EXPECT_EQ(stringField(Fixture::row(s),"reason"),"window_state_unknown");
    EXPECT_EQ(f.store.writes,1u);
}
TEST(ShadowContacts, OldOrChangedDuplicateCannotClearAnOpenContact) {
    Fixture f;readyContacts(f);auto closed=contactObservation(f,1,0);f.send("ha/observations",closed.get());
    auto open=contactObservation(f,2,1);f.send("ha/observations",open.get());
    f.send("ha/observations",closed.get());auto s=f.state();
    EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(s),"target_centi_c")));
    cJSON_ReplaceItemInObjectCaseSensitive(open.get(),"window_open",cJSON_CreateFalse());f.send("ha/observations",open.get());s=f.state();
    EXPECT_EQ(stringField(Fixture::row(s),"reason"),"window_open");
    auto next=contactObservation(f,3,0);f.send("ha/observations",next.get());s=f.state();
    EXPECT_TRUE(cJSON_IsNumber(field(Fixture::row(s),"target_centi_c")));
}
TEST(ShadowContacts, InvalidContactPoliciesCannotReachDurableStorage) {
    for(const auto* policy:{R"({"maximum_age_ms":true})",R"({"maximum_age_ms":0})",
            R"({"maximum_age_ms":86400001})",R"({"maximum_age_ms":1.5})",
            R"({"maximum_age_ms":10000,"trust":true})"}) {
        Fixture f;f.start();f.connect();f.heartbeat();auto p=f.configuration(contactConfig(policy));
        f.send("ha/config",p.get());EXPECT_EQ(f.store.writes,0u);EXPECT_FALSE(f.core->faulted());
    }
}
TEST(ShadowContacts, OmittedContextAndFutureAgeCannotBecomeAValidTemperatureRefresh) {
    Fixture f;readyContacts(f);auto p=contactObservation(f,1,1);f.send("ha/observations",p.get());
    auto missing=f.observation(2);f.send("ha/observations",missing.get());auto s=f.state();
    EXPECT_EQ(stringField(Fixture::row(s),"reason"),"window_open");
    auto invalid=contactObservation(f,2,0);cJSON_ReplaceItemInObjectCaseSensitive(invalid.get(),"window_age_ms",cJSON_CreateNumber(-1));
    f.send("ha/observations",invalid.get());s=f.state();EXPECT_EQ(stringField(Fixture::row(s),"reason"),"window_open");
    auto unknown=contactObservation(f,2,-1);f.send("ha/observations",unknown.get());s=f.state();
    EXPECT_EQ(stringField(Fixture::row(s),"reason"),"window_state_unknown");
}
}
