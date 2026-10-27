#include "ShadowControllerFixture.h"
namespace {
TEST(ModernMetrics, OptionalProviderNoReadBeforeSessionAndOneBoundedSnapshotAtThirtySeconds) {
    Fixture f;unsigned reads=0;f.metricsProvider=[&](auto& stream){++reads;stream<<metricFixture();};
    f.start();EXPECT_EQ(reads,0u);
    auto hello=f.get("fw/hello");ASSERT_TRUE(cJSON_IsArray(field(hello.get(),"read_only_capabilities")));
    f.connect();f.heartbeat();f.configure();f.connect();f.heartbeat();EXPECT_EQ(reads,0u);
    ++f.now;f.tick();ASSERT_EQ(reads,1u);
    auto p=f.get("fw/telemetry/ems_metrics");
    EXPECT_EQ(uintField(p.get(),"sequence"),1u);EXPECT_EQ(uintField(p.get(),"config_revision"),1u);
    EXPECT_EQ(stringField(p.get(),"adapter_session_id"),f.session);EXPECT_EQ(stringField(p.get(),"grant_id"),f.grant);
    EXPECT_FALSE(cJSON_IsTrue(field(p.get(),"boiler_output_enabled")));
    EXPECT_FALSE(cJSON_IsTrue(field(p.get(),"actuator_output_enabled")));
    EXPECT_TRUE(validMetricsSnapshot(field(p.get(),"metrics")));
    EXPECT_LE(f.output.at("fw/telemetry/ems_metrics").size(),maximumMetricsEnvelopeBytes);
    for(unsigned i=1;i<=30;++i) {f.now+=1000;f.tick();f.syncSession();f.heartbeat(i+1);}
    EXPECT_EQ(reads,2u);p=f.get("fw/telemetry/ems_metrics");EXPECT_EQ(uintField(p.get(),"sequence"),2u);
    EXPECT_EQ(f.store.writes,1u);auto state=f.state();EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(state),"demand")));
}
TEST(ModernMetrics, EmptyOrUnadmittedProviderDoesNotAdvertiseOrPublishAndDisconnectCannotRead) {
    Fixture empty;empty.ready();++empty.now;empty.tick();
    EXPECT_EQ(empty.output.count("fw/telemetry/ems_metrics"),0u);
    auto h=empty.get("fw/hello");EXPECT_EQ(field(h.get(),"read_only_capabilities"),nullptr);
    Fixture f;unsigned reads=0;f.metricsProvider=[&](auto& stream){++reads;stream<<metricFixture();};
    f.ready();f.core->disconnected();f.now+=1000;f.tick();EXPECT_EQ(reads,0u);
    EXPECT_EQ(f.output.count("fw/telemetry/ems_metrics"),0u);
}
TEST(ModernMetrics, CorruptOrSecretBearingGetterFailsReadOnlyAndDoesNotFaultControl) {
    for(auto body:{std::string("{bad"),std::string(1025,'x'),
        std::string("{\"counterDefinition\":\"observation-total-v2\",\"password\":\"NEVER_LEAK\"}")}) {
        Fixture f;unsigned reads=0;f.metricsProvider=[&](auto& stream){++reads;stream<<body;};
        f.ready();++f.now;f.tick();EXPECT_EQ(reads,1u);EXPECT_FALSE(f.core->faulted());
        EXPECT_EQ(f.output.count("fw/telemetry/ems_metrics"),0u);
        ++f.now;f.tick();EXPECT_EQ(reads,1u);EXPECT_EQ(f.store.writes,1u);
    }
}
TEST(ModernMetrics, SharedMetricShapeRejectsBooleanCountersUnknownsAndLegacyNumericalFields) {
    auto root=parseControlJson(metricFixture());ASSERT_TRUE(validMetricsSnapshot(root.get()));
    cJSON_ReplaceItemInObjectCaseSensitive(root.get(),"totalEnergyUsedKwh",cJSON_CreateNumber(0));
    EXPECT_FALSE(validMetricsSnapshot(root.get()));
    root=parseControlJson(metricFixture());
    cJSON_ReplaceItemInObjectCaseSensitive(root.get(),"totalEnergyUsedKwhV2",cJSON_CreateBool(false));
    EXPECT_FALSE(validMetricsSnapshot(root.get()));
    root=parseControlJson(metricFixture());cJSON_AddStringToObject(root.get(),"extra","not_a_config_relay");
    EXPECT_FALSE(validMetricsSnapshot(root.get()));
}
TEST(ShadowRuntime, ActualWireConfigurationObservationAndTargetRoundTripNeverEnablesOutputs) {
    Fixture f; f.ready(); ASSERT_EQ(f.core->revision(),1u); EXPECT_EQ(f.store.writes,1u);
    auto o=f.observation(); f.send("ha/observations",o.get());
    auto state=f.state(); ASSERT_NE(Fixture::row(state),nullptr);
    EXPECT_TRUE(cJSON_IsTrue(field(Fixture::row(state),"demand")));
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"boiler_output_enabled")));
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"actuator_output_enabled")));
    auto command=f.command(); f.send("ha/user_command",command.get());
    auto s=f.state(); EXPECT_EQ(uintField(Fixture::row(s),"target_centi_c"),2300u);
    EXPECT_EQ(stringField(Fixture::row(s),"target_source"),"temporary");
}
TEST(ShadowRuntime, HeartbeatsAndCacheReportsCannotMakeStaleSourceFresh) {
    Fixture f; f.ready(); auto o=f.observation(1,19,"unverified"); f.send("ha/observations",o.get());
    auto s=f.state(); EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(s),"demand")));
    auto valid=f.observation(2,19,"physical_report",119000); f.now+=2000; f.send("ha/observations",valid.get());
    s=f.state(); EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(s),"demand"))); // conservative grant elapsed included
    auto fresh=f.observation(3); f.send("ha/observations",fresh.get());
    s=f.state(); EXPECT_TRUE(cJSON_IsTrue(field(Fixture::row(s),"demand")));
    for(unsigned i=0;i<25;++i) { f.now+=5000; f.tick(); f.syncSession(); f.heartbeat(2+i); }
    f.now+=3000; f.tick(); s=f.state();
    EXPECT_TRUE(cJSON_IsTrue(field(s.get(),"adapter_alive")));
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(s),"demand")));
    EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(s),"temperature_centi_c")));
}
TEST(ShadowRuntime, DuplicateChangedPayloadAndOldSequenceNeverReapplyOverride) {
    Fixture f; f.ready(); auto command=f.command(); f.send("ha/user_command",command.get());
    f.now+=1000; f.send("ha/user_command",command.get());
    auto ack=f.get("fw/user_command_result"); EXPECT_EQ(stringField(ack.get(),"status"),"duplicate");
    cJSON_ReplaceItemInObjectCaseSensitive(command.get(),"temperature_centi_c",cJSON_CreateNumber(3000)); f.send("ha/user_command",command.get());
    ack=f.get("fw/user_command_result"); EXPECT_EQ(stringField(ack.get(),"status"),"rejected");
    for(unsigned i=0;i<13;++i) { f.now+=5000; f.tick(); f.syncSession(); f.heartbeat(i+2); }
    f.now+=3000; f.tick(); auto s=f.state(); EXPECT_EQ(stringField(Fixture::row(s),"target_source"),"base");
    auto old=f.command("temporary",1,3000); f.send("ha/user_command",old.get());
    ack=f.get("fw/user_command_result"); EXPECT_EQ(stringField(ack.get(),"status"),"rejected");
}
TEST(ShadowRuntime, ExpiredGrantDiagnosticNeverAppliesOrRetriesTheCommand) {
    Fixture f;f.ready();auto command=f.command("temporary",1,2300);
    const auto saved=f.store.bytes;const auto writes=f.store.writes;
    f.now+=5000;f.tick(); // Rotate real firmware grant, keep old in-flight packet.
    f.send("ha/user_command",command.get());
    auto result=f.get("fw/user_command_result");
    EXPECT_EQ(stringField(result.get(),"status"),"rejected");
    EXPECT_EQ(stringField(result.get(),"rejection_reason"),"expired_grant");
    f.now+=3000;f.tick();auto state=f.state();
    EXPECT_EQ(uintField(Fixture::row(state),"target_centi_c"),2100u);
    const auto diagnostic=field(state.get(),"last_user_command_admission");
    ASSERT_TRUE(cJSON_IsObject(diagnostic));
    EXPECT_EQ(stringField(diagnostic,"outcome"),"expired_grant");
    EXPECT_EQ(stringField(diagnostic,"binding_id"),"1234abcd");
    EXPECT_EQ(uintField(diagnostic,"sequence"),1u);
    EXPECT_EQ(uintField(diagnostic,"received_config_revision"),1u);
    for(auto key:{"grant_id","grant_sequence","adapter_session_id","token","password","config_digest"})
        EXPECT_EQ(field(diagnostic,key),nullptr);
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"boiler_output_enabled")));
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"actuator_output_enabled")));
    EXPECT_EQ(f.store.bytes,saved);EXPECT_EQ(f.store.writes,writes);
    // An explicit new packet with the new grant may execute; the diagnostic
    // did not consume the rejected sequence or change the admission rule.
    f.syncSession();f.heartbeat(2);auto fresh=f.command("temporary",1,2300);
    f.send("ha/user_command",fresh.get());state=f.state();
    EXPECT_EQ(uintField(Fixture::row(state),"target_centi_c"),2300u);
    EXPECT_EQ(stringField(field(state.get(),"last_user_command_admission"),"outcome"),"accepted");
    EXPECT_EQ(f.store.bytes,saved);EXPECT_EQ(f.store.writes,writes);
}
TEST(ShadowRuntime, ChangedDuplicateDiagnosticDoesNotReapplyAndNewOwnerClearsIt) {
    Fixture f;f.ready();auto command=f.command();f.send("ha/user_command",command.get());
    cJSON_ReplaceItemInObjectCaseSensitive(command.get(),"temperature_centi_c",cJSON_CreateNumber(3000));
    f.send("ha/user_command",command.get());auto result=f.get("fw/user_command_result");
    EXPECT_EQ(stringField(result.get(),"rejection_reason"),"changed_duplicate");
    f.now+=3000;f.tick();auto state=f.state();
    EXPECT_EQ(uintField(Fixture::row(state),"target_centi_c"),2300u);
    EXPECT_EQ(stringField(field(state.get(),"last_user_command_admission"),"outcome"),"changed_duplicate");
    f.core->disconnected();f.core->connected(f.now);f.connect();f.heartbeat();++f.now;f.tick();state=f.state();
    EXPECT_EQ(field(state.get(),"last_user_command_admission"),nullptr);
    EXPECT_EQ(uintField(Fixture::row(state),"target_centi_c"),2100u);
}
TEST(ShadowRuntime, AtomicCommitFailuresIncludingCommittedButLostAckForceRecovery) {
    for(bool committed:{false,true}) {
        Fixture f; f.start(); f.connect(); f.heartbeat(); f.store.failSave=true; f.store.commitOnError=committed;
        f.configure(); EXPECT_TRUE(f.core->faulted()); EXPECT_EQ(f.core->revision(),0u);
        auto ack=f.get("fw/config_result"); EXPECT_EQ(stringField(ack.get(),"status"),"storage_fault");
        f.store.failSave=false; f.boot="boot2"; f.start();
        EXPECT_FALSE(f.core->faulted()); EXPECT_EQ(f.core->revision(),committed?1u:0u);
    }
}
TEST(ShadowRuntime, RebootReadbackMismatchAndDisconnectFenceAllOldPackets) {
    Fixture f; f.ready(); auto old=f.observation(); f.send("ha/observations",old.get());
    f.boot="boot2"; f.start(); EXPECT_EQ(f.core->revision(),1u); f.connect(true); f.heartbeat();
    f.send("ha/observations",old.get()); auto s=f.state(); EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(s),"demand")));
    auto obs=f.observation(2); f.send("ha/observations",obs.get());
    auto ack=f.get("fw/observation_result"); EXPECT_EQ(stringField(ack.get(),"status"),"mapping_conflict");
    auto request=f.envelope("snapshot"); f.send("ha/snapshot_request",request.get());
    auto snapshot=f.get("fw/config_snapshot"); EXPECT_EQ(uintField(snapshot.get(),"config_revision"),1u);
    f.core->disconnected(); f.core->connected(f.now); f.now+=3000; f.tick();
    s=f.state(); EXPECT_FALSE(cJSON_IsTrue(field(s.get(),"adapter_alive")));
    EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(s),"temperature_centi_c")));
}
TEST(ShadowRuntime, MissingHeartbeatSessionExpiresAndDelayedHeartbeatCannotReviveIt) {
    Fixture f; f.start(); f.connect(); const auto oldSession=f.session; auto heartbeat=f.envelope("adapter");
    f.now+=15000; f.send("ha/heartbeat",heartbeat.get()); f.tick(); f.connect(); EXPECT_NE(f.session,oldSession);
}
TEST(ShadowRuntime, InvalidConfigDoesNotConsumeSequenceOrTouchStoreAndWrongOwnerFailsClosed) {
    Fixture f; f.start(); f.connect(); f.heartbeat(); auto bad=f.configuration();
    cJSON_ReplaceItemInObjectCaseSensitive(bad.get(),"config_digest",cJSON_CreateString(mapping.c_str()));
    f.send("ha/config",bad.get()); EXPECT_EQ(f.store.writes,0u); f.configure(); EXPECT_EQ(f.store.writes,1u);
    auto cfg=config(2); auto pos=cfg.find("shadow"); cfg.replace(pos,6,"active");
    f.connect(); f.heartbeat(); auto unsupported=f.configuration(cfg); f.send("ha/config",unsupported.get()); EXPECT_EQ(f.store.writes,1u);
    auto duplicate=config(2); pos=duplicate.find("\"max_age_ms\":120000"); duplicate.replace(pos,19,"\"max_age_ms\":true");
    auto boolean=f.configuration(duplicate); f.send("ha/config",boolean.get()); EXPECT_EQ(f.store.writes,1u);
}
TEST(ShadowRuntime, StoreCorruptionIsDiagnosedAndReadOnlySnapshotsNeverWrite) {
    Fixture f; f.store.bytes="{broken"; f.start(); EXPECT_TRUE(f.core->faulted());
    Fixture ok; ok.ready(); auto request=ok.envelope("snapshot"); ok.send("ha/snapshot_request",request.get());
    auto snapshot=ok.get("fw/config_snapshot"); EXPECT_EQ(uintField(snapshot.get(),"config_revision"),1u);
    EXPECT_EQ(controlTestHash(printJson(field(snapshot.get(),"config"))),ok.core->digest()); EXPECT_EQ(ok.store.writes,1u);
}
TEST(ShadowRuntime, ReadbackErrorNeverPartiallyActivatesAndWrongOwnerCannotOpen) {
    Fixture f; f.start(); f.connect(); f.heartbeat(); f.store.corruptReadback=true; f.configure();
    EXPECT_TRUE(f.core->faulted()); EXPECT_EQ(f.core->revision(),0u);
    Fixture wrong; wrong.start(); auto hello=wrong.get("fw/hello");
    std::string raw=R"({"api":1,"controller_id":"e32_lab","boot_id":"boot1","epoch":1,"challenge_id":")"+
        stringField(hello.get(),"challenge_id")+R"(","adapter_id":"other_ha","client_nonce":"new","known_revision":0,"known_digest":""})";
    wrong.core->receive("ha/open_session",raw,wrong.now,1792368000,true);
    EXPECT_FALSE(wrong.output.count("fw/session"));
}
TEST(ShadowRuntime, EightZonesAreBoundedAndDuplicateSensorCannotReplaceAcceptedConfig) {
    std::string zones;
    for(unsigned i=0;i<8;++i) {
        auto z=R"({"actuator_id":"trv)"+std::to_string(i)+R"(","base_centi_c":2100,"max_age_ms":120000,"report_evidence":"physical_report","schedule":null,"sensor_id":"room)"+
            std::to_string(i)+R"(","zone_id":"1234abc)"+std::to_string(i)+R"("})";
        if(i) zones+=",";
        zones+=z;
    }
    Fixture f; f.start(); f.connect(); f.heartbeat(); auto eight=f.configuration(config(1,zones)); f.send("ha/config",eight.get());
    EXPECT_EQ(f.core->revision(),1u); f.connect(); f.heartbeat(); f.now+=3000; f.tick();
    auto state=f.state(); EXPECT_EQ(cJSON_GetArraySize(field(state.get(),"zones")),8);
    const auto position=zones.find("room1"); ASSERT_NE(position,std::string::npos); zones.replace(position,5,"room0");
    auto invalid=f.configuration(config(2,zones)); f.send("ha/config",invalid.get()); EXPECT_EQ(f.store.writes,1u);
}
TEST(ShadowRuntime, KnownHashAndSeededRawMalformedWireNeverEnableAnyOutput) {
    EXPECT_EQ(controlTestHash("abc"),"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    Fixture f; f.ready(); auto command=f.command(); const auto valid=printJson(command.get());
    std::mt19937 random(0x20261020);
    for(unsigned i=0;i<30000;++i) {
        std::string bytes;
        if(i%2) { bytes=valid; bytes[random()%bytes.size()]=static_cast<char>(random()%256); }
        else { bytes.resize(random()%1000); for(auto &c:bytes)c=static_cast<char>(random()%256); }
        f.core->receive("ha/user_command",bytes,f.now,1792368000,true);
    }
    f.now+=3000; f.tick(); auto state=f.state();
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"boiler_output_enabled")));
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"actuator_output_enabled")));
    EXPECT_EQ(f.store.writes,1u);
}
TEST(ShadowRuntime, PubSubClientReceiveBufferReuseCannotEraseSnapshotRetryTopic) {
    Fixture f; f.ready(); auto request=f.envelope("snapshot"); f.send("ha/snapshot_request",request.get());
    f.output.erase("fw/config_snapshot");
    std::string topic="ha/snapshot_request";
    f.afterPublish=[&]{std::fill(topic.begin(),topic.end(),'x');};
    f.core->receive(topic,printJson(request.get()),f.now,1792368000,true);
    EXPECT_TRUE(f.output.count("fw/config_snapshot"));
}

TEST(ShadowRuntime, RealDemandIsNotUnqualifiedHydraulicReadinessAndReconnectClearsBand) {
    Fixture f; f.ready(); auto cold=f.observation(1,19);
    f.send("ha/observations",cold.get()); auto first=f.state();
    auto supervisor=field(first.get(),"supervisor");
    ASSERT_NE(supervisor,nullptr);
    EXPECT_STREQ(stringField(supervisor,"reason").c_str(),"hydraulic_profile_unqualified");
    EXPECT_TRUE(cJSON_IsTrue(field(supervisor,"requested_heat")));
    EXPECT_FALSE(cJSON_IsTrue(field(supervisor,"physical_outputs_enabled")));
    f.core->disconnected(); f.core->connected(f.now); f.connect(); f.heartbeat();
    auto band=f.observation(1,21);
    f.send("ha/observations",band.get()); auto after=f.state();
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(after),"demand")));
    EXPECT_FALSE(cJSON_IsTrue(field(after.get(),"boiler_output_enabled")));
}

TEST(GrantNonce, ExplicitCapabilityAndAcceptedHeartbeatOnlyAnchorsNextScheduledRotation) {
    Fixture f;f.ready();
    auto h=f.get("fw/hello");auto caps=field(h.get(),"session_capabilities");
    ASSERT_TRUE(cJSON_IsArray(caps));EXPECT_STREQ(caps->child->valuestring,"session.grant_nonce.v1");
    auto hb=nonceHeartbeat(f,2,"requestA");auto before=f.output.at("fw/session");f.send("ha/heartbeat",hb.get());
    EXPECT_EQ(stringField(f.get("fw/heartbeat_result").get(),"status"),"accepted");
    EXPECT_EQ(f.output.at("fw/session"),before); // Not an immediate grant rotation.
    f.now+=5000;f.tick();f.syncSession();
    auto issued=f.get("fw/session");EXPECT_EQ(stringField(issued.get(),"grant_request_nonce"),"requestA");
    EXPECT_EQ(uintField(issued.get(),"grant_sequence"),2u);EXPECT_FALSE(f.core->faulted());
    auto state=f.state();EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"boiler_output_enabled")));
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"actuator_output_enabled")));
}
TEST(GrantNonce, DuplicateOrChangedOrWrongOwnerCannotReplaceAcceptedProof) {
    Fixture f;f.ready();auto hb=nonceHeartbeat(f,2,"requestA");f.send("ha/heartbeat",hb.get());f.send("ha/heartbeat",hb.get());
    EXPECT_EQ(stringField(f.get("fw/heartbeat_result").get(),"status"),"duplicate");
    auto changed=nonceHeartbeat(f,2,"requestChanged");f.send("ha/heartbeat",changed.get());
    EXPECT_EQ(stringField(f.get("fw/heartbeat_result").get(),"status"),"rejected");
    auto foreign=nonceHeartbeat(f,3,"requestForeign");cJSON_SetValuestring(cJSON_GetObjectItemCaseSensitive(foreign.get(),"adapter_id"),"other");
    f.send("ha/heartbeat",foreign.get());f.now+=5000;f.tick();f.syncSession();
    EXPECT_EQ(stringField(f.get("fw/session").get(),"grant_request_nonce"),"requestA");
    f.now+=5000;f.tick();f.syncSession();EXPECT_EQ(field(f.get("fw/session").get(),"grant_request_nonce"),nullptr);
}
TEST(GrantNonce, MalformedNonceNeverConsumesHeartbeatSequence) {
    for(const char *bad:{"","x/y","abcdefghijklmnopqrstuvwxyz0123456789"}) {
        Fixture f;f.ready();auto hb=nonceHeartbeat(f,2,bad);f.send("ha/heartbeat",hb.get());
        auto good=nonceHeartbeat(f,2,"valid");f.send("ha/heartbeat",good.get());
        EXPECT_EQ(stringField(f.get("fw/heartbeat_result").get(),"status"),"accepted");
        f.now+=5000;f.tick();f.syncSession();EXPECT_EQ(stringField(f.get("fw/session").get(),"grant_request_nonce"),"valid");
    }
    Fixture f;f.ready();auto hb=nonceHeartbeat(f,2,nullptr);cJSON_AddNullToObject(hb.get(),"grant_request_nonce");
    f.send("ha/heartbeat",hb.get());auto good=nonceHeartbeat(f,2,"valid");f.send("ha/heartbeat",good.get());
    EXPECT_EQ(stringField(f.get("fw/heartbeat_result").get(),"status"),"accepted");
}
TEST(GrantNonce, LatestNewHeartbeatWinsAndOldPeerBodyStillAccepted) {
    Fixture f;f.ready();auto one=nonceHeartbeat(f,2,"first"),two=nonceHeartbeat(f,3,"second");
    f.send("ha/heartbeat",one.get());f.send("ha/heartbeat",two.get());f.now+=5000;f.tick();f.syncSession();
    EXPECT_EQ(stringField(f.get("fw/session").get(),"grant_request_nonce"),"second");
    auto three=nonceHeartbeat(f,4,"third");f.send("ha/heartbeat",three.get());f.heartbeat(5);
    f.now+=5000;f.tick();f.syncSession();EXPECT_EQ(field(f.get("fw/session").get(),"grant_request_nonce"),nullptr);
    EXPECT_FALSE(f.core->faulted());
}
TEST(GrantNonce, ReconnectAndConfigurationInvalidationClearPendingAndIssuedProofs) {
    Fixture f;f.ready();auto hb=nonceHeartbeat(f,2,"notPortable");f.send("ha/heartbeat",hb.get());
    f.core->disconnected();f.core->connected(f.now);f.connect();f.heartbeat();
    EXPECT_EQ(field(f.get("fw/session").get(),"grant_request_nonce"),nullptr);
    f.now+=5000;f.tick();f.syncSession();EXPECT_EQ(field(f.get("fw/session").get(),"grant_request_nonce"),nullptr);
    auto second=nonceHeartbeat(f,2,"oldConfig");f.send("ha/heartbeat",second.get());
    auto cfg=f.configuration(config(2));f.send("ha/config",cfg.get());f.connect();f.heartbeat();
    EXPECT_EQ(field(f.get("fw/session").get(),"grant_request_nonce"),nullptr);
}
TEST(GrantNonce, NonceCannotBeAttachedToAnotherStreamOrRaiseAnyPhysicalFlag) {
    Fixture f;f.ready();auto observation=f.observation(1);cJSON_AddStringToObject(observation.get(),"grant_request_nonce","notHeartbeat");
    f.send("ha/observations",observation.get());auto good=f.observation(1);f.send("ha/observations",good.get());
    EXPECT_EQ(stringField(f.get("fw/observation_result").get(),"status"),"accepted");
    f.now+=5000;f.tick();f.syncSession();EXPECT_EQ(field(f.get("fw/session").get(),"grant_request_nonce"),nullptr);
    auto state=f.state();EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"boiler_output_enabled")));
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"actuator_output_enabled")));
}

}

namespace {
TEST(ComfortRuntime, DurableConfigAndActualPriorityAndVisibleMonotoneExpiry) {
    Fixture f;comfortReady(f);
    auto obs=contextObservation(f,1,false,true);f.send("ha/observations",obs.get());
    auto state=f.state();EXPECT_EQ(uintField(Fixture::row(state),"target_centi_c"),1600u);
    auto away=comfortCommand(f,"away");f.send("ha/user_command",away.get());
    auto boost=comfortCommand(f,"boost",2,2300,1000);f.send("ha/user_command",boost.get());
    state=f.state();EXPECT_EQ(uintField(Fixture::row(state),"target_centi_c"),2300u);
    EXPECT_EQ(uintField(Fixture::row(state),"override_remaining_ms"),1000u);
    auto unknown=contextObservation(f,2,false,false,false);f.send("ha/observations",unknown.get());
    state=f.state();EXPECT_EQ(uintField(Fixture::row(state),"target_centi_c"),2300u);
    auto open=contextObservation(f,3,true);f.send("ha/observations",open.get());
    state=f.state();EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(state),"target_centi_c")));
    f.now+=1000;
    auto close=contextObservation(f,4);f.send("ha/observations",close.get());
    state=f.state();EXPECT_EQ(uintField(Fixture::row(state),"target_centi_c"),1600u);
    EXPECT_EQ(uintField(Fixture::row(state),"override_remaining_ms"),0u);
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"actuator_output_enabled")));
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"boiler_output_enabled")));
    EXPECT_EQ(f.store.writes,1u);
}
TEST(ComfortRuntime, FrostBeatsWindowButLimitsAndBadCommandsNeverBypassAdmission) {
    Fixture f;comfortReady(f);auto o=contextObservation(f,1,true);f.send("ha/observations",o.get());
    auto cmd=comfortCommand(f,"frost");f.send("ha/user_command",cmd.get());
    auto state=f.state();EXPECT_EQ(uintField(Fixture::row(state),"target_centi_c"),500u);
    auto bad=comfortCommand(f,"boost",2,2600,1000);f.send("ha/user_command",bad.get());
    auto good=comfortCommand(f,"boost",2,2300,1000);f.send("ha/user_command",good.get());
    EXPECT_EQ(stringField(f.get("fw/user_command_result").get(),"status"),"accepted");
    state=f.state();EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(state),"target_centi_c")));
    auto off=comfortCommand(f,"off",3);f.send("ha/user_command",off.get());
    state=f.state();EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(state),"demand")));
}
TEST(ComfortRuntime, ReconnectAndRebootKeepConfigButNeverOldManualChoiceOrContext) {
    Fixture f;comfortReady(f);auto o=contextObservation(f);f.send("ha/observations",o.get());
    auto cmd=comfortCommand(f,"boost",1,2300,10000);f.send("ha/user_command",cmd.get());
    f.core->disconnected();f.core->connected(f.now);f.connect();f.heartbeat();
    auto snap=f.envelope("snapshot");f.send("ha/snapshot_request",snap.get());
    auto state=f.state();EXPECT_EQ(uintField(Fixture::row(state),"override_remaining_ms"),0u);
    EXPECT_EQ(stringField(Fixture::row(state),"comfort_mode"),"auto");
    EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(state),"target_centi_c")));
    f.boot="boot2";f.start();f.connect();f.heartbeat();snap=f.envelope("snapshot");f.send("ha/snapshot_request",snap.get());
    state=f.state();EXPECT_EQ(uintField(Fixture::row(state),"override_remaining_ms"),0u);
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(state),"demand")));EXPECT_EQ(f.store.writes,1u);
}
TEST(ComfortRuntime, UnavailableOrStalePresenceNeverMeansAwayAndNoContextEvidencePromotesTemperature) {
    Fixture f;comfortReady(f);auto o=contextObservation(f,1,false,false,false);f.send("ha/observations",o.get());
    auto state=f.state();EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(state),"target_centi_c")));
    o=contextObservation(f,2);cJSON_ReplaceItemInObjectCaseSensitive(o.get(),"evidence",cJSON_CreateString("unverified"));
    f.send("ha/observations",o.get());state=f.state();EXPECT_EQ(uintField(Fixture::row(state),"target_centi_c"),2100u);
    EXPECT_FALSE(cJSON_IsTrue(field(Fixture::row(state),"demand")));
    o=contextObservation(f,3);cJSON_ReplaceItemInObjectCaseSensitive(o.get(),"presence_age_ms",cJSON_CreateNumber(120000));
    f.send("ha/observations",o.get());state=f.state();EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(state),"target_centi_c")));
}
}

namespace {
TEST(ComfortRuntime, ExpiredVacationExactRetryAcknowledgedButCannotRestartOrConsumeNewInvalidSequence) {
    Fixture f;comfortReady(f,false);
    auto cmd=comfortCommand(f,"vacation");
    cJSON_ReplaceItemInObjectCaseSensitive(cmd.get(),"vacation_until_utc",cJSON_CreateNumber(1792368001));
    f.send("ha/user_command",cmd.get());
    EXPECT_EQ(stringField(f.get("fw/user_command_result").get(),"status"),"accepted");
    f.now+=2000;
    f.core->receive("ha/user_command",printJson(cmd.get()),f.now,1792368002,true);
    EXPECT_EQ(stringField(f.get("fw/user_command_result").get(),"status"),"duplicate");
    cJSON_ReplaceItemInObjectCaseSensitive(cmd.get(),"sequence",cJSON_CreateNumber(2));
    f.core->receive("ha/user_command",printJson(cmd.get()),f.now,1792368002,true);
    auto valid=comfortCommand(f,"away",2);
    f.core->receive("ha/user_command",printJson(valid.get()),f.now,1792368002,true);
    EXPECT_EQ(stringField(f.get("fw/user_command_result").get(),"status"),"accepted");
    auto state=f.state();EXPECT_EQ(stringField(Fixture::row(state),"comfort_mode"),"away");
    EXPECT_EQ(uintField(Fixture::row(state),"override_remaining_ms"),0u);
}
}

namespace {
TEST(ComfortContactsRuntime, NegotiatesContactSupportAndHonoursExplicitOriginalReportAge) {
    Fixture f;f.start();auto hello=f.get("fw/hello");bool advertised=false;
    const auto caps=field(hello.get(),"control_capabilities");
    for(auto c=caps->child;c;c=c->next)if(cJSON_IsString(c)&&std::string(c->valuestring)=="comfort.contacts.v1")advertised=true;
    EXPECT_TRUE(advertised);f.connect();f.heartbeat();
    auto record=parseControlJson(comfortConfig());
    auto z=cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(record.get(),"zones"),0);
    auto p=cJSON_GetObjectItemCaseSensitive(z,"comfort");cJSON_AddNumberToObject(p,"window_max_age_ms",3600000);
    auto request=f.configuration(printJson(record.get()));f.send("ha/config",request.get());f.connect();f.heartbeat();
    ASSERT_EQ(f.core->revision(),1u);
    auto observation=contextObservation(f);cJSON_ReplaceItemInObject(observation.get(),"window_age_ms",cJSON_CreateNumber(180000));
    f.send("ha/observations",observation.get());auto state=f.state();
    EXPECT_EQ(uintField(Fixture::row(state),"target_centi_c"),2100u);
    ++f.now;auto expired=contextObservation(f,2);cJSON_ReplaceItemInObject(expired.get(),"window_age_ms",cJSON_CreateNumber(3600000));
    f.send("ha/observations",expired.get());state=f.state();
    EXPECT_TRUE(cJSON_IsNull(field(Fixture::row(state),"target_centi_c")));
    EXPECT_STREQ(stringField(Fixture::row(state),"reason").c_str(),"window_state_unknown");
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"actuator_output_enabled")));
    EXPECT_FALSE(cJSON_IsTrue(field(state.get(),"boiler_output_enabled")));
}
TEST(ComfortContactsRuntime, InvalidOrPresenceOnlyContactAgeCannotBeCommitted) {
    for(const auto value:{"true","999","86400001","1000.5","\"3600000\""}) {
        Fixture f;f.start();f.connect();f.heartbeat();
        auto record=parseControlJson(comfortConfig());
        auto z=cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(record.get(),"zones"),0);
        cJSON_AddItemToObject(cJSON_GetObjectItemCaseSensitive(z,"comfort"),"window_max_age_ms",cJSON_Parse(value));
        auto request=f.configuration(printJson(record.get()));f.send("ha/config",request.get());
        EXPECT_EQ(f.core->revision(),0u)<<value;
        EXPECT_EQ(f.store.writes,0u);
    }
    Fixture f;f.start();f.connect();f.heartbeat();auto record=parseControlJson(comfortConfig(false));
    auto z=cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(record.get(),"zones"),0);
    cJSON_AddNumberToObject(cJSON_GetObjectItemCaseSensitive(z,"comfort"),"window_max_age_ms",3600000);
    auto request=f.configuration(printJson(record.get()));f.send("ha/config",request.get());
    EXPECT_EQ(f.core->revision(),0u);
}
}
