#include "control/HttpAccessPolicy.h"
#include "control/NetworkBootPlan.h"
#include "control/CaptivePortalPolicy.h"
#include <gtest/gtest.h>
using namespace heating::control;
TEST(CaptivePortal, OperatingSystemProbesAndArbitraryHttpHostsRedirectOnlyOnAPInterface) {
    for(auto path:{"/generate_204","/gen_204","/hotspot-detect.html","/library/test/success.html","/success.html","/ncsi.txt","/connecttest.txt","/redirect","/fwlink","/canonical.html","/"}) {
        EXPECT_EQ(portalAccess(true,true,"10.10.10.1","10.10.10.1",path,"GET"),PortalAccess::Redirect);
        EXPECT_EQ(portalAccess(true,false,"10.10.10.1","10.10.10.1",path,"GET"),PortalAccess::Authenticated);
        EXPECT_EQ(portalAccess(false,true,"10.10.10.1","10.10.10.1",path,"GET"),PortalAccess::Authenticated);
    }
    EXPECT_EQ(portalAccess(true,true,"example.com","10.10.10.1","/any/path","GET"),PortalAccess::Redirect);
}
TEST(CaptivePortal, OnlyExplicitSetupRoutesOnCanonicalAPAreLoginExceptions) {
    for(auto path:{"/setup","/setup.html","/setup.js","/setup/status","/setup/scan","/ui-language.js","/ui-messages.js"})
        EXPECT_EQ(portalAccess(true,true,"10.10.10.1","10.10.10.1",path,"GET"),PortalAccess::Setup);
    for(auto path:{"/setup/scan","/setup/network","/setup/finish"}) {
        EXPECT_EQ(portalAccess(true,true,"10.10.10.1","10.10.10.1",path,"POST"),PortalAccess::Setup);
        EXPECT_EQ(portalAccess(true,false,"10.10.10.1","10.10.10.1",path,"POST"),PortalAccess::Authenticated);
        EXPECT_EQ(portalAccess(true,true,"evil.test","10.10.10.1",path,"POST"),PortalAccess::Authenticated);
    }
    for(auto path:{"/setup/reenter","/config/device","/config/reboot","/ota","/otafs","/config/rooms","/setup/network/evil"})
        for(auto method:{"GET","POST","DELETE"}) EXPECT_EQ(portalAccess(true,true,"10.10.10.1","10.10.10.1",path,method),PortalAccess::Authenticated);
    EXPECT_FALSE(sameOrigin("http://evil.test","10.10.10.1","cross-site"));
    EXPECT_FALSE(allowedHttpMethod("/setup/finish","GET"));
}
TEST(HttpAccess, ReadRoutesCannotInvokeRebootUploadOrMutationWithGet) {
    for(auto route:{"/config/reboot","/ota","/otafs","/setup/network","/setup/reenter","/config/temporary"}) EXPECT_FALSE(allowedHttpMethod(route,"GET"));
    EXPECT_TRUE(allowedHttpMethod("/config/reboot","POST"));
    EXPECT_TRUE(allowedHttpMethod("/config/wifi","POST"));
    EXPECT_FALSE(allowedHttpMethod("/status","POST"));
    EXPECT_FALSE(allowedHttpMethod("/index.html","DELETE"));
    EXPECT_FALSE(allowedHttpMethod("/config/wifi","DELETE"));
}
TEST(HttpAccess, ModernModeCannotHaveASecondLegacyRoomWriter) {
    EXPECT_TRUE(legacyControlWrite("/config/temporary","POST"));
    EXPECT_TRUE(legacyControlWrite("/config/programs/test","DELETE"));
    EXPECT_FALSE(legacyControlWrite("/config/programs/test","GET"));
    EXPECT_FALSE(legacyControlWrite("/config/device","POST"));
}
TEST(HttpAccess, CrossOriginAndNullOriginRejectedButAuthenticatedCliHasNoOrigin) {
    EXPECT_FALSE(sameOrigin("http://evil.test","10.10.10.1","cross-site"));
    EXPECT_FALSE(sameOrigin("null","10.10.10.1",""));
    EXPECT_FALSE(sameOrigin("http://10.10.10.1.evil.test","10.10.10.1",""));
    EXPECT_TRUE(sameOrigin("http://10.10.10.1","10.10.10.1","same-origin"));
    EXPECT_TRUE(sameOrigin("","10.10.10.1",""));
}
TEST(HttpAccess, StaticFallbackCannotTraverseToConfigurationOrDecodeAnAlias) {
    EXPECT_TRUE(safeStaticPath("/deps/chart.umd.js.gz"));
    for(auto path:{"/../cfg/cfgnetwork.json","/%2e%2e/cfg/cfgnetwork.json","/..%2fcfg/config.json","/a\\b","//../cfg"}) EXPECT_FALSE(safeStaticPath(path));
}
TEST(NetworkBoot, FirstBootAndExplicitRecoveryNeverStartEthernetClockAlongsideWifi) {
    for(bool configured:{false,true}) for(bool credentials:{false,true}) for(bool recovery:{false,true}) {
        const auto plan=networkBootPlan(configured,credentials,recovery);
        EXPECT_NE(plan.wifi,plan.ethernet);
        EXPECT_FALSE(plan.setupAp&&plan.ethernet);
        EXPECT_EQ(plan.setupAp,recovery||(!configured&&!credentials));
        if(recovery) EXPECT_TRUE(plan.wifi);
        if(configured&&!recovery) { EXPECT_TRUE(plan.ethernet); EXPECT_FALSE(plan.setupAp); }
    }
}
