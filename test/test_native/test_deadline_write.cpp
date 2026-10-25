#include "control/DeadlineWrite.h"
#include <gtest/gtest.h>
#include <stdexcept>
using heating::control::DeadlineWrite;
namespace {
const uint8_t bytes[]{1,2,3};
TEST(DeadlineWrite, MissingOrUnusedScopeCannotReportCompletedHandoff) {
    DeadlineWrite writer;EXPECT_FALSE(writer.begin({}));int sends=0;
    EXPECT_EQ(writer.write(bytes,3,[&](auto,size_t n){++sends;return n;}),0u);
    EXPECT_FALSE(writer.finish());ASSERT_TRUE(writer.begin([]{return true;}));EXPECT_FALSE(writer.finish());EXPECT_EQ(sends,0);
}
TEST(DeadlineWrite, SingleNonblockingHandoffUsesSameCheckBeforeAndAfter) {
    DeadlineWrite writer;int checks=0,sends=0;ASSERT_TRUE(writer.begin([&]{++checks;return true;}));
    EXPECT_EQ(writer.write(bytes,3,[&](auto data,size_t n){++sends;EXPECT_EQ(data,bytes);return n;}),3u);
    EXPECT_TRUE(writer.finish());EXPECT_EQ(checks,2);EXPECT_EQ(sends,1);
}
TEST(DeadlineWrite, ExpiredOrUnavailableBudgetNeverInvokesSendOrRetries) {
    DeadlineWrite writer;int sends=0;ASSERT_TRUE(writer.begin([]{return false;}));
    for(int i=0;i<3;++i)EXPECT_EQ(writer.write(bytes,3,[&](auto,size_t n){++sends;return n;}),0u);
    EXPECT_FALSE(writer.finish());EXPECT_EQ(sends,0);
}
TEST(DeadlineWrite, PartialAndZeroWritesNeverRetryRemainingBytes) {
    for(size_t count:{0u,1u}){DeadlineWrite writer;int sends=0;ASSERT_TRUE(writer.begin([]{return true;}));
        auto send=[&](auto,size_t){++sends;return count;};EXPECT_EQ(writer.write(bytes,3,send),count);
        EXPECT_EQ(writer.write(bytes,3,send),0u);EXPECT_FALSE(writer.finish());EXPECT_EQ(sends,1);
    }
}
TEST(DeadlineWrite, LateOrClockFaultAfterPossibleIOPreservesUncertainty) {
    for(bool throws:{false,true}){DeadlineWrite writer;int checks=0,sends=0;
        ASSERT_TRUE(writer.begin([&]{if(++checks==2){if(throws)throw std::runtime_error("clock");return false;}return true;}));
        EXPECT_EQ(writer.write(bytes,3,[&](auto,size_t n){++sends;return n;}),3u);
        EXPECT_FALSE(writer.finish());EXPECT_EQ(sends,1);
    }
}
TEST(DeadlineWrite, ThrowingPrecheckOrSendCannotBecomeSuccess) {
    for(bool atSend:{false,true}){DeadlineWrite writer;int sends=0;
        ASSERT_TRUE(writer.begin([&]{if(!atSend)throw std::runtime_error("precheck");return true;}));
        EXPECT_EQ(writer.write(bytes,3,[&](auto,size_t)->size_t{++sends;throw std::runtime_error("IO");}),0u);
        EXPECT_FALSE(writer.finish());EXPECT_EQ(sends,atSend?1:0);
    }
}
TEST(DeadlineWrite, ReentrantBeginFinishAndWriteCannotReplaceOrClearExecutingCheck) {
    for(int kind=0;kind<3;++kind){DeadlineWrite writer;int sends=0;
        ASSERT_TRUE(writer.begin([&]{if(kind==0){EXPECT_FALSE(writer.begin([]{return true;}));}
            else if(kind==1){EXPECT_FALSE(writer.finish());}
            else{EXPECT_EQ(writer.write(bytes,3,[&](auto,size_t n){++sends;return n;}),0u);}return true;}));
        EXPECT_EQ(writer.write(bytes,3,[&](auto,size_t n){++sends;return n;}),0u);
        EXPECT_FALSE(writer.finish());EXPECT_EQ(sends,0);
    }
}
TEST(DeadlineWrite, NullPayloadAndImpossibleCountRetireWriteScope) {
    for(bool null:{false,true}){DeadlineWrite writer;int sends=0;ASSERT_TRUE(writer.begin([]{return true;}));
        EXPECT_EQ(writer.write(null?nullptr:bytes,3,[&](auto,size_t)->size_t{++sends;return 4;}),0u);
        EXPECT_FALSE(writer.finish());EXPECT_EQ(sends,null?0:1);
    }
}
TEST(DeadlineWrite, ExplicitNewScopeIsSeparateFromFailedTransactionAndDoesNotRetryIt) {
    DeadlineWrite writer;int sends=0;ASSERT_TRUE(writer.begin([]{return true;}));
    EXPECT_EQ(writer.write(bytes,3,[&](auto,size_t)->size_t{++sends;return 1;}),1u);EXPECT_FALSE(writer.finish());
    ASSERT_TRUE(writer.begin([]{return true;}));EXPECT_EQ(writer.write(bytes,3,[&](auto,size_t n){++sends;return n;}),3u);
    EXPECT_TRUE(writer.finish());EXPECT_EQ(sends,2); // Parent owner separately denies automatic retry after failure.
}
}
