#include "control/DeadlineWiFiClient.h"
#include "control/ActuatorChannels.h"
#include <gtest/gtest.h>
#include <unistd.h>
#include <cerrno>
#include <array>
#include <vector>
using heating::control::DeadlineWiFiClient;
namespace {
struct Pair {
    int sockets[2]{-1,-1};
    Pair(){if(::socketpair(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK,0,sockets))throw std::runtime_error("socketpair");}
    ~Pair(){::close(sockets[0]);::close(sockets[1]);}
};
TEST(DeadlineWiFiClient, OrdinaryAndActuatorTrafficUseSameActualSocketWithoutSdkWriteWait) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);const uint8_t data[]{1,2,3};uint8_t received[3];
    EXPECT_EQ(client.write(data,3),3u);EXPECT_EQ(client.ordinaryWrites,0);ASSERT_EQ(::recv(pair.sockets[1],received,3,0),3);
    ASSERT_TRUE(client.beginDeadlineWrite([]{return true;}));
    WiFiClient& publicApi=client;EXPECT_EQ(publicApi.write(data,3),3u);EXPECT_TRUE(client.finishDeadlineWrite());
    EXPECT_EQ(client.ordinaryWrites,0);ASSERT_EQ(::recv(pair.sockets[1],received,3,0),3);EXPECT_EQ(received[2],3);
}
TEST(DeadlineWiFiClient, OrdinaryFullSocketHasOneTotalBudgetAndCannotAppendAnotherFrame) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);int small=4096;
    ASSERT_EQ(::setsockopt(pair.sockets[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof(small)),0);
    std::array<uint8_t,4096> buffer{};bool full=false;
    for(int i=0;i<128;++i)if(::send(pair.sockets[0],buffer.data(),buffer.size(),MSG_DONTWAIT|MSG_NOSIGNAL)<0){ASSERT_EQ(errno,EAGAIN);full=true;break;}
    ASSERT_TRUE(full);const uint8_t data=42;const auto start=std::chrono::steady_clock::now();
    EXPECT_EQ(client.write(&data,1),0u);
    const auto elapsed=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-start).count();
    // Host scheduling is not a hard real-time claim; the deterministic policy
    // tests prove the exact deadline. This detects the old ten-second SDK wait.
    EXPECT_GE(elapsed,90);EXPECT_LT(elapsed,2000);EXPECT_EQ(client.fd(),-1);
    EXPECT_EQ(client.write(&data,1),0u);EXPECT_EQ(client.ordinaryWrites,0);
}
TEST(DeadlineWiFiClient, OrdinaryLargeBinaryFrameCompletesAcrossActualPartialSocketHandoffs) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);int small=4096;
    ASSERT_EQ(::setsockopt(pair.sockets[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof(small)),0);
    std::array<uint8_t,8448> sent{};for(size_t i=0;i<sent.size();++i)sent[i]=i%251;
    std::vector<uint8_t> received;bool failed=false;
    std::thread reader([&]{
        delay(10);std::array<uint8_t,2048> chunk{};
        const auto end=std::chrono::steady_clock::now()+std::chrono::seconds(2);
        while(received.size()<sent.size()&&std::chrono::steady_clock::now()<end) {
            const auto count=::recv(pair.sockets[1],chunk.data(),chunk.size(),0);
            if(count>0)received.insert(received.end(),chunk.begin(),chunk.begin()+count);
            else if(count==0)break;
            else if(errno==EAGAIN||errno==EWOULDBLOCK)delay(1);
            else {failed=true;break;}
        }
    });
    const auto written=client.write(sent.data(),sent.size());reader.join();
    EXPECT_EQ(written,sent.size());EXPECT_FALSE(failed);
    EXPECT_EQ(received,(std::vector<uint8_t>(sent.begin(),sent.end())));EXPECT_EQ(client.ordinaryWrites,0);
}
TEST(DeadlineWiFiClient, OrdinaryPartialFrameClosesSocketWithoutClaimingNoBytesWereSent) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);int small=1024;
    ASSERT_EQ(::setsockopt(pair.sockets[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof(small)),0);
    std::array<uint8_t,8448> sent{};for(size_t i=0;i<sent.size();++i)sent[i]=i%251;
    EXPECT_EQ(client.write(sent.data(),sent.size()),0u);EXPECT_EQ(client.fd(),-1);
    const uint8_t nextFrame=255;EXPECT_EQ(client.write(&nextFrame,1),0u);
    std::vector<uint8_t> received;std::array<uint8_t,2048> chunk{};
    for(;;) {
        const auto count=::recv(pair.sockets[1],chunk.data(),chunk.size(),0);
        if(count<=0){EXPECT_EQ(count,0);break;}
        received.insert(received.end(),chunk.begin(),chunk.begin()+count);
    }
    ASSERT_GT(received.size(),0u);ASSERT_LT(received.size(),sent.size());
    EXPECT_EQ(received,(std::vector<uint8_t>(sent.begin(),sent.begin()+received.size())));
    EXPECT_EQ(client.ordinaryWrites,0);
}
TEST(DeadlineWiFiClient, ExpiredAbsoluteGuardHandsOffNoBytes) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);const uint8_t data[]{1};uint8_t received;
    ASSERT_TRUE(client.beginDeadlineWrite([]{return false;}));EXPECT_EQ(client.write(data,1),0u);EXPECT_FALSE(client.finishDeadlineWrite());
    EXPECT_EQ(::recv(pair.sockets[1],&received,1,0),-1);EXPECT_EQ(errno,EAGAIN);EXPECT_EQ(client.ordinaryWrites,0);
}
TEST(DeadlineWiFiClient, FullSocketBufferReturnsWithoutRetryOrWaitingAndScopeStaysFailed) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);int small=4096;
    ASSERT_EQ(::setsockopt(pair.sockets[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof(small)),0);
    std::array<uint8_t,4096> buffer{};bool full=false;
    for(int i=0;i<128;++i)if(::send(pair.sockets[0],buffer.data(),buffer.size(),MSG_DONTWAIT|MSG_NOSIGNAL)<0){ASSERT_EQ(errno,EAGAIN);full=true;break;}
    ASSERT_TRUE(full);ASSERT_TRUE(client.beginDeadlineWrite([]{return true;}));
    EXPECT_EQ(client.write(buffer.data(),1),0u);EXPECT_EQ(client.write(buffer.data(),1),0u);EXPECT_FALSE(client.finishDeadlineWrite());
    EXPECT_EQ(client.ordinaryWrites,0);
}
TEST(DeadlineWiFiClient, LatePostcheckDoesNotPretendAlreadyWrittenBytesCanBeUndone) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);int checks=0;const uint8_t data[]{7};uint8_t received;
    ASSERT_TRUE(client.beginDeadlineWrite([&]{return ++checks==1;}));
    EXPECT_EQ(client.write(data,1),1u);EXPECT_FALSE(client.finishDeadlineWrite());
    ASSERT_EQ(::recv(pair.sockets[1],&received,1,0),1);EXPECT_EQ(received,7);EXPECT_EQ(client.ordinaryWrites,0);
}
}

namespace {
TEST(DeadlineWiFiClient, RecursiveHandoffPredicateSendsNoBytesOnExistingSocket) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);
    const uint8_t data[]{42};uint8_t received=0;int calls=0;
    heating::control::ActuatorChannels* owner=nullptr;
    heating::control::ActuatorChannels channels{
        [](const auto&)->heating::control::ActuatorChannel::Source{return {};},
        [](std::string_view,uint64_t)->std::optional<heating::control::ActuatorSessionContext>{return {};},
        [&]{if(++calls==1){EXPECT_FALSE(owner->beforeHandoff(5000));}return true;},
        []()->uint64_t{return 1000;},
        [](std::string_view,std::string_view,uint64_t){ADD_FAILURE();return false;}};
    owner=&channels;
    ASSERT_TRUE(client.beginDeadlineWrite([&]{return channels.beforeHandoff(5000);}));
    EXPECT_EQ(client.write(data,1),0u);EXPECT_FALSE(client.finishDeadlineWrite());
    EXPECT_TRUE(channels.retired());EXPECT_EQ(calls,1);EXPECT_EQ(client.ordinaryWrites,0);
    EXPECT_EQ(::recv(pair.sockets[1],&received,1,0),-1);EXPECT_EQ(errno,EAGAIN);
}
}
