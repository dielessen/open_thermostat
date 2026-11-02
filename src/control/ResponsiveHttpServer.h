#pragma once
#include "control/HttpRequestBounds.h"
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <string>
#include <utility>

namespace heating::control {
// The parser's view of the request: first the bytes ResponsiveHttpServer already
// read (the head, or the whole of a small request), then the socket, with an
// overall deadline. After the deadline, or once the sender is gone with nothing
// left, the request has ended: no data, not connected and no wait per read
// (Io::noWait: Stream timeout 0). Inside a multipart body the parser then reads
// a closing boundary instead, because each of its form loops waits for a boundary
// line and would otherwise spin forever on an unterminated field.
// synthesized(): those closing bytes were used; the request is then not handled.
template<class Client, class Io>
class DeadlineClient : public Client {
public:
    DeadlineClient(const Client &client, std::string prefix, uint32_t start, uint32_t limitMs, const std::string &boundary)
        : Client(client), prefix_(std::move(prefix)), start_(start), limit_(limitMs),
          closing_(boundary.empty() ? std::string()
                   : "\r\n--" + boundary + "--\r\nContent-Disposition: form-data; name=\"_\"\r\n\r\n") {}
    int available() override {
        const int kept = int(prefix_.size() - used_);
        return kept + (expired() ? 0 : std::max(Client::available(), 0));
    }
    int read() override {
        uint8_t byte = 0;
        return read(&byte, 1) == 1 ? byte : -1;
    }
    int read(uint8_t *buf, size_t size) override {
        if (!buf || !size) return 0;
        if (used_ < prefix_.size()) {
            const size_t n = std::min(size, prefix_.size() - used_);
            std::copy_n(prefix_.data() + used_, n, buf);
            used_ += n;
            return int(n);
        }
        if (!expired()) {
            const int got = Client::read(buf, size);
            if (got > 0) return got;
            if (got == 0 && Client::connected()) return 0;  // nothing yet: the parser waits (Stream timeout)
            end();                                          // the sender is gone
        }
        if (closing_.empty()) return 0;
        synthesized_ = true;
        for (size_t i = 0; i < size; ++i) buf[i] = uint8_t(closing_[next_++ % closing_.size()]);
        return int(size);
    }
    int peek() override {
        if (used_ < prefix_.size()) return (unsigned char)prefix_[used_];
        if (!expired()) return Client::peek();
        return closing_.empty() ? -1 : (unsigned char)closing_[next_ % closing_.size()];
    }
    uint8_t connected() override { return used_ < prefix_.size() || (!expired() && Client::connected()); }
    bool ended() const { return ended_; }
    bool synthesized() const { return synthesized_; }

private:
    bool expired() {
        if (!ended_ && uint32_t(millis() - start_) >= limit_) end();
        return ended_;
    }
    void end() { ended_ = true; Io::noWait(*this); }
    std::string prefix_;
    size_t used_ = 0;
    uint32_t start_, limit_;
    std::string closing_;
    size_t next_ = 0;
    bool ended_ = false, synthesized_ = false;
};

// The pinned single-client WebServer, with bounds before it parses (HttpRequestBounds.h):
// * no first byte within 250 ms: the connection is closed (an empty preconnection
//   otherwise blocks every queued request, including trial supervision, for 5 s);
// * the head is read here, without blocking, until complete: at most 4 KB within
//   10 s, while the loop keeps running; then refused (400/408/413/415/431) or admitted;
// * a request of at most 4 KB is read complete here as well, so the SDK parses it
//   from memory and never waits; larger bodies and uploads must pass admit (REST:
//   a signed-in session with its CSRF proof) and are parsed with an overall
//   deadline from the connection (10 s, uploads 10 min).
// Io: using Client = the SDK client type; static void noWait(Client&) sets the Stream timeout to 0.
template<class Server, class Io>
class ResponsiveHttpServer : public Server {
public:
    using Server::Server;
    using Client = typename Io::Client;
    static constexpr uint32_t initialDataWaitMs = 250;
    // 0: go on; else the HTTP status the request is refused with before parsing.
    using Admission = std::function<int(const HttpRequestHead &)>;
    void setAdmission(Admission admit) { admit_ = std::move(admit); }

    void handleClient() override {
        if (this->_currentStatus == HC_NONE) {
            this->_currentClient = this->_server.available();
            if (!this->_currentClient) {
                if (this->_nullDelay) delay(1);
                return;
            }
            this->_currentStatus = HC_WAIT_READ;
            this->_statusChange = millis();
            pending_ = Pending{};
        }
        // A closed client and the wait after a response stay with the SDK (it parses nothing then).
        if (this->_currentStatus != HC_WAIT_READ || !this->_currentClient.connected()) {
            Server::handleClient();
            if (this->_currentStatus == HC_NONE) pending_ = Pending{};
            return;
        }
        const uint32_t age = millis() - this->_statusChange;
        const bool late = age >= HttpRequestBounds::deadlineMs;
        if (!pending_.admitted) {
            const size_t room = HttpRequestBounds::maxHeadBytes - pending_.bytes.size();
            if (!take(room)) {
                if ((pending_.bytes.empty() && age >= initialDataWaitMs) || late) {
                    if (pending_.bytes.empty()) drop(); else refuse(408);
                }
                return;
            }
            HttpRequestHead head;
            const auto status = parseHttpRequestHead(pending_.bytes, head);
            if (status == HttpHeadStatus::incomplete) { if (late) refuse(408); return; }
            if (status != HttpHeadStatus::complete) { refuse(status == HttpHeadStatus::too_large ? 431 : 400); return; }
            int refusal = httpRequestRefusal(head);
            pending_.buffered = httpBufferedRequest(head);
            if (!refusal && !pending_.buffered && admit_) refusal = admit_(head);
            if (refusal) { refuse(refusal); return; }
            pending_.admitted = true;
            pending_.need = head.size + size_t(head.contentLength);
            pending_.limitMs = httpUploadRoute(head.path) ? HttpRequestBounds::uploadDeadlineMs : HttpRequestBounds::deadlineMs;
            pending_.boundary = head.multipart ? head.boundary : std::string();
        }
        if (pending_.buffered && pending_.bytes.size() < pending_.need) {
            take(pending_.need - pending_.bytes.size());
            if (pending_.bytes.size() < pending_.need) { if (late) refuse(408); return; }
        }
        parse();
    }

private:
    struct Pending {
        bool admitted = false, buffered = false;
        size_t need = 0;
        uint32_t limitMs = HttpRequestBounds::deadlineMs;
        std::string bytes, boundary;
    };
    // Reads what has arrived (at most room bytes) without waiting; false: nothing new.
    bool take(size_t room) {
        const int available = this->_currentClient.available();
        if (available <= 0 || !room) return false;
        char chunk[512];
        const size_t want = std::min({size_t(available), room, sizeof chunk});
        const int got = this->_currentClient.read(reinterpret_cast<uint8_t *>(chunk), want);
        if (got <= 0) return false;
        pending_.bytes.append(chunk, size_t(got));
        return true;
    }
    // As WebServer::handleClient after its parse (2.0.17), with the deadline view.
    void parse() {
        bool handled = false;
        {
            DeadlineClient<Client, Io> client(this->_currentClient, std::move(pending_.bytes), this->_statusChange,
                                              pending_.limitMs, pending_.boundary);
            handled = this->_parseRequest(client) && !client.synthesized();
        }
        if (handled) {
            this->_currentClient.setTimeout(HTTP_MAX_SEND_WAIT / 1000);
            this->_contentLength = CONTENT_LENGTH_NOT_SET;
            this->_handleRequest();
        }
        drop();
    }
    void refuse(int status) {
        const char *body = httpRefusalBody(status);
        const size_t length = std::char_traits<char>::length(body);
        char head[192];
        const int n = std::snprintf(head, sizeof head, "HTTP/1.1 %d %s\r\nContent-Type: application/json\r\nContent-Length: %u\r\n"
                                    "Cache-Control: no-store\r\nConnection: close\r\n\r\n", status, httpReason(status), unsigned(length));
        if (n > 0 && size_t(n) < sizeof head) {
            this->_currentClient.write(reinterpret_cast<const uint8_t *>(head), size_t(n));
            this->_currentClient.write(reinterpret_cast<const uint8_t *>(body), length);
        }
        drop();
    }
    void drop() {
        this->_currentClient.stop();
        this->_currentClient = Client();
        this->_currentStatus = HC_NONE;
        this->_currentUpload.reset();
        this->_currentRaw.reset();
        pending_ = Pending{};
    }
    Admission admit_;
    Pending pending_;
};
}
