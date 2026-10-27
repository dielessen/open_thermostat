#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <lwip/sockets.h>
#include <fcntl.h>
#include <cerrno>
#include <cstdint>
#include <limits>

namespace heating::control {
// Owns the prospective native MQTT socket until transfer to WiFiClient. All
// methods run on the same product task. No extra task, socket or protocol owner.
class PendingTcpConnect final {
public:
    static constexpr uint64_t timeoutMs=3000; // Same TCP budget as pinned WiFiClient.
    enum class State {pending,ready,failed};
    PendingTcpConnect()=default;
    PendingTcpConnect(const PendingTcpConnect&)=delete;
    PendingTcpConnect& operator=(const PendingTcpConnect&)=delete;
    ~PendingTcpConnect(){cancel();}

    bool started()const{return started_;}
    uint64_t deadlineMs()const{return deadline_;}
    bool start(uint32_t ipv4,uint16_t port,uint64_t now) {
        cancel();started_=true;lastPoll_=now;phase_=Phase::failed;
        if(!ipv4||!port||now>std::numeric_limits<uint64_t>::max()-timeoutMs)return false;
        deadline_=now+timeoutMs;
        socket_=lwip_socket(AF_INET,SOCK_STREAM,0);
        if(socket_<0)return false;
        if(!selectable(socket_))return fail();
        originalFlags_=lwip_fcntl(socket_,F_GETFL,0);
        if(originalFlags_<0||lwip_fcntl(socket_,F_SETFL,originalFlags_|O_NONBLOCK)<0)return fail();
        sockaddr_in address{};address.sin_family=AF_INET;
        address.sin_addr.s_addr=ipv4;address.sin_port=htons(port);
        const int result=lwip_connect(socket_,reinterpret_cast<sockaddr*>(&address),sizeof(address));
        if(result==0)phase_=Phase::connected;
        else if(errno==EINPROGRESS||errno==EWOULDBLOCK||errno==EALREADY)phase_=Phase::pending;
        else return fail();
        return true;
    }
    State poll(uint64_t now) {
        if(socket_<0||phase_==Phase::failed)return State::failed;
        if(now<lastPoll_||now>=deadline_){fail();return State::failed;}
        lastPoll_=now;
        if(phase_==Phase::pending) {
            fd_set writable;FD_ZERO(&writable);FD_SET(socket_,&writable);
            timeval immediate{}; // No network wait inside the product/HTTP loop.
            const auto ready=lwip_select(socket_+1,nullptr,&writable,nullptr,&immediate);
            if(ready<0&&errno==EINTR)return State::pending;
            if(ready<0){fail();return State::failed;}
            if(!ready)return State::pending;
            int error=0;socklen_t length=sizeof(error);
            if(!FD_ISSET(socket_,&writable)||lwip_getsockopt(socket_,SOL_SOCKET,SO_ERROR,&error,&length)<0
               ||length!=sizeof(error)||error){fail();return State::failed;}
            phase_=Phase::connected;
        }
        if(phase_==Phase::connected) {
            // Match the pinned client's accepted socket behavior and timeouts.
            // All later reads/writes retain that SAME WiFiClient instance.
            timeval timeout{static_cast<long>(timeoutMs/1000),0};
            if(lwip_setsockopt(socket_,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout))<0
               ||lwip_setsockopt(socket_,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout))<0
               ||lwip_fcntl(socket_,F_SETFL,originalFlags_)<0){fail();return State::failed;}
            phase_=Phase::ready;
        }
        return State::ready;
    }
    // Transfers one raw socket only after readiness AND a fresh deadline check.
    // The caller immediately gives it to the public WiFiClient(fd) constructor.
    int take(uint64_t now) {
        if(phase_!=Phase::ready||socket_<0||now<lastPoll_||now>=deadline_) {fail();return -1;}
        const int result=socket_;socket_=-1;phase_=Phase::failed;started_=false;
        return result;
    }
    void cancel() {fail();started_=false;}
private:
    enum class Phase {pending,connected,ready,failed};
    static bool selectable(int socket) {
#ifdef LWIP_SELECT_MAXNFDS
        return socket>=LWIP_SOCKET_OFFSET&&socket<LWIP_SELECT_MAXNFDS;
#elif defined(LWIP_SOCKET_OFFSET)
        return socket>=LWIP_SOCKET_OFFSET&&socket-LWIP_SOCKET_OFFSET<FD_SETSIZE;
#else
        return socket>=0&&socket<FD_SETSIZE;
#endif
    }
    bool fail() {
        if(socket_>=0){lwip_close(socket_);socket_=-1;}
        phase_=Phase::failed;return false;
    }
    int socket_=-1,originalFlags_=0;
    uint64_t lastPoll_=0,deadline_=0;
    Phase phase_=Phase::failed;
    bool started_=false;
};
}
#endif
