#include <gtest/gtest.h>
#include "control/GraphSessionOwner.h"
#include "ControlTestHash.h"
#include <fstream>
using namespace heating::control;
namespace gt=heating::graph_test;
namespace {
struct GraphSessionStore:ControlStore {
    std::string data;size_t writes=0;
    bool load(std::string& out)override{out=data;return true;}
    bool save(std::string_view raw)override{++writes;data=raw;return true;}
};
using Fields=std::map<std::string,std::string>;
std::string text(const std::string& raw){return "\""+raw+"\"";}
std::string document(const Fields& fields) {
    std::string out="{";
    for(const auto& field:fields) {if(out.size()>1)out+=",";out+=text(field.first)+":"+field.second;}
    return out+"}";
}
struct Protocol {
    GraphSessionStore store;uint32_t nonce=0;std::string anchor;
    std::vector<std::pair<std::string,std::string>> frames;
    std::unique_ptr<GraphSessionOwner> owner;
    Protocol(bool missingNonce=false) {
        std::ifstream file("test/fixtures/graph-shadow-validation.jsonl");std::string line;std::getline(file,line);
        gt::Json record(cJSON_Parse(line.c_str()),cJSON_Delete);if(!record)throw std::runtime_error("fixture");
        anchor=gt::str(gt::get(gt::get(record.get(),"context"),"qualification_digest"));
        owner=std::make_unique<GraphSessionOwner>("e32_test","test_boot","test_owner",anchor,store,controlTestHash,
            [&,missingNonce]{return missingNonce?std::string():"random_"+std::to_string(++nonce);},
            [&](auto topic,auto bytes){frames.emplace_back(topic,bytes);});
    }
    gt::Json last(const char* topic) {
        for(auto it=frames.rbegin();it!=frames.rend();++it)
            if(it->first==topic)return gt::parse(it->second);
        throw std::runtime_error(std::string("missing frame ")+topic);
    }
    std::string open() {
        auto hello=last("fw/hello");return document({
            {"adapter_id",text("test_owner")},{"adapter_session_id",text("test_session")},
            {"api","2"},{"boot_id",text("test_boot")},
            {"challenge_id",text(gt::str(gt::get(hello.get(),"challenge_id")))},
            {"client_nonce",text("test_client_nonce")},{"controller_id",text("e32_test")},
            {"epoch",gt::print(gt::get(hello.get(),"epoch"))},{"transport",text(GraphSessionOwner::transport)}});
    }
    Fields envelope(const char* binding,uint32_t seq=1) {
        auto session=last("fw/session");Fields values;
        for(const char* key:{"adapter_id","adapter_session_id","api","boot_id","config_revision",
            "controller_id","epoch","grant_id","grant_sequence"})values[key]=gt::print(gt::get(session.get(),key));
        values["binding_id"]=text(binding);values["sequence"]=std::to_string(seq);return values;
    }
    std::string heartbeat(uint32_t seq=1,const char* proof="proof_first") {
        auto values=envelope("adapter",seq);values["grant_request_nonce"]=text(proof);return document(values);
    }
    void start() {owner->connected(100);owner->receive("ha/open_session",open(),100);}
    void physicalOff() {
        EXPECT_FALSE(owner->configuration().boilerOutputEnabled());
        EXPECT_FALSE(owner->configuration().actuatorOutputEnabled());EXPECT_EQ(store.writes,0u);
    }
};
TEST(GraphSessionOwner, ExplicitVersionProfileAndFreshProofOnlyAfterNewAcceptedHeartbeat) {
    Protocol p;p.start();auto hello=p.last("fw/hello");
    EXPECT_EQ(gt::str(gt::get(hello.get(),"profile")),GraphSessionOwner::profile);
    EXPECT_EQ(gt::str(gt::get(hello.get(),"transport")),GraphSessionOwner::transport);
    auto hb=p.heartbeat();p.owner->receive("ha/heartbeat",hb,101);
    auto newer=p.heartbeat(2,"proof_latest");p.owner->receive("ha/heartbeat",newer,102);
    p.owner->receive("ha/heartbeat",p.heartbeat(2,"changed_duplicate"),103);
    p.owner->tick(5100);auto grant=p.last("fw/session");
    EXPECT_EQ(gt::str(gt::get(grant.get(),"grant_request_nonce")),"proof_latest");
    p.physicalOff();
}
TEST(GraphSessionOwner, ExactOpenAndHeartbeatRetriesCannotResetWatermarksOrRenewLease) {
    Protocol p;p.owner->connected(100);const auto open=p.open();
    p.owner->receive("ha/open_session",open,100);const auto hb=p.heartbeat();
    p.owner->receive("ha/heartbeat",hb,100);
    p.owner->receive("ha/open_session",open,200);
    p.owner->receive("ha/heartbeat",hb,5000);
    p.owner->tick(15100);auto hello=p.last("fw/hello");
    EXPECT_EQ(gt::integer(gt::get(hello.get(),"epoch"),1,UINT32_MAX),2);
    EXPECT_FALSE(p.owner->configuration().alive(15100));p.physicalOff();
}
TEST(GraphSessionOwner, WholeHeartbeatShapeAndNonceRequiredBeforeAdmission) {
    Protocol p;p.start();const auto valid=p.heartbeat();
    auto values=p.envelope("adapter");values["grant_request_nonce"]=text("proof_first");values["private_secret"]=text("never_forward");
    p.frames.clear();p.owner->receive("ha/heartbeat",document(values),101);EXPECT_TRUE(p.frames.empty());
    values.erase("private_secret");values.erase("grant_request_nonce");
    p.owner->receive("ha/heartbeat",document(values),102);EXPECT_TRUE(p.frames.empty());
    p.owner->receive("ha/heartbeat",valid,103);ASSERT_FALSE(p.frames.empty());
    auto cap=p.last("fw/graph_capability");EXPECT_EQ(gt::integer(gt::get(cap.get(),"sequence"),1,UINT32_MAX),1);
    p.physicalOff();
}
TEST(GraphSessionOwner, WrongOwnerMajorChallengeOrUnscopedSnapshotCannotBeginAdmission) {
    for(const char* key:{"adapter_id","api","challenge_id"}) {
        Protocol p;p.owner->connected(100);auto open=gt::parse(p.open());
        if(std::strcmp(key,"api")==0)cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(open.get(),key),1);
        else cJSON_SetValuestring(cJSON_GetObjectItemCaseSensitive(open.get(),key),"foreign");
        p.frames.clear();p.owner->receive("ha/open_session",gt::print(open.get()),101);
        EXPECT_TRUE(p.frames.empty());EXPECT_FALSE(p.owner->configuration().alive(101));p.physicalOff();
    }
    Protocol p;p.start();const auto snapshot=document(p.envelope("snapshot"));
    p.frames.clear();p.owner->receive("ha/snapshot_request",snapshot,101);EXPECT_TRUE(p.frames.empty());p.physicalOff();
}
TEST(GraphSessionOwner, ExactReadOnlySnapshotRetryAllowedButExpiredGrantOrLeaseNotRevived) {
    Protocol p;p.start();p.owner->receive("ha/heartbeat",p.heartbeat(),101);
    const auto snapshot=document(p.envelope("snapshot"));p.frames.clear();
    p.owner->receive("ha/snapshot_request",snapshot,102);ASSERT_EQ(p.frames.size(),2u);
    p.frames.clear();p.owner->receive("ha/snapshot_request",snapshot,103);ASSERT_EQ(p.frames.size(),2u);
    auto duplicate=p.last("fw/snapshot_result");EXPECT_EQ(gt::str(gt::get(duplicate.get(),"status")),"duplicate");
    p.frames.clear();p.owner->receive("ha/snapshot_request",snapshot,10100);EXPECT_TRUE(p.frames.empty());
    p.owner->tick(15101);auto hello=p.last("fw/hello");
    EXPECT_EQ(gt::integer(gt::get(hello.get(),"epoch"),1,UINT32_MAX),2);p.physicalOff();
}
TEST(GraphSessionOwner, MonotoneReversalInvalidNonceAndLegacyStoreFailClosed) {
    Protocol p;p.start();p.owner->tick(99);EXPECT_TRUE(p.owner->faulted());p.physicalOff();
    Protocol nonce(true);nonce.owner->connected(100);EXPECT_TRUE(nonce.owner->faulted());nonce.physicalOff();
    GraphSessionStore old;old.data="{\"mode\":\"shadow\",\"revision\":1}";
    GraphSessionOwner legacy("e32_test","test_boot","test_owner",p.anchor,old,controlTestHash,
        []{return "good_nonce";},[](auto,auto){});
    EXPECT_TRUE(legacy.faulted());legacy.connected(100);
    EXPECT_EQ(old.writes,0u);EXPECT_EQ(old.data,"{\"mode\":\"shadow\",\"revision\":1}");
}
}
