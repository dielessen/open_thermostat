#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include "DeadlineWrite.h"
#include "SocketWriteBudget.h"
#include <WiFiClient.h>
#include <lwip/sockets.h>
#include <esp_timer.h>
#include <cerrno>

namespace heating::control {
// The existing PubSubClient still frames MQTT and owns this ONE connection.
// Actuator publishes retain their original one-handoff deadline contract.
// Ordinary MQTT writes have a separate total latency bound on this same socket.
class DeadlineWiFiClient final:public WiFiClient {
public:
    using WiFiClient::write;
    // PubSubClient may otherwise fall back to synchronous connect if the peer
    // closes between our ready check and its handshake. Product TCP admission
    // is exclusively the cooperative preconnect path on this same connection.
    int connect(IPAddress,uint16_t)override{return 0;}
    int connect(IPAddress,uint16_t,int32_t)override{return 0;}
    int connect(const char*,uint16_t)override{return 0;}
    int connect(const char*,uint16_t,int32_t)override{return 0;}
    bool adoptConnectedSocket(int socket) {
        if(socket<0)return false;
        if(deadline_.active()){lwip_close(socket);return false;}
        // Public SDK accepted-socket constructor + shared-handle assignment.
        // Consumes the unique raw socket; no duplicate descriptor or new SYN.
        WiFiClient ready(socket);WiFiClient::operator=(ready);
        if(!connected()){stop();return false;}
        return true;
    }
    bool beginDeadlineWrite(DeadlineWrite::Check check){return deadline_.begin(std::move(check));}
    bool finishDeadlineWrite(){return deadline_.finish();}
    size_t write(uint8_t value)override{return write(&value,1);}
    size_t write(const uint8_t* bytes,size_t size)override {
        if(!deadline_.active()) {
            if(!size)return 0;
            const auto result=SocketWriteBudget::write(bytes,size,
                []{return static_cast<uint64_t>(esp_timer_get_time()/1000);},
                [this](const uint8_t* data,size_t length)->std::ptrdiff_t {
                    const int socket=fd();if(socket<0)return -1;
                    const auto count=::send(socket,data,length,MSG_DONTWAIT);
                    if(count<0&&(errno==EAGAIN||errno==EWOULDBLOCK||errno==EINTR))return 0;
                    return count>0?count:-1;
                },[]{delay(1);});
            if(!result.complete) {
                // A partial or late MQTT frame cannot precede another packet.
                // Failed return is an uncertain outcome, never proof of no IO.
                socketBudgetDisconnects.fetch_add(1,std::memory_order_relaxed);
                stop();return 0;
            }
            return result.written;
        }
        return deadline_.write(bytes,size,[this](const uint8_t* data,size_t length)->size_t {
            const int socket=fd();
            if(socket<0)return 0;
            const auto result=::send(socket,data,length,MSG_DONTWAIT);
            return result>0?static_cast<size_t>(result):0;
        });
    }
private:
    DeadlineWrite deadline_;
};
}
#endif
