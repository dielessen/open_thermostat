#pragma once
#include <cstddef>
#include <cstdint>
#include <sys/socket.h>
#include <chrono>
#include <thread>
#include <memory>
#include <unistd.h>
#include <cerrno>
#include <sys/ioctl.h>
#include "Client.h"
inline void delay(uint32_t ms){std::this_thread::sleep_for(std::chrono::milliseconds(ms));}
// Public-API fixture only, NOT replacement SDK firmware. Real sockets below.
class WiFiClient:public Client {
public:
    WiFiClient()=default;
    explicit WiFiClient(int socket):owned_(std::make_shared<Handle>(socket)){}
    WiFiClient& operator=(const WiFiClient& other){if(this!=&other){stop();owned_=other.owned_;socket_=other.socket_;}return *this;}
    virtual ~WiFiClient()=default;
    virtual int connect(IPAddress,uint16_t){++synchronousConnects;return 0;}
    virtual int connect(IPAddress,uint16_t,int32_t){++synchronousConnects;return 0;}
    virtual int connect(const char*,uint16_t){++synchronousConnects;return 0;}
    virtual int connect(const char*,uint16_t,int32_t){++synchronousConnects;return 0;}
    virtual size_t write(uint8_t value){return write(&value,1);}
    virtual size_t write(const uint8_t* bytes,size_t size){
        ++ordinaryWrites;const auto n=::send(fd(),bytes,size,MSG_DONTWAIT|MSG_NOSIGNAL);return n>0?static_cast<size_t>(n):0;
    }
    virtual int fd()const{return owned_?owned_->socket:socket_;}
    virtual void stop(){owned_.reset();if(socket_>=0)::shutdown(socket_,SHUT_RDWR);socket_=-1;}
    virtual uint8_t connected(){if(fd()<0)return false;char byte;const auto count=::recv(fd(),&byte,1,MSG_PEEK|MSG_DONTWAIT);return count>0||(count<0&&(errno==EAGAIN||errno==EWOULDBLOCK));}
    int available()override{int bytes=0;return fd()>=0&&::ioctl(fd(),FIONREAD,&bytes)==0?bytes:0;}
    int read()override{uint8_t byte;return read(&byte,1)==1?byte:-1;}
    int read(uint8_t* bytes,size_t size)override{return ::recv(fd(),bytes,size,MSG_DONTWAIT);}
    int peek()override{uint8_t byte;return ::recv(fd(),&byte,1,MSG_PEEK|MSG_DONTWAIT)==1?byte:-1;}
    void flush()override{}
    operator bool()override{return connected();}
    void fixtureSocket(int socket){stop();socket_=socket;}
    int ordinaryWrites=0,synchronousConnects=0;
private:
    struct Handle {explicit Handle(int value):socket(value){} ~Handle(){::close(socket);}int socket;};
    std::shared_ptr<Handle> owned_;
    int socket_=-1;
};
