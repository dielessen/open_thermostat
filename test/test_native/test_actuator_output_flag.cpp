// actuator.output.v1 (radiator valves, beta.24): the HA v1 session reports whether the E32
// itself drives radiator valves. Only an HA that asks for it in ha/capabilities gets the real
// value; HA up to 0.4.0b15 never asks and must keep seeing false (it refuses true). Not in the
// hello: its capability lists are full; GET /config/heating/trv names it under "features".
#include "ShadowControllerFixture.h"
namespace {
ControlJson capabilityRequest(std::initializer_list<const char*> caps) {
    auto o=objectJson(); auto list=cJSON_AddArrayToObject(o.get(),"read_only");
    for(const char* c:caps)cJSON_AddItemToArray(list,cJSON_CreateString(c));
    return o;
}
bool named(const ControlJson& hello,const char* name) {
    for(const char* key:{"read_only_capabilities","control_capabilities","session_capabilities"}) {
        const cJSON* caps=field(hello.get(),key);
        for(const cJSON* c=caps?caps->child:nullptr;c;c=c->next)
            if(cJSON_IsString(c)&&std::string_view(c->valuestring)==name)return true;
    }
    return false;
}
ControlJson nextState(Fixture& f) { f.now+=3000; f.tick(); return f.state(); }
bool actuators(Fixture& f) { auto s=nextState(f); return cJSON_IsTrue(field(s.get(),"actuator_output_enabled")); }

TEST(ActuatorOutputFlag, NeverInTheHelloSoItsListsStayWithinEight) {
    Fixture f; f.boilerProvider=[](std::ostream&,size_t){}; f.start();
    f.core->setBoilerOutput([]{return false;}); f.core->setActuatorOutput([]{return true;});
    f.now+=3000; f.tick();
    const auto hello=f.get("fw/hello");
    EXPECT_FALSE(named(hello,"actuator.output.v1"));
    for(const char* key:{"read_only_capabilities","control_capabilities","session_capabilities"}) {
        const cJSON* caps=field(hello.get(),key);
        EXPECT_LE(caps?cJSON_GetArraySize(caps):0,8)<<key;
    }
}

TEST(ActuatorOutputFlag, AnHaThatNeverAsksSeesFalseEvenWhileValvesAreDriven) {
    Fixture f; f.ready(); f.core->setActuatorOutput([]{return true;});
    EXPECT_FALSE(actuators(f));
    auto older=capabilityRequest({"boiler.fields.v2","boiler.output.v1"}); f.send("ha/capabilities",older.get()); // a b14/b15 request
    EXPECT_FALSE(actuators(f));
}

TEST(ActuatorOutputFlag, AskedForItFollowsTheValvesAndANewSessionForgetsIt) {
    Fixture f; bool driving=false; f.ready(); f.core->setActuatorOutput([&]{return driving;});
    auto request=capabilityRequest({"boiler.output.v1","actuator.output.v1"}); f.send("ha/capabilities",request.get());
    EXPECT_FALSE(actuators(f));          // no valve control on, or the E32 does not drive the boiler
    driving=true;  EXPECT_TRUE(actuators(f));
    driving=false; EXPECT_FALSE(actuators(f));
    driving=true; f.connect(); f.heartbeat();
    EXPECT_FALSE(actuators(f));          // a new session starts without the capability
}

// Harmless while unused, byte for byte: firmware with valve support but no valve driven sends
// exactly what it sent before, to an HA that asks for the capability and to one that does not.
TEST(ActuatorOutputFlag, UnusedValveSupportChangesNoByteOfTheSession) {
    for(const bool asks:{false,true}) {
        Fixture before,unused,driving;
        before.ready(); unused.ready(); driving.ready();
        unused.core->setActuatorOutput([]{return false;});   // valves configured, none driven
        driving.core->setActuatorOutput([]{return true;});   // driven: only an HA that asked sees it
        auto request=asks?capabilityRequest({"boiler.output.v1","actuator.output.v1"}):capabilityRequest({"boiler.output.v1"});
        for(Fixture* f:{&before,&unused,&driving}) f->send("ha/capabilities",request.get());
        for(int step=0;step<200;++step) {
            for(Fixture* f:{&before,&unused,&driving}) { f->now+=3000; f->tick(); if(step%5==0) f->heartbeat(); }
            ASSERT_EQ(before.output,unused.output)<<"step "<<step<<(asks?" (asked)":"");
            if(!asks) ASSERT_EQ(before.output,driving.output)<<"step "<<step;
        }
    }
}

TEST(ActuatorOutputFlag, WithoutAProviderItStaysFalseWhateverHaAsks) {
    Fixture f; f.ready();
    auto request=capabilityRequest({"actuator.output.v1"}); f.send("ha/capabilities",request.get());
    EXPECT_FALSE(actuators(f));
}
}
