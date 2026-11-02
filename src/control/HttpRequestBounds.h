#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace heating::control {
// Bounds for one HTTP request BEFORE the pinned WebServer parses it. That parser
// reads the whole request (headers and body) synchronously in one loop step,
// before any handler or sign-in check runs, and waits up to 5 s for each pause
// of the sender without an overall limit: a slow or huge body stalled the
// control loop for minutes. ResponsiveHttpServer peeks at the request head
// first, refuses what does not fit here, and lets the SDK parse a small request
// only once it is complete; large bodies (only signed-in clients) and uploads
// get an overall deadline.
struct HttpRequestBounds {
    static constexpr std::size_t maxHeadBytes = 4096;      // request line and headers
    static constexpr std::size_t bufferedBytes = 4096;     // a request this small is complete before parsing
    static constexpr uint64_t maxBodyBytes = 32768;        // every route except the uploads
    static constexpr uint64_t maxUploadBytes = 8ULL << 20; // /ota and /otafs (the handlers check the image size)
    static constexpr uint32_t deadlineMs = 10000;          // from the connection to the end of the request
    static constexpr uint32_t uploadDeadlineMs = 600000;   // Home Assistant paces an image in 2 KB blocks
};
inline bool httpUploadRoute(std::string_view path) { return path == "/ota" || path == "/otafs"; }

inline bool httpSameName(std::string_view a, std::string_view b) {
    if (a.size() != b.size()) return false;
    for (std::size_t i = 0; i < a.size(); ++i) {
        char x = a[i], y = b[i];
        if (x >= 'A' && x <= 'Z') x = char(x - 'A' + 'a');
        if (y >= 'A' && y <= 'Z') y = char(y - 'A' + 'a');
        if (x != y) return false;
    }
    return true;
}
inline std::string_view httpTrim(std::string_view v) {
    while (!v.empty() && (v.front() == ' ' || v.front() == '\t')) v.remove_prefix(1);
    while (!v.empty() && (v.back() == ' ' || v.back() == '\t')) v.remove_suffix(1);
    return v;
}

// The head as the pinned parser will read it (Parsing.cpp, arduino-esp32 2.0.17).
struct HttpRequestHead {
    std::string_view method, path, headers;  // headers: the lines after the request line
    std::size_t size = 0;                    // bytes up to and including the blank line
    uint64_t contentLength = 0;
    bool multipart = false;
    std::string boundary;                    // as the parser derives it: after '=', quotes removed
    std::string_view header(std::string_view name) const {
        for (auto rest = headers; !rest.empty();) {
            const auto end = rest.find("\r\n");
            const auto line = rest.substr(0, end);
            const auto colon = line.find(':');
            if (colon != std::string_view::npos && httpSameName(line.substr(0, colon), name)) return httpTrim(line.substr(colon + 1));
            if (end == std::string_view::npos) break;
            rest.remove_prefix(end + 2);
        }
        return {};
    }
};
enum class HttpHeadStatus { incomplete, complete, too_large, invalid };
// bytes: what has arrived so far (peeked, not consumed). Duplicate or malformed
// Content-Length/Content-Type headers and header lines without ':' are invalid:
// the parser would read such a request differently than these bounds.
inline HttpHeadStatus parseHttpRequestHead(std::string_view bytes, HttpRequestHead &out) {
    const auto end = bytes.find("\r\n\r\n");
    if (end == std::string_view::npos || end + 4 > HttpRequestBounds::maxHeadBytes)
        return bytes.size() >= HttpRequestBounds::maxHeadBytes || end != std::string_view::npos
            ? HttpHeadStatus::too_large : HttpHeadStatus::incomplete;
    out = HttpRequestHead{};
    out.size = end + 4;
    const auto head = bytes.substr(0, end);
    const auto lineEnd = head.find("\r\n");
    const auto line = head.substr(0, lineEnd);
    const auto first = line.find(' '), second = first == std::string_view::npos ? first : line.find(' ', first + 1);
    if (first == 0 || first == std::string_view::npos || second == std::string_view::npos) return HttpHeadStatus::invalid;
    out.method = line.substr(0, first);
    out.path = line.substr(first + 1, second - first - 1);
    out.path = out.path.substr(0, out.path.find('?'));
    out.headers = lineEnd == std::string_view::npos ? std::string_view() : head.substr(lineEnd + 2);
    bool length = false, type = false;
    for (auto rest = out.headers; !rest.empty();) {
        const auto next = rest.find("\r\n");
        const auto h = rest.substr(0, next);
        const auto colon = h.find(':');
        if (colon == std::string_view::npos || colon == 0) return HttpHeadStatus::invalid;
        const auto name = h.substr(0, colon), value = httpTrim(h.substr(colon + 1));
        if (httpSameName(name, "Content-Length")) {
            if (length || value.empty() || value.size() > 12) return HttpHeadStatus::invalid;
            for (char c : value) {
                if (c < '0' || c > '9') return HttpHeadStatus::invalid;
                out.contentLength = out.contentLength * 10 + uint64_t(c - '0');
            }
            length = true;
        } else if (httpSameName(name, "Content-Type")) {
            if (type) return HttpHeadStatus::invalid;
            type = true;
            if (value.substr(0, 10) == "multipart/") {
                out.multipart = true;
                const auto eq = value.find('=');
                for (char c : eq == std::string_view::npos ? value : value.substr(eq + 1)) if (c != '"') out.boundary += c;
                if (out.boundary.empty() || out.boundary.size() > 70) return HttpHeadStatus::invalid;
            }
        } else if (httpSameName(name, "Transfer-Encoding")) {
            return HttpHeadStatus::invalid;  // the parser reads Content-Length only
        }
        if (next == std::string_view::npos) break;
        rest.remove_prefix(next + 2);
    }
    return HttpHeadStatus::complete;
}
// 0: within the bounds; else the status to refuse the request with, before parsing.
inline int httpRequestRefusal(const HttpRequestHead &head) {
    const bool upload = httpUploadRoute(head.path);
    // Only the uploads take multipart forms (the parser's form loops have no limit of their own).
    const bool uploadPost = upload && head.method == "POST";
    if (head.multipart != uploadPost && (head.multipart || uploadPost)) return 415;
    if (head.contentLength > (upload ? HttpRequestBounds::maxUploadBytes : HttpRequestBounds::maxBodyBytes)) return 413;
    return 0;
}
// A request that is read complete (non-blocking, across loop steps) before the parser
// starts; the others (large bodies and uploads) need a signed-in client first.
inline bool httpBufferedRequest(const HttpRequestHead &head) {
    return !httpUploadRoute(head.path) && head.size + head.contentLength <= HttpRequestBounds::bufferedBytes;
}
inline const char *httpRefusalBody(int status) {
    switch (status) {
    case 400: return "{\"error\":\"invalid_request\"}";
    case 401: return "{\"error\":\"authentication_required\"}";
    case 403: return "{\"error\":\"password_change_required\"}";
    case 408: return "{\"error\":\"request_timeout\"}";
    case 413: return "{\"error\":\"request_too_large\"}";
    case 415: return "{\"error\":\"unsupported_request\"}";
    case 431: return "{\"error\":\"headers_too_large\"}";
    default: return "{\"error\":\"request_refused\"}";
    }
}
inline const char *httpReason(int status) {
    switch (status) {
    case 400: return "Bad Request"; case 401: return "Unauthorized"; case 403: return "Forbidden";
    case 408: return "Request Timeout"; case 413: return "Payload Too Large"; case 415: return "Unsupported Media Type";
    case 431: return "Request Header Fields Too Large"; default: return "Error";
    }
}
}
