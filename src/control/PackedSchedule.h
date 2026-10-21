#pragma once
#include "UtcSchedule.h"
#include <cJSON.h>
#include <cmath>
#include <cstring>
#include <string_view>

namespace heating::control {
// Explicit packed schedule policy, only within the independently selected week
// contract. No expanded cJSON tree or extra persistent/scheduler owner.
inline constexpr const char* packedSchedulePolicy="wall-clock-packed/v1";
template<class Consumer>
bool forEachPackedTransition(const cJSON* document,Consumer consume) {
    auto field=[document](const char* key){return cJSON_GetObjectItemCaseSensitive(document,key);};
    auto integral=[](const cJSON* item,int64_t low,int64_t high) {
        return cJSON_IsNumber(item)&&std::isfinite(item->valuedouble)
            &&std::floor(item->valuedouble)==item->valuedouble
            &&item->valuedouble>=low&&item->valuedouble<=high;
    };
    const auto from=field("valid_from_utc"),until=field("valid_until_utc"),base=field("base_centi_c");
    if(!integral(from,UtcSchedule::minimumUtcSecond,UtcSchedule::maximumUtcSecond-1)
        ||!integral(until,UtcSchedule::minimumUtcSecond+1,UtcSchedule::maximumUtcSecond)
        ||!integral(base,500,3500))return false;
    const int64_t start=static_cast<int64_t>(from->valuedouble),end=static_cast<int64_t>(until->valuedouble);
    if(end<=start||end-start>UtcSchedule::maximumHorizonSeconds)return false;
    const auto chunks=field("transitions");
    if(!cJSON_IsArray(chunks)||cJSON_GetArraySize(chunks)<1||cJSON_GetArraySize(chunks)>13)return false;
    constexpr std::string_view alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    size_t count=0;int64_t previous=start-1;
    for(auto chunk=chunks->child;chunk;chunk=chunk->next) {
        if(!cJSON_IsString(chunk)||!chunk->valuestring)return false;
        const std::string_view text=chunk->valuestring;
        if(text.size()<6||text.size()>60||text.size()%6||(chunk->next&&text.size()!=60))return false;
        for(size_t offset=0;offset<text.size();offset+=6) {
            uint64_t value=0;
            for(size_t j=0;j<6;++j) {
                auto digit=alphabet.find(text[offset+j]);if(digit==std::string_view::npos)return false;
                value=(value<<6)|digit;
            }
            const int64_t at=start+static_cast<int64_t>(value>>12);
            const auto target=static_cast<int16_t>(value&4095);
            if(at<start||at>=end||at<=previous||(!count&&at!=start)||!UtcSchedule::validTemperature(target)
                ||count>=UtcSchedule::maximumTransitions||!consume(at,target,count))return false;
            previous=at;++count;
        }
    }
    return count>0;
}
}
