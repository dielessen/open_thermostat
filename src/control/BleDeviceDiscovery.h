#pragma once
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <ostream>
#include "control/JsonString.h"

namespace heating::control {
// Discovery hints only. A full list never prevents processing a configured sensor.
// Fixed memory: nearby advertisers cannot grow the heap for the lifetime of boot.
class BleDeviceDiscovery {
public:
    using Address = std::array<uint8_t,6>;
    static constexpr std::size_t capacity = 128;
    struct Hint { std::array<char,41> name{}; bool completeName = false; int rssi = -127; };
    const Hint& hint(std::size_t index) const { return hints_[index]; }
    // Advertisement names are untrusted hints, never a model or identity proof.
    bool remember(const Address& address, int rssi = -127, const uint8_t* data = nullptr, std::size_t length = 0) {

        auto at = std::lower_bound(begin(),end(),address);
        const auto index = static_cast<std::size_t>(at-begin());
        if (at != end() && *at == address) { update(hints_[index],rssi,data,length); return true; }
        if (size_ == capacity) { overflowed_ = true; return false; }
        std::move_backward(hints_.begin()+index,hints_.begin()+size_,hints_.begin()+size_+1);
        hints_[index] = {};
        update(hints_[index],rssi,data,length);
        std::move_backward(at,end(),end()+1);
        *at = address;
        ++size_;
        return true;
    }
    void clear() { addresses_={}; hints_={}; size_=0; overflowed_=false; }
    std::size_t size() const { return size_; }
    bool overflowed() const { return overflowed_; }
    // A status response shows at most this many hints, strongest signal first:
    // the 5 s Bluetooth poll stays a few KB and never builds a 128-entry tree.
    static constexpr std::size_t shown = 32;
    void writeJson(std::ostream& out) const {
        std::array<uint8_t,capacity> order{};
        for (std::size_t i = 0; i < size_; ++i) order[i] = static_cast<uint8_t>(i);
        const auto count = std::min(shown,size_);
        std::partial_sort(order.begin(),order.begin()+count,order.begin()+size_,
            [this](uint8_t a, uint8_t b) { return hints_[a].rssi > hints_[b].rssi || (hints_[a].rssi == hints_[b].rssi && a < b); });
        const auto hex = [&](std::size_t i) {
            constexpr char digits[] = "0123456789abcdef";
            out.put('"'); for (auto byte : addresses_[i]) { out.put(digits[byte >> 4]); out.put(digits[byte & 15]); } out.put('"');
        };
        out << "\"discovery_full\":" << (overflowed_ || size_ > shown ? "true" : "false")
            << ",\"discovery_capacity\":" << shown << ",\"nearby\":[";
        for (std::size_t i = 0; i < count; ++i) { if (i) out.put(','); hex(order[i]); }
        out << "],\"nearby_devices\":[";
        for (std::size_t i = 0; i < count; ++i) {
            const auto& hint = hints_[order[i]];
            out << (i ? ",{\"address\":" : "{\"address\":"); hex(order[i]);
            out << ",\"name\":"; writeJsonString(out, hint.name.data());
            out << ",\"rssi\":" << hint.rssi << '}';
        }
        out.put(']');
    }
    std::array<Address,capacity>::const_iterator begin() const { return addresses_.begin(); }
    std::array<Address,capacity>::const_iterator end() const { return addresses_.begin()+size_; }
    std::array<Address,capacity>::iterator begin() { return addresses_.begin(); }
    std::array<Address,capacity>::iterator end() { return addresses_.begin()+size_; }
private:
    static void update(Hint& hint, int rssi, const uint8_t* data, std::size_t length) {
        hint.rssi = std::max(-127,std::min(20,rssi));
        if(!data) return;
        for(std::size_t pos=0;pos<length;) {
            const auto size=data[pos];
            if(!size || size>length-pos-1) break;
            const auto type=data[pos+1];
            if((type==9 || (type==8 && !hint.completeName)) && size>1) {
                // Preserve valid UTF-8 sequences and omit controls / malformed bytes.
                std::array<char,41> name{}; std::size_t out=0;
                for(std::size_t i=pos+2;i<pos+size+1;) {
                    const auto c=data[i];
                    std::size_t n=c<0x80?1:c>=0xc2&&c<=0xdf?2:c>=0xe0&&c<=0xef?3:c>=0xf0&&c<=0xf4?4:0;
                    bool valid=n && i+n<=pos+size+1;
                    for(std::size_t j=1;valid&&j<n;++j)valid=(data[i+j]&0xc0)==0x80;
                    if(valid&&n>=3)valid=!(c==0xe0&&data[i+1]<0xa0)&&!(c==0xed&&data[i+1]>=0xa0)&&!(c==0xf0&&data[i+1]<0x90)&&!(c==0xf4&&data[i+1]>=0x90);
                    if(!valid){++i;continue;}
                    if(c>=0x20&&c!=0x7f){if(out+n>40)break;for(std::size_t j=0;j<n;++j)name[out++]=static_cast<char>(data[i+j]);}
                    i+=n;
                }
                const bool visible=std::any_of(name.begin(),name.begin()+out,[](char c){return c!=' ';});
                if(visible){hint.name=name;hint.completeName=type==9;}
                if(type==9&&visible)break;
            }
            pos+=size+1;
        }
    }
    std::array<Hint,capacity> hints_{};
    std::array<Address,capacity> addresses_{};
    std::size_t size_ = 0;
    bool overflowed_ = false;
};
static_assert(sizeof(BleDeviceDiscovery)<=7000,"BLE discovery memory budget changed");
}
