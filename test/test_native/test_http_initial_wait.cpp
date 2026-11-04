// ResponsiveHttpServer against a model of the pinned WebServer (arduino-esp32 2.0.17):
// its handleClient, and a _parseRequest that reads like Parsing.cpp (Stream timeout per
// read, 5 s per pause of a body, a form field loop that waits for a boundary line).
// The fake clock advances only while that parser waits (or delay() runs), so "blocked" is
// measured exactly. -DOT_OLD_RESPONSIVE_SERVER builds the same tests against the beta header
// (one template argument, no admission) to show which ones failed before the bounds.
#include <cstdint>
#include <deque>
#include <memory>
#include <string>
#include <utility>
#include <vector>
#include <gtest/gtest.h>
namespace {
uint32_t httpTestNow;
uint32_t millis() { return httpTestNow; }
void delay(uint32_t ms) { httpTestNow += ms; }
enum HTTPClientStatus { HC_NONE, HC_WAIT_READ, HC_WAIT_CLOSE };
struct Socket {
    std::string in, out;
    size_t pos = 0;
    std::vector<std::pair<uint32_t, std::string>> later;  // bytes that arrive at a time
    uint32_t closeAt = UINT32_MAX;                          // the sender goes away
    unsigned stops = 0, reads = 0;
    // How the peer reads a response: at most `takes` bytes per send, at most once per takeEveryMs.
    size_t takes = SIZE_MAX;
    uint32_t takeEveryMs = 0, lastTake = 0;
    void deliver() {
        for (auto it = later.begin(); it != later.end();)
            if (it->first <= httpTestNow) { in += it->second; it = later.erase(it); } else ++it;
    }
    int take(const uint8_t *b, size_t n) {  // one non-blocking send: bytes taken, 0 = the buffer is full
        if (takeEveryMs && lastTake && httpTestNow - lastTake < takeEveryMs) return 0;
        const size_t k = std::min(n, takes);
        if (!k) return 0;
        lastTake = httpTestNow;
        out.append(reinterpret_cast<const char *>(b), k);
        return int(k);
    }
};
struct FakeClient {
    std::shared_ptr<Socket> s;
    unsigned long timeoutMs = 1000;  // Stream::_timeout
    FakeClient() = default;
    explicit FakeClient(std::shared_ptr<Socket> socket) : s(std::move(socket)) {}
    virtual ~FakeClient() = default;
    FakeClient(const FakeClient &) = default;
    FakeClient &operator=(const FakeClient &) = default;
    explicit operator bool() const { return bool(s); }
    virtual int available() { if (!s) return 0; s->deliver(); return int(s->in.size() - s->pos); }
    virtual int read() { uint8_t b = 0; return read(&b, 1) == 1 ? b : -1; }
    virtual int read(uint8_t *b, size_t n) {
        if (!s) return -1;
        s->deliver(); ++s->reads;
        const size_t k = std::min(n, s->in.size() - s->pos);
        for (size_t i = 0; i < k; ++i) b[i] = uint8_t(s->in[s->pos + i]);
        s->pos += k; return int(k);
    }
    virtual int peek() { if (!s) return -1; s->deliver(); return s->pos < s->in.size() ? (unsigned char)s->in[s->pos] : -1; }
    virtual uint8_t connected() { return s && httpTestNow < s->closeAt; }
    void stop() { if (s) ++s->stops; s.reset(); }
    size_t write(const uint8_t *b, size_t n) { if (s) s->out.append(reinterpret_cast<const char *>(b), n); return n; }
    int setTimeout(uint32_t) { return 0; }
};
// Stream::timedRead and readStringUntil: every empty read waits 1 ms of the fake clock.
int timedRead(FakeClient &c) {
    const uint32_t start = millis();
    do {
        const int b = c.read();
        if (b >= 0) return b;
        if (!c.timeoutMs) break;
        ++httpTestNow;
    } while (millis() - start < c.timeoutMs);
    return -1;
}
std::string readStringUntil(FakeClient &c, char end) {
    std::string out;
    for (int b; (b = timedRead(c)) >= 0 && b != end;) out += char(b);
    return out;
}
struct FakeServerSocket {
    std::deque<FakeClient> queue;
    FakeClient available() { if (queue.empty()) return {}; auto c = queue.front(); queue.pop_front(); return c; }
};
struct PinnedServerSurface {
    int _currentStatus = HC_NONE;
    uint32_t _statusChange = 100;
    FakeClient _currentClient;
    FakeServerSocket _server;
    bool _nullDelay = true;
    std::unique_ptr<int> _currentUpload, _currentRaw;
    size_t _contentLength = 0;
    unsigned calls = 0, parses = 0, handled = 0;
    bool hung = false;
    uint32_t blockedMs = 0;
    std::string body;
    virtual ~PinnedServerSurface() = default;
    virtual void handleClient() {  // WebServer::handleClient
        ++calls;
        if (_currentStatus == HC_NONE) {
            _currentClient = _server.available();
            if (!_currentClient) return;
            _currentStatus = HC_WAIT_READ; _statusChange = millis();
        }
        bool keep = false;
        if (_currentClient.connected() && _currentStatus == HC_WAIT_READ) {
            if (_currentClient.available()) { if (_parseRequest(_currentClient)) _handleRequest(); }
            else keep = millis() - _statusChange <= 5000;
        }
        if (!keep) { _currentClient = FakeClient(); _currentStatus = HC_NONE; }
    }
    // As Parsing.cpp: request line, headers, then the plain body (5 s per pause) or a form field.
    bool _parseRequest(FakeClient &c) {
        ++parses;
        const uint32_t start = millis();
        readStringUntil(c, '\r'); readStringUntil(c, '\n');
        size_t length = 0; std::string boundary;
        for (;;) {
            const auto h = readStringUntil(c, '\r'); readStringUntil(c, '\n');
            if (h.empty()) break;
            const auto colon = h.find(':');
            if (colon == std::string::npos) break;
            const auto name = h.substr(0, colon), value = h.substr(colon + 2);
            if (name == "Content-Length") length = std::stoul(value);
            if (name == "Content-Type" && value.rfind("multipart/", 0) == 0) boundary = value.substr(value.find('=') + 1);
        }
        bool complete = true;
        if (boundary.empty()) {
            body.clear();
            while (body.size() < length) {  // readBytesWithTimeout(HTTP_MAX_POST_WAIT)
                int tries = 5000, n = 0;
                while (!(n = c.available()) && tries--) ++httpTestNow;
                if (!n) break;
                for (int i = 0; i < n; ++i) { const int b = timedRead(c); if (b < 0) break; body += char(b); }
            }
            complete = body.size() >= length;
        } else {
            for (int i = 0; i < 3; ++i) { readStringUntil(c, '\r'); readStringUntil(c, '\n'); }  // boundary, disposition, blank
            for (unsigned spins = 0;; ++spins) {                                                  // a text field
                const auto line = readStringUntil(c, '\r'); readStringUntil(c, '\n');
                if (line.rfind("--" + boundary, 0) == 0) break;
                if (spins > 20000) { hung = true; complete = false; break; }
            }
        }
        blockedMs += millis() - start;
        return complete;
    }
    // The handler's answer, written like WebServer::send: the head, then the body.
    std::string response;
    size_t responded = 0;
    uint32_t writeMs = 0;
    virtual size_t _currentClientWrite(const char *b, size_t l) { return _currentClient.write(reinterpret_cast<const uint8_t *>(b), l); }
    virtual size_t _currentClientWrite_P(const char *b, size_t l) { return _currentClientWrite(b, l); }
    void _handleRequest() {
        ++handled;
        if (response.empty()) return;
        const uint32_t start = millis();
        const size_t head = std::min<size_t>(response.size(), 100);
        responded += _currentClientWrite(response.data(), head);
        responded += _currentClientWrite_P(response.data() + head, response.size() - head);
        writeMs += millis() - start;
    }
};
struct FakeIo {
    using Client = FakeClient;
    static void noWait(FakeClient &c) { c.timeoutMs = 0; }
    static int send(FakeClient &c, const uint8_t *b, size_t n) { return c.s ? c.s->take(b, n) : -1; }
};
}
#define HTTP_MAX_SEND_WAIT 5000
#define CONTENT_LENGTH_NOT_SET ((size_t) -2)
#include "control/ResponsiveHttpServer.h"
#ifdef OT_OLD_RESPONSIVE_SERVER
using HttpServer = heating::control::ResponsiveHttpServer<PinnedServerSurface>;
template<class F> void admit(HttpServer &, F) {}
#else
using HttpServer = heating::control::ResponsiveHttpServer<PinnedServerSurface, FakeIo>;
template<class F> void admit(HttpServer &s, F f) { s.setAdmission(f); }
#endif
namespace {
std::shared_ptr<Socket> connect(HttpServer &s, std::string bytes = "") {
    auto socket = std::make_shared<Socket>(); socket->in = std::move(bytes);
    s._server.queue.push_back(FakeClient(socket));
    return socket;
}
std::string request(const std::string &method, const std::string &path, const std::string &body, const std::string &extra = "") {
    return method + " " + path + " HTTP/1.1\r\nHost: 192.168.1.40\r\n" + extra +
        (body.empty() && method == "GET" ? "" : "Content-Length: " + std::to_string(body.size()) + "\r\n") + "\r\n" + body;
}
// Runs the loop until the connection is done; the fake clock only moves inside the parser or here.
void run(HttpServer &s, uint32_t untilMs, uint32_t stepMs = 10) {
    for (; httpTestNow < untilMs; httpTestNow += stepMs) s.handleClient();
}
}

TEST(HttpInitialWait, EmptyConnectionIsRetiredAtBoundary) {
    HttpServer s; httpTestNow = 100; auto socket = connect(s); s.handleClient();
    httpTestNow = 349; s.handleClient(); EXPECT_EQ(socket->stops, 0u);
    httpTestNow = 350; s.handleClient(); EXPECT_EQ(socket->stops, 1u); EXPECT_EQ(s._currentStatus, HC_NONE);
    EXPECT_EQ(s.parses, 0u);
}
TEST(HttpInitialWait, ClockWrapStillAppliesTheSameDeadline) {
    HttpServer s; httpTestNow = UINT32_MAX - 99; auto socket = connect(s); s.handleClient();
    httpTestNow = 149; s.handleClient(); EXPECT_EQ(socket->stops, 0u);
    httpTestNow = 150; s.handleClient(); EXPECT_EQ(socket->stops, 1u);
}
TEST(HttpInitialWait, ACompleteSmallRequestIsHandledAsBefore) {
    HttpServer s; httpTestNow = 100; connect(s, request("POST", "/config/heating/comfort", R"({"room":"woonkamer"})"));
    run(s, 200);
    EXPECT_EQ(s.handled, 1u); EXPECT_EQ(s.body, R"({"room":"woonkamer"})"); EXPECT_EQ(s.blockedMs, 0u);
}
TEST(HttpRequestBounds, OversizedBodyIsRefusedBeforeAnyParserOrHandler) {
    HttpServer s; httpTestNow = 100; auto socket = connect(s, request("POST", "/config/heating", std::string(40000, 'x')));
    run(s, 200);
    EXPECT_EQ(s.parses, 0u); EXPECT_EQ(s.handled, 0u);
    EXPECT_EQ(socket->out.rfind("HTTP/1.1 413 ", 0), 0u) << socket->out;
    EXPECT_NE(socket->out.find(R"({"error":"request_too_large"})"), std::string::npos);
    EXPECT_LT(socket->pos, 4096u);  // the body was never read
}
TEST(HttpRequestBounds, MultipartIsOnlyForTheUploads) {
    HttpServer s; httpTestNow = 100;
    auto socket = connect(s, request("POST", "/config/device", "--B\r\n", "Content-Type: multipart/form-data; boundary=B\r\n"));
    run(s, 200);
    EXPECT_EQ(s.parses, 0u); EXPECT_EQ(socket->out.rfind("HTTP/1.1 415 ", 0), 0u) << socket->out;
}
TEST(HttpRequestBounds, ASlowHeadNeverBlocksTheLoopAndEndsAfterTenSeconds) {
    HttpServer s; httpTestNow = 100; auto socket = connect(s, "P");
    const std::string rest = request("POST", "/auth/login", "username=admin&password=x").substr(1);
    for (size_t i = 0; i < rest.size(); ++i) socket->later.push_back({uint32_t(200 + 1000 * i), rest.substr(i, 1)});
    run(s, 12000);
    EXPECT_EQ(s.parses, 0u); EXPECT_EQ(s.blockedMs, 0u);
    EXPECT_EQ(socket->out.rfind("HTTP/1.1 408 ", 0), 0u) << socket->out;
}
TEST(HttpRequestBounds, ASmallBodyThatTricklesInIsParsedOnlyWhenCompleteWithoutWaiting) {
    HttpServer s; httpTestNow = 100;
    const auto all = request("POST", "/auth/login", "username=admin&password=correct-horse");
    const auto split = all.find("\r\n\r\n") + 4;
    auto socket = connect(s, all.substr(0, split));
    for (size_t i = split; i < all.size(); ++i) socket->later.push_back({uint32_t(100 + 200 * (i - split + 1)), all.substr(i, 1)});
    run(s, 9000);
    EXPECT_EQ(s.parses, 1u); EXPECT_EQ(s.handled, 1u); EXPECT_EQ(s.body, "username=admin&password=correct-horse");
    EXPECT_EQ(s.blockedMs, 0u);  // the loop kept running; the parser read from memory
}
TEST(HttpRequestBounds, LargeBodiesNeedASignedInClientBeforeTheyAreRead) {
    HttpServer s; httpTestNow = 100;
    std::vector<std::string> paths;
    admit(s, [&](const heating::control::HttpRequestHead &head) {
        paths.emplace_back(head.path);
        return head.header("X-OpenThermostat-CSRF") == std::string(64, 'a') ? 0 : 401;
    });
    auto socket = connect(s, request("POST", "/config/heating", std::string(8000, 'x')));
    run(s, 200);
    EXPECT_EQ(s.parses, 0u); EXPECT_EQ(socket->out.rfind("HTTP/1.1 401 ", 0), 0u) << socket->out;
    EXPECT_EQ(paths, std::vector<std::string>{"/config/heating"});
}
TEST(HttpRequestBounds, ASignedInSlowLargeBodyBlocksAtMostTheDeadlinePlusOneSdkWait) {
    // 8000 bytes, the first 1000 at once, then one byte every 4.9 s: before, about 9.5 hours.
    HttpServer s; httpTestNow = 100;
    admit(s, [](const heating::control::HttpRequestHead &) { return 0; });
    const auto all = request("POST", "/config/heating", std::string(8000, 'x'), "X-OpenThermostat-CSRF: " + std::string(64, 'a') + "\r\n");
    const auto split = all.find("\r\n\r\n") + 4 + 1000;
    auto socket = connect(s, all.substr(0, split));
    for (size_t i = split; i < all.size(); ++i) socket->later.push_back({uint32_t(100 + 4900 * (i - split + 1)), all.substr(i, 1)});
    run(s, 200);
    while (s._currentStatus != HC_NONE && httpTestNow < 100000000) { httpTestNow += 10; s.handleClient(); }
    EXPECT_EQ(s.parses, 1u); EXPECT_EQ(s.handled, 0u);
    EXPECT_LE(s.blockedMs, heating::control::HttpRequestBounds::deadlineMs + 5000 + 1000) << s.blockedMs;
}
TEST(HttpRequestBounds, AnUploadWhoseSenderVanishesInsideAFormFieldEndsAndIsNotHandled) {
    // The SDK's form field loop waits for a boundary line; a sender gone mid-field spun it forever.
    HttpServer s; httpTestNow = 100;
    admit(s, [](const heating::control::HttpRequestHead &) { return 0; });
    const std::string form = "--OTB\r\nContent-Disposition: form-data; name=\"size\"\r\n\r\n12";
    auto socket = connect(s, "POST /ota HTTP/1.1\r\nHost: 192.168.1.40\r\nContent-Type: multipart/form-data; boundary=OTB\r\n"
                             "Content-Length: 4000000\r\n\r\n" + form);
    socket->closeAt = 150;
    run(s, 200);
    while (s._currentStatus != HC_NONE && httpTestNow < 100000000) { httpTestNow += 10; s.handleClient(); }
    EXPECT_FALSE(s.hung); EXPECT_EQ(s.parses, 1u); EXPECT_EQ(s.handled, 0u);
    EXPECT_LE(s.blockedMs, 1000u) << s.blockedMs;
}
#ifndef OT_OLD_RESPONSIVE_SERVER
// Review R2-08: an upload the update gate refuses anyway (a boot not confirmed yet, an update or a
// boiler session) is refused by the admission, 409 before a byte of its body is read; before, the
// parser read the whole image and every 1436-byte chunk ran the authorization and wrote a refusal.
TEST(HttpRequestBounds, ABlockedUploadIsRefusedBeforeItsBodyIsRead) {
    HttpServer s; httpTestNow = 100;
    admit(s, [](const heating::control::HttpRequestHead &head) { return head.path == "/ota" ? 409 : 0; });
    const std::string image(500000, 'x');
    auto socket = connect(s, "POST /ota HTTP/1.1\r\nHost: 192.168.1.40\r\nContent-Type: multipart/form-data; boundary=OTB\r\n"
                             "Content-Length: " + std::to_string(image.size()) + "\r\n\r\n" + image);
    run(s, 200);
    EXPECT_EQ(s.parses, 0u); EXPECT_EQ(s.handled, 0u);
    EXPECT_EQ(socket->out.rfind("HTTP/1.1 409 Conflict\r\n", 0), 0u) << socket->out;
    EXPECT_NE(socket->out.find(R"({"error":"device_busy"})"), std::string::npos);
    EXPECT_LT(socket->pos, 4096u); // the image was never read
    EXPECT_EQ(socket->stops, 1u);
}
// Review R2-03: an upload waits unread, without blocking the loop, while the admission holds it
// (the E32 first withdraws its boiler request); admitted, it is parsed and gets its full deadline.
// A hold that never ends is refused after holdMs, the body never read.
TEST(HttpRequestBounds, AHeldUploadWaitsUnreadWhileTheLoopRunsThenIsParsed) {
    using heating::control::HttpRequestBounds;
    const std::string form = "--OTB\r\nContent-Disposition: form-data; name=\"size\"\r\n\r\n12\r\n--OTB--\r\n";
    const std::string upload = "POST /ota HTTP/1.1\r\nHost: 192.168.1.40\r\nContent-Type: multipart/form-data; boundary=OTB\r\n"
                               "Content-Length: " + std::to_string(form.size()) + "\r\n\r\n" + form;
    HttpServer s; httpTestNow = 100;
    unsigned asks = 0; bool released = false;
    admit(s, [&](const heating::control::HttpRequestHead &head) {
        ++asks; EXPECT_EQ(head.path, "/ota");
        return released ? 0 : HttpRequestBounds::admitLater;
    });
    auto socket = connect(s, upload);
    run(s, 30000); // 30 s of loop passes: each one returns at once
    EXPECT_EQ(s.parses, 0u); EXPECT_EQ(s.blockedMs, 0u); EXPECT_GT(asks, 100u);
    EXPECT_EQ(socket->stops, 0u); EXPECT_FALSE(s.idle()); EXPECT_TRUE(socket->out.empty());
    released = true;
    run(s, 30100);
    EXPECT_EQ(s.parses, 1u); EXPECT_EQ(s.handled, 1u); EXPECT_TRUE(s.idle());
    // Never released: refused after holdMs.
    HttpServer never; httpTestNow = 100;
    admit(never, [](const heating::control::HttpRequestHead &) { return HttpRequestBounds::admitLater; });
    auto refused = connect(never, upload);
    run(never, 100 + HttpRequestBounds::holdMs - 1000);
    EXPECT_TRUE(refused->out.empty());
    run(never, 100 + HttpRequestBounds::holdMs + 1000);
    EXPECT_EQ(refused->out.rfind("HTTP/1.1 503 ", 0), 0u) << refused->out;
    EXPECT_EQ(never.parses, 0u); EXPECT_TRUE(never.idle());
    // The sender gives up while held: the request ends, nothing parsed.
    HttpServer gone; httpTestNow = 100;
    admit(gone, [](const heating::control::HttpRequestHead &) { return HttpRequestBounds::admitLater; });
    auto vanished = connect(gone, upload); vanished->closeAt = 5000;
    run(gone, 6000);
    EXPECT_EQ(gone.parses, 0u); EXPECT_TRUE(gone.idle());
}
// Review R2-02: the response side is bounded like the request side. A client that takes nothing
// holds the loop 2 s, one that drips a byte a second at most 10 s for the whole response (head
// and body together); it is then closed and the rest is dropped. A fast client gets everything.
TEST(HttpResponseBounds, AStalledOrDrippingClientIsClosedAfterTheWriteBound) {
    using heating::control::BoundedSend;
    const std::string body(100000, 'x');
    struct Case { size_t takes; uint32_t everyMs, atMostMs; bool complete; };
    for (const Case c : {Case{0, 0, BoundedSend::stallMs, false}, Case{1, 1000, BoundedSend::totalMs, false},
                         Case{1460, 1, 1000, true}, Case{SIZE_MAX, 0, 0, true}}) {
        HttpServer s; httpTestNow = 100; s.response = body;
        auto socket = connect(s, request("GET", "/status/history", ""));
        socket->takes = c.takes; socket->takeEveryMs = c.everyMs;
        s.handleClient();
        EXPECT_EQ(s.handled, 1u) << c.takes;
        EXPECT_LE(s.writeMs, c.atMostMs) << c.takes;
        EXPECT_EQ(s.responded == body.size(), c.complete) << c.takes << " " << s.responded;
        EXPECT_EQ(socket->out.size(), s.responded) << c.takes;
        EXPECT_TRUE(s.idle());
        if (!c.complete) { EXPECT_GE(s.writeMs + 1, c.atMostMs) << c.takes; }
        // The next request gets its own budget.
        auto next = connect(s, request("GET", "/status/history", ""));
        s.handleClient();
        EXPECT_EQ(next->out, body);
    }
}
#endif
TEST(HttpRequestBounds, HeadParsingMirrorsThePinnedParser) {
    using namespace heating::control;
    HttpRequestHead head;
    EXPECT_EQ(parseHttpRequestHead("POST /x HTTP/1.1\r\nHost: a\r\n", head), HttpHeadStatus::incomplete);
    ASSERT_EQ(parseHttpRequestHead("POST /config/heating?x=1 HTTP/1.1\r\ncontent-length:  12 \r\nCookie: OTSESSION=1\r\n\r\nbody", head),
              HttpHeadStatus::complete);
    EXPECT_EQ(head.method, "POST"); EXPECT_EQ(head.path, "/config/heating"); EXPECT_EQ(head.contentLength, 12u);
    EXPECT_EQ(head.header("COOKIE"), "OTSESSION=1"); EXPECT_EQ(head.size, std::string_view("POST /config/heating?x=1 HTTP/1.1\r\ncontent-length:  12 \r\nCookie: OTSESSION=1\r\n\r\n").size());
    ASSERT_EQ(parseHttpRequestHead("POST /ota HTTP/1.1\r\nContent-Type: multipart/form-data; boundary=\"OT x\"\r\n\r\n", head), HttpHeadStatus::complete);
    EXPECT_TRUE(head.multipart); EXPECT_EQ(head.boundary, "OT x");
    for (auto bad : {"POST /x HTTP/1.1\r\nContent-Length: 1\r\nContent-Length: 1\r\n\r\n", "POST /x HTTP/1.1\r\nContent-Length: -1\r\n\r\n",
                     "POST /x HTTP/1.1\r\nContent-Length: 0x10\r\n\r\n", "POST /x HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n",
                     "POST /x HTTP/1.1\r\nno colon here\r\n\r\n", "POST\r\n\r\n", "POST /x HTTP/1.1\r\nContent-Type: a\r\nContent-Type: b\r\n\r\n"})
        EXPECT_EQ(parseHttpRequestHead(bad, head), HttpHeadStatus::invalid) << bad;
    EXPECT_EQ(parseHttpRequestHead(std::string(5000, 'a'), head), HttpHeadStatus::too_large);
    EXPECT_EQ(parseHttpRequestHead("GET / HTTP/1.1\r\nX: " + std::string(5000, 'a') + "\r\n\r\n", head), HttpHeadStatus::too_large);
}
