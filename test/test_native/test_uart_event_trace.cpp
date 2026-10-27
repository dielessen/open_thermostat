#include "EMS/UartEventTrace.h"
#include "EMS/EmsEchoRxDebt.h"
#include <gtest/gtest.h>
#include <sstream>
using heating::ems::EmsEchoRxDebt;
using heating::ems::UartEventTrace;
using Kind=UartEventTrace::Kind;

static std::string json(const UartEventTrace::Snapshot& s){std::ostringstream o;s.writeJSON(o);return o.str();}

TEST(UartEventTrace, NoFaultIsNull){EXPECT_EQ(json({}),"null");}

TEST(UartEventTrace, FrozenCopyIsOldestFirstAndUnaffectedByLaterEvents){
    UartEventTrace t;t.record(Kind::writeStart,6,10);t.record(Kind::data,1,20);t.record(Kind::brk,0,30);
    const auto s=t.freeze({1,1,true,true,2},40);t.record(Kind::data,9,50);
    EXPECT_EQ(json(s),"{\"frozen_at_us\":40,\"echo_consumed\":1,\"echo_trailing\":1,\"echo_frame\":true,"
        "\"echo_broken\":true,\"pending_length\":2,\"events\":[[\"write_start\",6,10],[\"data\",1,20],[\"break\",0,30]]}");
}

TEST(UartEventTrace, RingKeepsOnlyTheMostRecentEvents){
    UartEventTrace t;for(uint32_t i=0;i<UartEventTrace::capacity+5;++i)t.record(Kind::data,i,i);
    const auto s=t.freeze({},0);ASSERT_EQ(s.count,UartEventTrace::capacity);
    EXPECT_EQ(s.events.front().atUs,5u);EXPECT_EQ(s.events.back().atUs,UartEventTrace::capacity+4);
}

TEST(UartEventTrace, OversizedEventSizeSaturates){
    UartEventTrace t;t.record(Kind::data,70000,1);EXPECT_EQ(t.freeze({},2).events[0].size,65535u);
}

// Candidate causes of the attended-trial fault 6 ms after a completed write.
// They show which event orders reach echo_event_accounting; they do not prove
// which one happened on the bus. The frozen device trace has to decide that.
TEST(EmsEchoRxDebtHypothesis, MissedOwnBreakThenBoilerReplyBreaksAccountingAtBoilerBreak){
    EmsEchoRxDebt d;for(int i=0;i<6;++i)ASSERT_TRUE(d.consumedByte());
    for(int i=0;i<6;++i)EXPECT_EQ(d.dataEvent(1),0u);
    EXPECT_EQ(d.dataEvent(1),1u); // Our delimiter byte; our BREAK event never arrives.
    EXPECT_EQ(d.dataEvent(1),1u); // Reply byte from the boiler.
    EXPECT_TRUE(d.broken());EXPECT_FALSE(d.atBreak()); // Boiler BREAK => accounting fault.
}

TEST(EmsEchoRxDebtHypothesis, DelimiterAndReplyCoalescedIntoOneEventBreaksAccounting){
    EmsEchoRxDebt d;for(int i=0;i<6;++i)ASSERT_TRUE(d.consumedByte());
    for(int i=0;i<6;++i)EXPECT_EQ(d.dataEvent(1),0u);
    EXPECT_EQ(d.dataEvent(2),2u); // Late ISR: delimiter + reply in one UART_DATA event.
    EXPECT_TRUE(d.broken());EXPECT_FALSE(d.atBreak());
}

TEST(EmsEchoRxDebtHypothesis, OrderlyDelimiterBreakThenReplyStaysHealthy){
    EmsEchoRxDebt d;for(int i=0;i<6;++i)ASSERT_TRUE(d.consumedByte());
    for(int i=0;i<6;++i)EXPECT_EQ(d.dataEvent(1),0u);
    EXPECT_EQ(d.dataEvent(1),1u);EXPECT_TRUE(d.atBreak());d.reset(); // Our BREAK.
    EXPECT_EQ(d.dataEvent(1),1u);EXPECT_TRUE(d.atBreak());          // Reply, then its BREAK.
}
