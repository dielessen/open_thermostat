#include "control/WebAuthSession.h"
#include "control/HttpAccessPolicy.h"
#include "control/CaptivePortalPolicy.h"
#include <gtest/gtest.h>
#include <string>
using namespace heating::control;
namespace { std::string token(char c) { return std::string(64,c); } }
TEST(WebAuth, MobileAndDesktopSessionsDoNotInvalidateEachOther) {
    WebAuthSession s;
    ASSERT_NE(s.issue(token('a'),token('b'),100),nullptr);
    ASSERT_NE(s.issue(token('c'),token('d'),101),nullptr);
    for(uint64_t now:{101,200,10000}) {
        EXPECT_NE(s.find(token('a'),now),nullptr); EXPECT_NE(s.find(token('c'),now),nullptr);
        EXPECT_TRUE(s.csrf(token('a'),token('b'),now)); EXPECT_TRUE(s.csrf(token('c'),token('d'),now));
        EXPECT_FALSE(s.csrf(token('a'),token('d'),now)); EXPECT_FALSE(s.csrf(token('c'),token('b'),now));
    }
}
TEST(WebAuth, ReadingDoesNotExtendAbsoluteLifetimeOrReviveExpiredSession) {
    WebAuthSession s; ASSERT_NE(s.issue(token('a'),token('b'),100),nullptr);
    EXPECT_NE(s.find(token('a'),100),nullptr); EXPECT_NE(s.find(token('a'),99+WebAuthSession::lifetimeMs),nullptr);
    EXPECT_EQ(s.find(token('a'),100+WebAuthSession::lifetimeMs),nullptr);
    EXPECT_FALSE(s.csrf(token('a'),token('b'),100+WebAuthSession::lifetimeMs));
    EXPECT_EQ(s.find(token('a'),99),nullptr);
}
TEST(WebAuth, RebootDoesNotRestoreAnyCookieAndOverflowCannotIssue) {
    WebAuthSession oldBoot; ASSERT_NE(oldBoot.issue(token('a'),token('b'),100),nullptr);
    WebAuthSession newBoot; EXPECT_EQ(newBoot.find(token('a'),100),nullptr);
    EXPECT_EQ(newBoot.issue(token('c'),token('d'),UINT64_MAX),nullptr);
}
TEST(WebAuth, FullCapacityNeverEvictsAnotherBrowserAndOwnReloginRotates) {
    WebAuthSession s;
    for(int i=0;i<4;++i) ASSERT_NE(s.issue(token('0'+i*2),token('1'+i*2),100),nullptr);
    EXPECT_EQ(s.issue(token('8'),token('9'),101),nullptr);
    EXPECT_NE(s.find(token('0'),101),nullptr); EXPECT_NE(s.find(token('6'),101),nullptr);
    ASSERT_NE(s.issue(token('8'),token('9'),101,token('0')),nullptr);
    EXPECT_EQ(s.find(token('0'),101),nullptr); EXPECT_NE(s.find(token('8'),101),nullptr);
    EXPECT_NE(s.find(token('6'),101),nullptr);
}
TEST(WebAuth, LogoutRevokesOnlyOwnCookieAndProof) {
    WebAuthSession s; ASSERT_NE(s.issue(token('a'),token('b'),100),nullptr); ASSERT_NE(s.issue(token('c'),token('d'),100),nullptr);
    s.revoke(token('a')); EXPECT_EQ(s.find(token('a'),101),nullptr); EXPECT_NE(s.find(token('c'),101),nullptr);
    EXPECT_FALSE(s.csrf(token('a'),token('b'),101));
    EXPECT_NE(s.issue(token('e'),token('f'),101),nullptr);
}
TEST(WebAuth, ForgedOrMalformedTokensCannotAuthenticate) {
    WebAuthSession s; ASSERT_NE(s.issue(token('a'),token('b'),100),nullptr);
    for(const auto &t:{std::string(),std::string(63,'a'),std::string(65,'a'),token('A'),token('z'),token('b')}) {
        EXPECT_EQ(s.find(t,101),nullptr); EXPECT_FALSE(s.csrf(t,token('b'),101));
    }
    EXPECT_FALSE(s.csrf(token('a'),"",101)); EXPECT_FALSE(s.csrf(token('a'),token('a'),101));
    EXPECT_EQ(s.issue("bad",token('d'),101),nullptr);
    EXPECT_EQ(s.issue(token('e'),token('e'),101),nullptr);
    EXPECT_EQ(s.issue(token('e'),token('a'),101),nullptr);
}
TEST(WebAuth, CookieParsingRejectsDuplicateMalformedAndOversizedHeaders) {
    const auto a=token('a'),b=token('b');
    EXPECT_EQ(WebAuthSession::cookieToken("OTSESSION="+a),a);
    EXPECT_EQ(WebAuthSession::cookieToken("other=ok; OTSESSION="+a+"; preference=dark"),a);
    for(const auto &h:{"OTSESSION="+a+"; OTSESSION="+b,"OTSESSION="+a+"; OTSESSION="+a,
        std::string("OTSESSION=short"),std::string("OTSESSION"),"OTSESSION="+a+"\r\nX=y",std::string(2049,'x')})
        EXPECT_TRUE(WebAuthSession::cookieToken(h).empty());
    EXPECT_TRUE(WebAuthSession::cookieToken("NOTSESSION="+a).empty());
}
TEST(WebAuth, LoginCooldownDoesNotDestroyValidSessions) {
    WebAuthSession s; ASSERT_NE(s.issue(token('a'),token('b'),1),nullptr);
    for(int i=0;i<5;++i) { EXPECT_TRUE(s.loginAllowed(100+i)); s.loginFailed(100+i); }
    EXPECT_FALSE(s.loginAllowed(105)); EXPECT_FALSE(s.loginAllowed(30099));
    EXPECT_NE(s.find(token('a'),105),nullptr); EXPECT_TRUE(s.loginAllowed(30100));
    s.loginFailed(30100); EXPECT_TRUE(s.loginAllowed(30101)); s.loginSucceeded(); EXPECT_TRUE(s.loginAllowed(30101));
}
TEST(WebAuth, PublicResourcesAreExactAndCannotExposeControlOrRecovery) {
    for(auto p:{"/login","/login.js","/auth-client.js","/auth/login"}) EXPECT_TRUE(publicAuthResource(p));
    for(auto p:{"/auth/session","/auth/logout","/login.html","/login/../config/device","/status","/config/device","/ota","/otafs","/recovery","/setup/network"}) EXPECT_FALSE(publicAuthResource(p));
    EXPECT_TRUE(allowedHttpMethod("/auth/login","POST")); EXPECT_FALSE(allowedHttpMethod("/auth/login","GET"));
    EXPECT_TRUE(allowedHttpMethod("/auth/logout","POST")); EXPECT_FALSE(allowedHttpMethod("/auth/logout","GET"));
    EXPECT_FALSE(sameOrigin("http://foreign.test","device","cross-site"));
}
TEST(WebAuth, APSetupRemainsLocalInterfaceScopedNotCookieBypass) {
    EXPECT_EQ(portalAccess(true,true,"10.10.10.1","10.10.10.1","/setup/network","POST"),PortalAccess::Setup);
    EXPECT_EQ(portalAccess(true,false,"10.10.10.1","10.10.10.1","/setup/network","POST"),PortalAccess::Authenticated);
    EXPECT_EQ(portalAccess(true,true,"10.10.10.1","10.10.10.1","/config/device","POST"),PortalAccess::Authenticated);
    EXPECT_TRUE(legacyControlWrite("/config/rooms","POST"));
}

TEST(WebAuth, ActualRouteGateRejectsAnonymousApiAndAllCookieOnlyMutations) {
    WebAuthSession sessions;
    for(auto p:{"/status","/status/version","/status/ems","/config/device","/rooms.html","/auth/session"})
        EXPECT_EQ(webAuthDecision(sessions,p,"GET","","",100,false),WebAuthDecision::authentication_required);
    for(auto p:{"/","/index.html","/recovery","/setup"})
        EXPECT_EQ(webAuthDecision(sessions,p,"GET","","",100,false),WebAuthDecision::redirect_login);
    ASSERT_NE(sessions.issue(token('a'),token('b'),100),nullptr);
    for(auto p:{"/config/device","/config/reboot","/setup/network","/ota","/otafs","/updates/install","/auth/logout"}) {
        EXPECT_EQ(webAuthDecision(sessions,p,"POST","","",101,false),WebAuthDecision::authentication_required);
        EXPECT_EQ(webAuthDecision(sessions,p,"POST",token('a'),"",101,false),WebAuthDecision::csrf_required);
        EXPECT_EQ(webAuthDecision(sessions,p,"POST",token('a'),token('c'),101,false),WebAuthDecision::csrf_required);
        EXPECT_EQ(webAuthDecision(sessions,p,"POST",token('a'),token('b'),101,false),WebAuthDecision::allow);
    }
    EXPECT_EQ(webAuthDecision(sessions,"/config/programs/test","DELETE",token('a'),"",101,false),WebAuthDecision::csrf_required);
    EXPECT_EQ(webAuthDecision(sessions,"/auth/session","GET",token('a'),"",101,false),WebAuthDecision::allow);
    EXPECT_EQ(webAuthDecision(sessions,"/setup/network","POST","","",101,true),WebAuthDecision::allow);
}
