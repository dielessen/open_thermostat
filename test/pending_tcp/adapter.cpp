// Actual connector/client and pinned public MQTT implementation. Native API
// faults are explicit; successful traffic uses finite loopback sockets only.
#include "control/PendingTcpConnect.h"
#include "control/DeadlineWiFiClient.h"
#include <PubSubClient.h>
#include <gtest/gtest.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <limits>
#include <thread>
#include <vector>

namespace {
using Tcp=heating::control::PendingTcpConnect;
using MqttSocket=heating::control::DeadlineWiFiClient;
enum class Fault {none,open,descriptorRange,getFlags,nonblocking,connect,select,interrupted,
                  spuriousReady,getError,shortError,refused,sendTimeout,receiveTimeout,restoreFlags};
Fault fault=Fault::none;
bool simulated=true,ready=false,immediate=false;
unsigned opens=0,closes=0,connects=0,selects=0;
uint32_t destination=0;uint16_t destinationPort=0;
int lastOpened=-1;
class PendingTcpTest:public testing::Test {
    void SetUp()override {fault=Fault::none;simulated=true;ready=immediate=false;opens=closes=connects=selects=0;lastOpened=-1;destination=0;destinationPort=0;}
};
struct Socket {
    int value=-1;
    explicit Socket(int fd=-1):value(fd){}
    ~Socket(){if(value>=0)::close(value);}
    Socket(const Socket&)=delete;
};
constexpr uint32_t arbitraryIpv4=0x0100007f;
}
int lwip_socket(int domain,int type,int protocol) {
    if(fault==Fault::open){errno=EMFILE;return -1;}
    int fd=::socket(domain,type,protocol);
    if(fd>=0&&fault==Fault::descriptorRange){const int high=::fcntl(fd,F_DUPFD_CLOEXEC,FD_SETSIZE+7);::close(fd);fd=high;}
    if(fd>=0){++opens;lastOpened=fd;}return fd;
}
int lwip_connect(int fd,const sockaddr* address,socklen_t length) {
    ++connects;const auto& ipv4=*reinterpret_cast<const sockaddr_in*>(address);
    destination=ipv4.sin_addr.s_addr;destinationPort=ntohs(ipv4.sin_port);
    if(fault==Fault::connect){errno=ECONNREFUSED;return -1;}
    if(!simulated)return ::connect(fd,address,length);
    if(immediate)return 0;
    errno=EINPROGRESS;return -1;
}
int lwip_fcntl(int fd,int command,int flags) {
    if((command==F_GETFL&&fault==Fault::getFlags)
       ||(command==F_SETFL&&(flags&O_NONBLOCK)&&fault==Fault::nonblocking)
       ||(command==F_SETFL&&!(flags&O_NONBLOCK)&&fault==Fault::restoreFlags)){errno=EBADF;return -1;}
    return ::fcntl(fd,command,flags);
}
int lwip_select(int count,fd_set* read,fd_set* write,fd_set* except,timeval* timeout) {
    ++selects;EXPECT_NE(timeout,nullptr);
    if(timeout){EXPECT_EQ(timeout->tv_sec,0);EXPECT_EQ(timeout->tv_usec,0);}
    if(fault==Fault::select||fault==Fault::interrupted){errno=fault==Fault::interrupted?EINTR:EBADF;return -1;}
    if(!simulated)return ::select(count,read,write,except,timeout);
    if(fault==Fault::spuriousReady){FD_ZERO(write);return 1;}
    return ready?1:0;
}
int lwip_getsockopt(int fd,int level,int name,void* value,socklen_t* size) {
    if(fault==Fault::getError){errno=EBADF;return -1;}
    if(fault==Fault::shortError){*size=1;return 0;}
    if(fault==Fault::refused){*static_cast<int*>(value)=ECONNREFUSED;return 0;}
    return ::getsockopt(fd,level,name,value,size);
}
int lwip_setsockopt(int fd,int level,int name,const void* value,socklen_t size) {
    if((name==SO_SNDTIMEO&&fault==Fault::sendTimeout)||(name==SO_RCVTIMEO&&fault==Fault::receiveTimeout)){errno=EINVAL;return -1;}
    return ::setsockopt(fd,level,name,value,size);
}
int lwip_close(int fd){++closes;return ::close(fd);}

TEST_F(PendingTcpTest, PendingConnectReturnsImmediatelyAndEachPollMakesOneZeroWaitProbe) {
    {Tcp tcp;ASSERT_TRUE(tcp.start(arbitraryIpv4,1883,100));EXPECT_TRUE(tcp.started());
     for(unsigned i=0;i<100;++i)EXPECT_EQ(tcp.poll(101+i),Tcp::State::pending);
     EXPECT_EQ(selects,100u);EXPECT_EQ(opens,1u);EXPECT_EQ(connects,1u);
     EXPECT_EQ(destination,arbitraryIpv4);EXPECT_EQ(destinationPort,1883);}
    EXPECT_EQ(closes,1u);
}
TEST_F(PendingTcpTest, ReadySocketRestoresPinnedTimeoutsAndTransfersOnlyOnce) {
    Tcp tcp;ASSERT_TRUE(tcp.start(arbitraryIpv4,1883,100));ready=true;
    EXPECT_EQ(tcp.poll(101),Tcp::State::ready);const int fd=tcp.take(102);ASSERT_GE(fd,0);
    EXPECT_FALSE(tcp.started());EXPECT_EQ(tcp.take(103),-1);tcp.cancel();EXPECT_EQ(closes,0u);
    EXPECT_EQ(::fcntl(fd,F_GETFL)&O_NONBLOCK,0);
    for(int option:{SO_SNDTIMEO,SO_RCVTIMEO}){timeval value{};socklen_t size=sizeof(value);
        ASSERT_EQ(::getsockopt(fd,SOL_SOCKET,option,&value,&size),0);EXPECT_EQ(value.tv_sec,3);}
    ::close(fd);
}
TEST_F(PendingTcpTest, ImmediateNativeConnectStillRequiresConfigurationAndFreshHandoff) {
    immediate=true;Tcp tcp;ASSERT_TRUE(tcp.start(arbitraryIpv4,1883,1));
    EXPECT_EQ(tcp.poll(2),Tcp::State::ready);EXPECT_EQ(selects,0u);
    const int fd=tcp.take(3);ASSERT_GE(fd,0);::close(fd);
}
TEST_F(PendingTcpTest, EveryNativeFailureRetiresItsOwnedSocketWithoutRetry) {
    for(const auto mode:{Fault::open,Fault::getFlags,Fault::nonblocking,Fault::connect,Fault::select,
            Fault::spuriousReady,Fault::getError,Fault::shortError,Fault::refused,
            Fault::sendTimeout,Fault::receiveTimeout,Fault::restoreFlags}) {
        fault=mode;ready=true;opens=closes=connects=selects=0;
        {Tcp tcp;tcp.start(arbitraryIpv4,1883,1);EXPECT_EQ(tcp.poll(2),Tcp::State::failed);
         EXPECT_EQ(tcp.take(3),-1);tcp.cancel();}
        EXPECT_EQ(opens,mode==Fault::open?0u:1u);EXPECT_EQ(closes,opens);EXPECT_LE(connects,1u);EXPECT_LE(selects,1u);
    }
}
TEST_F(PendingTcpTest, OriginalDeadlineIsNotRenewedByProgressOrInterruptedProbes) {
    Tcp tcp;ASSERT_TRUE(tcp.start(arbitraryIpv4,1883,100));fault=Fault::interrupted;
    EXPECT_EQ(tcp.poll(101),Tcp::State::pending);fault=Fault::none;
    EXPECT_EQ(tcp.poll(100+Tcp::timeoutMs-1),Tcp::State::pending);
    const auto probes=selects;EXPECT_EQ(tcp.poll(100+Tcp::timeoutMs),Tcp::State::failed);
    EXPECT_EQ(selects,probes);EXPECT_EQ(closes,1u);EXPECT_EQ(tcp.poll(102),Tcp::State::failed);
}
TEST_F(PendingTcpTest, LateReadinessCannotReviveExpiredAttempt) {
    Tcp tcp;ASSERT_TRUE(tcp.start(arbitraryIpv4,1883,1));ready=true;
    EXPECT_EQ(tcp.poll(1+Tcp::timeoutMs),Tcp::State::failed);EXPECT_EQ(selects,0u);EXPECT_EQ(closes,1u);
}
TEST_F(PendingTcpTest, DelayBetweenReadyAndTransferCannotRenewDeadline) {
    Tcp tcp;ASSERT_TRUE(tcp.start(arbitraryIpv4,1883,1));ready=true;
    ASSERT_EQ(tcp.poll(2),Tcp::State::ready);EXPECT_EQ(tcp.take(1+Tcp::timeoutMs),-1);EXPECT_EQ(closes,1u);
}
TEST_F(PendingTcpTest, BackwardsPollAndTransferRetireReadiness) {
    for(bool atTransfer:{false,true}) {
        Tcp tcp;ASSERT_TRUE(tcp.start(arbitraryIpv4,1883,100));ready=atTransfer;
        EXPECT_EQ(tcp.poll(200),atTransfer?Tcp::State::ready:Tcp::State::pending);
        if(atTransfer)EXPECT_EQ(tcp.take(199),-1);else EXPECT_EQ(tcp.poll(199),Tcp::State::failed);
    }
    EXPECT_EQ(closes,2u);
}
TEST_F(PendingTcpTest, ReplacingOrCancellingAttemptClosesTheOldRawSocket) {
    Tcp tcp;ASSERT_TRUE(tcp.start(arbitraryIpv4,1883,1));
    ASSERT_TRUE(tcp.start(arbitraryIpv4+1,1884,2));EXPECT_EQ(closes,1u);
    EXPECT_EQ(destination,arbitraryIpv4+1);EXPECT_EQ(destinationPort,1884);
    tcp.cancel();tcp.cancel();EXPECT_EQ(closes,2u);EXPECT_FALSE(tcp.started());
}
TEST_F(PendingTcpTest, InvalidAddressPortAndDeadlineOverflowOpenNothing) {
    Tcp tcp;EXPECT_FALSE(tcp.start(0,1883,1));EXPECT_FALSE(tcp.start(arbitraryIpv4,0,1));
    EXPECT_FALSE(tcp.start(arbitraryIpv4,1883,std::numeric_limits<uint64_t>::max()-1));
    EXPECT_EQ(opens,0u);EXPECT_EQ(connects,0u);
}
TEST_F(PendingTcpTest, DescriptorOutsideSelectStorageFailsBeforeFdSetCanOverflow) {
    fault=Fault::descriptorRange;Tcp tcp;EXPECT_FALSE(tcp.start(arbitraryIpv4,1883,1));
    EXPECT_EQ(selects,0u);EXPECT_EQ(connects,0u);EXPECT_EQ(closes,opens);
    EXPECT_EQ(tcp.poll(2),Tcp::State::failed);
}

namespace {
struct Listener {
    Socket socket{::socket(AF_INET,SOCK_STREAM,0)};
    uint16_t port=0;
    Listener() {
        if(socket.value<0)throw std::runtime_error("local socket");
        sockaddr_in address{};address.sin_family=AF_INET;address.sin_addr.s_addr=inet_addr("127.0.0.1");
        if(::bind(socket.value,reinterpret_cast<sockaddr*>(&address),sizeof(address))||::listen(socket.value,1))throw std::runtime_error("local listen");
        socklen_t length=sizeof(address);
        if(::getsockname(socket.value,reinterpret_cast<sockaddr*>(&address),&length))throw std::runtime_error("local address");
        port=ntohs(address.sin_port);
    }
    int accept() {
        fd_set waiting;FD_ZERO(&waiting);FD_SET(socket.value,&waiting);timeval timeout{2,0};
        if(::select(socket.value+1,&waiting,nullptr,nullptr,&timeout)!=1)return -1;
        return ::accept(socket.value,nullptr,nullptr);
    }
};
int connectedSocket(Tcp& pending,uint16_t port) {
    if(!pending.start(inet_addr("127.0.0.1"),port,1))return -1;
    for(unsigned i=0;i<1000;++i) {
        const auto result=pending.poll(2+i);
        if(result==Tcp::State::failed)return -1;
        if(result==Tcp::State::ready)return pending.take(3+i);
        delay(1);
    }
    return -1;
}
bool receiveByte(int fd,uint8_t& byte) {
    fd_set waiting;FD_ZERO(&waiting);FD_SET(fd,&waiting);timeval timeout{2,0};
    return ::select(fd+1,&waiting,nullptr,nullptr,&timeout)==1&&::recv(fd,&byte,1,0)==1;
}
std::vector<uint8_t> receivePacket(int fd) {
    uint8_t header=0;if(!receiveByte(fd,header))return {};
    std::vector<uint8_t> result{header};unsigned length=0,multiplier=1;
    for(unsigned i=0;;++i){
        uint8_t digit;if(i==4||!receiveByte(fd,digit))return {};
        result.push_back(digit);length+=(digit&127)*multiplier;
        if(length>8448)return {};
        if(!(digit&128))break;
        multiplier*=128;
    }
    for(unsigned i=0;i<length;++i){uint8_t byte;if(!receiveByte(fd,byte))return {};result.push_back(byte);}
    return result;
}
}
TEST_F(PendingTcpTest, ActualPublicMqttHandshakeAndGuardedPublishShareOneLoopbackConnection) {
    simulated=false;Listener listener;std::vector<std::vector<uint8_t>> packets;std::atomic<bool> serverOk{true};
    std::thread server([&]{
        Socket accepted(listener.accept());if(accepted.value<0){serverOk=false;return;}
        packets.push_back(receivePacket(accepted.value));
        const uint8_t ack[]{0x20,2,0,0};if(::send(accepted.value,ack,sizeof(ack),MSG_NOSIGNAL)!=4){serverOk=false;return;}
        for(unsigned i=0;i<3;++i)packets.push_back(receivePacket(accepted.value));
    });
    bool adopted=false,connected=false,published=false,guarded=false,finished=false;int sdkConnects=-1,sdkWrites=-1;
    {Tcp pending;const int raw=connectedSocket(pending,listener.port);MqttSocket socket;
     adopted=socket.adoptConnectedSocket(raw);
     PubSubClient mqtt(socket);mqtt.setServer(IPAddress(inet_addr("127.0.0.1")),listener.port);mqtt.setSocketTimeout(1);
     mqtt.setBufferSize(8448);
     connected=mqtt.connect("isolated-test-client");
     if(connected){published=mqtt.publish("fixture/data","hello");
         if(socket.beginDeadlineWrite([]{return true;})){guarded=mqtt.publish("fixture/bounded","one");finished=socket.finishDeadlineWrite();}
         mqtt.disconnect();}
     sdkConnects=socket.synchronousConnects;sdkWrites=socket.ordinaryWrites;}
    server.join();EXPECT_TRUE(serverOk);EXPECT_TRUE(adopted);EXPECT_TRUE(connected);EXPECT_TRUE(published);EXPECT_TRUE(guarded);EXPECT_TRUE(finished);
    EXPECT_EQ(opens,1u);EXPECT_EQ(connects,1u);EXPECT_EQ(sdkConnects,0);EXPECT_EQ(sdkWrites,0);
    ASSERT_EQ(packets.size(),4u);for(const auto& packet:packets)ASSERT_GE(packet.size(),2u);
    EXPECT_EQ(packets[0][0],0x10);EXPECT_EQ(packets[1][0],0x30);EXPECT_EQ(packets[2][0],0x30);EXPECT_EQ(packets[3][0],0xe0);
}
TEST_F(PendingTcpTest, ActualNativePacketBudgetPreservesLargeBinaryPayloadOnTheSameConnection) {
    simulated=false;Listener listener;std::vector<uint8_t> packet;
    std::vector<uint8_t> payload(8192);for(size_t i=0;i<payload.size();++i)payload[i]=i%251;
    std::thread server([&]{
        Socket accepted(listener.accept());if(accepted.value<0)return;
        if(receivePacket(accepted.value).empty())return;
        const uint8_t ack[]{0x20,2,0,0};if(::send(accepted.value,ack,sizeof(ack),MSG_NOSIGNAL)!=4)return;
        packet=receivePacket(accepted.value);
    });
    bool published=false,adopted=false;
    {Tcp pending;MqttSocket socket;adopted=socket.adoptConnectedSocket(connectedSocket(pending,listener.port));
     PubSubClient mqtt(socket);mqtt.setServer(IPAddress(arbitraryIpv4),listener.port);mqtt.setSocketTimeout(1);
     if(mqtt.setBufferSize(8448)&&mqtt.connect("large-fixture"))published=mqtt.publish("fixture/large",payload.data(),payload.size(),false);}
    server.join();EXPECT_TRUE(adopted);EXPECT_TRUE(published);ASSERT_GT(packet.size(),payload.size());
    EXPECT_EQ(packet[0],0x30);EXPECT_TRUE(std::equal(payload.begin(),payload.end(),packet.end()-payload.size()));
    EXPECT_EQ(opens,1u);EXPECT_EQ(connects,1u);
}
TEST_F(PendingTcpTest, RealMqttFallbackCannotEnterAnySynchronousSdkConnectOverload) {
    MqttSocket socket;PubSubClient mqtt(socket);mqtt.setServer(IPAddress(arbitraryIpv4),1883);
    EXPECT_FALSE(mqtt.connect("closed-fixture"));EXPECT_EQ(socket.synchronousConnects,0);
    WiFiClient& publicApi=socket;
    EXPECT_EQ(publicApi.connect(IPAddress(arbitraryIpv4),1883),0);
    EXPECT_EQ(publicApi.connect(IPAddress(arbitraryIpv4),1883,3000),0);
    EXPECT_EQ(publicApi.connect("unused.invalid",1883),0);
    EXPECT_EQ(publicApi.connect("unused.invalid",1883,3000),0);
    EXPECT_EQ(socket.synchronousConnects,0);EXPECT_EQ(opens,0u);EXPECT_EQ(connects,0u);
}
TEST_F(PendingTcpTest, PeerLossAfterAdoptionCannotCauseMqttToOpenAnotherSocket) {
    simulated=false;Listener listener;Tcp pending;MqttSocket socket;
    const int raw=connectedSocket(pending,listener.port);ASSERT_GE(raw,0);
    Socket accepted(listener.accept());ASSERT_GE(accepted.value,0);ASSERT_TRUE(socket.adoptConnectedSocket(raw));
    ::shutdown(accepted.value,SHUT_RDWR);
    for(unsigned i=0;i<100&&socket.connected();++i)delay(1);
    ASSERT_FALSE(socket.connected());PubSubClient mqtt(socket);mqtt.setServer(IPAddress(arbitraryIpv4),1883);
    EXPECT_FALSE(mqtt.connect("lost-fixture"));EXPECT_EQ(socket.synchronousConnects,0);EXPECT_EQ(opens,1u);
}
TEST_F(PendingTcpTest, ActiveActuatorScopeRejectsSocketReplacementAndClosesIncomingOwnership) {
    simulated=false;Listener listener;Tcp pending;MqttSocket socket;
    const int raw=connectedSocket(pending,listener.port);ASSERT_GE(raw,0);Socket accepted(listener.accept());ASSERT_GE(accepted.value,0);
    int pair[2];ASSERT_EQ(::socketpair(AF_UNIX,SOCK_STREAM,0,pair),0);Socket previous(pair[0]),reader(pair[1]);socket.fixtureSocket(pair[0]);
    ASSERT_TRUE(socket.beginDeadlineWrite([]{return true;}));EXPECT_FALSE(socket.adoptConnectedSocket(raw));
    EXPECT_EQ(::fcntl(raw,F_GETFL),-1);EXPECT_EQ(errno,EBADF);
    const uint8_t byte=42;uint8_t received=0;EXPECT_EQ(socket.write(&byte,1),1u);
    EXPECT_EQ(::recv(reader.value,&received,1,0),1);EXPECT_EQ(received,42);
    EXPECT_TRUE(socket.finishDeadlineWrite());EXPECT_EQ(socket.fd(),previous.value);
}
TEST_F(PendingTcpTest, FailedAdoptionClosesTransferredSocketWithoutLeavingAStaleHandle) {
    int pair[2];ASSERT_EQ(::socketpair(AF_UNIX,SOCK_STREAM,0,pair),0);::close(pair[1]);
    MqttSocket socket;EXPECT_FALSE(socket.adoptConnectedSocket(pair[0]));
    EXPECT_EQ(socket.fd(),-1);EXPECT_EQ(::fcntl(pair[0],F_GETFL),-1);EXPECT_EQ(errno,EBADF);
    EXPECT_FALSE(socket.adoptConnectedSocket(-1));EXPECT_EQ(socket.synchronousConnects,0);
}
TEST_F(PendingTcpTest, SilentMqttPeerRetainsSeparateOneSecondConnackTimeout) {
    simulated=false;Listener listener;
    std::thread server([&]{Socket accepted(listener.accept());if(accepted.value>=0){receivePacket(accepted.value);delay(1500);}});
    bool connected=false,adopted=false;long long elapsed=0;
    {Tcp pending;MqttSocket socket;const int raw=connectedSocket(pending,listener.port);
     adopted=socket.adoptConnectedSocket(raw);PubSubClient mqtt(socket);mqtt.setServer(IPAddress(arbitraryIpv4),listener.port);mqtt.setSocketTimeout(1);
     const auto start=std::chrono::steady_clock::now();connected=mqtt.connect("silent-fixture");
     elapsed=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-start).count();}
    server.join();EXPECT_TRUE(adopted);EXPECT_FALSE(connected);EXPECT_GE(elapsed,900);EXPECT_LT(elapsed,3000);EXPECT_EQ(opens,1u);
}
