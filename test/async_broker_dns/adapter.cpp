// Public lwIP API fixture. No network, firmware macro bypass or extra owner.
#include "control/AsyncBrokerDns.h"
#include <gtest/gtest.h>
#include <algorithm>
#include <atomic>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace {
using Dns=heating::control::AsyncBrokerDns;
constexpr uint32_t brokerA=0x0101a8c0,brokerB=0x0201a8c0;
enum class Reply {delayed,cached,error,synchronousFailure,ipv6,zero};
struct Job {tcpip_callback_fn call;void* context;};
struct Lookup {std::string name;dns_found_callback call;void* context;};
std::mutex guard;
std::deque<Job> queue;
std::vector<Lookup> pending;
std::vector<std::string> names;
Reply reply=Reply::delayed;
bool rejectQueue=false;
thread_local bool tcpipThread=false;
unsigned posted=0,lookups=0;

bool runQuery() {
    Job job;
    {std::lock_guard<std::mutex> lock(guard);if(queue.empty())return false;job=queue.front();queue.pop_front();}
    tcpipThread=true;job.call(job.context);tcpipThread=false;return true;
}
void complete(size_t index,uint32_t value=brokerA,bool ipv4=true) {
    Lookup item;
    {std::lock_guard<std::mutex> lock(guard);ASSERT_LT(index,pending.size());item=std::move(pending[index]);pending.erase(pending.begin()+index);}
    const ip_addr_t address{{value},ipv4};
    tcpipThread=true;item.call(item.name.c_str(),value?&address:nullptr,item.context);tcpipThread=false;
}
class AsyncDnsTest:public testing::Test {
    void SetUp()override {
        ASSERT_TRUE(queue.empty());ASSERT_TRUE(pending.empty());
        reply=Reply::delayed;rejectQueue=false;posted=lookups=0;names.clear();
    }
    void TearDown()override {
        // Native callbacks own retired slots until completion. Drain them just
        // like the real resolver; no test-only production reset or pool access.
        reply=Reply::error;
        while(runQuery()){}
        while(!pending.empty())complete(0,0);
    }
};
}
err_t tcpip_try_callback(tcpip_callback_fn fn,void* arg) {
    std::lock_guard<std::mutex> lock(guard);++posted;
    if(rejectQueue)return ERR_MEM;
    queue.push_back({fn,arg});return ERR_OK;
}
err_t dns_gethostbyname_addrtype(const char* host,ip_addr_t* cached,dns_found_callback fn,void* arg,u8_t family) {
    EXPECT_TRUE(tcpipThread);EXPECT_EQ(family,LWIP_DNS_ADDRTYPE_IPV4);
    std::lock_guard<std::mutex> lock(guard);++lookups;names.emplace_back(host);
    switch(reply) {
        case Reply::cached:*cached={{brokerA},true};return ERR_OK;
        case Reply::error:return ERR_ARG;
        case Reply::synchronousFailure:fn(host,nullptr,arg);return ERR_INPROGRESS;
        case Reply::ipv6:*cached={{brokerA},false};return ERR_OK;
        case Reply::zero:*cached={{0},true};return ERR_OK;
        default:pending.push_back({host,fn,arg});return ERR_INPROGRESS;
    }
}

TEST_F(AsyncDnsTest, DelayedLookupReturnsToOwnerImmediatelyAndPollsNeverRequeue) {
    Dns dns;ASSERT_TRUE(dns.start("broker.local",100));
    EXPECT_TRUE(dns.started());EXPECT_EQ(lookups,0u);EXPECT_EQ(posted,1u);
    for(unsigned i=0;i<100000;++i)EXPECT_EQ(dns.poll(101).state,Dns::State::pending);
    EXPECT_EQ(posted,1u);ASSERT_TRUE(runQuery());EXPECT_EQ(lookups,1u);
    EXPECT_EQ(names,std::vector<std::string>{"broker.local"});
    EXPECT_EQ(dns.poll(102).state,Dns::State::pending);
    complete(0);const auto result=dns.poll(103);
    EXPECT_EQ(result.state,Dns::State::ready);EXPECT_EQ(result.ipv4,brokerA);
    dns.cancel();EXPECT_FALSE(dns.started());EXPECT_EQ(dns.poll(104).state,Dns::State::failed);
}
TEST_F(AsyncDnsTest, CachedAddressStillResolvesOnTcpipThreadAndDoesNotBecomePrivateCache) {
    reply=Reply::cached;Dns dns;ASSERT_TRUE(dns.start("cache.example",1));
    EXPECT_EQ(dns.poll(1).state,Dns::State::pending);ASSERT_TRUE(runQuery());
    EXPECT_EQ(dns.poll(2).ipv4,brokerA);dns.cancel();
    ASSERT_TRUE(dns.start("cache.example",3));ASSERT_TRUE(runQuery());
    EXPECT_EQ(lookups,2u);EXPECT_EQ(dns.poll(4).state,Dns::State::ready);
}
TEST_F(AsyncDnsTest, NativeFailureAndSynchronousFailureNeverProduceAnAddress) {
    for(auto mode:{Reply::error,Reply::synchronousFailure,Reply::ipv6,Reply::zero}) {
        reply=mode;Dns dns;ASSERT_TRUE(dns.start("broker.example",1));ASSERT_TRUE(runQuery());
        EXPECT_EQ(dns.poll(2).state,Dns::State::failed);EXPECT_EQ(dns.poll(2).ipv4,0u);
    }
    reply=Reply::delayed;Dns dns;ASSERT_TRUE(dns.start("missing.example",1));ASSERT_TRUE(runQuery());
    complete(0,0);EXPECT_EQ(dns.poll(2).state,Dns::State::failed);
}
TEST_F(AsyncDnsTest, FullNativeMailboxFailsWithoutAnyWaitOrLookup) {
    rejectQueue=true;Dns dns;EXPECT_FALSE(dns.start("broker.example",1));
    EXPECT_TRUE(dns.started());EXPECT_EQ(dns.poll(2).state,Dns::State::failed);
    EXPECT_TRUE(queue.empty());EXPECT_EQ(lookups,0u);
    rejectQueue=false;ASSERT_TRUE(dns.start("broker.example",3));ASSERT_TRUE(runQuery());complete(0);
    EXPECT_EQ(dns.poll(4).state,Dns::State::ready);
}
TEST_F(AsyncDnsTest, RetiredQueuedRequestDoesNotEvenStartDns) {
    {Dns dns;ASSERT_TRUE(dns.start("retired.example",1));}
    ASSERT_TRUE(runQuery());EXPECT_EQ(lookups,0u);EXPECT_TRUE(pending.empty());
}
TEST_F(AsyncDnsTest, ReplacementOwnsDifferentSlotUntilOldCallbackHasFinished) {
    Dns dns;ASSERT_TRUE(dns.start("old.example",1));ASSERT_TRUE(runQuery());
    ASSERT_TRUE(dns.start("new.example",2));ASSERT_TRUE(runQuery());
    ASSERT_EQ(pending.size(),2u);complete(0,brokerA);
    EXPECT_EQ(dns.poll(3).state,Dns::State::pending);
    complete(0,brokerB);EXPECT_EQ(dns.poll(4).ipv4,brokerB);
}
TEST_F(AsyncDnsTest, DestructorCannotLeaveNativeCallbackWithDanglingOwner) {
    {auto dns=std::make_unique<Dns>();ASSERT_TRUE(dns->start("gone.example",1));ASSERT_TRUE(runQuery());}
    Dns next;ASSERT_TRUE(next.start("next.example",2));ASSERT_TRUE(runQuery());
    complete(0,brokerA);EXPECT_EQ(next.poll(3).state,Dns::State::pending);
    complete(0,brokerB);EXPECT_EQ(next.poll(4).ipv4,brokerB);
}
TEST_F(AsyncDnsTest, RetiredPendingSlotsRemainBoundedAndBecomeReusableAfterNativeCompletion) {
    for(size_t i=0;i<Dns::slotCount;++i) {
        Dns dns;ASSERT_TRUE(dns.start("retired.example",1));ASSERT_TRUE(runQuery());
    }
    Dns dns;EXPECT_FALSE(dns.start("full.example",2));
    EXPECT_EQ(dns.poll(3).state,Dns::State::failed);EXPECT_EQ(posted,Dns::slotCount);
    complete(0);ASSERT_TRUE(dns.start("free.example",4));ASSERT_TRUE(runQuery());
    complete(pending.size()-1,brokerB);EXPECT_EQ(dns.poll(5).ipv4,brokerB);
}
TEST_F(AsyncDnsTest, OriginalDeadlineRejectsLateReadyAnswersAndBackwardsTime) {
    for(bool backwards:{false,true}) {
        Dns dns;ASSERT_TRUE(dns.start("late.example",100));ASSERT_TRUE(runQuery());
        EXPECT_EQ(dns.poll(100+Dns::timeoutMs-1).state,Dns::State::pending);
        complete(0);
        EXPECT_EQ(dns.poll(backwards?99:100+Dns::timeoutMs).state,Dns::State::failed);
        EXPECT_EQ(dns.poll(101).state,Dns::State::failed); // no resurrection
    }
}
TEST_F(AsyncDnsTest, TimeoutDoesNotFreeNativeCallbackStorageEarly) {
    Dns dns;ASSERT_TRUE(dns.start("old.example",1));ASSERT_TRUE(runQuery());
    EXPECT_EQ(dns.poll(1+Dns::timeoutMs).state,Dns::State::failed);
    ASSERT_TRUE(dns.start("new.example",20000));ASSERT_TRUE(runQuery());
    complete(0,brokerA);EXPECT_EQ(dns.poll(20001).state,Dns::State::pending);
    complete(0,brokerB);EXPECT_EQ(dns.poll(20002).ipv4,brokerB);
}
TEST_F(AsyncDnsTest, BackwardsPollWithinOriginalDeadlineCannotRejuvenatePendingRequest) {
    Dns dns;ASSERT_TRUE(dns.start("clock.example",100));ASSERT_TRUE(runQuery());
    EXPECT_EQ(dns.poll(1000).state,Dns::State::pending);
    EXPECT_EQ(dns.poll(999).state,Dns::State::failed);
    complete(0);EXPECT_EQ(dns.poll(1001).state,Dns::State::failed);
}
TEST_F(AsyncDnsTest, HostnameStorageIsOwnedBoundedAndNeverUsesCallerMemory) {
    Dns dns;std::string host="original.example";ASSERT_TRUE(dns.start(host,1));host.assign(500,'x');
    ASSERT_TRUE(runQuery());EXPECT_EQ(names.back(),"original.example");complete(0);dns.cancel();
    for(const auto& invalid:std::vector<std::string>{"",std::string(254,'x'),std::string("a\0b",3),"white space","newline\n",std::string(1,static_cast<char>(255))})
        EXPECT_FALSE(dns.start(invalid,2));
    EXPECT_EQ(posted,1u);
    reply=Reply::cached;ASSERT_TRUE(dns.start(std::string(253,'a'),3));ASSERT_TRUE(runQuery());
    EXPECT_EQ(names.back().size(),253u);EXPECT_EQ(dns.poll(4).state,Dns::State::ready);
}
TEST_F(AsyncDnsTest, ConcurrentNativeCompletionAndOwnerRetirementDoNotShareOwnerLifetime) {
    // A real second thread exercises release/acquire publication and retirement.
    // Every callback completes once before the next iteration, as native lwIP does.
    for(unsigned i=0;i<1000;++i) {
        Dns dns;ASSERT_TRUE(dns.start("race.example",1));ASSERT_TRUE(runQuery());
        std::thread callback([]{complete(0,brokerA);});
        if(i%2)dns.cancel();
        else {const auto result=dns.poll(2);EXPECT_TRUE(result.state==Dns::State::pending||result.state==Dns::State::ready);}
        callback.join();
    }
}

TEST_F(AsyncDnsTest, ConcurrentDestructionAndImmediateReplacementKeepOldCallbackIsolated) {
    for(unsigned i=0;i<1000;++i) {
        auto old=std::make_unique<Dns>();ASSERT_TRUE(old->start("old.example",1));ASSERT_TRUE(runQuery());
        std::thread callback([]{complete(0,brokerA);});
        old.reset();
        Dns replacement;ASSERT_TRUE(replacement.start("replacement.example",2));
        callback.join();ASSERT_TRUE(runQuery());
        EXPECT_EQ(replacement.poll(3).state,Dns::State::pending);
        complete(0,brokerB);EXPECT_EQ(replacement.poll(4).ipv4,brokerB);
    }
}
