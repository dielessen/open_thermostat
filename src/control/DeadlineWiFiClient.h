#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include "DeadlineWrite.h"
#include <WiFiClient.h>
#include <lwip/sockets.h>

namespace heating::control {
// The existing PubSubClient still frames MQTT and owns this ONE connection.
// Only an explicit actuator publish changes write behavior, synchronously.
// Ordinary shadow traffic keeps the pinned WiFiClient implementation.
class DeadlineWiFiClient final:public WiFiClient {
public:
    using WiFiClient::write;
    bool beginDeadlineWrite(DeadlineWrite::Check check){return deadline_.begin(std::move(check));}
    bool finishDeadlineWrite(){return deadline_.finish();}
    size_t write(uint8_t value)override{return write(&value,1);}
    size_t write(const uint8_t* bytes,size_t size)override {
        if(!deadline_.active())return WiFiClient::write(bytes,size);
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
