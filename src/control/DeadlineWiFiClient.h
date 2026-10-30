#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include "DeadlineWrite.h"
#include "MqttOutbox.h"
#include <WiFiClient.h>
#include <lwip/sockets.h>
#include <esp_timer.h>
#include <cerrno>
#include <cstdlib>
#include <string>
#if __has_include(<esp_heap_caps.h>)
#include <esp_heap_caps.h>
#endif

namespace heating::control {
// The existing PubSubClient still frames MQTT and owns this ONE connection.
// Actuator publishes retain their original one-handoff deadline contract.
// Ordinary MQTT writes go to the outbox (MqttOutbox.h): write() returns once
// the whole frame is queued, poll()/write() drain it nonblocking, and only a
// real stall (no byte for 15 s) or a socket error closes the session.
class DeadlineWiFiClient final:public WiFiClient {
public:
    static constexpr size_t outboxBytes=24576,controlReserve=9216,telemetryHighWater=8192;
    DeadlineWiFiClient() {
        // Once, from PSRAM (internal RAM only without PSRAM); never per frame.
#if __has_include(<esp_heap_caps.h>)
        arena_=static_cast<uint8_t*>(heap_caps_malloc(outboxBytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
        if(!arena_)arena_=static_cast<uint8_t*>(heap_caps_malloc(outboxBytes,MALLOC_CAP_8BIT));
#else
        arena_=static_cast<uint8_t*>(std::malloc(outboxBytes));
#endif
        outbox_.attach(arena_,outboxBytes,controlReserve,telemetryHighWater);
    }
    ~DeadlineWiFiClient()override{
#if __has_include(<esp_heap_caps.h>)
        heap_caps_free(arena_);
#else
        std::free(arena_);
#endif
    }
    DeadlineWiFiClient(const DeadlineWiFiClient&)=delete;
    DeadlineWiFiClient& operator=(const DeadlineWiFiClient&)=delete;
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
        outbox_.clear(); // A new session never sends an old session's frames.
        // Public SDK accepted-socket constructor + shared-handle assignment.
        // Consumes the unique raw socket; no duplicate descriptor or new SYN.
        WiFiClient ready(socket);WiFiClient::operator=(ready);
        if(!connected()){stop();return false;}
        return true;
    }
    // PUBLISH topics under this prefix are classified by mqttTopicClass; all else is control.
    void setTopicPrefix(std::string prefix){prefix_=std::move(prefix);}
    // A deadline write never interleaves with queued bytes: drain first, and
    // refuse (no IO, no disconnect) while a frame is half sent or session frames wait.
    bool beginDeadlineWrite(DeadlineWrite::Check check){
        if(!deadline_.active()&&!drain())return false;
        if(!outbox_.idleForDeadline())return false;
        return deadline_.begin(std::move(check));
    }
    bool finishDeadlineWrite(){return deadline_.finish();}
    // MQTT loop: drain a slice; close only on a real stall or a socket error.
    void poll(){if(drain()&&fd()>=0&&outbox_.stalled(now()))fail(MqttCounters::stalledDisconnects);}
    bool acceptsTelemetry()const{return outbox_.acceptsTelemetry();}
    const MqttOutbox& outbox()const{return outbox_;}
    // fw/heartbeat: the largest queue and the slowest frame since the last call.
    void takeWindow(size_t& peakBytes,uint32_t& latencyMaxMs){peakBytes=outbox_.peak();latencyMaxMs=windowLatencyMax_;outbox_.resetPeak();windowLatencyMax_=0;}
    int available()override{if(!outbox_.empty())drain();return WiFiClient::available();}
    // PubSubClient's DISCONNECT and the offline notice get one short chance.
    // A failure seen here (the peer already left) is not a write-path disconnect.
    void stop()override{
        stopping_=true;
        if(!deadline_.active())for(const auto until=now()+20;!outbox_.empty()&&fd()>=0&&now()<until&&drain();)delay(1);
        stopping_=false;outbox_.clear();WiFiClient::stop();
    }
    size_t write(uint8_t value)override{return write(&value,1);}
    size_t write(const uint8_t* bytes,size_t size)override {
        if(!deadline_.active()) {
            if(!size||!bytes||fd()<0)return 0;
            std::string_view topic;bool coalesce=false;auto cls=MqttOutbox::control;
            if(MqttOutbox::parse(bytes,size,topic)&&!prefix_.empty()&&topic.substr(0,prefix_.size())==prefix_)
                cls=mqttTopicClass(topic.substr(prefix_.size()),coalesce);
            if(outbox_.push(bytes,size,cls,coalesce,now())==MqttOutbox::Push::rejected) {
                // The whole frame is refused (full, malformed or partial): the stream stays intact.
                MqttCounters::rejected.fetch_add(1,std::memory_order_relaxed);return 0;
            }
            const auto queued=static_cast<uint32_t>(outbox_.bytes());
            if(queued>MqttCounters::peakBytes.load(std::memory_order_relaxed))MqttCounters::peakBytes.store(queued,std::memory_order_relaxed);
            drain();
            return size;
        }
        return deadline_.write(bytes,size,[this](const uint8_t* data,size_t length)->size_t {
            const int socket=fd();
            if(socket<0)return 0;
            const auto result=::send(socket,data,length,MSG_DONTWAIT);
            return result>0?static_cast<size_t>(result):0;
        });
    }
private:
    static uint64_t now(){return static_cast<uint64_t>(esp_timer_get_time()/1000);}
    // false: the socket failed and is closed.
    bool drain() {
        if(outbox_.empty()||deadline_.active())return true;
        const auto result=outbox_.pump([this](const uint8_t* data,size_t length)->std::ptrdiff_t {
            const int socket=fd();if(socket<0)return -1;
            const auto count=::send(socket,data,length,MSG_DONTWAIT);
            if(count<0&&(errno==EAGAIN||errno==EWOULDBLOCK||errno==EINTR))return 0;
            return count>0?count:-1;
        },now,[this](size_t bytes,uint64_t latency,bool){
            MqttCounters::frames.fetch_add(1,std::memory_order_relaxed);
            MqttCounters::bytes.fetch_add(static_cast<uint32_t>(bytes),std::memory_order_relaxed);
            const auto ms=static_cast<uint32_t>(latency>UINT32_MAX?UINT32_MAX:latency);
            MqttCounters::latencySumMs.fetch_add(ms,std::memory_order_relaxed);
            if(ms>windowLatencyMax_)windowLatencyMax_=ms;
            if(ms>MqttCounters::latencyMaxMs.load(std::memory_order_relaxed))MqttCounters::latencyMaxMs.store(ms,std::memory_order_relaxed);
        });
        if(result!=MqttOutbox::Pump::error)return true;
        fail(MqttCounters::socketErrorDisconnects);return false;
    }
    // A half-sent frame cannot be followed by another packet: close the socket.
    void fail(std::atomic<uint32_t>& reason){if(!stopping_)reason.fetch_add(1,std::memory_order_relaxed);outbox_.clear();WiFiClient::stop();}
    DeadlineWrite deadline_;
    MqttOutbox outbox_;
    uint8_t* arena_=nullptr;
    std::string prefix_;
    bool stopping_=false;
    uint32_t windowLatencyMax_=0;
};
}
#endif
