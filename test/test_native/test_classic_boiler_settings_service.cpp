#include "EMS/ClassicBoilerSettingsService.h"
#include "control/HttpAccessPolicy.h"
#include "update/ReleasePolicy.h"
#include <gtest/gtest.h>
#include <sstream>
using namespace heating::ems;
namespace {
std::string owner(64,'a');
std::string body(){return "{\"schema\":1,\"boot_id\":\"000000000000002a\",\"revision\":1,\"entity\":\"heatingtemp\",\"value\":45,\"exclusive_owner_confirmed\":true,\"independent_stop_confirmed\":true}";}
std::string replace(std::string value,const std::string& from,const std::string& to){value.replace(value.find(from),from.size(),to);return value;}
TEST(ClassicSettingsService, DefaultProductionGateNeverQueuesAWrite){
    ClassicBoilerSettingsService service{42};
    auto result=service.request(body(),owner,100,true);
    EXPECT_EQ(result.http,409);EXPECT_STREQ(result.error,"settings_transport_unqualified");EXPECT_FALSE(service.active());
    std::ostringstream out;service.writeJSON(out,100,true);
    auto json=heating::control::parseControlJson(out.str());ASSERT_TRUE(json);
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(json.get(),"available")));
    EXPECT_TRUE(cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(json.get(),"write_attempted")));
}
TEST(ClassicSettingsService, InvalidAuthenticationAndMalformedOrUnexpectedFieldsReject){
    ClassicBoilerSettingsService service{42,true};
    EXPECT_EQ(service.request(body(),"",100,true).http,401);
    for(const auto& invalid:{std::string(385,'x'),std::string("{}"),std::string("[]"),
        replace(body(),"\"schema\":1","\"schema\":1.5"),
        replace(body(),"\"value\":45","\"value\":true"),
        replace(body(),"\"value\":45","\"value\":45.5"),
        replace(body(),"\"revision\":1","\"revision\":0"),
        replace(body(),"\"entity\":\"heatingtemp\"","\"entity\":\"reset\""),
        replace(body(),"\"value\":45","\"value\":91"),
        replace(body(),"\"value\":45","\"value\":-1"),
        replace(body(),"\"value\":45","\"value\":45,\"source_address\":11"),
        replace(body(),"\"value\":45","\"value\":45,\"value\":46")}){
        EXPECT_EQ(service.request(invalid,owner,100,true).http,400)<<invalid;
        EXPECT_FALSE(service.active());
    }
}
TEST(ClassicSettingsService, BootAndBothSiteDeclarationsAreRequired){
    ClassicBoilerSettingsService service{42,true};
    EXPECT_EQ(service.request(replace(body(),"000000000000002a","000000000000002b"),owner,100,true).http,409);
    for(auto field:{"exclusive_owner_confirmed","independent_stop_confirmed"})
        EXPECT_EQ(service.request(replace(body(),std::string("\"")+field+"\":true",std::string("\"")+field+"\":false"),owner,100,true).http,400);
    EXPECT_FALSE(service.active());
}
TEST(ClassicSettingsService, ExactDuplicateIsIdempotentButDifferentOperatorOrValueCannotReuseRevision){
    ClassicBoilerSettingsService service{42,true};
    EXPECT_EQ(service.request(body(),owner,100,true).http,202);
    auto duplicate=service.request(body(),owner,101,true);EXPECT_EQ(duplicate.http,200);EXPECT_TRUE(duplicate.duplicate);
    EXPECT_EQ(service.request(body(),std::string(64,'b'),101,true).http,403);
    EXPECT_EQ(service.request(replace(body(),"\"value\":45","\"value\":46"),owner,101,true).http,409);
}
TEST(ClassicSettingsService, PermissionLossRejectsEvenWithQualifiedTransport){
    ClassicBoilerSettingsService service{42,true};
    EXPECT_EQ(service.request(body(),owner,100,false).http,409);EXPECT_FALSE(service.active());
}
TEST(ClassicSettingsService, StatusListsOnlyFourDefinedSettingsAndNeverSessionTokens){
    ClassicBoilerSettingsService service{42,true};
    ASSERT_EQ(service.request(body(),owner,100,true).http,202);
    std::ostringstream out;service.writeJSON(out,100,true);
    EXPECT_EQ(out.str().find(owner),std::string::npos);
    auto json=heating::control::parseControlJson(out.str());ASSERT_TRUE(json);
    auto fields=cJSON_GetObjectItemCaseSensitive(json.get(),"settings");ASSERT_EQ(cJSON_GetArraySize(fields),4);
    const char* names[]={"heatingactivated","heatingtemp","burnminperiod","pumpdelay"};
    const int offsets[]={0,1,6,8},maximums[]={1,90,120,60};
    for(int i=0;i<4;++i){auto field=cJSON_GetArrayItem(fields,i);
        EXPECT_STREQ(cJSON_GetObjectItemCaseSensitive(field,"entity")->valuestring,names[i]);
        EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(field,"offset")->valueint,offsets[i]);
        EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(field,"maximum")->valueint,maximums[i]);
    }
}
TEST(ClassicSettingsService, HttpMethodOriginUpdateAndTrialPoliciesProtectWriteRoute){
    using namespace heating::control;
    EXPECT_TRUE(allowedHttpMethod("/boiler/settings/write","POST"));
    for(auto method:{"GET","PUT","DELETE"})EXPECT_FALSE(allowedHttpMethod("/boiler/settings/write",method));
    EXPECT_TRUE(boilerTestMutationBlocked("/boiler/settings/write",true));
    EXPECT_FALSE(sameOrigin("http://other","e32.local","cross-site"));
    for(int flag=0;flag<3;++flag)
        EXPECT_TRUE(heating::update::mutationBlocked("/boiler/settings/write",flag==0,flag==1,flag==2));
    EXPECT_FALSE(heating::update::mutationBlocked("/boiler/settings/write",false,false,false));
}
TEST(ClassicSettingsService, StatusCorrelatesIntentPhaseAndRequesterWithoutTokenDisclosure){
    ClassicBoilerSettingsService service{42,true};ASSERT_EQ(service.request(body(),owner,100,true).http,202);
    for(bool same:{false,true}){
        std::ostringstream out;service.writeJSON(out,100,true,same?owner:std::string(64,'b'));
        auto json=heating::control::parseControlJson(out.str());ASSERT_TRUE(json);
        EXPECT_EQ(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(json.get(),"owned_by_requester")),same);
        EXPECT_STREQ(cJSON_GetObjectItemCaseSensitive(json.get(),"phase")->valuestring,"queued_write");
        auto request=cJSON_GetObjectItemCaseSensitive(json.get(),"request");
        EXPECT_STREQ(cJSON_GetObjectItemCaseSensitive(request,"entity")->valuestring,"heatingtemp");
        EXPECT_EQ(cJSON_GetObjectItemCaseSensitive(request,"value")->valueint,45);
        EXPECT_TRUE(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(json.get(),"response_at_ms")));
        EXPECT_EQ(out.str().find(owner),std::string::npos);
    }
}

}
