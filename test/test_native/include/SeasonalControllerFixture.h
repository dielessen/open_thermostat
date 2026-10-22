#pragma once
#include "ShadowControllerFixture.h"
#include <stdexcept>

namespace {
SeasonalControllerSource sourceFor() {
    SeasonalControllerSource p;
    p.controllerId="e32_lab";p.configDigest=controlTestHash(config());p.count=1;p.maximumSafetyAgeMs=2000;
    auto& z=p.zones[0];z.zoneId="1234abcd";z.sensorId="room1";z.actuatorId="trv1";
    z.seasonal.enabled=z.seasonal.installationQualified=z.seasonal.frostAdviceReviewed=true;
    z.seasonal.maximumSensorAgeMs=120000;z.seasonal.maximumStepGapMs=300000;
    return p;
}
void bind(Fixture& f,SeasonalControllerSource& p,SeasonalSafetySnapshot& safety) {
    f.seasonalSource=&p;
    f.seasonalSafety=[&]{auto copy=safety;if(copy.sampledAt==UINT64_MAX)copy.sampledAt=f.now;return copy;};
}
SeasonalSafetySnapshot safe() {
    SeasonalSafetySnapshot v;v.sampledAt=UINT64_MAX;v.limitsKnownSafe=v.dhwStateKnown=true;return v;
}
ControlJson report(Fixture& f,unsigned age=0,const char* evidence="physical_report") {
    auto o=f.observation(++f.seasonalObservationSequence,19,evidence,age);
    f.send("ha/observations",o.get());return f.state();
}
void readyPinned(Fixture& f) {
    f.ready();
    auto first=report(f);
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(first),"demand")));
    EXPECT_STREQ(stringField(Fixture::row(first),"reason").c_str(),"seasonal_owner_changed");
    // Preserve the original kernel's one-frame owner-change stop. A subsequent
    // genuinely new admitted source sequence is a separate policy evaluation.
    auto next=report(f);
    EXPECT_TRUE(cJSON_IsTrue(field(Fixture::row(next),"demand")));
}
void outputsFalse(const ControlJson& state) {
    EXPECT_TRUE(cJSON_IsFalse(field(state.get(),"boiler_output_enabled")));
    EXPECT_TRUE(cJSON_IsFalse(field(state.get(),"actuator_output_enabled")));
    EXPECT_TRUE(cJSON_IsFalse(field(field(state.get(),"supervisor"),"physical_outputs_enabled")));
    EXPECT_STREQ(stringField(field(state.get(),"supervisor"),"reason").c_str(),"hydraulic_profile_unqualified");
}
uint64_t losses(const ControlJson& s) {return uintField(Fixture::row(s),"seasonal_restrictions");}
}
