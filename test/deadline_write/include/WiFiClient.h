#pragma once
#include <cstddef>
#include <cstdint>
#include <sys/socket.h>
// Public-API fixture only, NOT replacement SDK firmware. Real sockets below.
class WiFiClient {
public:
    virtual ~WiFiClient()=default;
    virtual size_t write(uint8_t value){return write(&value,1);}
    virtual size_t write(const uint8_t* bytes,size_t size){
        ++ordinaryWrites;const auto n=::send(socket_,bytes,size,MSG_DONTWAIT|MSG_NOSIGNAL);return n>0?static_cast<size_t>(n):0;
    }
    virtual int fd()const{return socket_;}
    void fixtureSocket(int socket){socket_=socket;}
    int ordinaryWrites=0;
private:
    int socket_=-1;
};
