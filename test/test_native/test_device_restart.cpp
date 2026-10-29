#include "update/RestartTimer.h"
#include "control/HttpAccessPolicy.h"
#include "control/WebAuthSession.h"
#include <gtest/gtest.h>
using namespace heating;
TEST(DeviceRestart, BusyAndPendingBootCannotInterruptUpdateOrBootValidation) {
    for(bool busy:{false,true})for(bool pending:{false,true})
        EXPECT_EQ(update::manualRebootAllowed(busy,pending),!busy&&!pending);
    update::RestartTimer timer;timer.schedule(100,1000);
    EXPECT_FALSE(timer.due(1099,false));EXPECT_TRUE(timer.due(1100,false));
    EXPECT_FALSE(timer.due(1100,true));
}
TEST(DeviceRestart, PostOnlyValidSessionAndOwnCsrfNoLanSetupException) {
    EXPECT_TRUE(control::allowedHttpMethod("/updates/reboot","POST"));
    for(auto method:{"GET","DELETE","HEAD","PUT"})EXPECT_FALSE(control::allowedHttpMethod("/updates/reboot",method));
    control::WebAuthSession sessions;const std::string token(64,'a'),csrf(64,'b'),other(64,'c');
    using D=control::WebAuthDecision;
    EXPECT_EQ(control::webAuthDecision(sessions,"/updates/reboot","POST","","",0,false),D::authentication_required);
    ASSERT_NE(sessions.issue(token,csrf,1),nullptr);
    EXPECT_EQ(control::webAuthDecision(sessions,"/updates/reboot","POST",token,"",2,false),D::csrf_required);
    EXPECT_EQ(control::webAuthDecision(sessions,"/updates/reboot","POST",token,other,2,false),D::csrf_required);
    EXPECT_EQ(control::webAuthDecision(sessions,"/updates/reboot","POST",token,csrf,2,false),D::allow);
    EXPECT_FALSE(control::sameOrigin("http://other.invalid","device","cross-site"));
}
TEST(DeviceRestart, NewImageConfirmsAfterAHealthyMinuteWithoutNeedingTheNetwork) {
    using B=update::BootConfirmation;
    EXPECT_EQ(B::decide(59999,true),B::Action::wait);
    EXPECT_EQ(B::decide(60000,true),B::Action::confirm);   // Wi-Fi/HA state is not an input
    EXPECT_EQ(B::decide(60000,false),B::Action::wait);     // supervisor not (yet) running
    EXPECT_EQ(B::decide(179999,false),B::Action::wait);
    EXPECT_EQ(B::decide(180000,false),B::Action::rollback);
}
TEST(DeviceRestart, ControlledRestartWaitsForUpdatesBootValidationAndBoilerSessions) {
    for(bool busy:{false,true})for(bool pending:{false,true})for(bool session:{false,true})
        EXPECT_EQ(update::controlledRestartAllowed(busy,pending,session),!busy&&!pending&&!session);
}
