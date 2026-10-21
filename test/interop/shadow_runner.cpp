// Short-lived test executable for HA/FW interop. Not a product bridge/service.
// Each stdin line is a test event; stdout carries actual firmware publications.
#include "control/ShadowController.h"
#include "ControlTestHash.h"
#include <iostream>
#include <fstream>

using namespace heating::control;
struct TestStore:ControlStore {
    std::string bytes; bool fail=false,commitOnError=false;
    bool load(std::string &out) override {out=bytes;return true;}
    bool save(std::string_view value) override {if(!fail||commitOnError)bytes=value;return !fail;}
};
int main(int argc,char **argv) {
    const std::string adapter=argc>1?argv[1]:"ha1";
    TestStore store; unsigned nonce=0; std::unique_ptr<ShadowController> core;
    std::string metricRaw;ShadowController::Metrics provider;
    if(argc>2&&std::string(argv[2])=="metrics")provider=[&](auto& out){out<<metricRaw;};
    // TEST-only explicit source bundle, read BEFORE controller construction.
    // Never an incoming product packet/profile factory or physical qualification.
    const bool seasonal=argc>3&&std::string(argv[2])=="seasonal";
    SeasonalControllerSource seasonalSource;
    SeasonalSafetySnapshot safety;
    SeasonalControllerSource::Safety safetyProvider;
    if(seasonal) {
        char bytes[4097];std::ifstream input(argv[3],std::ios::binary);
        input.read(bytes,sizeof(bytes));const auto length=input.gcount();
        if(length<=0||length>4096)return 5;
        const std::string raw(bytes,static_cast<size_t>(length));
        auto config=parseControlJson(raw);if(!config)return 5;
        const auto zones=field(config.get(),"zones");const auto count=cJSON_GetArraySize(zones);
        if(!cJSON_IsArray(zones)||count<1||count>8)return 5;
        seasonalSource.controllerId="e32_lab";seasonalSource.configDigest=controlTestHash(raw);
        seasonalSource.count=static_cast<size_t>(count);seasonalSource.maximumSafetyAgeMs=2000;
        for(int i=0;i<count;++i) {
            auto zone=cJSON_GetArrayItem(zones,i);auto& pin=seasonalSource.zones[static_cast<size_t>(i)];
            pin.zoneId=stringField(zone,"zone_id");pin.sensorId=stringField(zone,"sensor_id");pin.actuatorId=stringField(zone,"actuator_id");
            pin.seasonal.enabled=pin.seasonal.installationQualified=pin.seasonal.frostAdviceReviewed=true;
            pin.seasonal.maximumSensorAgeMs=120000;pin.seasonal.maximumStepGapMs=300000;
        }
        safety.limitsKnownSafe=safety.dhwStateKnown=true; // Declared fixture report at boot0.
        safetyProvider=[&]{return safety;}; // GET does NOT re-date a source report.
    }
    const auto publish=[](std::string_view topic,std::string_view bytes) {
        auto root=objectJson(); cJSON_AddStringToObject(root.get(),"topic",std::string(topic).c_str());
        cJSON_AddItemToObject(root.get(),"payload",cJSON_Parse(std::string(bytes).c_str()));
        std::cout<<printJson(root.get())<<std::endl;
    };
    const auto boot=[&](const std::string &id) {core=std::make_unique<ShadowController>("e32_lab",id,adapter,store,controlTestHash,[&]{return "nonce"+std::to_string(++nonce);},publish,provider,seasonal?&seasonalSource:nullptr,safetyProvider);};
    boot("boot1");
    std::string line;
    while(std::getline(std::cin,line)) {
        if(line.size()>24576) return 2;
        ControlJson event(cJSON_Parse(line.c_str()),cJSON_Delete);
        if(!event||!integerField(event.get(),"now",0,9007199254740991ULL)) return 3;
        const auto now=uintField(event.get(),"now");
        const auto utc=integerField(event.get(),"utc",0,4102444800ULL)?uintField(event.get(),"utc"):1792368000ULL;
        const bool timeValid=!cJSON_IsFalse(field(event.get(),"clock_valid"));
        const auto op=stringField(event.get(),"op");
        if(op=="boot") boot(stringField(event.get(),"boot_id"));
        else if(op=="connect") core->connected(now);
        else if(op=="disconnect") core->disconnected();
        else if(op=="tick") core->tick(now,utc,timeValid);
        else if(op=="receive") {
            const auto raw=field(event.get(),"raw");
            core->receive(stringField(event.get(),"topic"),cJSON_IsString(raw)?raw->valuestring:printJson(field(event.get(),"payload")),now,utc,timeValid);
        } else if(op=="safety_snapshot"&&seasonal) {
            safety.sampledAt=now;
            safety.limitsKnownSafe=cJSON_IsTrue(field(event.get(),"limits_known_safe"));
            safety.dhwStateKnown=cJSON_IsTrue(field(event.get(),"dhw_state_known"));
            safety.dhwActive=cJSON_IsTrue(field(event.get(),"dhw_active"));
        } else if(op=="metrics_payload") metricRaw=stringField(event.get(),"raw");
        else if(op=="store_fault") {store.fail=cJSON_IsTrue(field(event.get(),"fail"));store.commitOnError=cJSON_IsTrue(field(event.get(),"commit_on_error"));}
        else return 4;
        std::cout<<"{\"event_done\":true}"<<std::endl;
    }
}
