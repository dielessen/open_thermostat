#include "control/HttpAccessPolicy.h"
#include "control/NetworkBootPlan.h"
#include <gtest/gtest.h>
using namespace heating::control;
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
