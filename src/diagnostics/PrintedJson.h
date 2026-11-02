#pragma once
#include <cJSON.h>
#include <string_view>

namespace heating::diagnostics {
// One serialized cJSON document, owned until the response is written. On E32
// the cJSON hooks (main.cpp) put the print buffer in PSRAM. Arduino's
// WebServer::send(code,type,const char*) copies a body into a String first,
// which comes from internal RAM up to CONFIG_SPIRAM_MALLOC_ALWAYSINTERNAL
// (4 KiB): the /status/logs pages, /updates/status and smaller settings pages.
// sendJson writes the printed bytes in place instead, so a JSON body never
// costs internal heap beyond the TCP buffers that carry it.
class PrintedJson final {
public:
    explicit PrintedJson(const cJSON *root):text_(root?cJSON_PrintUnformatted(root):nullptr) {}
    PrintedJson(const PrintedJson&)=delete;
    PrintedJson& operator=(const PrintedJson&)=delete;
    ~PrintedJson() {if(text_)cJSON_free(text_);}
    explicit operator bool() const {return text_!=nullptr;}
    std::string_view view() const {return text_?std::string_view(text_):std::string_view{};}
private:
    char *text_;
};

// Server provides sendView(code,content_type,body) (REST.h WebServerStringView).
// A failed print answers 503 with a fixed body and never a partial document.
template<class Server>
bool sendJson(Server &server,int code,const cJSON *root,std::string_view failure="{\"error\":\"status_unavailable\"}") {
    const PrintedJson text(root);
    if(!text||text.view().empty()) {server.sendView(503,"application/json",failure);return false;}
    server.sendView(code,"application/json",text.view());
    return true;
}
}
