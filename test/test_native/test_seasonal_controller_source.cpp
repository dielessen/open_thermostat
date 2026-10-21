// Reuse actual native controller/admission/wire fixtures AND their original tests.
// Build this TU instead of a second test_shadow_controller.cpp instance.
#include "test_shadow_controller.cpp"
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
TEST(SeasonalControllerSource, ActualAdmittedWireUsesPinnedExistingPolicyAndNoPhysicalQualification) {
    Fixture f;auto pin=sourceFor();auto safety=safe();bind(f,pin,safety);readyPinned(f);
    auto s=report(f);outputsFalse(s);
    EXPECT_TRUE(cJSON_IsTrue(field(Fixture::row(s),"demand")));
    EXPECT_TRUE(cJSON_IsTrue(field(Fixture::row(s),"seasonal_policy")));
    EXPECT_TRUE(cJSON_IsFalse(field(Fixture::row(s),"frost_protection_available")));
    EXPECT_EQ(losses(s),0u);
    EXPECT_STREQ(stringField(Fixture::row(s),"reason").c_str(),"shadow_seasonal_demand");
    // The SOURCE bundle is copied, not remotely mutable after construction.
    pin.zones[0].sensorId="another";auto again=report(f);
    EXPECT_TRUE(cJSON_IsTrue(field(Fixture::row(again),"demand")));
}
TEST(SeasonalControllerSource, DefaultApi1KeepsOriginalPolicyAndNoNewProfileAdvertisement) {
    Fixture f;f.ready();auto s=report(f);outputsFalse(s);
    EXPECT_TRUE(cJSON_IsTrue(field(Fixture::row(s),"demand")));
    EXPECT_EQ(field(Fixture::row(s),"seasonal_policy"),nullptr);
    EXPECT_STREQ(stringField(Fixture::row(s),"reason").c_str(),"shadow_demand");
    const auto h=f.get("fw/hello");
    EXPECT_EQ(cJSON_GetArraySize(field(h.get(),"control_capabilities")),1);
}
TEST(SeasonalControllerSource, InvalidSourcePinsOrMissingProviderFailBeforeWritingWithoutFallback) {
    for(unsigned bad=0;bad<7;++bad) {
        Fixture f;auto pin=sourceFor();auto safety=safe();bind(f,pin,safety);
        if(bad==0)pin.count=0;
        if(bad==1)pin.count=9;
        if(bad==2)pin.controllerId="other";
        if(bad==3)pin.configDigest="not-a-digest";
        if(bad==4)pin.zones[0].seasonal.installationQualified=false;
        if(bad==5)pin.maximumSafetyAgeMs=0;
        if(bad==6)f.seasonalSafety={};
        f.start();EXPECT_TRUE(f.core->faulted())<<bad;EXPECT_EQ(f.store.writes,0u);
    }
}
TEST(SeasonalControllerSource, WrongConfigDigestSchemaOrBindingCannotBeWrittenOrLoaded) {
    for(unsigned bad=0;bad<4;++bad) {
        Fixture f;auto pin=sourceFor();auto safety=safe();bind(f,pin,safety);
        if(bad==0)pin.configDigest=std::string(64,'b');
        if(bad==1)pin.zones[0].sensorId="other";
        if(bad==2)pin.zones[0].actuatorId="other";
        if(bad==3)pin.zones[0].zoneId="11111111";
        f.ready();EXPECT_EQ(f.store.writes,0u)<<bad;EXPECT_EQ(f.core->revision(),0u);
        Fixture loaded;loaded.store.bytes=config();bind(loaded,pin,safety);loaded.start();
        EXPECT_TRUE(loaded.core->faulted())<<bad;EXPECT_EQ(loaded.store.writes,0u);
    }
    Fixture future;auto pin=sourceFor();auto safety=safe();bind(future,pin,safety);
    future.start();future.connect();future.heartbeat();
    auto cfg=parseControlJson(config());cJSON_SetNumberValue(const_cast<cJSON*>(field(cfg.get(),"schema")),2);
    auto message=future.configuration(printJson(cfg.get()));future.send("ha/config",message.get());
    EXPECT_EQ(future.store.writes,0u);
}
TEST(SeasonalControllerSource, SafetyUnknownFutureExactExpiryDhwAndSummerAllWithdrawExistingLogicalDemand) {
    for(unsigned bad=0;bad<7;++bad) {
        Fixture f;auto pin=sourceFor();auto safety=safe();bind(f,pin,safety);readyPinned(f);
        auto first=report(f);ASSERT_TRUE(cJSON_IsTrue(field(Fixture::row(first),"demand")));
        if(bad==0)safety.limitsKnownSafe=false;
        if(bad==1)safety.dhwStateKnown=false;
        if(bad==2)safety.dhwActive=true;
        if(bad==3)safety.summer=true;
        if(bad==4)safety.allOff=true;
        if(bad==5)safety.sampledAt=f.now+1;
        if(bad==6)safety.sampledAt=f.now-pin.maximumSafetyAgeMs;
        auto s=report(f);outputsFalse(s);
        EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(s),"demand")))<<bad;
        EXPECT_NE(losses(s),0u)<<bad;
    }
}
TEST(SeasonalControllerSource, ConcurrentOffUnknownLimitAndDhwLossAllRemainVisible) {
    Fixture f;auto pin=sourceFor();auto safety=safe();bind(f,pin,safety);readyPinned(f);report(f);
    safety.limitsKnownSafe=false;safety.dhwStateKnown=false;safety.dhwActive=true;
    auto off=f.command("off");f.send("ha/user_command",off.get());auto s=f.state();outputsFalse(s);
    const auto l=losses(s);
    EXPECT_NE(l&seasonalRestriction(SeasonalRestriction::stop),0u);
    EXPECT_NE(l&seasonalRestriction(SeasonalRestriction::limitsUnknown),0u);
    EXPECT_NE(l&seasonalRestriction(SeasonalRestriction::dhwUnknown),0u);
    EXPECT_NE(l&seasonalRestriction(SeasonalRestriction::dhwPriority),0u);
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(s),"demand")));
}
TEST(SeasonalControllerSource, ActualSampleAgeProvenanceAndSourceProfileTtlNeverRenewFromControllerGet) {
    Fixture f;auto pin=sourceFor();pin.zones[0].seasonal.maximumSensorAgeMs=1000;
    auto safety=safe();bind(f,pin,safety);readyPinned(f);auto first=report(f);
    ASSERT_TRUE(cJSON_IsTrue(field(Fixture::row(first),"demand")));
    f.now+=3000;f.tick();auto stale=f.state();outputsFalse(stale);
    // Underlying generic120s measurement is still valid, narrower SOURCE policy isn't.
    EXPECT_EQ(uintField(Fixture::row(stale),"sample_state"),1u);
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(stale),"demand")));
    EXPECT_NE(losses(stale)&seasonalRestriction(SeasonalRestriction::sourceUnavailable),0u);
    auto restored=report(f,0,"restored");
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(restored),"demand")));
}
TEST(SeasonalControllerSource, PreemptionCannotResumeOnAnotherGrantOrSameOwnerBeforeFreshSession) {
    Fixture f;auto pin=sourceFor();auto safety=safe();bind(f,pin,safety);readyPinned(f);report(f);
    safety.preempted=true;auto stopped=report(f);
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(stopped),"demand")));
    safety.preempted=false;auto cached=report(f);
    EXPECT_STREQ(stringField(Fixture::row(cached),"reason").c_str(),"seasonal_new_owner_required");
    f.now+=5000;f.tick();f.syncSession();f.heartbeat(2);auto grantOnly=report(f);
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(grantOnly),"demand")));
    f.core->disconnected();f.now+=1;f.core->connected(f.now);f.connect();f.heartbeat();f.seasonalObservationSequence=0;
    auto ownerChanged=report(f);
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(ownerChanged),"demand")));
    auto fresh=report(f);outputsFalse(fresh);
    EXPECT_TRUE(cJSON_IsTrue(field(Fixture::row(fresh),"demand")));
}
TEST(SeasonalControllerSource, ReconnectHasNoRestoredTemperatureOrDemandAndNeedsNewReport) {
    Fixture f;auto pin=sourceFor();auto safety=safe();bind(f,pin,safety);readyPinned(f);report(f);
    f.core->disconnected();f.now+=1;f.core->connected(f.now);f.connect();f.heartbeat();f.seasonalObservationSequence=0;
    f.now+=3000;f.tick();auto before=f.state();outputsFalse(before);
    EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(before),"temperature_centi_c")));
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(before),"demand")));
    auto fresh=report(f);outputsFalse(fresh);
    EXPECT_TRUE(cJSON_IsTrue(field(Fixture::row(fresh),"demand")));
}
TEST(SeasonalControllerSource, SafetyObserverExceptionAndOwnerLossNeverUsePreCallbackAlive) {
    for(bool unusual:{false,true}) {
        Fixture f;auto pin=sourceFor();auto safety=safe();bind(f,pin,safety);
        const auto original=f.seasonalSafety;
        bool armed=false;
        f.seasonalSafety=[&]()->SeasonalSafetySnapshot {
            if(armed) {if(unusual)throw 7;throw std::runtime_error("private-producer-error");}
            return original();
        };
        readyPinned(f);report(f);armed=true;auto s=report(f);outputsFalse(s);
        EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(s),"demand")));
    }
    Fixture f;auto pin=sourceFor();auto safety=safe();bind(f,pin,safety);
    const auto original=f.seasonalSafety;bool armed=false;
    f.seasonalSafety=[&]{if(armed)f.core->disconnected();return original();};
    readyPinned(f);report(f);armed=true;auto lost=report(f);outputsFalse(lost);
    EXPECT_TRUE(cJSON_IsFalse(field(lost.get(),"adapter_alive")));
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(lost),"demand")));
}
TEST(SeasonalControllerSource, ReadObserverReentryLatchesUnknownAndCannotRearmPolicy) {
    Fixture f;auto pin=sourceFor();auto safety=safe();bind(f,pin,safety);
    const auto original=f.seasonalSafety;bool armed=false,inside=false;
    f.seasonalSafety=[&] {
        if(armed&&!inside) {
            inside=true;auto snap=f.envelope("snapshot");f.send("ha/snapshot_request",snap.get());inside=false;
        }
        return original();
    };
    readyPinned(f);report(f);armed=true;auto entered=report(f);outputsFalse(entered);
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(entered),"demand")));
    armed=false;auto later=report(f);outputsFalse(later);
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(later),"demand")));
}
}

TEST(SeasonalControllerSource, ActualTwoZonesMissingStaleAndAllOffNeverManufactureAnotherZoneRequest) {
    Fixture f;auto pin=sourceFor();auto safety=safe();pin.count=2;
    auto& second=pin.zones[1];second=pin.zones[0];
    second.zoneId="11223344";second.sensorId="room2";second.actuatorId="trv2";
    pin.zones[0].seasonal.maximumSensorAgeMs=1000;
    const auto cfg=parseControlJson(config());
    const auto firstZone=printJson(field(cfg.get(),"zones")->child);
    auto secondZone=parseControlJson(firstZone);
    cJSON_SetValuestring(const_cast<cJSON*>(field(secondZone.get(),"zone_id")),"11223344");
    cJSON_SetValuestring(const_cast<cJSON*>(field(secondZone.get(),"sensor_id")),"room2");
    cJSON_SetValuestring(const_cast<cJSON*>(field(secondZone.get(),"actuator_id")),"trv2");
    const auto bytes=config(1,firstZone+","+printJson(secondZone.get()));
    pin.configDigest=controlTestHash(bytes);bind(f,pin,safety);
    f.start();f.connect();f.heartbeat();auto message=f.configuration(bytes);f.send("ha/config",message.get());
    ASSERT_EQ(f.store.writes,1u);f.connect();f.heartbeat();
    auto changed=report(f);EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(changed),"demand")));
    auto first=report(f);outputsFalse(first);
    auto rows=field(first.get(),"zones");
    EXPECT_TRUE(cJSON_IsTrue(field(rows->child,"demand")));
    EXPECT_FALSE(cJSON_IsTrue(field(rows->child->next,"demand")));
    auto observation=f.envelope("room2");
    cJSON_AddStringToObject(observation.get(),"zone_id","11223344");
    cJSON_AddBoolToObject(observation.get(),"source_available",true);
    cJSON_AddNumberToObject(observation.get(),"temperature_c",19);
    cJSON_AddNumberToObject(observation.get(),"source_sample_age_ms",0);
    cJSON_AddStringToObject(observation.get(),"evidence","physical_report");
    f.send("ha/observations",observation.get());
    f.now+=3000;f.tick();auto secondOnly=f.state();outputsFalse(secondOnly);
    rows=field(secondOnly.get(),"zones");
    EXPECT_FALSE(cJSON_IsTrue(field(rows->child,"demand")));
    EXPECT_TRUE(cJSON_IsTrue(field(rows->child->next,"demand")));
    EXPECT_TRUE(cJSON_IsTrue(field(field(secondOnly.get(),"supervisor"),"requested_heat")));
    auto off=f.command("off");
    cJSON_SetValuestring(const_cast<cJSON*>(field(off.get(),"binding_id")),"11223344");
    f.send("ha/user_command",off.get());auto allOff=f.state();outputsFalse(allOff);
    rows=field(allOff.get(),"zones");
    EXPECT_FALSE(cJSON_IsTrue(field(rows->child,"demand")));
    EXPECT_FALSE(cJSON_IsTrue(field(rows->child->next,"demand")));
    EXPECT_FALSE(cJSON_IsTrue(field(field(allOff.get(),"supervisor"),"requested_heat")));
}

TEST(SeasonalControllerSource, ExplicitSameFrostTargetPrecedesWindowAndSummerButNeverLimitsOrOff) {
    Fixture f;auto pin=sourceFor();auto safety=safe();safety.summer=true;
    pin.configDigest=controlTestHash(comfortConfig());bind(f,pin,safety);comfortReady(f);
    auto obs=contextObservation(f,1,true,false,false);
    cJSON_SetNumberValue(const_cast<cJSON*>(field(obs.get(),"temperature_c")),3);
    f.send("ha/observations",obs.get());
    auto frost=comfortCommand(f,"frost");f.send("ha/user_command",frost.get());
    auto s=f.state();outputsFalse(s);
    EXPECT_EQ(uintField(Fixture::row(s),"target_centi_c"),500u);
    EXPECT_STREQ(stringField(Fixture::row(s),"reason").c_str(),"shadow_frost_advice");
    EXPECT_TRUE(cJSON_IsTrue(field(Fixture::row(s),"demand")));
    EXPECT_TRUE(cJSON_IsFalse(field(Fixture::row(s),"learning_allowed")));
    safety.limitsKnownSafe=false;
    auto next=contextObservation(f,2,true,false,false);
    cJSON_SetNumberValue(const_cast<cJSON*>(field(next.get(),"temperature_c")),3);
    f.send("ha/observations",next.get());auto limited=f.state();outputsFalse(limited);
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(limited),"demand")));
    EXPECT_NE(losses(limited)&seasonalRestriction(SeasonalRestriction::limitsUnknown),0u);
    auto off=comfortCommand(f,"off",2);f.send("ha/user_command",off.get());auto stopped=f.state();outputsFalse(stopped);
    EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(stopped),"target_centi_c")));
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(stopped),"demand")));
    EXPECT_NE(losses(stopped)&seasonalRestriction(SeasonalRestriction::stop),0u);
    // Source and displayed frost target may not disagree, even inside both ranges.
    Fixture mismatch;auto bad=sourceFor();bad.configDigest=controlTestHash(comfortConfig());
    bad.zones[0].seasonal.frostTargetCentiC=600;bind(mismatch,bad,safety);
    mismatch.start();mismatch.connect();mismatch.heartbeat();
    auto cfg=mismatch.configuration(comfortConfig());mismatch.send("ha/config",cfg.get());
    EXPECT_EQ(mismatch.store.writes,0u);
}

namespace {
TEST(SeasonalControllerSource, ReviewedIdentityAdvertisesExactOwnerAndPinWithoutPhysicalCapability) {
    Fixture f;auto pin=sourceFor();pin.profileDigest=std::string(64,'a');auto safety=safe();bind(f,pin,safety);readyPinned(f);
    const auto hello=f.get("fw/hello");const auto identity=field(hello.get(),"source_policy");
    ASSERT_NE(identity,nullptr);EXPECT_EQ(cJSON_GetArraySize(identity),7);
    EXPECT_EQ(uintField(identity,"schema"),1u);
    EXPECT_EQ(stringField(identity,"kind"),"seasonal.shadow.v1");
    EXPECT_EQ(stringField(identity,"adapter_id"),"ha1");
    EXPECT_EQ(stringField(identity,"profile_digest"),std::string(64,'a'));
    EXPECT_EQ(stringField(identity,"config_pin"),controlTestHash(config()));
    EXPECT_TRUE(cJSON_IsFalse(field(identity,"physical_outputs_enabled")));
    EXPECT_TRUE(cJSON_IsFalse(field(identity,"frost_protection_available")));
    pin.profileDigest=std::string(64,'b'); // External mutation cannot revise active SOURCE identity.
    const auto state=report(f);outputsFalse(state);
    EXPECT_EQ(stringField(field(state.get(),"source_policy"),"profile_digest"),std::string(64,'a'));
}
TEST(SeasonalControllerSource, MalformedReviewedIdentityFailsClosedBeforeDurableWrite) {
    for(auto identity:{std::string("bad"),std::string(64,'A'),std::string(63,'a'),std::string(65,'a')}) {
        Fixture f;auto pin=sourceFor();pin.profileDigest=identity;auto safety=safe();bind(f,pin,safety);
        EXPECT_FALSE(pin.valid());f.start();EXPECT_TRUE(f.core->faulted());EXPECT_EQ(f.store.writes,0u);
    }
}
TEST(SeasonalControllerSource, OrdinaryApi1AndAnonymousSourceDoNotFabricateReviewedPolicyIdentity) {
    Fixture plain;plain.ready();EXPECT_EQ(field(plain.get("fw/hello").get(),"source_policy"),nullptr);
    Fixture legacy;auto pin=sourceFor();auto safety=safe();bind(legacy,pin,safety);readyPinned(legacy);
    EXPECT_EQ(field(legacy.get("fw/hello").get(),"source_policy"),nullptr);
    EXPECT_EQ(field(report(legacy).get(),"source_policy"),nullptr);
}
}

namespace {
TEST(SeasonalControllerSource, MissingOrWrongExplicitPeerPolicyEchoNeverCreatesSessionOrStoreWrite) {
    for(unsigned bad=0;bad<3;++bad) {
        Fixture f;auto pin=sourceFor();pin.profileDigest=std::string(64,'a');auto safety=safe();bind(f,pin,safety);f.start();
        auto h=f.get("fw/hello");auto open=objectJson();
        cJSON_AddNumberToObject(open.get(),"api",1);cJSON_AddStringToObject(open.get(),"controller_id","e32_lab");
        cJSON_AddStringToObject(open.get(),"boot_id","boot1");cJSON_AddNumberToObject(open.get(),"epoch",uintField(h.get(),"epoch"));
        cJSON_AddStringToObject(open.get(),"adapter_id","ha1");cJSON_AddStringToObject(open.get(),"client_nonce","client1");
        cJSON_AddStringToObject(open.get(),"challenge_id",stringField(h.get(),"challenge_id").c_str());
        cJSON_AddNumberToObject(open.get(),"known_revision",0);cJSON_AddStringToObject(open.get(),"known_digest","");
        if(bad) {
            cJSON_AddStringToObject(open.get(),"source_profile_digest",bad==1?std::string(64,'b').c_str():pin.profileDigest.c_str());
            cJSON_AddStringToObject(open.get(),"source_config_pin",bad==2?std::string(64,'b').c_str():pin.configDigest.c_str());
        }
        f.send("ha/open_session",open.get());EXPECT_EQ(f.output.count("fw/session"),0u)<<bad;EXPECT_EQ(f.store.writes,0u);
        cJSON_DeleteItemFromObjectCaseSensitive(open.get(),"source_profile_digest");cJSON_DeleteItemFromObjectCaseSensitive(open.get(),"source_config_pin");
        cJSON_AddStringToObject(open.get(),"source_profile_digest",pin.profileDigest.c_str());
        cJSON_AddStringToObject(open.get(),"source_config_pin",pin.configDigest.c_str());
        f.send("ha/open_session",open.get());EXPECT_EQ(f.output.count("fw/session"),1u);EXPECT_EQ(f.store.writes,0u);
    }
}
}
