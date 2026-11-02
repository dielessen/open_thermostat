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
TEST(HttpAccess, BluetoothDiscoveryRequiresAnExplicitProtectedPost) {
    EXPECT_FALSE(allowedHttpMethod("/config/bluetooth/scan","GET"));
    EXPECT_TRUE(allowedHttpMethod("/config/bluetooth/scan","POST"));
    EXPECT_FALSE(allowedHttpMethod("/config/bluetooth/scan","DELETE"));
    EXPECT_TRUE(allowedHttpMethod("/config/bluetooth","GET"));
    EXPECT_TRUE(allowedHttpMethod("/config/bluetooth","POST"));
    EXPECT_FALSE(allowedHttpMethod("/bluetooth/status","POST"));
    EXPECT_TRUE(boilerTestMutationBlocked("/config/bluetooth",true));
    EXPECT_TRUE(boilerTestMutationBlocked("/config/bluetooth/scan",true));
    EXPECT_EQ(portalAccess(true,true,"10.10.10.1","10.10.10.1","/config/bluetooth","POST"),PortalAccess::Authenticated);
}
TEST(HttpAccess, HostHeaderMustNameThisDeviceAgainstDnsRebinding) {
    // The device IP, the setup AP IP and the hostname (with .local or a home-router suffix), optional port.
    for(auto host:{"192.168.1.40","192.168.1.40:80","192.168.4.1","openthermostat-ab12","OpenThermostat-AB12.local",
                   "openthermostat-ab12.local.","openthermostat-ab12.fritz.box","openthermostat-ab12.home.arpa:80",
                   "openthermostat-ab12.lan"})
        EXPECT_TRUE(knownHostHeader(host,"192.168.1.40","192.168.4.1","openthermostat-ab12",80))<<host;
    EXPECT_TRUE(knownHostHeader("192.168.1.40:8080","192.168.1.40","0.0.0.0","heating",8080));
    // A rebinding page names its own site; ports, IPs and look-alike names that are not this device fail.
    for(auto host:{"","evil.example","evil.example:80","192.168.1.40:8080","192.168.1.41","192.168.1.40:","192.168.1.40:abc",
                   "openthermostat-ab12.evil.example","openthermostat-ab12.local.evil.example","xopenthermostat-ab12",
                   "openthermostat-ab12x.local","[::1]","[fe80::1]:80",".","0.0.0.0","localhost","127.0.0.1",
                   "192.168.1.40:000080000"})
        EXPECT_FALSE(knownHostHeader(host,"192.168.1.40","192.168.4.1","openthermostat-ab12",80))<<host;
    // Without a running access point (0.0.0.0) or a hostname only the device IP counts.
    EXPECT_FALSE(knownHostHeader("0.0.0.0","192.168.1.40","0.0.0.0","",80));
    EXPECT_FALSE(knownHostHeader(".local","192.168.1.40","0.0.0.0","",80));
    EXPECT_TRUE(knownHostHeader("192.168.1.40","192.168.1.40","0.0.0.0","",80));
}
