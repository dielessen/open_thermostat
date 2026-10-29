#include "control/DeadlineWiFiClient.h"
#include "control/ActuatorChannels.h"
#include <gtest/gtest.h>
#include <unistd.h>
#include <cerrno>
#include <csignal>
#include <array>
#include <string>
#include <vector>
using heating::control::DeadlineWiFiClient;
namespace {
struct Pair {
    int sockets[2]{-1,-1};
    Pair(){if(::socketpair(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK,0,sockets))throw std::runtime_error("socketpair");}
    ~Pair(){::close(sockets[0]);::close(sockets[1]);}
};
using heating::control::MqttCounters;
// A PUBLISH exactly as PubSubClient frames it (one write per packet).
std::vector<uint8_t> publish(const std::string& topic,size_t payload,uint8_t fill=0) {
    std::vector<uint8_t> f{0x30};size_t length=2+topic.size()+payload;
    do{uint8_t d=length&127;length>>=7;if(length)d|=128;f.push_back(d);}while(length);
    f.push_back(uint8_t(topic.size()>>8));f.push_back(uint8_t(topic.size()));f.insert(f.end(),topic.begin(),topic.end());
    for(size_t i=0;i<payload;++i)f.push_back(uint8_t(fill+i%251));
    return f;
}
const std::vector<uint8_t> pingreq{0xC0,0x00};
bool fill(int socket) {
    std::array<uint8_t,4096> buffer{};
    for(int i=0;i<128;++i)if(::send(socket,buffer.data(),buffer.size(),MSG_DONTWAIT|MSG_NOSIGNAL)<0)return errno==EAGAIN;
    return false;
}
std::vector<uint8_t> readAll(int socket,size_t atLeast,DeadlineWiFiClient& client) {
    std::vector<uint8_t> received;std::array<uint8_t,2048> chunk{};
    const auto end=std::chrono::steady_clock::now()+std::chrono::seconds(3);
    while(received.size()<atLeast&&std::chrono::steady_clock::now()<end) {
        client.poll();
        const auto count=::recv(socket,chunk.data(),chunk.size(),MSG_DONTWAIT);
        if(count>0)received.insert(received.end(),chunk.begin(),chunk.begin()+count);
        else if(count==0)break;
        else delay(1);
    }
    return received;
}
TEST(DeadlineWiFiClient, OrdinaryAndActuatorTrafficUseSameActualSocketWithoutSdkWriteWait) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);uint8_t received[2];
    EXPECT_EQ(client.write(pingreq.data(),2),2u);EXPECT_EQ(client.ordinaryWrites,0);ASSERT_EQ(::recv(pair.sockets[1],received,2,0),2);
    ASSERT_TRUE(client.beginDeadlineWrite([]{return true;}));
    const uint8_t data[]{1,2,3};
    WiFiClient& publicApi=client;EXPECT_EQ(publicApi.write(data,3),3u);EXPECT_TRUE(client.finishDeadlineWrite());
    uint8_t raw[3];
    EXPECT_EQ(client.ordinaryWrites,0);ASSERT_EQ(::recv(pair.sockets[1],raw,3,0),3);EXPECT_EQ(raw[2],3);
}
TEST(DeadlineWiFiClient, AFullSocketQueuesTheFrameAndKeepsTheSessionWithoutWaiting) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);client.setTopicPrefix("p/v1/");int small=4096;
    ASSERT_EQ(::setsockopt(pair.sockets[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof(small)),0);
    ASSERT_TRUE(fill(pair.sockets[0]));
    const auto stalled=MqttCounters::stalledDisconnects.load(),errors=MqttCounters::socketErrorDisconnects.load();
    const auto frame=publish("p/v1/fw/state/heating",900);const auto start=std::chrono::steady_clock::now();
    EXPECT_EQ(client.write(frame.data(),frame.size()),frame.size());   // queued: success for PubSubClient
    EXPECT_EQ(client.write(pingreq.data(),2),2u);
    const auto elapsed=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-start).count();
    EXPECT_LT(elapsed,50);EXPECT_GE(client.fd(),0);EXPECT_FALSE(client.outbox().empty());
    for(int i=0;i<300;++i){client.poll();delay(1);}               // 300 ms of backpressure: no disconnect
    EXPECT_GE(client.fd(),0);
    // The broker reads its backlog: the queued frames follow, whole, control (PINGREQ) first.
    std::vector<uint8_t> drained;std::array<uint8_t,4096> chunk{};
    for(;;){const auto n=::recv(pair.sockets[1],chunk.data(),chunk.size(),MSG_DONTWAIT);if(n<=0)break;drained.insert(drained.end(),chunk.begin(),chunk.begin()+n);}
    const auto tail=readAll(pair.sockets[1],frame.size()+2,client);
    std::vector<uint8_t> expected=pingreq;expected.insert(expected.end(),frame.begin(),frame.end());
    drained.insert(drained.end(),tail.begin(),tail.end());
    ASSERT_GE(drained.size(),expected.size());
    EXPECT_TRUE(std::equal(expected.begin(),expected.end(),drained.end()-expected.size()));
    EXPECT_TRUE(client.outbox().empty());EXPECT_GE(client.fd(),0);
    EXPECT_EQ(MqttCounters::stalledDisconnects.load(),stalled);EXPECT_EQ(MqttCounters::socketErrorDisconnects.load(),errors);
    EXPECT_EQ(client.ordinaryWrites,0);
}
TEST(DeadlineWiFiClient, OrdinaryLargeBinaryFrameCompletesAcrossActualPartialSocketHandoffs) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);int small=4096;
    ASSERT_EQ(::setsockopt(pair.sockets[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof(small)),0);
    const auto sent=publish("fixture/large",8192);
    EXPECT_EQ(client.write(sent.data(),sent.size()),sent.size());
    const auto received=readAll(pair.sockets[1],sent.size(),client);
    EXPECT_EQ(received,sent);EXPECT_EQ(client.ordinaryWrites,0);EXPECT_TRUE(client.outbox().empty());
}
TEST(DeadlineWiFiClient, PartialOrMalformedPacketsAreRefusedWholeAndTheStreamStaysIntact) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);
    const auto rejected=MqttCounters::rejected.load();
    const auto frame=publish("p/v1/fw/state/heating",10);
    EXPECT_EQ(client.write(frame.data(),frame.size()-1),0u);       // a split packet
    const uint8_t one=0x30;EXPECT_EQ(client.write(&one,1),0u);     // PubSubClient's byte-wise publish_P
    EXPECT_EQ(MqttCounters::rejected.load(),rejected+2);EXPECT_GE(client.fd(),0);
    EXPECT_EQ(client.write(frame.data(),frame.size()),frame.size());
    EXPECT_EQ(readAll(pair.sockets[1],frame.size(),client),frame);
}
TEST(DeadlineWiFiClient, APeerThatLeftIsASocketErrorDisconnect) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);
    const auto errors=MqttCounters::socketErrorDisconnects.load();
    std::signal(SIGPIPE,SIG_IGN);                                  // lwIP has no SIGPIPE
    ::shutdown(pair.sockets[1],SHUT_RDWR);
    client.write(pingreq.data(),2);                                // queued, then the send fails
    client.poll();
    EXPECT_EQ(client.fd(),-1);EXPECT_TRUE(client.outbox().empty());
    EXPECT_EQ(MqttCounters::socketErrorDisconnects.load(),errors+1);
    EXPECT_EQ(client.write(pingreq.data(),2),0u);                  // nothing queues on a closed socket
}
TEST(DeadlineWiFiClient, ADeadlineWriteWaitsForAHalfSentFrameAndNeverInterleaves) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);int small=4096;
    ASSERT_EQ(::setsockopt(pair.sockets[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof(small)),0);
    ASSERT_TRUE(fill(pair.sockets[0]));
    const auto big=publish("fixture/large",8192);
    EXPECT_EQ(client.write(big.data(),big.size()),big.size());
    std::vector<uint8_t> received;std::array<uint8_t,1000> chunk{};
    const auto n=::recv(pair.sockets[1],chunk.data(),chunk.size(),0);    // room for part of the frame
    ASSERT_GT(n,0);received.insert(received.end(),chunk.begin(),chunk.begin()+n);
    client.poll();
    ASSERT_FALSE(client.outbox().empty());
    int checks=0;
    EXPECT_FALSE(client.beginDeadlineWrite([&]{++checks;return true;}));   // refused: no IO, no disconnect
    EXPECT_EQ(checks,0);EXPECT_GE(client.fd(),0);
    const auto start=std::chrono::steady_clock::now();
    while(!client.outbox().empty()&&std::chrono::steady_clock::now()-start<std::chrono::seconds(3)) {
        client.poll();
        const auto k=::recv(pair.sockets[1],chunk.data(),chunk.size(),MSG_DONTWAIT);
        if(k>0)received.insert(received.end(),chunk.begin(),chunk.begin()+k);else delay(1);
    }
    ASSERT_TRUE(client.outbox().empty());
    ASSERT_TRUE(client.beginDeadlineWrite([]{return true;}));
    EXPECT_EQ(client.write(pingreq.data(),2),2u);EXPECT_TRUE(client.finishDeadlineWrite());
    for(;;){const auto k=::recv(pair.sockets[1],chunk.data(),chunk.size(),MSG_DONTWAIT);if(k<=0)break;received.insert(received.end(),chunk.begin(),chunk.begin()+k);}
    // The whole frame, then the deadline write: no byte of one inside the other.
    auto expected=big;expected.insert(expected.end(),pingreq.begin(),pingreq.end());
    ASSERT_GE(received.size(),expected.size());
    EXPECT_TRUE(std::equal(expected.begin(),expected.end(),received.end()-expected.size()));
}
TEST(DeadlineWiFiClient, ReconnectClearsTheQueue) {
    Pair pair;DeadlineWiFiClient client;client.fixtureSocket(pair.sockets[0]);int small=4096;
    ASSERT_EQ(::setsockopt(pair.sockets[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof(small)),0);
    ASSERT_TRUE(fill(pair.sockets[0]));
    EXPECT_EQ(client.write(pingreq.data(),2),2u);ASSERT_FALSE(client.outbox().empty());
    int next[2];ASSERT_EQ(::socketpair(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK,0,next),0);
    EXPECT_TRUE(client.adoptConnectedSocket(next[0]));
    EXPECT_TRUE(client.outbox().empty());
    uint8_t byte;EXPECT_EQ(::recv(next[1],&byte,1,MSG_DONTWAIT),-1);  // the old session's frame is gone
    ::close(next[1]);
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
