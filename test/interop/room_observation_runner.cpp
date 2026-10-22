// Finite source-only fixture: actual EMS parser + EmsMetrics serializers.
// Room body is explicitly synthetic; no broker/controller/device is invoked.
#include "EmsMetrics.h"
#include <iostream>
#include <map>
using namespace heating::ems;
struct Peer {
    uint64_t now=1000000;
    std::map<uint16_t,std::function<void(const EmsTelegram&)>> callbacks;
    EmsMetrics metrics;
    explicit Peer(char boot):metrics([this](uint16_t id,auto fn){callbacks[id]=fn;},
        [this]{return now;},std::string(32,boot)) {}
    void frame(unsigned flags=3) {
        EmsTelegram telegram(EmsTelegram::BROADCAST,8,0,6,0xE4,
            std::vector<uint8_t>{60,2,88,0,50,static_cast<uint8_t>(flags)});
        const auto raw=telegram.encodeToRawDataWithCRC();
        callbacks.at(0xE4)(EmsTelegram::fromRawData(raw.data(),raw.size()));
    }
    void row(unsigned local,unsigned age=0) {
        std::cout<<"{\"at\":"<<local<<",\"room\":{\"roomObservation\":";
        metrics.getRoomContext(std::cout);
        std::cout<<",\"rooms\":[{\"id\":\"a1b2c3d4\",\"currentTemp\":2000,\"currentTempAgeMs\":"
            <<age<<",\"isBeingHeatedState\":\"on\"}]},\"ems\":{\"roomEstimateObservation\":";
        metrics.getRoomObservation(std::cout);std::cout<<"}}";
    }
};
int main() {
    Peer a('a');a.frame();std::cout<<"[";a.row(0);
    a.now+=10000;std::cout<<",";a.row(10,10000);
    a.now+=19000;std::cout<<",";a.row(29,29000);
    a.now+=1000;std::cout<<",";a.row(30,30000);
    a.now+=1000;a.frame(0);std::cout<<",";a.row(31,31000);
    Peer b('b');b.now=1000;b.frame();std::cout<<",";b.row(32);
    std::cout<<"]\n";return 0;
}
