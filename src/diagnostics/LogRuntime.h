#pragma once
#include "SystemLog.h"
#include "LogStorage.h"
#include <esp_system.h>
#include <esp_timer.h>
#include <lwip/sockets.h>
#include <lwip/inet.h>
#include <fcntl.h>
namespace heating::diagnostics {
inline uint64_t uptimeMs(){return uint64_t(esp_timer_get_time())/1000;}
class LogRuntime {
public:
    SystemLog log;
    uint32_t boot=0;
    bool storageReady=false;
    void begin() {
        boot=esp_random();const auto saved=loadSettings();storageReady=bool(saved);
        log.configure(saved?*saved:Settings{});setConnected(false);
    }
    bool save(const Settings& s) {
        if(!saveSettings(s))return false;
        log.configure(s);storageReady=true;lastMark_=uptimeMs();closeSocket();return true;
    }
    void poll(bool connected,const char* hostname) {
        if(!connected||!log.syslogEnabled()){setConnected(false);closeSocket();return;}
        const auto settings=log.settings();
        if(!settings.enabled){setConnected(false);closeSocket();return;}
        setConnected(true);
        const auto now=uptimeMs();
        if(settings.markSeconds&&now-lastMark_>=uint64_t(settings.markSeconds)*1000){
            lastMark_=now;log.append(3,"Syslog","MARK",now);
        }
        if(now-lastSend_<100)return;
        lastSend_=now;Record record;Settings destination;
        if(!log.pop(record,destination))return;
        if(socket_<0){socket_=lwip_socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);if(socket_>=0&&lwip_fcntl(socket_,F_SETFL,O_NONBLOCK)<0)closeSocket();}
        if(socket_<0){log.sent(false);return;}
        sockaddr_in address{};address.sin_family=AF_INET;address.sin_port=htons(destination.port);
        address.sin_addr.s_addr=inet_addr(destination.server.data());
        const auto message=rfc5424(record,hostname?hostname:"");
        const auto bytes=lwip_sendto(socket_,message.data(),message.size(),MSG_DONTWAIT,reinterpret_cast<sockaddr*>(&address),sizeof(address));
        log.sent(bytes==int(message.size()));
        // UDP acceptance is not server acknowledgement. No retries/backlog replay.
        if(bytes<0)closeSocket();
    }
private:
    // This serialized runtime is the only firmware owner of log reachability.
    // Do not repeatedly lock/flush the queue for an unchanged network state.
    enum class LinkState {unknown,offline,online};
    LinkState linkState_=LinkState::unknown;
    int socket_=-1;
    uint64_t lastSend_=0,lastMark_=0;
    void setConnected(bool connected){
        const auto next=connected?LinkState::online:LinkState::offline;
        if(linkState_==next)return;
        if(connected)log.online();else log.offline();
        linkState_=next;
    }
    void closeSocket(){if(socket_>=0){lwip_close(socket_);socket_=-1;}}
};
inline LogRuntime runtime;
}
