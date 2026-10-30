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
    EXPECT_NE(s.find(token('a'),100),nullptr);
    for(uint64_t now=100+WebAuthSession::idleTimeoutMs/2;now<100+WebAuthSession::lifetimeMs;now+=WebAuthSession::idleTimeoutMs/2)
        ASSERT_TRUE(s.touch(token('a'),now));
    EXPECT_NE(s.find(token('a'),99+WebAuthSession::lifetimeMs),nullptr);
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
    for(auto p:{"/login","/login.js","/auth-client.js","/auth/login","/ui-language.js","/ui-messages.js"}) EXPECT_TRUE(publicAuthResource(p));
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

TEST(WebAuth, SettingsReadbackIsOpaqueStableAndDoesNotReplaceAuthenticationOrCsrf) {
    WebAuthSession sessions;
    ASSERT_NE(sessions.issue(token('a'),token('b'),100),nullptr);
    const auto tag=sessions.settingsReadback(token('a'),token('c'),token('d'),101);
    EXPECT_EQ(tag,token('d')); EXPECT_NE(tag,token('c'));
    EXPECT_EQ(sessions.settingsReadback(token('a'),token('c'),token('e'),102),tag);
    EXPECT_TRUE(sessions.settingsReadbackMatches(token('a'),"\""+token('d')+"\"",token('c'),103));
    EXPECT_FALSE(sessions.csrf(token('a'),token('d'),103));
    EXPECT_EQ(sessions.find(token('d'),103),nullptr);
    EXPECT_FALSE(sessions.settingsReadbackMatches(token('d'),"\""+token('d')+"\"",token('c'),103));
}

TEST(WebAuth, SettingsReadbackRejectsEveryPersistedChangeAndRotatesOnlyThatSession) {
    WebAuthSession sessions;
    ASSERT_NE(sessions.issue(token('a'),token('b'),100),nullptr);
    ASSERT_NE(sessions.issue(token('e'),token('f'),100),nullptr);
    ASSERT_EQ(sessions.settingsReadback(token('a'),token('c'),token('d'),101),token('d'));
    ASSERT_EQ(sessions.settingsReadback(token('e'),token('c'),token('1'),101),token('1'));
    // The caller hashes complete raw settings: even a redacted secret rotation
    // changes this hash. No old tag may approve it before a fresh read.
    EXPECT_FALSE(sessions.settingsReadbackMatches(token('a'),"\""+token('d')+"\"",token('2'),102));
    EXPECT_FALSE(sessions.settingsReadbackMatches(token('e'),"\""+token('1')+"\"",token('2'),102));
    ASSERT_EQ(sessions.settingsReadback(token('a'),token('2'),token('3'),103),token('3'));
    EXPECT_FALSE(sessions.settingsReadbackMatches(token('a'),"\""+token('d')+"\"",token('2'),104));
    EXPECT_TRUE(sessions.settingsReadbackMatches(token('a'),"\""+token('3')+"\"",token('2'),104));
    EXPECT_FALSE(sessions.settingsReadbackMatches(token('e'),"\""+token('3')+"\"",token('2'),104));
    EXPECT_TRUE(sessions.settingsReadbackMatches(token('e'),"\""+token('1')+"\"",token('c'),104));
}

TEST(WebAuth, SettingsReadbackRejectsMissingMalformedWildcardAndWeakOrCombinedTags) {
    WebAuthSession sessions; ASSERT_NE(sessions.issue(token('a'),token('b'),100),nullptr);
    EXPECT_FALSE(sessions.settingsReadbackMatches(token('a'),"\""+token('d')+"\"",token('c'),101));
    ASSERT_EQ(sessions.settingsReadback(token('a'),token('c'),token('d'),101),token('d'));
    for(const auto &tag:{std::string(),std::string("*"),token('d'),"W/\""+token('d')+"\"",
            "\""+token('d')+"\", \""+token('d')+"\"","\""+token('D')+"\""})
        EXPECT_FALSE(sessions.settingsReadbackMatches(token('a'),tag,token('c'),102));
    for(const auto &nonce:{std::string(),token('z'),token('a'),token('b')})
        EXPECT_TRUE(sessions.settingsReadback(token('a'),token('c'),nonce,102).empty());
    EXPECT_TRUE(sessions.settingsReadback(token('0'),token('c'),token('e'),102).empty());
}

TEST(WebAuth, SettingsReadbackCannotSurviveLogoutReloginExpiryOrReboot) {
    WebAuthSession sessions; ASSERT_NE(sessions.issue(token('a'),token('b'),100),nullptr);
    ASSERT_EQ(sessions.settingsReadback(token('a'),token('c'),token('d'),101),token('d'));
    const auto quoted="\""+token('d')+"\"";
    EXPECT_FALSE(sessions.settingsReadbackMatches(token('a'),quoted,token('c'),99));
    EXPECT_FALSE(sessions.settingsReadbackMatches(token('a'),quoted,token('c'),100+WebAuthSession::lifetimeMs));
    WebAuthSession boot; EXPECT_FALSE(boot.settingsReadbackMatches(token('a'),quoted,token('c'),102));
    sessions.revoke(token('a')); EXPECT_FALSE(sessions.settingsReadbackMatches(token('a'),quoted,token('c'),102));
    ASSERT_NE(sessions.issue(token('e'),token('f'),103),nullptr);
    EXPECT_FALSE(sessions.settingsReadbackMatches(token('e'),quoted,token('c'),104));
}

TEST(WebAuth, SettingsReadbackTagCannotBecomeANewLoginCookieOrCsrfProof) {
    WebAuthSession sessions; ASSERT_NE(sessions.issue(token('a'),token('b'),100),nullptr);
    ASSERT_EQ(sessions.settingsReadback(token('a'),token('c'),token('d'),101),token('d'));
    EXPECT_EQ(sessions.issue(token('d'),token('e'),102),nullptr);
    EXPECT_EQ(sessions.issue(token('e'),token('d'),102),nullptr);
    EXPECT_EQ(sessions.issue(token('d'),token('e'),102,token('a')),nullptr);
    EXPECT_NE(sessions.find(token('a'),103),nullptr);
    EXPECT_FALSE(sessions.csrf(token('a'),token('d'),103));
}

TEST(WebAuth, SeparateSettingsStoresKeepIndependentOpaqueReadbackFences) {
    WebAuthSession sessions;using Scope=WebAuthSession::SettingsScope;
    ASSERT_NE(sessions.issue(token('a'),token('b'),100),nullptr);
    ASSERT_EQ(sessions.settingsReadback(token('a'),token('c'),token('d'),101),token('d'));
    ASSERT_EQ(sessions.settingsReadback(token('a'),token('e'),token('f'),102,Scope::bluetooth),token('f'));
    EXPECT_TRUE(sessions.settingsReadbackMatches(token('a'),'"'+token('d')+'"',token('c'),103));
    EXPECT_TRUE(sessions.settingsReadbackMatches(token('a'),'"'+token('f')+'"',token('e'),103,Scope::bluetooth));
    EXPECT_FALSE(sessions.settingsReadbackMatches(token('a'),'"'+token('f')+'"',token('e'),103));
    EXPECT_FALSE(sessions.settingsReadbackMatches(token('a'),'"'+token('d')+'"',token('c'),103,Scope::bluetooth));
    EXPECT_EQ(sessions.settingsReadback(token('a'),token('1'),token('2'),104),token('2'));
    EXPECT_TRUE(sessions.settingsReadbackMatches(token('a'),'"'+token('f')+'"',token('e'),105,Scope::bluetooth));
    EXPECT_FALSE(sessions.settingsReadbackMatches(token('a'),'"'+token('f')+'"',token('3'),105,Scope::bluetooth));
}
TEST(WebAuth, ReadbackScopesCannotAliasTokensProofsOrEachOther) {
    WebAuthSession sessions;using Scope=WebAuthSession::SettingsScope;
    ASSERT_NE(sessions.issue(token('a'),token('b'),100),nullptr);
    ASSERT_EQ(sessions.settingsReadback(token('a'),token('c'),token('d'),101),token('d'));
    EXPECT_TRUE(sessions.settingsReadback(token('a'),token('e'),token('d'),102,Scope::bluetooth).empty());
    EXPECT_TRUE(sessions.settingsReadback(token('a'),token('e'),token('a'),102,Scope::bluetooth).empty());
    EXPECT_TRUE(sessions.settingsReadback(token('a'),token('e'),token('b'),102,Scope::bluetooth).empty());
    ASSERT_EQ(sessions.settingsReadback(token('a'),token('e'),token('f'),102,Scope::bluetooth),token('f'));
    EXPECT_EQ(sessions.issue(token('f'),token('1'),103),nullptr);
    EXPECT_EQ(sessions.issue(token('1'),token('f'),103),nullptr);
    EXPECT_TRUE(sessions.settingsReadback(token('a'),token('1'),token('f'),104).empty());
    EXPECT_TRUE(sessions.settingsReadback(token('a'),token('1'),token('2'),104,static_cast<Scope>(255)).empty());
    EXPECT_FALSE(sessions.settingsReadbackMatches(token('a'),'"'+token('f')+'"',token('e'),104,static_cast<Scope>(255)));
}

TEST(WebAuth, ExplicitCredentialRecoveryReplacesAllSessionsAndTheirSettingsFences) {
    WebAuthSession s;
    for(int i=0;i<4;++i) ASSERT_NE(s.issue(token('0'+i*2),token('1'+i*2),100),nullptr);
    ASSERT_FALSE(s.settingsReadback(token('0'),token('c'),token('d'),101).empty());
    ASSERT_NE(s.issue(token('8'),token('9'),102,{},true),nullptr);
    for(int i=0;i<4;++i) EXPECT_EQ(s.find(token('0'+i*2),103),nullptr);
    EXPECT_FALSE(s.settingsReadbackMatches(token('8'),"\""+token('d')+"\"",token('c'),103));
    EXPECT_NE(s.find(token('8'),103),nullptr);
    EXPECT_TRUE(s.csrf(token('8'),token('9'),103));
    EXPECT_NE(s.issue(token('a'),token('b'),104),nullptr);
}
TEST(WebAuth, RecoveryRejectsInvalidEntropyAliasesAndClockWithoutRevokingSessions) {
    WebAuthSession s;ASSERT_NE(s.issue(token('a'),token('b'),100),nullptr);
    EXPECT_EQ(s.issue("bad",token('d'),101,{},true),nullptr);
    EXPECT_EQ(s.issue(token('c'),token('c'),101,{},true),nullptr);
    EXPECT_EQ(s.issue(token('a'),token('d'),101,{},true),nullptr);
    EXPECT_EQ(s.issue(token('c'),token('b'),101,{},true),nullptr);
    EXPECT_EQ(s.issue(token('c'),token('d'),UINT64_MAX,{},true),nullptr);
    EXPECT_NE(s.find(token('a'),102),nullptr);EXPECT_TRUE(s.csrf(token('a'),token('b'),102));
}

TEST(WebAuth, IdleSessionExpiresAtBoundaryAndCannotBeRevivedByLookupsOrRequests) {
    WebAuthSession s;ASSERT_NE(s.issue(token('a'),token('b'),100),nullptr);
    const auto deadline=100+WebAuthSession::idleTimeoutMs;
    EXPECT_NE(s.find(token('a'),deadline-1),nullptr);
    EXPECT_TRUE(s.csrf(token('a'),token('b'),deadline-1));
    EXPECT_EQ(s.remainingMs(token('a'),deadline-1),1u);
    EXPECT_EQ(s.find(token('a'),deadline),nullptr);
    EXPECT_FALSE(s.touch(token('a'),deadline));
    EXPECT_FALSE(s.csrf(token('a'),token('b'),deadline));
    EXPECT_EQ(s.remainingMs(token('a'),deadline),0u);
}
TEST(WebAuth, AuthenticatedActivityOnlyRenewsItsOwnSessionWithoutMovingHardDeadline) {
    WebAuthSession s;ASSERT_NE(s.issue(token('a'),token('b'),100),nullptr);
    ASSERT_NE(s.issue(token('c'),token('d'),100),nullptr);
    const auto activeAt=100+WebAuthSession::idleTimeoutMs/2;
    ASSERT_TRUE(s.touch(token('a'),activeAt));
    EXPECT_NE(s.find(token('a'),100+WebAuthSession::idleTimeoutMs),nullptr);
    EXPECT_EQ(s.find(token('c'),100+WebAuthSession::idleTimeoutMs),nullptr);
    EXPECT_EQ(s.remainingMs(token('a'),activeAt),WebAuthSession::idleTimeoutMs);
    EXPECT_EQ(s.find(token('a'),activeAt-1),nullptr);
    EXPECT_FALSE(s.touch(token('a'),activeAt-1));
    EXPECT_EQ(s.find(token('a'),activeAt+WebAuthSession::idleTimeoutMs),nullptr);
}
TEST(WebAuth, IdleSlotsAreReusedWithoutEvictingTheActiveBrowser) {
    WebAuthSession s;for(int i=0;i<4;++i)ASSERT_NE(s.issue(token('0'+i*2),token('1'+i*2),100),nullptr);
    ASSERT_TRUE(s.touch(token('0'),100+WebAuthSession::idleTimeoutMs/2));
    ASSERT_NE(s.issue(token('8'),token('9'),100+WebAuthSession::idleTimeoutMs),nullptr);
    EXPECT_NE(s.find(token('0'),100+WebAuthSession::idleTimeoutMs),nullptr);
    EXPECT_NE(s.find(token('8'),100+WebAuthSession::idleTimeoutMs),nullptr);
    EXPECT_EQ(s.find(token('2'),100+WebAuthSession::idleTimeoutMs),nullptr);
}
TEST(WebAuth, RejectedRequestsCannotRefreshAStoredSession) {
    WebAuthSession s;ASSERT_NE(s.issue(token('a'),token('b'),100),nullptr);
    const auto at=100+WebAuthSession::idleTimeoutMs-1;
    EXPECT_EQ(webAuthDecision(s,"/config/device","POST",token('a'),"wrong",at,false),WebAuthDecision::csrf_required);
    EXPECT_EQ(webAuthDecision(s,"/status","GET",token('c'),"",at,false),WebAuthDecision::authentication_required);
    EXPECT_EQ(s.find(token('a'),at+1),nullptr);
}
TEST(WebAuth, FullTableEvictsOnlyTheLeastRecentlyUsedIdleSessionWhenAllowed) {
    // Live on 30 Oct 2026: four slots held by polling pages and closed tabs,
    // Home Assistant got session_capacity on every sign-in.
    WebAuthSession s;
    for(int i=0;i<4;++i) ASSERT_NE(s.issue(token('0'+i*2),token('1'+i*2),100+i),nullptr);
    const uint64_t later=200+WebAuthSession::evictIdleMs;
    ASSERT_TRUE(s.touch(token('0'),later-1000)); ASSERT_TRUE(s.touch(token('4'),later-5000)); // polling pages
    // Not allowed (boiler test, settings write or update active): no eviction.
    EXPECT_EQ(s.issue(token('8'),token('9'),later,{},false,false),nullptr);
    // Allowed: the oldest idle one ('2', last seen at 101) gives way; the
    // other idle one ('6', 103) and the two active pages stay.
    ASSERT_NE(s.issue(token('8'),token('9'),later,{},false,true),nullptr);
    EXPECT_EQ(s.find(token('2'),later),nullptr);
    for(char c:{'0','4','6','8'}) EXPECT_NE(s.find(token(c),later),nullptr) << c;
    // Next: '6' is the only idle one left.
    ASSERT_NE(s.issue(token('a'),token('b'),later+1,{},false,true),nullptr);
    EXPECT_EQ(s.find(token('6'),later+1),nullptr);
    // Every remaining session active within evictIdleMs: refused, nobody evicted.
    EXPECT_EQ(s.issue(token('c'),token('d'),later+2,{},false,true),nullptr);
    for(char c:{'0','4','8','a'}) EXPECT_NE(s.find(token(c),later+2),nullptr) << c;
    // Explicit recovery still revokes all and admits the caller.
    ASSERT_NE(s.issue(token('c'),token('d'),later+3,{},true),nullptr);
    EXPECT_EQ(s.find(token('0'),later+3),nullptr); EXPECT_NE(s.find(token('c'),later+3),nullptr);
}
