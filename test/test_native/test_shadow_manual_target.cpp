#include "ShadowControllerFixture.h"
namespace {
TEST(ShadowManualTarget, OrdinaryOverrideReportsExpiryWithoutComfortOrReplayRenewal) {
    Fixture f;f.ready();auto sample=f.observation();f.send("ha/observations",sample.get());
    auto before=f.state();EXPECT_EQ(uintField(Fixture::row(before),"override_remaining_ms"),0u);
    auto request=f.command();f.send("ha/user_command",request.get());auto s=f.state();
    EXPECT_EQ(uintField(Fixture::row(s),"override_remaining_ms"),60000u);
    EXPECT_EQ(uintField(Fixture::row(s),"target_centi_c"),2300u);
    EXPECT_EQ(field(Fixture::row(s),"comfort_mode"),nullptr);
    const auto writes=f.store.writes;
    for(unsigned i=1;i<=6;++i) {
        f.now+=10000;f.tick();f.syncSession();f.heartbeat(i+1);
        // Original retries are unable to create a later expiry deadline.
        f.send("ha/user_command",request.get());s=f.state();
        EXPECT_EQ(uintField(Fixture::row(s),"override_remaining_ms"),60000-i*10000);
    }
    EXPECT_EQ(uintField(Fixture::row(s),"target_centi_c"),2100u);
    EXPECT_EQ(stringField(Fixture::row(s),"target_source"),"base");
    EXPECT_FALSE(cJSON_IsTrue(field(s.get(),"boiler_output_enabled")));
    EXPECT_FALSE(cJSON_IsTrue(field(s.get(),"actuator_output_enabled")));
    EXPECT_EQ(f.store.writes,writes);
}
}
