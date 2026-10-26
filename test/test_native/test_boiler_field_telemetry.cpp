#include "ShadowControllerFixture.h"
#include "EMS/ClassicBoilerMonitor.h"
#include <set>
namespace {
using namespace heating::ems;
TEST(BoilerFieldTelemetry, RealMonitorSerializesAll69ImmutableFieldsWithinGroupBudget) {
    ClassicBoilerMonitor m;
    for(auto type:{0x18,0x19,0x16,0x33,0x34})
        m.receive(EmsTelegram(EmsTelegram::BROADCAST,8,0,0,type,std::vector<uint8_t>(27,0)),100);
    std::set<unsigned> ids;
    for(size_t group=0;group<7;++group) {
        std::ostringstream out;m.writeFieldGroup(out,1000,group);
        EXPECT_LE(out.str().size(),maximumBoilerGroupBytes);
        auto j=parseControlJson(out.str());ASSERT_TRUE(j);ASSERT_TRUE(validBoilerGroup(j.get(),group));
        auto entries=field(j.get(),"fields");for(auto f=entries->child;f;f=f->next) {
            auto id=cJSON_GetArrayItem(f,0)->valueint;EXPECT_TRUE(ids.insert(id).second);
            EXPECT_STREQ(boilerFieldSpecs[id].name,boilerFieldSpecs[ids.size()-1].name);
            EXPECT_EQ(cJSON_GetArrayItem(f,2)->valueint,100);
        }
    }
    EXPECT_EQ(ids.size(),69u);
}
TEST(BoilerFieldTelemetry, GetterRequiresSessionAndMappingAndNeverChangesControlReadiness) {
    Fixture f;ClassicBoilerMonitor m;unsigned reads=0;
    f.boilerProvider=[&](auto& out,size_t group){++reads;m.writeFieldGroup(out,f.now,group);};
    f.start();EXPECT_EQ(reads,0u);f.connect();f.heartbeat();EXPECT_EQ(reads,0u);
    f.configure();f.connect();f.heartbeat();++f.now;f.tick();ASSERT_EQ(reads,1u);
    auto p=f.get("fw/telemetry/boiler_fields");EXPECT_EQ(uintField(p.get(),"group"),0u);
    EXPECT_EQ(stringField(p.get(),"adapter_session_id"),f.session);
    EXPECT_EQ(stringField(p.get(),"grant_id"),f.grant);EXPECT_TRUE(validBoilerGroup(field(p.get(),"values"),0));
    EXPECT_TRUE(cJSON_IsFalse(field(p.get(),"boiler_output_enabled")));
    EXPECT_TRUE(cJSON_IsFalse(field(p.get(),"actuator_output_enabled")));
    EXPECT_LE(printJson(p.get()).size(),maximumBoilerEnvelopeBytes);
    auto writes=f.store.writes;++f.now;f.tick();EXPECT_EQ(reads,1u);EXPECT_EQ(f.store.writes,writes);
    f.core->disconnected();f.now+=3000;f.tick();EXPECT_EQ(reads,1u);
}
TEST(BoilerFieldTelemetry, InvalidAndSecretBearingProviderCannotPublishOrFaultControl) {
    for(auto raw:{std::string("{bad"),std::string(1201,'x'),std::string("{\"password\":\"NO_RELAY\"}")}) {
        Fixture f;f.boilerProvider=[&](auto& out,size_t){out<<raw;};f.ready();++f.now;f.tick();
        EXPECT_EQ(f.output.count("fw/telemetry/boiler_fields"),0u);EXPECT_FALSE(f.core->faulted());
    }
}
TEST(BoilerFieldTelemetry, UnknownFieldsAndQualityForgeryAreRejectedWithoutSchemaLoosening) {
    ClassicBoilerMonitor m;m.receive(EmsTelegram(EmsTelegram::BROADCAST,8,0,7,0x18,std::vector<uint8_t>{0}),100);
    std::ostringstream out;m.writeFieldGroup(out,200,0);auto j=parseControlJson(out.str());ASSERT_TRUE(validBoilerGroup(j.get(),0));
    auto bit=cJSON_GetArrayItem(field(j.get(),"fields"),7);auto quality=cJSON_GetArrayItem(bit,3);
    cJSON_SetNumberValue(quality,0);EXPECT_FALSE(validBoilerGroup(j.get(),0));
    cJSON_SetNumberValue(quality,1);EXPECT_TRUE(validBoilerGroup(j.get(),0));
    cJSON_AddStringToObject(j.get(),"credential","NO_RELAY");EXPECT_FALSE(validBoilerGroup(j.get(),0));
}
TEST(BoilerFieldTelemetry, SameTimeConflictPublishesNullWithOriginalAcquisitionAndValidSchema) {
    ClassicBoilerMonitor m;
    m.receive(EmsTelegram(EmsTelegram::BROADCAST,8,0,4,0x18,std::vector<uint8_t>{30}),100);
    m.receive(EmsTelegram(EmsTelegram::BROADCAST,8,0,4,0x18,std::vector<uint8_t>{0}),100);
    std::ostringstream out;m.writeFieldGroup(out,200,0);
    auto json=parseControlJson(out.str());ASSERT_TRUE(validBoilerGroup(json.get(),0));
    const auto row=cJSON_GetArrayItem(field(json.get(),"fields"),4);
    EXPECT_TRUE(cJSON_IsNull(cJSON_GetArrayItem(row,1)));
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetArrayItem(row,2)),100);
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetArrayItem(row,4)),24);
    m.receive(EmsTelegram(EmsTelegram::BROADCAST,8,0,4,0x18,std::vector<uint8_t>{0}),201);
    std::ostringstream newer;m.writeFieldGroup(newer,201,0);
    const auto recovered=parseControlJson(newer.str());ASSERT_TRUE(validBoilerGroup(recovered.get(),0));
    EXPECT_EQ(cJSON_GetNumberValue(cJSON_GetArrayItem(cJSON_GetArrayItem(field(recovered.get(),"fields"),4),1)),0);
}

}

TEST(BoilerFieldTelemetry, DiagnosticTimestampsKeepOriginalInvalidStaleAndFutureObservation) {
    ClassicBoilerMonitor monitor;
    auto value=[&](uint64_t now,const char* name,const char* key) {
        std::ostringstream out;monitor.writeJSON(out,now);
        std::unique_ptr<cJSON,decltype(&cJSON_Delete)> j(cJSON_Parse(out.str().c_str()),cJSON_Delete);
        EXPECT_TRUE(j);
        const auto* f=cJSON_GetObjectItem(cJSON_GetObjectItem(j.get(),"fields"),name);
        const auto* v=cJSON_GetObjectItem(f,key);return cJSON_IsNumber(v)?v->valuedouble:-1.;
    };
    EXPECT_EQ(value(0,"measured_flow_temperature","observed_at_ms"),-1);
    monitor.receive({EmsTelegram::BROADCAST,8,0,0,0x18,{0,0,200,0,0,0}},0);
    EXPECT_EQ(value(0,"measured_flow_temperature","observed_at_ms"),0);
    EXPECT_EQ(value(100000,"measured_flow_temperature","observed_at_ms"),0);
    monitor.receive({EmsTelegram::BROADCAST,8,0,1,0x18,{0x80,0}},200000);
    EXPECT_EQ(value(200001,"measured_flow_temperature","observed_at_ms"),200000);
    EXPECT_EQ(value(100,"measured_flow_temperature","observed_at_ms"),200000);
    EXPECT_EQ(value(100,"measured_flow_temperature","age_ms"),-1);
}
