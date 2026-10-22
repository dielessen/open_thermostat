#pragma once
#include "ReleasePolicy.h"
#include <vector>

namespace heating::update {
struct Release {std::string tag;bool prerelease=false;};

// One bounded response at a time: releases for HA and other components must not
// consume the two compatible E32 choices. Never retain a JSON tree during the
// subsequent manifest download or publish a partial list after a fetch failure.
template<class Fetch>
bool discoverReleases(Fetch &&fetch,std::vector<Release> &out,std::string &error) {
    std::vector<Release> found;
    for(unsigned page=1;page<=maxReleasePages;++page) {
        std::string raw;
        if(!fetch(releasePageUrl(page),32768,raw,error))return false;
        auto root=releaseJson(raw);
        if(!root||!cJSON_IsArray(root.get())||cJSON_GetArraySize(root.get())>1) {
            error="Ongeldig of te groot GitHub-releaseantwoord.";return false;
        }
        if(!root->child){out=std::move(found);return true;}
        const auto entry=root->child;
        const auto tag=string(entry,"tag_name");
        if(!cJSON_IsObject(entry)||!validTag(tag)||cJSON_IsTrue(field(entry,"draft"))||
           std::any_of(found.begin(),found.end(),[&](const Release &r){return r.tag==tag;}))continue;
        bool manifest=false,image=false;
        const auto assets=field(entry,"assets");
        if(cJSON_IsArray(assets))for(auto asset=assets->child;asset;asset=asset->next) {
            manifest|=string(asset,"name")=="e32v2-update.json";
            image|=string(asset,"name")=="firmware.bin";
        }
        if(!manifest||!image)continue;
        const bool prerelease=cJSON_IsTrue(field(entry,"prerelease"));
        root.reset();raw.clear();raw.shrink_to_fit();
        std::string manifestBytes;Manifest parsed;
        if(!fetch(assetUrl(tag,"e32v2-update.json"),4096,manifestBytes,error))return false;
        if(parseManifest(manifestBytes,tag,parsed))found.push_back({tag,prerelease});
        if(found.size()==2){out=std::move(found);return true;}
    }
    if(!found.empty()){out=std::move(found);return true;}
    error="Geen passende E32-release in de eerste twaalf releaseberichten; oudere releases zijn niet gecontroleerd.";
    return false;
}
}
