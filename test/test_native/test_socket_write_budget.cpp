#include "control/SocketWriteBudget.h"
#include <gtest/gtest.h>
#include <array>
#include <algorithm>
#include <vector>
using heating::control::SocketWriteBudget;
namespace {
TEST(SocketWriteBudget, PartialProgressPreservesByteOrderWithoutRenewingBudget) {
    uint64_t now=1000;std::vector<uint8_t> actual;unsigned calls=0,waits=0;
    const std::array<uint8_t,5> bytes{{1,2,3,4,5}};
    const auto result=SocketWriteBudget::write(bytes.data(),bytes.size(),[&]{return now;},
        [&](const uint8_t* data,size_t size)->std::ptrdiff_t {
            ++calls;now+=10;const auto n=std::min(size,size_t{2});actual.insert(actual.end(),data,data+n);return n;
        },[&]{++waits;});
    EXPECT_TRUE(result.complete);EXPECT_EQ(result.written,bytes.size());
    EXPECT_EQ(actual,(std::vector<uint8_t>{1,2,3,4,5}));EXPECT_EQ(calls,3u);EXPECT_EQ(waits,0u);
}
TEST(SocketWriteBudget, BackpressureYieldsOnlyUntilOriginalDeadline) {
    uint64_t now=1000;unsigned calls=0,waits=0;const uint8_t byte=1;
    const auto result=SocketWriteBudget::write(&byte,1,[&]{return now;},
        [&](const uint8_t*,size_t)->std::ptrdiff_t{++calls;return 0;},[&]{++waits;now+=10;});
    EXPECT_FALSE(result.complete);EXPECT_EQ(result.written,0u);EXPECT_EQ(now,1000u+SocketWriteBudget::maximumMs);
    EXPECT_EQ(calls,SocketWriteBudget::maximumMs/10);EXPECT_EQ(waits,SocketWriteBudget::maximumMs/10);
    EXPECT_EQ(SocketWriteBudget::maximumMs,300u);
}
TEST(SocketWriteBudget, PartialWriteCannotResetTheTotalBudget) {
    uint64_t now=1000;unsigned calls=0;const std::array<uint8_t,10> bytes{};
    const auto result=SocketWriteBudget::write(bytes.data(),bytes.size(),[&]{return now;},
        [&](const uint8_t*,size_t)->std::ptrdiff_t{++calls;now+=SocketWriteBudget::maximumMs/4;return 1;},[]{});
    EXPECT_FALSE(result.complete);EXPECT_EQ(result.written,4u);EXPECT_EQ(calls,4u);
}
TEST(SocketWriteBudget, LateFullHandoffIsUncertainAndPreservesActualByteCount) {
    uint64_t now=1000;const uint8_t byte=1;
    const auto result=SocketWriteBudget::write(&byte,1,[&]{return now;},
        [&](const uint8_t*,size_t)->std::ptrdiff_t{now+=SocketWriteBudget::maximumMs;return 1;},[]{ADD_FAILURE();});
    EXPECT_FALSE(result.complete);EXPECT_EQ(result.written,1u);
}
TEST(SocketWriteBudget, BackwardsOrStuckClockCannotCreateAnUnboundedRetryLoop) {
    for(bool backwards:{false,true}) {
        uint64_t now=1000;unsigned calls=0;const uint8_t byte=1;
        const auto result=SocketWriteBudget::write(&byte,1,[&]{return now;},
            [&](const uint8_t*,size_t)->std::ptrdiff_t{++calls;if(backwards)--now;return 0;},[]{});
        EXPECT_FALSE(result.complete);EXPECT_EQ(result.written,0u);
        EXPECT_EQ(calls,backwards?1u:SocketWriteBudget::maximumCalls);
    }
}
TEST(SocketWriteBudget, InvalidSizeOrFatalSendNeverRetriesOrClaimsCompletion) {
    for(int count:{-1,2}) {
        unsigned calls=0;const uint8_t byte=1;
        const auto result=SocketWriteBudget::write(&byte,1,[]{return uint64_t{0};},
            [&](const uint8_t*,size_t)->std::ptrdiff_t{++calls;return count;},[]{ADD_FAILURE();});
        EXPECT_FALSE(result.complete);EXPECT_EQ(result.written,0u);EXPECT_EQ(calls,1u);
    }
    const auto invalid=SocketWriteBudget::write(nullptr,1,[]{ADD_FAILURE();return uint64_t{0};},
        [](const uint8_t*,size_t)->std::ptrdiff_t{ADD_FAILURE();return 0;},[]{ADD_FAILURE();});
    EXPECT_FALSE(invalid.complete);EXPECT_EQ(invalid.written,0u);
}
}
