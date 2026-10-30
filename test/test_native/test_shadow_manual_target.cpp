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
    // A countdown alone is no change: the remaining time comes with the next
    // published state (at least every stateRefreshMs), the expiry at once.
    uint64_t previous=60000;
    for(unsigned i=1;i<=6;++i) {
        f.now+=10000;f.tick();f.syncSession();f.heartbeat(i+1);
        // Original retries are unable to create a later expiry deadline.
        f.send("ha/user_command",request.get());s=f.state();
        const auto remaining=uintField(Fixture::row(s),"override_remaining_ms");
        EXPECT_LE(remaining,previous);EXPECT_GE(remaining+ShadowController::stateRefreshMs,60000-uint64_t(i)*10000);
        previous=remaining;
    }
    EXPECT_EQ(previous,0u);
    EXPECT_EQ(uintField(Fixture::row(s),"target_centi_c"),2100u);
    EXPECT_EQ(stringField(Fixture::row(s),"target_source"),"base");
    EXPECT_FALSE(cJSON_IsTrue(field(s.get(),"boiler_output_enabled")));
    EXPECT_FALSE(cJSON_IsTrue(field(s.get(),"actuator_output_enabled")));
    EXPECT_EQ(f.store.writes,writes);
}
}
