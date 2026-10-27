#pragma once
#ifdef OPENTHERMOSTAT_E32V2
#include <lwip/dns.h>
#include <lwip/tcpip.h>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <string_view>

namespace heating::control {
// One lookup lease on the existing lwIP resolver. Owner methods are serialized
// on the product task. Native callbacks run on tcpip_thread and never hold an
// owner pointer. No worker task, socket, private DNS cache or blocking queue post.
class AsyncBrokerDns final {
public:
    static constexpr size_t maximumHostBytes=253;
    static constexpr size_t slotCount=4;
    static constexpr uint64_t timeoutMs=16000;
    enum class State { pending,ready,failed };
    struct Result { State state; uint32_t ipv4; };
    AsyncBrokerDns()=default;
    AsyncBrokerDns(const AsyncBrokerDns&)=delete;
    AsyncBrokerDns& operator=(const AsyncBrokerDns&)=delete;
    ~AsyncBrokerDns(){cancel();}

    bool started()const{return started_;}
    bool start(std::string_view host,uint64_t now) {
        cancel();started_=true;startedAt_=lastPoll_=now;
        if(host.empty()||host.size()>maximumHostBytes||host.find('\0')!=std::string_view::npos)return false;
        for(const unsigned char c:host)if(c<=32||c>=127)return false;
        static_assert(maximumHostBytes<DNS_MAX_NAME_LENGTH);
        for(auto& candidate:slots_) {
            // A retired lease stays reserved until the native callback's last
            // access. A delayed callback cannot write into a replacement owner.
            if(candidate.pending.load(std::memory_order_acquire))continue;
            bool unused=false;
            if(!candidate.active.compare_exchange_strong(unused,true,std::memory_order_acq_rel))continue;
            slot_=&candidate;
            candidate.phase.store(Phase::pending,std::memory_order_relaxed);
            std::memcpy(candidate.host,host.data(),host.size());candidate.host[host.size()]='\0';
            candidate.pending.store(true,std::memory_order_release);
            if(tcpip_try_callback(query,&candidate)==ERR_OK)return true;
            // An unsuccessful try-post cannot have queued the callback.
            candidate.pending.store(false,std::memory_order_release);
            candidate.active.store(false,std::memory_order_release);slot_=nullptr;
            return false;
        }
        return false; // Fixed pool exhaustion fails immediately, never grows.
    }
    Result poll(uint64_t now) {
        if(!slot_)return {State::failed,0};
        // Neither progress nor repeated polls renew the original deadline.
        if(now<lastPoll_||now-startedAt_>=timeoutMs) {
            retireSlot();return {State::failed,0};
        }
        lastPoll_=now;
        switch(slot_->phase.load(std::memory_order_acquire)) {
            case Phase::ready:return {State::ready,slot_->address};
            case Phase::failed:return {State::failed,0};
            default:return {State::pending,0};
        }
    }
    void cancel() {retireSlot();started_=false;}
private:
    enum class Phase:uint32_t {pending,ready,failed};
    struct Slot {
        std::atomic<bool> active{false},pending{false};
        std::atomic<Phase> phase{Phase::pending};
        char host[maximumHostBytes+1]{};
        uint32_t address=0;
    };
    // Outlives every transport and every DNS callback, including retired owners.
    // No slot is reused while a queued query or native DNS callback can use it.
    static Slot slots_[slotCount];
    static void finish(Slot& slot,const ip_addr_t* address) {
        if(slot.active.load(std::memory_order_acquire)) {
            const uint32_t value=address&&IP_IS_V4(address)?ip4_addr_get_u32(ip_2_ip4(address)):0;
            slot.address=value;
            slot.phase.store(value?Phase::ready:Phase::failed,std::memory_order_release);
        }
        // MUST be the final slot access. Main may now reuse a retired slot.
        slot.pending.store(false,std::memory_order_release);
    }
    static void found(const char*,const ip_addr_t* address,void* context) {
        finish(*static_cast<Slot*>(context),address);
    }
    static void query(void* context) {
        auto& slot=*static_cast<Slot*>(context);
        // Acquire the immutable hostname before accessing it on tcpip_thread.
        if(!slot.pending.load(std::memory_order_acquire))return;
        if(!slot.active.load(std::memory_order_acquire)) {
            slot.pending.store(false,std::memory_order_release);return;
        }
        ip_addr_t cached{};
        const auto status=dns_gethostbyname_addrtype(slot.host,&cached,found,&slot,LWIP_DNS_ADDRTYPE_IPV4);
        // ERR_INPROGRESS owns the final access through found(), including the
        // SDK's possible synchronous error callback during dns_enqueue().
        if(status!=ERR_INPROGRESS)finish(slot,status==ERR_OK?&cached:nullptr);
    }
    void retireSlot() {
        if(slot_)slot_->active.store(false,std::memory_order_release);
        slot_=nullptr;
    }
    Slot* slot_=nullptr;
    uint64_t startedAt_=0,lastPoll_=0;
    bool started_=false;
};
inline AsyncBrokerDns::Slot AsyncBrokerDns::slots_[AsyncBrokerDns::slotCount];
}
#endif
