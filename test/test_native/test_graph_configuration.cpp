#include "GraphConfigurationFixture.h"
namespace {
TEST(GraphConfiguration, ExactSharedValidatorAtomicTupleAndRebootDataNoAdmission) {
    Fixture f;Store store;GraphShadowConfiguration owner("e32_test","test_boot","test_owner",f.anchor,store,controlTestHash);
    ASSERT_TRUE(owner.initialize());admit(owner);ASSERT_TRUE(owner.alive(100));
    ASSERT_EQ(owner.apply(f.raw(),f.map(),101),"graph_committed_no_admission");
    EXPECT_EQ(store.writes,1);EXPECT_EQ(owner.revision(),1u);EXPECT_EQ(owner.mappingRevision(),1u);
    EXPECT_EQ(owner.configDigest(),controlTestHash(owner.configBytes()));EXPECT_EQ(owner.mappingBytes(),f.map());
    EXPECT_LE(store.bytes.size(),owner.maximumStoreBytes);EXPECT_FALSE(owner.alive(102));
    EXPECT_FALSE(owner.boilerOutputEnabled());EXPECT_FALSE(owner.actuatorOutputEnabled());
    GraphShadowConfiguration reboot("e32_test","new_boot","test_owner",f.anchor,store,controlTestHash);
    ASSERT_TRUE(reboot.initialize());EXPECT_EQ(reboot.revision(),1u);EXPECT_FALSE(reboot.alive(102));
    EXPECT_EQ(reboot.configBytes(),owner.configBytes());
}
TEST(GraphConfiguration, NoLeaseExpiredGrantWrongOwnerAndUnknownVersionNeverWrite) {
    Fixture f;Store store;GraphShadowConfiguration owner("e32_test","test_boot","test_owner",f.anchor,store,controlTestHash);
    ASSERT_TRUE(owner.initialize());auto wrong=identity();wrong.adapter="foreign";EXPECT_FALSE(owner.openSession(wrong));
    ASSERT_TRUE(owner.openSession(identity()));ASSERT_TRUE(owner.issueGrant("test_grant",1,100,1000));
    EXPECT_EQ(owner.apply(f.raw(),f.map(),100),"graph_session_rejected");EXPECT_EQ(store.writes,0);
    EXPECT_EQ(owner.heartbeat(heartbeat(),100).code,AdmissionCode::accepted);
    EXPECT_EQ(owner.apply(f.raw(),f.map(),1100),"graph_session_rejected");EXPECT_EQ(store.writes,0);
}
TEST(GraphConfiguration, InvalidWholeGraphDoesNotConsumeSequenceAndNoAutomaticLegacyMigration) {
    Fixture f;Store store;GraphShadowConfiguration owner("e32_test","test_boot","test_owner",f.anchor,store,controlTestHash);
    ASSERT_TRUE(owner.initialize());admit(owner);
    Fixture bad;Fixture::set(bad.config(),"schema",3);bad.rehash();
    EXPECT_EQ(owner.apply(bad.raw(),bad.map(),101),"unsupported_schema");EXPECT_EQ(store.writes,0);
    EXPECT_EQ(owner.apply(f.raw(),f.map(),102),"graph_committed_no_admission");
    Store legacy;legacy.bytes="{\"mapping_digest\":\"old\",\"mode\":\"shadow\",\"revision\":1,\"schema\":1,\"zones\":[]}";
    const auto original=legacy.bytes;GraphShadowConfiguration blocked("e32_test","test_boot","test_owner",f.anchor,legacy,controlTestHash);
    EXPECT_FALSE(blocked.initialize());EXPECT_TRUE(blocked.faulted());EXPECT_EQ(legacy.bytes,original);EXPECT_EQ(legacy.writes,0);
}
TEST(GraphConfiguration, AmbiguousCommittedAndBadReadbackDisableUntilFreshObjectLoadsData) {
    for(bool committed:{false,true}) {
        Fixture f;Store store;GraphShadowConfiguration owner("e32_test","test_boot","test_owner",f.anchor,store,controlTestHash);
        ASSERT_TRUE(owner.initialize());admit(owner);
        if(committed){store.writeOk=false;store.commitOnFailure=true;}else store.corrupt=true;
        EXPECT_EQ(owner.apply(f.raw(),f.map(),101),"storage_fault");EXPECT_TRUE(owner.faulted());EXPECT_EQ(owner.revision(),0u);
        EXPECT_FALSE(owner.alive(102));owner.apply(f.raw(),f.map(),102);EXPECT_EQ(store.writes,1);
        GraphShadowConfiguration reboot("e32_test","new_boot","test_owner",f.anchor,store,controlTestHash);
        EXPECT_EQ(reboot.initialize(),committed);if(committed){EXPECT_EQ(reboot.revision(),1u);}
        EXPECT_FALSE(reboot.alive(102));
    }
}
TEST(GraphConfiguration, OwnerAnchorDigestOrUnknownStoredSchemaCannotReplaceAcceptedData) {
    Fixture f;Store good;GraphShadowConfiguration owner("e32_test","test_boot","test_owner",f.anchor,good,controlTestHash);
    ASSERT_TRUE(owner.initialize());admit(owner);ASSERT_EQ(owner.apply(f.raw(),f.map(),101),"graph_committed_no_admission");
    for(int kind=0;kind<5;++kind) {
        Store store;store.bytes=good.bytes;std::string adapter="test_owner",anchor=f.anchor;
        if(kind==0)adapter="foreign";
        if(kind==1)anchor=std::string(64,'0');
        if(kind>=2&&kind<4){auto root=gt::parse(store.bytes);
            if(kind==2)Fixture::set(root.get(),"schema",2);else Fixture::text(root.get(),"config_digest",std::string(64,'0'));
            store.bytes=gt::print(root.get());}
        auto original=store.bytes;GraphShadowConfiguration blocked(kind==4?"foreign_board":"e32_test","new_boot",adapter,anchor,store,controlTestHash);
        EXPECT_FALSE(blocked.initialize());EXPECT_EQ(store.writes,0);EXPECT_EQ(store.bytes,original);
    }
}
TEST(GraphConfiguration, DurableExternalDriftAndMonotonicReversalFailClosedBeforeWrite) {
    Fixture f;Store store;GraphShadowConfiguration owner("e32_test","test_boot","test_owner",f.anchor,store,controlTestHash);
    ASSERT_TRUE(owner.initialize());admit(owner);store.bytes="external";
    EXPECT_EQ(owner.apply(f.raw(),f.map(),101),"storage_drift");EXPECT_EQ(store.writes,0);
    Store second;GraphShadowConfiguration reversed("e32_test","test_boot","test_owner",f.anchor,second,controlTestHash);
    ASSERT_TRUE(reversed.initialize());admit(reversed);
    EXPECT_EQ(reversed.apply(f.raw(),f.map(),99),"graph_monotonic_fault");EXPECT_EQ(second.writes,0);
}
TEST(GraphConfiguration, AppliedOrOldSessionReplayNeverWritesTwiceAndGrantRotationKeepsWatermarks) {
    Fixture f;Store store;GraphShadowConfiguration owner("e32_test","test_boot","test_owner",f.anchor,store,controlTestHash);
    ASSERT_TRUE(owner.initialize());admit(owner);
    EXPECT_FALSE(owner.openSession(identity())); // repeated local handshake does not reset streams.
    ASSERT_TRUE(owner.issueGrant("rotated",2,101,1000));
    Fixture::text(f.root.get(),"grant_id","rotated");Fixture::set(f.root.get(),"grant_sequence",2);
    ASSERT_EQ(owner.apply(f.raw(),f.map(),102),"graph_committed_no_admission");
    owner.apply(f.raw(),f.map(),103);EXPECT_EQ(store.writes,1);
    EXPECT_FALSE(owner.openSession(identity(1))); // same epoch/session after config cannot resurrect.
    auto fresh=identity(1,2);fresh.session="new_session";EXPECT_TRUE(owner.openSession(fresh));
    EXPECT_FALSE(owner.alive(104));
}
TEST(GraphConfiguration, HashUnavailableOrProviderExceptionFailClosedAndPreserveStore) {
    Fixture f;Store store;
    GraphShadowConfiguration missing("e32_test","test_boot","test_owner",f.anchor,store,[](auto){return std::string();});
    EXPECT_FALSE(missing.initialize());EXPECT_TRUE(missing.faulted());EXPECT_EQ(store.writes,0);
    GraphShadowConfiguration throws("e32_test","test_boot","test_owner",f.anchor,store,[](auto)->std::string{throw std::runtime_error("test provider unavailable");});
    EXPECT_FALSE(throws.initialize());EXPECT_TRUE(throws.faulted());EXPECT_EQ(store.writes,0);
}
TEST(GraphTuple, CanonicalAtomicRoundtripThenSameCoreAdmissionAndSingleDurableCommit) {
    Fixture f;const auto wire=encodeGraphTuple(f.raw(),f.map(),tupleContext(f),controlTestHash);
    const auto parts=decodeGraphTuple(wire,controlTestHash);
    EXPECT_EQ(parts.message,f.raw());EXPECT_EQ(parts.mapping,f.map());
    EXPECT_EQ(wire.size(),f.raw().size()+f.map().size()+11u);
    Store store;GraphShadowConfiguration owner("e32_test","test_boot","test_owner",f.anchor,store,controlTestHash);
    ASSERT_TRUE(owner.initialize());
    EXPECT_EQ(owner.applyTuple(wire,100),"identity");EXPECT_EQ(store.writes,0);
    admit(owner);ASSERT_EQ(owner.applyTuple(wire,101),"graph_committed_no_admission");
    EXPECT_EQ(owner.mappingBytes(),f.map());EXPECT_EQ(store.writes,1);
    owner.applyTuple(wire,102);EXPECT_EQ(store.writes,1);
    EXPECT_FALSE(owner.boilerOutputEnabled());EXPECT_FALSE(owner.actuatorOutputEnabled());
}
TEST(GraphTuple, TamperedMappingUnknownRootAndUnknownPrivateMappingRejectedBeforeWrite) {
    Fixture f;const auto good=encodeGraphTuple(f.raw(),f.map(),tupleContext(f),controlTestHash);
    Store store;GraphShadowConfiguration owner("e32_test","test_boot","test_owner",f.anchor,store,controlTestHash);
    ASSERT_TRUE(owner.initialize());admit(owner);
    auto changed=good;auto at=changed.find("\"resource_id\":\"");ASSERT_NE(at,std::string::npos);
    at+=std::strlen("\"resource_id\":\"");changed[at]=changed[at]=='0'?'1':'0';
    EXPECT_EQ(owner.applyTuple(changed,101),"mapping_conflict");EXPECT_EQ(store.writes,0);
    // Sorted unknown root field; strict exact schema rejects it.
    changed=good;changed.insert(1,"\"aaa\":0,");
    EXPECT_EQ(owner.applyTuple(changed,102),"schema");EXPECT_EQ(store.writes,0);
    // A local draft must pass SAME privacy/semantic validator before encoding.
    cJSON_AddStringToObject(f.mapping.get(),"service","switch.turn_on");f.rehash();
    EXPECT_THROW(encodeGraphTuple(f.raw(),f.map(),tupleContext(f),controlTestHash),gt::Failure);
    EXPECT_EQ(owner.applyTuple(good,103),"graph_committed_no_admission");EXPECT_EQ(store.writes,1);
}
TEST(GraphTuple, CanonicalTotalBudgetAndInvalidHashFailClosed) {
    Fixture f;const auto good=encodeGraphTuple(f.raw(),f.map(),tupleContext(f),controlTestHash);
    EXPECT_THROW(decodeGraphTuple(" "+good,controlTestHash),gt::Failure);
    EXPECT_THROW(decodeGraphTuple(std::string(8193,'x'),controlTestHash),gt::Failure);
    EXPECT_THROW(decodeGraphTuple(good,{}),gt::Failure);
    auto wrong=tupleContext(f);wrong.qualificationDigest=std::string(64,'0');
    EXPECT_THROW(encodeGraphTuple(f.raw(),f.map(),wrong,controlTestHash),gt::Failure);
    const auto key=good.find("\"mapping\":");ASSERT_NE(key,std::string::npos);
    auto duplicate=good;duplicate.insert(key,"\"mapping\":{},");
    EXPECT_THROW(decodeGraphTuple(duplicate,controlTestHash),gt::Failure);
}
TEST(GraphTuple, ExpiredLeaseDisconnectAndAmbiguousCommitNotResurrectedByCodec) {
    for(int phase=0;phase<3;++phase) {
        Fixture f;Store store;GraphShadowConfiguration owner("e32_test","test_boot","test_owner",f.anchor,store,controlTestHash);
        ASSERT_TRUE(owner.initialize());admit(owner);
        const auto wire=encodeGraphTuple(f.raw(),f.map(),tupleContext(f),controlTestHash);
        if(phase==0) {
            EXPECT_EQ(owner.applyTuple(wire,1100),"graph_session_rejected");EXPECT_EQ(store.writes,0);
        }else if(phase==1) {
            owner.disconnected();EXPECT_EQ(owner.applyTuple(wire,101),"graph_session_rejected");EXPECT_EQ(store.writes,0);
        }else {
            store.writeOk=false;store.commitOnFailure=true;
            EXPECT_EQ(owner.applyTuple(wire,101),"storage_fault");EXPECT_EQ(store.writes,1);EXPECT_TRUE(owner.faulted());
            owner.applyTuple(wire,102);EXPECT_EQ(store.writes,1);
            GraphShadowConfiguration restored("e32_test","new_boot","test_owner",f.anchor,store,controlTestHash);
            ASSERT_TRUE(restored.initialize());EXPECT_FALSE(restored.alive(103));EXPECT_EQ(restored.revision(),1u);
        }
    }
}
TEST(GraphAdmission, ExplicitMajorTwoInstanceNotDefaultOrUnknownMajor) {
    for(uint16_t version:{uint16_t(1),uint16_t(2),uint16_t(3)}) {
        SessionAdmission a("test_owner",Direction::ha_to_fw,version);
        if(version==3){EXPECT_FALSE(a.begin(identity()));continue;}
        ASSERT_TRUE(a.begin(identity()));ASSERT_TRUE(a.bind(0,"adapter",StreamKind::heartbeat));
        ASSERT_TRUE(a.issueGrant("test_grant",1,100,1000));
        EXPECT_EQ(a.admit(0,heartbeat(),100).code,version==2?AdmissionCode::accepted:AdmissionCode::wrong_version);
    }
}
}
