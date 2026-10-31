// boiler.output.v1 (beta.22): the HA v1 session reports whether the E32 itself
// sends the boiler request. Only an HA that asks for it in ha/capabilities gets
// the real value; HA 0.4.0b13 and older never ask and must keep seeing false.
#include "ShadowControllerFixture.h"
namespace {
ControlJson capabilityRequest(const char* cap) {
    auto o=objectJson(); auto list=cJSON_AddArrayToObject(o.get(),"read_only");
    cJSON_AddItemToArray(list,cJSON_CreateString(cap)); return o;
}
bool advertised(const ControlJson& hello) {
    const cJSON* caps=field(hello.get(),"read_only_capabilities");
    for(const cJSON* c=caps?caps->child:nullptr;c;c=c->next)
        if(cJSON_IsString(c)&&std::string_view(c->valuestring)=="boiler.output.v1")return true;
    return false;
}
// The next zone state after one state step (it is published on a change).
ControlJson nextState(Fixture& f) { f.now+=3000; f.tick(); return f.state(); }
bool output(Fixture& f) { auto s=nextState(f); EXPECT_FALSE(cJSON_IsTrue(field(s.get(),"actuator_output_enabled"))); return cJSON_IsTrue(field(s.get(),"boiler_output_enabled")); }

TEST(BoilerOutputFlag, TheHelloAdvertisesItOnlyWithTheHeatingProvider) {
    Fixture f; f.boilerProvider=[](std::ostream&,size_t){}; f.start();
    EXPECT_FALSE(advertised(f.get("fw/hello")));
    f.core->setBoilerOutput([]{return false;});
    f.now+=3000; f.tick();
    EXPECT_TRUE(advertised(f.get("fw/hello")));
}

TEST(BoilerOutputFlag, AnHaThatNeverAsksSeesFalseEvenWhileTheE32Sends) {
    Fixture f; bool sending=true; f.ready(); f.core->setBoilerOutput([&]{return sending;});
    EXPECT_FALSE(output(f));
    auto other=capabilityRequest("boiler.fields.v2"); f.send("ha/capabilities",other.get()); // a b13-style request
    EXPECT_FALSE(output(f));
}

TEST(BoilerOutputFlag, AskedForItFollowsTheGuardAndANewSessionForgetsIt) {
    Fixture f; bool sending=false; f.ready(); f.core->setBoilerOutput([&]{return sending;});
    auto request=capabilityRequest("boiler.output.v1"); f.send("ha/capabilities",request.get());
    EXPECT_FALSE(output(f));          // shadow, waiting for confirmation, stopping
    sending=true;  EXPECT_TRUE(output(f));   // the guard owns the boiler and sends
    sending=false; EXPECT_FALSE(output(f));  // hand-back, a foreign 0x1A, lost readings, a withdrawal
    sending=true; f.connect(); f.heartbeat();
    EXPECT_FALSE(output(f));          // a new session starts without the capability
}
}
