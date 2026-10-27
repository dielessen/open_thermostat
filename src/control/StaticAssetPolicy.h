#pragma once
#include <string_view>

namespace heating::control {
// Bounded, allocation-free HTTP negotiation. An invalid preference cannot turn
// on a coding; an absent header retains compatibility with legacy .gz URLs.
inline std::string_view assetTrim(std::string_view value) {
    while(!value.empty()&&(value.front()==' '||value.front()=='\t'))value.remove_prefix(1);
    while(!value.empty()&&(value.back()==' '||value.back()=='\t'))value.remove_suffix(1);
    return value;
}
inline bool assetEqual(std::string_view a,std::string_view b) {
    if(a.size()!=b.size())return false;
    for(size_t i=0;i<a.size();++i) {
        const auto lower=[](char c){return c>='A'&&c<='Z'?char(c+'a'-'A'):c;};
        if(lower(a[i])!=lower(b[i]))return false;
    }
    return true;
}
inline bool assetQuality(std::string_view value) {
    value=assetTrim(value);
    if(value.empty()||(value.front()!='0'&&value.front()!='1'))return false;
    bool positive=value.front()=='1';
    if(value.size()==1)return positive;
    if(value.size()<2||value[1]!='.'||value.size()>5)return false;
    for(size_t i=2;i<value.size();++i) {
        if(value[i]<'0'||value[i]>'9'||(value.front()=='1'&&value[i]!='0'))return false;
        if(value[i]!='0')positive=true;
    }
    return positive;
}
inline bool acceptsAssetCoding(std::string_view header,std::string_view wanted,
        bool absent,bool implicit) {
    if(header.size()>1024)return false;
    if(assetTrim(header).empty())return absent;
    bool wildcard=false,wildcardSeen=false,seen=false,accepted=true;
    while(!header.empty()) {
        auto end=header.find(',');
        auto item=assetTrim(header.substr(0,end));
        auto semi=item.find(';');
        auto coding=assetTrim(item.substr(0,semi));
        bool allowed=true;
        if(semi!=item.npos) {
            auto parameter=assetTrim(item.substr(semi+1));
            allowed=parameter.size()>=2&&assetEqual(parameter.substr(0,2),"q=")
                &&assetQuality(parameter.substr(2));
        }
        if(assetEqual(coding,wanted)){seen=true;accepted=accepted&&allowed;}
        else if(coding=="*"){wildcard=wildcardSeen?wildcard&&allowed:allowed;wildcardSeen=true;}
        if(end==header.npos)break;
        header.remove_prefix(end+1);
    }
    return seen?accepted:wildcardSeen?wildcard:implicit;
}
inline bool acceptsAssetGzip(std::string_view header,bool legacyGzipUrl=false) {
    return acceptsAssetCoding(header,"gzip",legacyGzipUrl,false);
}
inline bool acceptsAssetIdentity(std::string_view header) {
    return acceptsAssetCoding(header,"identity",true,true);
}
// If-None-Match uses weak comparison for GET, but only after route authorization.
inline bool assetNotModified(std::string_view header,std::string_view etag) {
    if(header.size()>2048||etag.size()!=66||etag.front()!='"'||etag.back()!='"')return false;
    header=assetTrim(header);
    if(header=="*")return true;
    while(!header.empty()) {
        auto end=header.find(',');auto item=assetTrim(header.substr(0,end));
        if(item.substr(0,2)=="W/")item.remove_prefix(2);
        if(item==etag)return true;
        if(end==header.npos)break;
        header.remove_prefix(end+1);
    }
    return false;
}
}
