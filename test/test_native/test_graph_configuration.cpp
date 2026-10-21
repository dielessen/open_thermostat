#include <gtest/gtest.h>
#include "control/GraphShadowConfiguration.h"
#include "ControlTestHash.h"
#include <fstream>
using namespace heating::control;
namespace gt=heating::graph_test;
namespace {
struct Store:ControlStore {
    std::string bytes;int writes=0;bool readOk=true,writeOk=true,commitOnFailure=false,corrupt=false;
    bool load(std::string& out) override {out=bytes;return readOk;}
    bool save(std::string_view input)override {++writes;if(writeOk||commitOnFailure)bytes=input;if(corrupt&&!bytes.empty())bytes[0]='X';return writeOk;}
};
struct Fixture {
    gt::Json root{nullptr,cJSON_Delete},mapping{nullptr,cJSON_Delete};std::string anchor;
    Fixture() {
        std::ifstream file("test/fixtures/graph-shadow-validation.jsonl");std::string line;std::getline(file,line);
        gt::Json record(cJSON_Parse(line.c_str()),cJSON_Delete);if(!record)throw std::runtime_error("shared fixture not found");
        anchor=gt::str(gt::get(gt::get(record.get(),"context"),"qualification_digest"));
        root=gt::parse(gt::str(gt::get(record.get(),"raw")));mapping=gt::parse(gt::str(gt::get(record.get(),"mapping_raw")));
        set(root.get(),"expected_revision",0);set(root.get(),"config_revision",0);
        set(config(),"revision",1);set(config(),"mapping_revision",1);set(mapping.get(),"mapping_revision",1);rehash();
    }
    static void set(cJSON* o,const char* key,int value) {auto p=cJSON_GetObjectItemCaseSensitive(o,key);if(!p)throw std::runtime_error("fixture field absent");cJSON_SetNumberValue(p,value);}
    static void text(cJSON* o,const char* key,const std::string& value) {auto p=cJSON_GetObjectItemCaseSensitive(o,key);if(!p||!cJSON_SetValuestring(p,value.c_str()))throw std::runtime_error("fixture string absent");}
    cJSON* config(){return cJSON_GetObjectItemCaseSensitive(root.get(),"config");}
    void rehash(){text(config(),"mapping_digest",controlTestHash(gt::print(mapping.get())));text(root.get(),"config_digest",controlTestHash(gt::print(config())));}
    std::string raw(){return gt::print(root.get());}
    std::string map(){return gt::print(mapping.get());}
};
SessionIdentity identity(uint32_t rev=0,uint32_t epoch=1) {return {"e32_test","test_boot","test_owner","test_session",epoch,rev};}
Envelope heartbeat(uint32_t revision=0,uint32_t sequence=1) {
    Envelope e;e.major=2;e.kind=StreamKind::heartbeat;e.direction=Direction::ha_to_fw;
    e.controller="e32_test";e.boot="test_boot";e.adapter="test_owner";e.session="test_session";
    e.epoch=1;e.revision=revision;e.binding="adapter";e.grant="test_grant";e.grantSequence=1;e.sequence=sequence;
    // Immutable fixed synthetic heartbeat bytes; real config digest is tested separately.
    e.payloadDigest[0]=1;return e;
}
void admit(GraphShadowConfiguration& owner,uint32_t rev=0) {
    ASSERT_TRUE(owner.openSession(identity(rev)));ASSERT_TRUE(owner.issueGrant("test_grant",1,100,1000));
    ASSERT_EQ(owner.heartbeat(heartbeat(rev),100).code,AdmissionCode::accepted);
}
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
gt::Context tupleContext(const Fixture& f) {
    return {"e32_test","test_boot","test_owner","test_session","test_grant",1,1,0,0,"",f.anchor};
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
