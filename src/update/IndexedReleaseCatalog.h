#pragma once
#include "ReleaseCatalog.h"
#include <array>
#include <limits>

namespace heating::update {
// A bounded fast path for this repository's canonical E32 release channels.
// Unknown version formats retain the general release scan. Annotated tags
// resolve one exact immutable tag object before a manifest is accepted.
// A tag is only a candidate: its public release and exact manifest are required.
enum class IndexedCatalogResult { Complete, Legacy, Failed };
inline constexpr char releaseReferenceApi[]=
    "https://api.github.com/repos/dielessen/open_thermostat/git/matching-refs/tags/v";
inline constexpr unsigned maxIndexedReferences=80, maxIndexedCandidates=12;

inline const cJSON *singleField(const cJSON *object,const char *name) {
    if(!cJSON_IsObject(object))return nullptr;
    const cJSON *found=nullptr;
    for(auto item=object->child;item;item=item->next)if(item->string&&std::strcmp(item->string,name)==0) {
        if(found)return nullptr;
        found=item;
    }
    return found;
}
inline std::string singleString(const cJSON *object,const char *name) {
    const auto item=singleField(object,name);
    return cJSON_IsString(item)?item->valuestring:"";
}
// major/minor/patch, channel (alpha < beta < rc < stable), sequence.
// Parse canonical tags only; no lexical comparison or publication-date guessing.
inline bool firmwareVersion(std::string_view tag,std::array<uint32_t,5> &result) {
    if(!validTag(tag))return false;
    size_t position=1;
    auto number=[&](uint32_t &out) {
        const auto start=position;uint32_t value=0;
        while(position<tag.size()&&tag[position]>='0'&&tag[position]<='9') {
            const unsigned digit=tag[position++]-'0';
            if(value>(std::numeric_limits<uint32_t>::max()-digit)/10)return false;
            value=value*10+digit;
        }
        if(position==start||(position-start>1&&tag[start]=='0'))return false;
        out=value;return true;
    };
    std::array<uint32_t,5> parsed{};
    for(unsigned i=0;i<3;++i) {
        if(!number(parsed[i]))return false;
        if(i<2&&(position==tag.size()||tag[position++]!='.'))return false;
    }
    constexpr std::string_view board="-e32v2";
    if(tag.substr(position,board.size())!=board)return false;
    position+=board.size();
    if(position==tag.size()) {parsed[3]=3;result=parsed;return true;}
    const std::array<std::string_view,3> channels{{"-alpha.","-beta.","-rc."}};
    for(uint32_t stage=0;stage<channels.size();++stage) {
        const auto suffix=channels[stage];
        if(tag.substr(position,suffix.size())!=suffix)continue;
        position+=suffix.size();parsed[3]=stage;
        if(!number(parsed[4])||position!=tag.size())return false;
        result=parsed;return true;
    }
    return false;
}
inline bool alphaVersion(std::string_view tag,std::array<uint32_t,4> &result) {
    std::array<uint32_t,5> parsed{};
    if(!firmwareVersion(tag,parsed)||parsed[3]!=0)return false;
    result={parsed[0],parsed[1],parsed[2],parsed[4]};return true;
}

// Availability never recommends a less mature channel than the installed one.
// All verified choices remain selectable explicitly on the update page.
inline std::string newerFirmwareRelease(std::string_view installed,const std::vector<Release> &releases) {
    std::array<uint32_t,5> current{},candidate{};
    if(!firmwareVersion(installed,current))return {};
    const auto minimumStage=current[3];
    std::string latest;
    for(const auto &release:releases)
        if(firmwareVersion(release.tag,candidate)&&candidate[3]>=minimumStage&&candidate>current) {
            current=candidate;latest=release.tag;
        }
    return latest;
}
inline std::string newerAlphaRelease(std::string_view installed,const std::vector<Release> &releases) {
    return newerFirmwareRelease(installed,releases);
}

// Fetch(url, byteLimit, body, error, status) supplies an actual HTTP status.
// Only a release-metadata 404 means an unpublished candidate, not a network
// failure. Never publish a partially verified choice list after another error.
template<class Fetch>
IndexedCatalogResult discoverIndexedReleases(Fetch &&fetch,std::vector<Release> &out,std::string &error) {
    struct Candidate {std::string tag,source;std::array<uint32_t,5> version;bool annotated=false;};
    std::string raw;int status=0;
    if(!fetch(releaseReferenceApi,32768,raw,error,status))return IndexedCatalogResult::Legacy;
    auto root=releaseJson(raw);
    if(status!=200||!root||!cJSON_IsArray(root.get())||
       cJSON_GetArraySize(root.get())>int(maxIndexedReferences))return IndexedCatalogResult::Legacy;
    std::vector<Candidate> candidates;
    for(auto item=root->child;item;item=item->next) {
        const auto ref=singleString(item,"ref");
        constexpr std::string_view prefix="refs/tags/";
        if(ref.substr(0,prefix.size())!=prefix)return IndexedCatalogResult::Legacy;
        Candidate candidate;candidate.tag=ref.substr(prefix.size());
        if(!firmwareVersion(candidate.tag,candidate.version))return IndexedCatalogResult::Legacy;
        const auto object=singleField(item,"object");
        candidate.source=singleString(object,"sha");
        const auto type=singleString(object,"type");
        if((type!="commit"&&type!="tag")||!hex(candidate.source,40))return IndexedCatalogResult::Legacy;
        candidate.annotated=type=="tag";
        candidates.push_back(std::move(candidate));
    }
    std::sort(candidates.begin(),candidates.end(),[](const Candidate &a,const Candidate &b){return a.version>b.version;});
    for(size_t i=1;i<candidates.size();++i)if(candidates[i-1].version==candidates[i].version)
        return IndexedCatalogResult::Legacy;
    const bool truncated=candidates.size()>maxIndexedCandidates;
    if(truncated)candidates.resize(maxIndexedCandidates);
    candidates.shrink_to_fit();
    // Release the JSON response and tree BEFORE any following TLS handshake.
    root.reset();raw.clear();raw.shrink_to_fit();
    std::vector<Release> choices;
    for(const auto &candidate:candidates) {
        root.reset();raw.clear();raw.shrink_to_fit();
        status=0;
        if(!fetch(std::string(releaseApi)+"/tags/"+candidate.tag,32768,raw,error,status)) {
            if(status==404)continue;
            return IndexedCatalogResult::Failed;
        }
        root=releaseJson(raw);
        if(status!=200||!root||!cJSON_IsObject(root.get())) {
            error="Invalid GitHub release response during the tag check.";return IndexedCatalogResult::Failed;
        }
        const auto prerelease=singleField(root.get(),"prerelease");
        if(singleString(root.get(),"tag_name")!=candidate.tag||
           !cJSON_IsFalse(singleField(root.get(),"draft"))||!cJSON_IsBool(prerelease)||
           !validReleasePublication(singleString(root.get(),"published_at")))continue;
        bool manifest=false,image=false;
        const auto assets=singleField(root.get(),"assets");
        if(cJSON_IsArray(assets))for(auto asset=assets->child;asset;asset=asset->next) {
            const auto name=singleString(asset,"name");
            manifest|=name=="e32v2-update.json";image|=name=="firmware.bin";
        }
        if(!manifest||!image)continue;
        const bool preview=cJSON_IsTrue(prerelease);
        root.reset();raw.clear();raw.shrink_to_fit();
        std::string expectedSource=candidate.source;
        if(candidate.annotated) {
            status=0;
            if(!fetch(std::string("https://api.github.com/repos/dielessen/open_thermostat/git/tags/")+
                      candidate.source,32768,raw,error,status))return IndexedCatalogResult::Failed;
            root=releaseJson(raw);
            if(status!=200||!root||!cJSON_IsObject(root.get())||
               singleString(root.get(),"sha")!=candidate.source||singleString(root.get(),"tag")!=candidate.tag) {
                error="Invalid GitHub tag object.";return IndexedCatalogResult::Failed;
            }
            const auto object=singleField(root.get(),"object");
            // Deep tag chains use the existing general scan rather than an
            // unbounded dereference loop or treating a tag hash as a commit.
            if(singleString(object,"type")!="commit")return IndexedCatalogResult::Legacy;
            expectedSource=singleString(object,"sha");
            if(!hex(expectedSource,40)) {
                error="Invalid firmware source in the GitHub tag object.";return IndexedCatalogResult::Failed;
            }
            root.reset();raw.clear();raw.shrink_to_fit();
        }
        status=0;
        if(!fetch(assetUrl(candidate.tag,"e32v2-update.json"),4096,raw,error,status))return IndexedCatalogResult::Failed;
        Manifest parsed;
        if(!parseManifest(raw,candidate.tag,parsed))continue;
        if(parsed.source!=expectedSource) {
            error="The GitHub tag and the firmware source do not match.";return IndexedCatalogResult::Failed;
        }
        choices.push_back({candidate.tag,preview});
        if(choices.size()==2)break;
    }
    if(choices.empty()||(truncated&&choices.size()<2))return IndexedCatalogResult::Legacy;
    error.clear();out=std::move(choices);return IndexedCatalogResult::Complete;
}
}
