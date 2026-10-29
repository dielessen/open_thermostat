#pragma once
#include "ReleasePolicy.h"
#include <vector>

namespace heating::update {
struct Release {std::string tag;bool prerelease=false;};

// One bounded response at a time: releases for HA and other components must not
// consume the two compatible E32 choices. Never retain a JSON tree during the
// subsequent manifest download or publish a partial list after a fetch failure.
// GitHub list order need not be publication order. Only canonical UTC dates
// participate in ranking; undated legacy entries remain usable after dated ones.
inline bool validReleasePublication(std::string_view value) {
    if(value.size()!=20)return false;
    for(size_t i=0;i<value.size();++i) {
        const char separator=i==4||i==7?'-':i==10?'T':i==13||i==16?':':i==19?'Z':0;
        if(separator?value[i]!=separator:value[i]<'0'||value[i]>'9')return false;
    }
    auto pair=[&](size_t i){return unsigned(value[i]-'0')*10+unsigned(value[i+1]-'0');};
    const unsigned year=pair(0)*100+pair(2),month=pair(5),day=pair(8);
    if(year<1970||month<1||month>12||pair(11)>23||pair(14)>59||pair(17)>59)return false;
    constexpr unsigned days[]{31,28,31,30,31,30,31,31,30,31,30,31};
    const unsigned limit=days[month-1]+(month==2&&year%4==0&&(year%100!=0||year%400==0));
    return day>=1&&day<=limit;
}
template<class Fetch>
bool discoverReleases(Fetch &&fetch,std::vector<Release> &out,std::string &error) {
    struct Candidate {Release release;std::string published;};
    std::vector<Candidate> found;
    auto finish=[&] {
        std::stable_sort(found.begin(),found.end(),[](const Candidate &a,const Candidate &b){return a.published>b.published;});
        std::vector<Release> choices;
        for(size_t i=0;i<std::min(size_t{2},found.size());++i)choices.push_back(std::move(found[i].release));
        out=std::move(choices);return true;
    };
    for(unsigned page=1;page<=maxReleasePages;++page) {
        std::string raw;
        if(!fetch(releasePageUrl(page),32768,raw,error))return false;
        auto root=releaseJson(raw);
        if(!root||!cJSON_IsArray(root.get())||cJSON_GetArraySize(root.get())>1) {
            error="Invalid or too large GitHub release response.";return false;
        }
        if(!root->child)return finish();
        const auto entry=root->child;
        const auto tag=string(entry,"tag_name");
        if(!cJSON_IsObject(entry)||!validTag(tag)||cJSON_IsTrue(field(entry,"draft"))||
           std::any_of(found.begin(),found.end(),[&](const Candidate &r){return r.release.tag==tag;}))continue;
        bool manifest=false,image=false;
        const auto assets=field(entry,"assets");
        if(cJSON_IsArray(assets))for(auto asset=assets->child;asset;asset=asset->next) {
            manifest|=string(asset,"name")=="e32v2-update.json";
            image|=string(asset,"name")=="firmware.bin";
        }
        if(!manifest||!image)continue;
        const bool prerelease=cJSON_IsTrue(field(entry,"prerelease"));
        auto published=string(entry,"published_at");
        if(!validReleasePublication(published))published.clear();
        root.reset();raw.clear();raw.shrink_to_fit();
        std::string manifestBytes;Manifest parsed;
        if(!fetch(assetUrl(tag,"e32v2-update.json"),4096,manifestBytes,error))return false;
        if(parseManifest(manifestBytes,tag,parsed))found.push_back({{tag,prerelease},std::move(published)});
    }
    if(!found.empty())return finish();
    error="No matching E32 release in the first twelve releases; older releases were not checked.";
    return false;
}
}
