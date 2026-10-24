#pragma once
#include "SystemLog.h"
#include "control/BoundedJson.h"
#include <optional>
namespace heating::diagnostics {
inline std::optional<Settings> parseSettings(std::string_view json) {
    if(json.size()>256)return std::nullopt;
    auto root=control::parseControlJson(json,true);
    if(!root||!cJSON_IsObject(root.get())||cJSON_GetArraySize(root.get())!=6)return std::nullopt;
    auto field=[&](const char* key){return cJSON_GetObjectItemCaseSensitive(root.get(),key);};
    const auto enabled=field("syslog_enabled"),server=field("server");
    if(!cJSON_IsBool(enabled)||!cJSON_IsString(server)||!server->valuestring||std::strlen(server->valuestring)>15)return std::nullopt;
    const auto number=[&](const char* key,unsigned low,unsigned high)->std::optional<unsigned>{
        auto value=field(key);if(!cJSON_IsNumber(value)||value->valuedouble<low||value->valuedouble>high||std::floor(value->valuedouble)!=value->valuedouble)return std::nullopt;
        return unsigned(value->valuedouble);
    };
    const auto port=number("port",1,65535),sys=number("syslog_level",0,5),web=number("web_level",0,5),mark=number("mark_interval_s",0,86400);
    if(!port||!sys||!web||!mark)return std::nullopt;
    Settings s;s.enabled=cJSON_IsTrue(enabled);std::strcpy(s.server.data(),server->valuestring);
    s.port=*port;s.syslogLevel=*sys;s.webLevel=*web;s.markSeconds=*mark;
    return valid(s)?std::optional<Settings>(s):std::nullopt;
}
inline std::string settingsJson(const Settings& s) {
    return std::string("{\"syslog_enabled\":")+(s.enabled?"true":"false")+",\"server\":\""+s.server.data()+"\",\"port\":"+std::to_string(s.port)
        +",\"syslog_level\":"+std::to_string(s.syslogLevel)+",\"web_level\":"+std::to_string(s.webLevel)+",\"mark_interval_s\":"+std::to_string(s.markSeconds)+"}";
}
}
