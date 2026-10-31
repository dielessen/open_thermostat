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
TEST(DeviceRestart, HealthyImageWithNetworkConfirmsAfterAMinute) {
    using B=update::BootConfirmation;
    EXPECT_EQ(B::decide(59999,true,true),B::Action::wait);
    EXPECT_EQ(B::decide(60000,true,true),B::Action::confirm); // Home Assistant is not an input
    EXPECT_EQ(B::decide(60000,false,true),B::Action::wait);   // supervisor not (yet) running
    EXPECT_EQ(B::decide(179999,false,true),B::Action::wait);
    EXPECT_EQ(B::decide(180000,false,true),B::Action::rollback);
}
TEST(DeviceRestart, ImageWithoutNetworkForTenMinutesRestartsForRollback) {
    using B=update::BootConfirmation;
    for(uint32_t t:{60000u,180000u,300000u,599999u})EXPECT_EQ(B::decide(t,true,false),B::Action::wait)<<t;
    EXPECT_EQ(B::decide(600000,true,false),B::Action::rollback);
    EXPECT_EQ(B::decide(600000,false,false),B::Action::rollback);
}
TEST(DeviceRestart, NetworkProvenOnlyAfterFiveMinutesConfirmsThen) {
    using B=update::BootConfirmation;
    EXPECT_EQ(B::decide(299999,true,false),B::Action::wait);
    EXPECT_EQ(B::decide(300000,true,true),B::Action::confirm);
    EXPECT_EQ(B::decide(600000,true,true),B::Action::confirm); // proof at the deadline still counts
}
TEST(DeviceRestart, WithoutBrokerAnIpHeldFiveMinutesProvesTheNetwork) {
    using B=update::BootConfirmation;
    // An Ethernet install without MQTT that nobody opens, behind a gateway that ignores ping.
    EXPECT_FALSE(B::networkProven(false,false,0));
    EXPECT_FALSE(B::networkProven(false,false,299999));
    EXPECT_TRUE(B::networkProven(false,false,300000));
    EXPECT_EQ(B::decide(310000,true,B::networkProven(false,false,300000)),B::Action::confirm);
    // A configured broker must answer (or the gateway, or a browser): link alone is no proof.
    EXPECT_FALSE(B::networkProven(false,true,600000));
    EXPECT_TRUE(B::networkProven(true,true,0));
    // Network lost after the update (the link broke, so the timer restarted): still rolled back.
    EXPECT_EQ(B::decide(600000,true,B::networkProven(false,false,240000)),B::Action::rollback);
}
TEST(DeviceRestart, FailedConfirmationIsRetriedOncePerMinute) {
    using B=update::BootConfirmation;
    EXPECT_TRUE(B::attemptDue(60000,0));       // first attempt
    EXPECT_FALSE(B::attemptDue(60001,60000));  // otadata write failed: not on every loop pass
    EXPECT_FALSE(B::attemptDue(119999,60000));
    EXPECT_TRUE(B::attemptDue(120000,60000));
}
TEST(DeviceRestart, ControlledRestartWaitsForUpdatesBootValidationAndBoilerSessions) {
    for(bool busy:{false,true})for(bool pending:{false,true})for(bool session:{false,true})
        EXPECT_EQ(update::controlledRestartAllowed(busy,pending,session),!busy&&!pending&&!session);
}
TEST(DeviceRestart, BoilerReleaseHoldWaitsForTheZeroAtMostNinetySeconds) {
    update::BoilerReleaseHold hold;
    EXPECT_TRUE(hold.ready(5000, true)); // nothing held: restart at once
    update::BoilerReleaseHold held;
    EXPECT_FALSE(held.ready(0, false)); // a millis() of 0 still starts the clock
    EXPECT_FALSE(held.ready(89999, false));
    EXPECT_TRUE(held.ready(90000, false));
    update::BoilerReleaseHold delivered;
    EXPECT_FALSE(delivered.ready(4294960000u, false));
    EXPECT_TRUE(delivered.ready(4294960000u + 20000u, true)); // the zero arrived (across the millis() wrap)
    update::BoilerReleaseHold wrap;
    EXPECT_FALSE(wrap.ready(4294960000u, false));
    EXPECT_FALSE(wrap.ready(4294960000u + 80000u, false));
    EXPECT_TRUE(wrap.ready(4294960000u + 90000u, false));
}
