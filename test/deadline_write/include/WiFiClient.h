#pragma once
#include <cstddef>
#include <cstdint>
#include <sys/socket.h>
#include <chrono>
#include <thread>
inline void delay(uint32_t ms){std::this_thread::sleep_for(std::chrono::milliseconds(ms));}
// Public-API fixture only, NOT replacement SDK firmware. Real sockets below.
class WiFiClient {
public:
    virtual ~WiFiClient()=default;
    virtual size_t write(uint8_t value){return write(&value,1);}
    virtual size_t write(const uint8_t* bytes,size_t size){
        ++ordinaryWrites;const auto n=::send(socket_,bytes,size,MSG_DONTWAIT|MSG_NOSIGNAL);return n>0?static_cast<size_t>(n):0;
    }
    virtual int fd()const{return socket_;}
    virtual void stop(){if(socket_>=0)::shutdown(socket_,SHUT_RDWR);socket_=-1;}
    void fixtureSocket(int socket){socket_=socket;}
    int ordinaryWrites=0;
private:
    int socket_=-1;
};
