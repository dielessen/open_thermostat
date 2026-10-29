#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>
#ifdef OPENTHERMOSTAT_E32V2
#include <lwip/sockets.h>
#endif
namespace heating::diagnostics {
// ICMP echo bytes (RFC 792) for the gateway liveness probe. A raw IPv4 socket
// receives the IP header in front of the ICMP message.
struct IcmpEcho {
    static constexpr size_t size = 16; // 8-byte header + 8 payload bytes
    static void request(uint8_t (&b)[size], uint16_t id, uint16_t seq) {
        b[0] = 8; b[1] = b[2] = b[3] = 0; // echo request, checksum filled below
        b[4] = id >> 8; b[5] = id & 0xFF; b[6] = seq >> 8; b[7] = seq & 0xFF;
        for (size_t i = 8; i < size; ++i) b[i] = static_cast<uint8_t>(i);
        const uint16_t sum = checksum(b, size);
        b[2] = sum >> 8; b[3] = sum & 0xFF;
    }
    // source: IPv4 address as stored in s_addr (network order).
    static bool isReply(const uint8_t* p, size_t n, uint32_t source, uint16_t id, uint16_t seq) {
        if (n < 20 || (p[0] >> 4) != 4 || p[9] != 1 || std::memcmp(p + 12, &source, 4) != 0) return false;
        const size_t ihl = (p[0] & 0x0Fu) * 4u, total = static_cast<size_t>(p[2] << 8 | p[3]);
        if (ihl < 20 || total > n || total < ihl + 8) return false;
        const uint8_t* m = p + ihl;
        return m[0] == 0 && m[1] == 0 && (m[4] << 8 | m[5]) == id && (m[6] << 8 | m[7]) == seq
            && checksum(m, total - ihl) == 0;
    }
    static uint16_t checksum(const uint8_t* p, size_t n) {
        uint32_t sum = 0;
        for (size_t i = 0; i + 1 < n; i += 2) sum += static_cast<uint32_t>(p[i] << 8 | p[i + 1]);
        if (n & 1) sum += static_cast<uint32_t>(p[n - 1] << 8);
        while (sum >> 16) sum = (sum & 0xFFFF) + (sum >> 16);
        return static_cast<uint16_t>(~sum);
    }
};

#ifdef OPENTHERMOSTAT_E32V2
// Proves the IP path while Wi-Fi reports "connected": one ICMP echo to the
// gateway every 30 s, polled from the loop without waiting. Only lwIP socket
// calls that the build already links (sockets.c, raw.c, icmp.c are reviewed);
// no esp_ping/ping_sock. Results feed SupervisorPolicy::networkDead.
class GatewayProbe {
public:
    static constexpr uint64_t periodMs = 30000, timeoutMs = 2000;
    static constexpr uint16_t id = 0x4F54; // "OT"
    enum class Result : uint8_t { none, ok, failed };
    bool due(uint64_t now) const { return socket_ < 0 && now >= next_; }
    // gateway in network order; a send error counts as a failed probe.
    Result start(uint64_t now, uint32_t gateway) {
        cancel();
        next_ = now + periodMs; deadline_ = now + timeoutMs; gateway_ = gateway; ++seq_;
        if (!gateway) return finish(Result::failed);
        socket_ = lwip_socket(AF_INET, SOCK_RAW, IPPROTO_ICMP);
        if (socket_ < 0) return finish(Result::failed);
        uint8_t echo[IcmpEcho::size];
        IcmpEcho::request(echo, id, seq_);
        sockaddr_in to{}; to.sin_family = AF_INET; to.sin_addr.s_addr = gateway;
        if (lwip_sendto(socket_, echo, sizeof(echo), 0, reinterpret_cast<sockaddr*>(&to), sizeof(to)) != static_cast<int>(sizeof(echo)))
            return finish(Result::failed);
        return Result::none;
    }
    Result poll(uint64_t now) {
        if (socket_ < 0) return Result::none;
        uint8_t buf[96]; // IP header with options + our reply; other ICMP is skipped
        for (int i = 0; i < 4; ++i) {
            const int n = lwip_recvfrom(socket_, buf, sizeof(buf), MSG_DONTWAIT, nullptr, nullptr);
            if (n <= 0) break;
            if (IcmpEcho::isReply(buf, static_cast<size_t>(n), gateway_, id, seq_)) return finish(Result::ok);
        }
        return now >= deadline_ ? finish(Result::failed) : Result::none;
    }
    void cancel() { if (socket_ >= 0) { lwip_close(socket_); socket_ = -1; } }
    uint32_t failures() const { return failures_; }
    void resetFailures() { failures_ = 0; }
private:
    Result finish(Result r) {
        cancel();
        failures_ = r == Result::ok ? 0 : failures_ + 1;
        return r;
    }
    int socket_ = -1;
    uint64_t next_ = 0, deadline_ = 0;
    uint32_t gateway_ = 0, failures_ = 0;
    uint16_t seq_ = 0;
};
#endif
}
