#pragma once
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
gt::Context tupleContext(const Fixture& f) {
    return {"e32_test","test_boot","test_owner","test_session","test_grant",1,1,0,0,"",f.anchor};
}
}
