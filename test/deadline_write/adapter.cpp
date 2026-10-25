#include "control/DeadlineWiFiClient.h"
#include <gtest/gtest.h>
#include <unistd.h>
#include <cerrno>
#include <array>
using heating::control::DeadlineWiFiClient;
namespace {
struct Pair {
    int sockets[2]{-1,-1};
    Pair(){if(::socketpair(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK,0,sockets))throw std::runtime_error("socketpair");}
    ~Pair(){::close(sockets[0]);::close(sockets[1]);}
};
TEST(DeadlineWiFiClient, OrdinaryTrafficDelegatesAndBoundedTrafficUsesActualSameSocket) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);const uint8_t data[]{1,2,3};uint8_t received[3];
    EXPECT_EQ(client.write(data,3),3u);EXPECT_EQ(client.ordinaryWrites,1);ASSERT_EQ(::recv(pair.sockets[1],received,3,0),3);
    ASSERT_TRUE(client.beginDeadlineWrite([]{return true;}));
    WiFiClient& publicApi=client;EXPECT_EQ(publicApi.write(data,3),3u);EXPECT_TRUE(client.finishDeadlineWrite());
    EXPECT_EQ(client.ordinaryWrites,1);ASSERT_EQ(::recv(pair.sockets[1],received,3,0),3);EXPECT_EQ(received[2],3);
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
