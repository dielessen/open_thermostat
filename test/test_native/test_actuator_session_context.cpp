#include "ShadowControllerFixture.h"
#include "control/ActuatorDispatch.h"
namespace {
std::string contextGrant(const ActuatorScope& scope) {
    auto root=objectJson();
    cJSON_AddStringToObject(root.get(),"adapter_id",scope.adapter.c_str());
    cJSON_AddStringToObject(root.get(),"adapter_session_id",scope.session.c_str());
    cJSON_AddNumberToObject(root.get(),"api",1);cJSON_AddStringToObject(root.get(),"binding_id",scope.binding.c_str());
    cJSON_AddStringToObject(root.get(),"boot_id",scope.boot.c_str());cJSON_AddStringToObject(root.get(),"command_kind","room_target");
    cJSON_AddStringToObject(root.get(),"config_digest",scope.digest.c_str());cJSON_AddNumberToObject(root.get(),"config_revision",scope.revision);
    cJSON_AddStringToObject(root.get(),"controller_id",scope.controller.c_str());cJSON_AddNumberToObject(root.get(),"epoch",scope.epoch);
    cJSON_AddStringToObject(root.get(),"grant_id","receiver1");cJSON_AddNumberToObject(root.get(),"grant_ms",5000);
    cJSON_AddNumberToObject(root.get(),"grant_sequence",1);return printJson(root.get());
}
TEST(ActuatorSessionContext, NoContextBeforeRealHandshakeMappingAndHeartbeat) {
    Fixture f;f.start();EXPECT_FALSE(f.core->actuatorSessionContext("trv1",f.now));
    f.connect();f.heartbeat();EXPECT_FALSE(f.core->actuatorSessionContext("trv1",f.now));
    f.configure();EXPECT_FALSE(f.core->actuatorSessionContext("trv1",f.now));
    f.connect();EXPECT_FALSE(f.core->actuatorSessionContext("trv1",f.now));f.heartbeat();
    EXPECT_TRUE(f.core->actuatorSessionContext("trv1",f.now));
}
TEST(ActuatorSessionContext, ExactOwnedTupleAndOriginalDeadlinesWithoutPublishWriteOrAuthority) {
    Fixture f;f.ready();const auto output=f.output;const auto bytes=f.store.bytes;const auto writes=f.store.writes;
    const auto context=f.core->actuatorSessionContext("trv1",f.now);ASSERT_TRUE(context);
    EXPECT_EQ(context->scope.controller,"e32_lab");EXPECT_EQ(context->scope.boot,f.boot);
    EXPECT_EQ(context->scope.adapter,"ha1");EXPECT_EQ(context->scope.session,f.session);
    EXPECT_EQ(context->scope.epoch,f.epoch);EXPECT_EQ(context->scope.revision,1u);
    EXPECT_EQ(context->scope.digest,f.digest);EXPECT_EQ(context->scope.binding,"trv1");
    EXPECT_EQ(context->leaseUntil,f.now+ShadowController::leaseMs);
    EXPECT_EQ(context->grantUntil,f.now+ShadowController::grantMs);
    EXPECT_EQ(context->validUntil(),context->grantUntil);EXPECT_FALSE(context->authorizesActuation());
    ++f.now;auto again=f.core->actuatorSessionContext("trv1",f.now);ASSERT_TRUE(again);
    EXPECT_EQ(again->leaseUntil,context->leaseUntil);EXPECT_EQ(again->grantUntil,context->grantUntil);
    EXPECT_EQ(f.output,output);EXPECT_EQ(f.store.bytes,bytes);EXPECT_EQ(f.store.writes,writes);
}
TEST(ActuatorSessionContext, UnknownBindingsExpiryAndDisconnectedOwnerNeverReturnOldContext) {
    Fixture f;f.ready();
    EXPECT_FALSE(f.core->actuatorSessionContext("foreign",f.now));
    EXPECT_FALSE(f.core->actuatorSessionContext("",f.now));
    EXPECT_FALSE(f.core->actuatorSessionContext("trv1/other",f.now));
    EXPECT_FALSE(f.core->actuatorSessionContext("trv1",f.now+ShadowController::grantMs));
    // Looking back after observing expiry cannot re-create proof.
    EXPECT_FALSE(f.core->actuatorSessionContext("trv1",f.now));
    f.core->disconnected();EXPECT_FALSE(f.core->actuatorSessionContext("trv1",f.now));
}
TEST(ActuatorSessionContext, ActualControllerLossClosesPreparedDispatcherBeforeAnyHandoff) {
    Fixture f;f.ready();auto context=f.core->actuatorSessionContext("trv1",f.now);ASSERT_TRUE(context);int sends=0;
    // Explicit synthetic test qualification only; the context itself NEVER
    // authorizes a physical profile, and normal factory selection is unchanged.
    ActuatorDispatch owner(context->scope,[&]{
        auto current=f.core->actuatorSessionContext("trv1",f.now);
        return current?ActuatorDispatch::Facts{current->scope,current->validUntil(),true}:ActuatorDispatch::Facts{};
    },[&]{return f.now;},[&](auto,uint64_t){++sends;return true;});
    ASSERT_TRUE(owner.accept(contextGrant(context->scope),f.now));
    f.core->disconnected();++f.now;
    EXPECT_EQ(owner.dispatch(2100),ActuatorDispatch::Outcome::refused);EXPECT_TRUE(owner.retired());EXPECT_EQ(sends,0);
}
TEST(ActuatorSessionContext, RealReconnectChangesScopeAndCannotReuseOldDispatchOwner) {
    Fixture f;f.ready();auto original=f.core->actuatorSessionContext("trv1",f.now);ASSERT_TRUE(original);int sends=0;
    ActuatorDispatch owner(original->scope,[&]{
        auto current=f.core->actuatorSessionContext("trv1",f.now);
        return current?ActuatorDispatch::Facts{current->scope,current->validUntil(),true}:ActuatorDispatch::Facts{};
    },[&]{return f.now;},[&](auto,uint64_t){++sends;return true;});
    ASSERT_TRUE(owner.accept(contextGrant(original->scope),f.now));
    ++f.now;f.core->connected(f.now);f.tick();f.connect();f.heartbeat();
    auto current=f.core->actuatorSessionContext("trv1",f.now);ASSERT_TRUE(current);
    EXPECT_FALSE(current->scope==original->scope);EXPECT_FALSE(current->authorizesActuation());
    EXPECT_EQ(owner.dispatch(2100),ActuatorDispatch::Outcome::refused);EXPECT_TRUE(owner.retired());EXPECT_EQ(sends,0);
}
}
