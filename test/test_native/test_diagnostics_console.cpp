#include "diagnostics/SystemLog.h"
#include "diagnostics/DiagnosticsQuery.h"
#include "control/WebAuthSession.h"
#include "control/HttpAccessPolicy.h"
#include "update/ReleasePolicy.h"
#include <gtest/gtest.h>
#include <string>
#include <vector>
using namespace heating::diagnostics;
using heating::control::WebAuthSession;
namespace {
std::string token(char c) { return std::string(64,c); }
std::vector<uint64_t> sequences(const SystemLog& log, uint64_t after = 0) {
    std::vector<uint64_t> out; Record r;
    while (log.next(after,r)) { out.push_back(r.sequence); after = r.sequence; }
    return out;
}
}

TEST(DiagnosticsLog, AttachMovesTheBootstrapRingInOrderAndKeepsCounting) {
    SystemLog log;
    for (int i = 0; i < 40; ++i) log.append(3,"App","boot",i); // 8 overwritten in the 32-record bootstrap ring
    std::vector<Record> storage(SystemLog::RetainedCapacity);
    ASSERT_TRUE(log.attach(storage.data(),storage.size()));
    EXPECT_TRUE(log.attached());
    EXPECT_EQ(log.capacity(),SystemLog::RetainedCapacity);
    auto seen = sequences(log);
    ASSERT_EQ(seen.size(),32u);
    EXPECT_EQ(seen.front(),9u); EXPECT_EQ(seen.back(),40u);
    for (int i = 0; i < 600; ++i) log.append(3,"App","later",100+i);
    const auto stats = log.stats();
    EXPECT_EQ(stats.retained,SystemLog::RetainedCapacity);
    EXPECT_EQ(stats.overwritten,8u+(32u+600u-SystemLog::RetainedCapacity));
    seen = sequences(log);
    ASSERT_EQ(seen.size(),SystemLog::RetainedCapacity);
    EXPECT_EQ(seen.back(),640u); EXPECT_EQ(seen.front(),640u-SystemLog::RetainedCapacity+1);
    for (size_t i = 1; i < seen.size(); ++i) EXPECT_EQ(seen[i],seen[i-1]+1);
}

TEST(DiagnosticsLog, AttachRefusesASmallerSecondOrMissingBuffer) {
    SystemLog log;
    std::vector<Record> small(SystemLog::Capacity), large(64), again(128);
    EXPECT_FALSE(log.attach(nullptr,64));
    EXPECT_FALSE(log.attach(small.data(),small.size()));
    EXPECT_FALSE(log.attached());
    ASSERT_TRUE(log.attach(large.data(),large.size()));
    EXPECT_FALSE(log.attach(again.data(),again.size())); // the history never moves twice
    EXPECT_EQ(log.capacity(),64u);
}

TEST(DiagnosticsLog, CursorSkipsGapsFromSyslogOnlyRecordsAndTailCountsRetainedRecords) {
    SystemLog log; Settings s; s.enabled = true; std::strcpy(s.server.data(),"127.0.0.1"); s.syslogLevel = 5; s.webLevel = 3;
    log.configure(s);
    for (int i = 0; i < 20; ++i) log.append(i % 2 ? 4 : 3,"App","row",i); // debug rows go to syslog only: odd sequences
    const auto web = sequences(log);
    ASSERT_EQ(web.size(),10u);
    EXPECT_EQ(web.front(),1u); EXPECT_EQ(web.back(),19u);
    EXPECT_EQ(sequences(log,4).front(),5u); // a cursor inside a gap finds the next web record
    EXPECT_EQ(sequences(log,log.tailCursor(3)),(std::vector<uint64_t>{15,17,19}));
    EXPECT_EQ(sequences(log,log.tailCursor(100)).size(),10u); // more than retained: everything
    EXPECT_EQ(log.tailCursor(0),0u);
    SystemLog empty; EXPECT_EQ(empty.tailCursor(5),0u);
}

TEST(DiagnosticsLog, PagesAndTailStayBounded) {
    EXPECT_LE(SystemLog::PageSize,32u);
    EXPECT_LE(SystemLog::TailMaximum,SystemLog::RetainedCapacity);
    EXPECT_LE(SystemLog::RetainedCapacity*sizeof(Record),128u*1024u); // PSRAM budget
}

TEST(DiagnosticsQuery, OnlyKnownSectionsEachOnce) {
    EXPECT_EQ(parseSections(""),allSections);
    EXPECT_EQ(parseSections("all"),allSections);
    EXPECT_EQ(parseSections("memory"),sectionMemory);
    EXPECT_EQ(parseSections("mqtt,sessions"),uint8_t(sectionMqtt|sectionSessions));
    EXPECT_EQ(parseSections("memory,tasks,nvs,mqtt,sessions,restarts,log"),allSections);
    for (const char* bad : {"shell","memory,","memory,,tasks",",memory","memory,memory","Memory"," memory",
                            "memory;reboot","all,memory","../memory"})
        EXPECT_FALSE(parseSections(bad).has_value()) << bad;
    EXPECT_FALSE(parseSections(std::string_view("memory\0x",8)).has_value()); // an embedded NUL is not a name
    EXPECT_FALSE(parseSections(std::string(65,'m')).has_value());
}

TEST(DiagnosticsQuery, ActionGateAllowsOncePerInterval) {
    ActionGate gate(10000);
    EXPECT_TRUE(gate.allow(5000));
    EXPECT_FALSE(gate.allow(5001));
    EXPECT_FALSE(gate.allow(14999));
    EXPECT_TRUE(gate.allow(15000));
    EXPECT_TRUE(gate.allow(100)); // a clock that went back never locks the action forever
}

TEST(DiagnosticsSessions, SummariesCarryNoTokensAndMarkTheCaller) {
    WebAuthSession s;
    ASSERT_NE(s.issue(token('0'),token('1'),1000),nullptr);
    ASSERT_NE(s.issue(token('2'),token('3'),5000),nullptr);
    std::vector<WebAuthSession::Summary> rows;
    s.summaries(token('2'),65000,[&](const WebAuthSession::Summary& row){rows.push_back(row);});
    ASSERT_EQ(rows.size(),2u);
    EXPECT_EQ(rows[0].ageMs,64000u); EXPECT_EQ(rows[0].idleMs,64000u); EXPECT_FALSE(rows[0].current);
    EXPECT_EQ(rows[1].ageMs,60000u); EXPECT_TRUE(rows[1].current);
    EXPECT_EQ(rows[1].remainingMs,WebAuthSession::idleTimeoutMs-60000);
    static_assert(sizeof(WebAuthSession::Summary)<=32,"a summary holds numbers only, never a token");
    rows.clear(); s.summaries("not-a-token",65000,[&](const WebAuthSession::Summary& row){rows.push_back(row);});
    for (const auto& row : rows) EXPECT_FALSE(row.current);
}

TEST(DiagnosticsSessions, EndIdleKeepsTheCallerAndRecentSessions) {
    WebAuthSession s;
    for (char c : {'0','2','4','6'}) ASSERT_NE(s.issue(token(c),token(char(c+1)),1000),nullptr);
    const uint64_t later = 1000 + WebAuthSession::evictIdleMs;
    ASSERT_TRUE(s.touch(token('4'),later-1)); // used a moment ago: not idle
    EXPECT_EQ(s.revokeIdle(token('0'),later),2u); // the caller '0' stays although idle
    EXPECT_NE(s.find(token('0'),later),nullptr);
    EXPECT_EQ(s.find(token('2'),later),nullptr);
    EXPECT_NE(s.find(token('4'),later),nullptr);
    EXPECT_EQ(s.find(token('6'),later),nullptr);
    EXPECT_EQ(s.revokeIdle(token('0'),later),0u);
}

TEST(DiagnosticsSessions, EndIdleIsPostOnlyWithCsrfAndBlockedDuringTestsWritesAndUpdates) {
    using namespace heating::control;
    EXPECT_TRUE(allowedHttpMethod("/diagnostics/sessions/end-idle","POST"));
    EXPECT_FALSE(allowedHttpMethod("/diagnostics/sessions/end-idle","GET"));
    EXPECT_TRUE(allowedHttpMethod("/status/diagnostics","GET"));
    EXPECT_FALSE(allowedHttpMethod("/status/diagnostics","POST"));
    WebAuthSession s; ASSERT_NE(s.issue(token('0'),token('1'),1000),nullptr);
    EXPECT_EQ(webAuthDecision(s,"/diagnostics/sessions/end-idle","POST",token('0'),"",1001,false),WebAuthDecision::csrf_required);
    EXPECT_EQ(webAuthDecision(s,"/diagnostics/sessions/end-idle","POST",token('0'),token('1'),1001,false),WebAuthDecision::allow);
    EXPECT_EQ(webAuthDecision(s,"/status/diagnostics","GET","",{},1001,false),WebAuthDecision::authentication_required);
    EXPECT_TRUE(boilerTestMutationBlocked("/diagnostics/sessions/end-idle",true));
    EXPECT_TRUE(boilerSettingsMutationBlocked("/diagnostics/sessions/end-idle",true));
    for (int bits = 0; bits < 8; ++bits)
        EXPECT_EQ(heating::update::mutationBlocked("/diagnostics/sessions/end-idle",bits&1,bits&2,bits&4),bits!=0);
    // The restart action is the existing confirmed /updates/reboot (System menu): refused during a
    // boiler test or settings write here, and by update::requestReboot during an update or unconfirmed image.
    EXPECT_TRUE(allowedHttpMethod("/updates/reboot","POST"));
    EXPECT_FALSE(allowedHttpMethod("/updates/reboot","GET"));
    EXPECT_TRUE(boilerTestMutationBlocked("/updates/reboot",true));
    EXPECT_TRUE(boilerSettingsMutationBlocked("/updates/reboot",true));
}
