#pragma once
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>

namespace heating::control {
// Discovery hints only. A full list never prevents processing a configured sensor.
// Fixed memory: nearby advertisers cannot grow the heap for the lifetime of boot.
class BleDeviceDiscovery {
public:
    using Address = std::array<uint8_t,6>;
    static constexpr std::size_t capacity = 32;
    bool remember(const Address& address) {
        auto at = std::lower_bound(begin(),end(),address);
        if (at != end() && *at == address) return true;
        if (size_ == capacity) { overflowed_ = true; return false; }
        std::move_backward(at,end(),end()+1);
        *at = address;
        ++size_;
        return true;
    }
    std::size_t size() const { return size_; }
    bool overflowed() const { return overflowed_; }
    std::array<Address,capacity>::const_iterator begin() const { return addresses_.begin(); }
    std::array<Address,capacity>::const_iterator end() const { return addresses_.begin()+size_; }
    std::array<Address,capacity>::iterator begin() { return addresses_.begin(); }
    std::array<Address,capacity>::iterator end() { return addresses_.begin()+size_; }
private:
    std::array<Address,capacity> addresses_{};
    std::size_t size_ = 0;
    bool overflowed_ = false;
};
static_assert(sizeof(BleDeviceDiscovery)<=208,"BLE discovery memory budget changed");
}
