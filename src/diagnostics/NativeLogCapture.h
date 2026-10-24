#pragma once
#include "SystemLog.h"
#include <cstdarg>
namespace heating::diagnostics {
inline uint8_t nativeLevel(std::string_view text) {
    const auto prefix=text.substr(0,96);size_t first=std::string_view::npos;uint8_t level=3;
    for(const auto& item:{std::pair<char,uint8_t>{'E',1},{'W',2},{'I',3},{'D',4},{'V',5}}){
        char bracket[]={'[',item.first,']','\0'},idf[]={item.first,' ','(','\0'};
        const auto position=std::min(prefix.find(bracket),prefix.substr(0,32).find(idf));
        if(position<first){first=position;level=item.second;}
    }
    return level;
}
inline void captureNative(SystemLog& log,const char* feature,uint64_t now,const char* format,va_list args) {
    char text[256]{};const int length=std::vsnprintf(text,sizeof(text),format,args);
    if(length>=0)log.append(nativeLevel(text),feature,text,now,length>=int(sizeof(text)));
}
void installNativeLogCapture();
}
