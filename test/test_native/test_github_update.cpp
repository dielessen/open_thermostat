#include "update/VerifiedOta.h"
#include "update/ReleaseCatalog.h"
#include "update/RestartTimer.h"
#include "control/HttpAccessPolicy.h"
#include "control/CaptivePortalPolicy.h"
#include <gtest/gtest.h>
#include <vector>
#include <map>
using namespace heating::update;
TEST(GitHubOtaRestart, UnarmedNeverRestartsAndGraceDoesNotDependOnBrowser) {
    RestartTimer timer;
    EXPECT_FALSE(timer.pending());EXPECT_FALSE(timer.due(100000,false));
    timer.schedule(1000);EXPECT_TRUE(timer.pending());
    EXPECT_FALSE(timer.due(3999,false));EXPECT_TRUE(timer.due(4000,false));
    EXPECT_FALSE(timer.due(5000,true));EXPECT_TRUE(timer.due(5000,false));
}
TEST(GitHubOtaRestart, DuplicateRequestsCannotPostponeRestart) {
    RestartTimer timer;timer.schedule(1000);timer.schedule(3900);
    EXPECT_TRUE(timer.due(4000,false));
    RestartTimer explicitRestart;explicitRestart.schedule(1000,1000);
    EXPECT_FALSE(explicitRestart.due(1999,false));EXPECT_TRUE(explicitRestart.due(2000,false));
}
TEST(GitHubOtaRestart, MillisRolloverAndZeroSentinelRemainBounded) {
    RestartTimer timer;timer.schedule(UINT32_MAX-1000);
    EXPECT_FALSE(timer.due(UINT32_MAX,false));EXPECT_FALSE(timer.due(1998,false));
    EXPECT_TRUE(timer.due(1999,false));
    RestartTimer zero;zero.schedule(UINT32_MAX-2999);
    EXPECT_TRUE(zero.pending());EXPECT_FALSE(zero.due(0,false));EXPECT_TRUE(zero.due(1,false));
}
namespace {
Manifest manifest(){return {"v0.1.0-e32v2-alpha.2",std::string(40,'a'),std::string(64,'b'),std::string(64,'c'),1024};}
std::string document(){auto m=manifest();return "{\"update_schema\":1,\"settings_schema\":1,\"board\":\"bbqkees_e32v2\",\"layout\":\"e32v2-dual-app-spiffs-v1\",\"ui\":\"embedded\",\"asset\":\"firmware.bin\",\"version\":\""+m.tag+"\",\"source_commit\":\""+m.source+"\",\"web_sha256\":\""+m.webSha+"\",\"sha256\":\""+m.sha256+"\",\"size\":1024}";}
std::vector<uint8_t> image(){auto m=manifest();std::vector<uint8_t> bytes(m.size,0);bytes[0]=0xe9;bytes[3]=0x4f;auto marker=m.marker();std::copy(marker.begin(),marker.end(),bytes.begin()+117);return bytes;}
struct Backend {
    bool beginOk=true,writeOk=true,hashOk=true,endOk=true,readOk=true,selectOk=true;
    unsigned begins=0,writes=0,hashes=0,ends=0,reads=0,selects=0,aborts=0;
    bool begin(uint32_t){++begins;return beginOk;}
    bool write(const uint8_t*,size_t){++writes;return writeOk;}
    bool hashMatches(const std::string&){++hashes;return hashOk;}
    bool end(){++ends;return endOk;}
    bool readbackMatches(uint32_t,const std::string&){++reads;return readOk;}
    bool select(){++selects;return selectOk;}
    void abort(){++aborts;}
};
}
TEST(GitHubRelease, ManifestRequiresExactBoardLayoutSchemaAndEmbeddedUI) {
    Manifest m;ASSERT_TRUE(parseManifest(document(),manifest().tag,m));EXPECT_EQ(m.marker(),manifest().marker());
    for(auto pair:{std::make_pair("bbqkees_e32v2","esp32dev"),{"e32v2-dual-app-spiffs-v1","other-layout"},{"embedded","spiffs"},{"firmware.bin","e32v2-factory.bin"}}){auto raw=document();raw.replace(raw.find(pair.first),std::strlen(pair.first),pair.second);EXPECT_FALSE(parseManifest(raw,manifest().tag,m));}
    for(auto key:{"update_schema","settings_schema"}){auto raw=document();auto off=raw.find(std::string("\"")+key+"\":1");raw[off+std::strlen(key)+3]='2';EXPECT_FALSE(parseManifest(raw,manifest().tag,m));}
}
TEST(GitHubRelease, ManifestRejectsDuplicatesWrongVersionHashSizeAndEscapedNul) {
    Manifest m;auto raw=document();raw.insert(1,"\"size\":1024,");EXPECT_FALSE(parseManifest(raw,manifest().tag,m));
    EXPECT_FALSE(parseManifest(document(),"v99.0",m));
    for(auto replacement:{"0","1024.5","3670017","-1","1e100"}){raw=document();raw.replace(raw.rfind("1024"),4,replacement);EXPECT_FALSE(parseManifest(raw,manifest().tag,m));}
    raw=document();raw[raw.find(std::string(64,'c'))]='z';EXPECT_FALSE(parseManifest(raw,manifest().tag,m));
    raw=document();raw.insert(raw.find("bbqkees"),"\\u0000");EXPECT_FALSE(parseManifest(raw,manifest().tag,m));
}
TEST(GitHubRelease, URLsCannotEscapeFixedHttpsDownloadHostsOrTagPath) {
    for(auto url:{"https://github.com/dielessen/open_thermostat/releases/download/v1/firmware.bin","https://release-assets.githubusercontent.com/blob?signed=1","https://api.github.com/repos/dielessen/open_thermostat/releases","https://objects.githubusercontent.com/path"})EXPECT_TRUE(allowedDownloadUrl(url));
    for(auto url:{"http://github.com/a","https://github.com.evil/a","https://github.com@evil/a","https://evil/github.com/a","file:///tmp/a","https://github.com/a\r\nHeader:x","https://github.com\\evil/a"})EXPECT_FALSE(allowedDownloadUrl(url));
    for(auto tag:{"../../main","v1/evil","v1?x","v1#frag","v1%2fmain","release","v1\n"})EXPECT_FALSE(validTag(tag));
    EXPECT_TRUE(assetUrl("v1.2.3-e32v2-alpha.2","firmware.bin").find("/v1.2.3-e32v2-alpha.2/")!=std::string::npos);
}
TEST(GitHubRelease, PublicApiJsonHasHardByteDepthAndNodeBudgets) {
    EXPECT_TRUE(releaseJson("[{\"tag_name\":\"v1\",\"body\":\"quoted \\\" text\"}]"));
    EXPECT_FALSE(releaseJson(std::string(32769,' ')));
    EXPECT_FALSE(releaseJson(std::string(17,'[')+std::string(17,']')));
    std::string many="[";for(int i=0;i<3000;++i)many+="0,";many+="0]";EXPECT_FALSE(releaseJson(many));
    many="[";for(int i=0;i<1500;++i)many+="0,";many+="0]";EXPECT_TRUE(releaseJson(many));
    EXPECT_FALSE(releaseJson("[\"\\u0000\"]"));EXPECT_FALSE(releaseJson("[\"unterminated]"));
    EXPECT_TRUE(releaseJson("[1] \n"));EXPECT_FALSE(releaseJson("[1]garbage"));
}
TEST(GitHubOta, FullVerifiedImageSelectsOnlyAfterEveryIndependentGate) {
    Backend b;{VerifiedOta<Backend> s(b,manifest());ASSERT_TRUE(s.begin());auto bytes=image();
      for(size_t i=0;i<bytes.size();++i)ASSERT_TRUE(s.append(&bytes[i],1));
      EXPECT_EQ(b.selects,0u);EXPECT_TRUE(s.finish());EXPECT_FALSE(s.finish());EXPECT_EQ(b.hashes,1u);EXPECT_EQ(b.ends,1u);EXPECT_EQ(b.reads,1u);EXPECT_EQ(b.selects,1u);}
    EXPECT_EQ(b.aborts,0u);
}
TEST(GitHubOta, TruncationOversizeAndMissingMarkerCannotSelect) {
    for(int fault=0;fault<3;++fault){Backend b;{VerifiedOta<Backend>s(b,manifest());ASSERT_TRUE(s.begin());auto bytes=image();
      if(fault==0)bytes.resize(bytes.size()-1);if(fault==1)bytes.push_back(0);if(fault==2)bytes[117]='X';
      const bool appended=s.append(bytes.data(),bytes.size());EXPECT_EQ(appended,fault!=1);EXPECT_FALSE(s.finish());EXPECT_EQ(b.selects,0u);EXPECT_EQ(b.hashes,0u);}
      EXPECT_EQ(b.aborts,1u);}
}
TEST(GitHubOta, WrongChipFactoryAndFlashLayoutHeadersCannotSelect) {
    for(auto index:{0,3,12,13}){Backend b;{VerifiedOta<Backend>s(b,manifest());ASSERT_TRUE(s.begin());auto bytes=image();bytes[index]=0xff;ASSERT_TRUE(s.append(bytes.data(),bytes.size()));EXPECT_FALSE(s.finish());EXPECT_EQ(b.selects,0u);}}
}
TEST(GitHubOta, HashImageReadbackAndBootSelectFailuresAbortAndNeverClaimSuccess) {
    for(int fault=0;fault<5;++fault){Backend b;
      if(fault==0)b.writeOk=false;if(fault==1)b.hashOk=false;if(fault==2)b.endOk=false;if(fault==3)b.readOk=false;if(fault==4)b.selectOk=false;
      {VerifiedOta<Backend>s(b,manifest());ASSERT_TRUE(s.begin());auto bytes=image();EXPECT_EQ(s.append(bytes.data(),bytes.size()),fault!=0);EXPECT_FALSE(s.finish());
        EXPECT_EQ(b.selects,fault==4?1u:0u);if(fault<=1)EXPECT_EQ(b.ends,0u);if(fault<=2)EXPECT_EQ(b.reads,0u);}
      EXPECT_EQ(b.aborts,1u);}
}
TEST(GitHubOta, AbandonedSessionAndBeginFailureDoNotSelect) {
    Backend b;{VerifiedOta<Backend>s(b,manifest());ASSERT_TRUE(s.begin());EXPECT_FALSE(s.begin());}EXPECT_EQ(b.aborts,1u);EXPECT_EQ(b.selects,0u);
    Backend failed;failed.beginOk=false;{VerifiedOta<Backend>s(failed,manifest());EXPECT_FALSE(s.begin());EXPECT_FALSE(s.finish());}EXPECT_EQ(failed.selects,0u);
}
TEST(GitHubOta, MutationRoutesArePostOnlyAndNeverCaptivePortalLoginExceptions) {
    using namespace heating::control;
    for(auto path:{"/updates/check","/updates/install","/updates/reboot","/updates/rollback"}){
      EXPECT_TRUE(allowedHttpMethod(path,"POST"));EXPECT_FALSE(allowedHttpMethod(path,"GET"));EXPECT_FALSE(allowedHttpMethod(path,"DELETE"));
      EXPECT_EQ(portalAccess(true,true,"10.10.10.1","10.10.10.1",path,"POST"),PortalAccess::Authenticated);
    }
}
TEST(GitHubOta, ConcurrentOrUnconfirmedUpdatesCannotBypassGateViaManualUpload) {
    for(bool working:{false,true})for(bool staged:{false,true})for(bool pending:{false,true}) {
      for(auto path:{"/ota","/otafs"})EXPECT_EQ(mutationBlocked(path,working,staged,pending),working||staged||pending);
      for(auto path:{"/config/reboot","/setup/reenter"})EXPECT_EQ(mutationBlocked(path,working,staged,pending),working||pending); // pending: a restart rolls back
      EXPECT_FALSE(mutationBlocked("/config/rooms",working,staged,pending));
    }
}

namespace {
std::string catalogEntry(const std::string &tag,bool prerelease=true,bool draft=false,bool assets=true) {
    return "[{\"tag_name\":\""+tag+"\",\"prerelease\":"+(prerelease?"true":"false")+
      ",\"draft\":"+(draft?"true":"false")+",\"assets\":"+
      (assets?"[{\"name\":\"e32v2-update.json\"},{\"name\":\"firmware.bin\"}]":"[]")+"}]";
}
std::string catalogManifest(const std::string &tag) {
    auto raw=document();raw.replace(raw.find(manifest().tag),manifest().tag.size(),tag);return raw;
}
struct CatalogFetch {
    std::map<std::string,std::string> responses;
    std::vector<std::pair<std::string,size_t>> calls;
    bool operator()(const std::string &url,size_t limit,std::string &raw,std::string &error) {
        calls.push_back({url,limit});const auto found=responses.find(url);
        if(found==responses.end()){error="fixture transport failure";return false;}
        raw=found->second;return raw.size()<=limit;
    }
    void page(unsigned n,const std::string &raw){responses[releasePageUrl(n)]=raw;}
    void release(unsigned n,const std::string &tag,bool prerelease=true) {
        page(n,catalogEntry(tag,prerelease));responses[assetUrl(tag,"e32v2-update.json")]=catalogManifest(tag);
    }
};
}
TEST(GitHubCatalog, FindsTwoCompatibleFirmwareReleasesPastMultipleHaReleases) {
    CatalogFetch fetch;fetch.page(1,catalogEntry("ha-v0.4.0.dev12"));
    fetch.page(2,catalogEntry("ha-v0.4.0.dev11"));
    fetch.release(3,"v0.1.0-e32v2-alpha.7");fetch.release(4,"v0.1.0-e32v2-alpha.6",false);fetch.page(5,"[]");
    std::vector<Release> out;std::string error;
    ASSERT_TRUE(discoverReleases(fetch,out,error));ASSERT_EQ(out.size(),2u);
    EXPECT_EQ(out[0].tag,"v0.1.0-e32v2-alpha.7");EXPECT_TRUE(out[0].prerelease);
    EXPECT_EQ(out[1].tag,"v0.1.0-e32v2-alpha.6");EXPECT_FALSE(out[1].prerelease);
    ASSERT_EQ(fetch.calls.size(),7u);
    for(const auto &call:fetch.calls)EXPECT_EQ(call.second,call.first.find("api.github.com")!=std::string::npos?32768u:4096u);
}
TEST(GitHubCatalog, SkipsDraftMissingImageDuplicateAndIncompatibleManifest) {
    CatalogFetch fetch;fetch.page(1,catalogEntry("v1",true,true));
    fetch.page(2,"[{\"tag_name\":\"v2\",\"assets\":[{\"name\":\"e32v2-update.json\"}]}]");
    fetch.release(3,"v3");fetch.responses[assetUrl("v3","e32v2-update.json")]=document();
    fetch.release(4,"v4");fetch.page(5,catalogEntry("v4"));fetch.release(6,"v5");fetch.page(7,"[]");
    std::vector<Release> out;std::string error;
    ASSERT_TRUE(discoverReleases(fetch,out,error));ASSERT_EQ(out.size(),2u);
    EXPECT_EQ(out[0].tag,"v4");EXPECT_EQ(out[1].tag,"v5");
    EXPECT_EQ(fetch.calls.size(),10u);
    EXPECT_EQ(std::count_if(fetch.calls.begin(),fetch.calls.end(),[](const auto &call){return call.first==assetUrl("v4","e32v2-update.json");}),1);
}
TEST(GitHubCatalog, EmptyApiPageCompletesKnownCatalogWithoutAnotherRequest) {
    CatalogFetch fetch;fetch.release(1,"v1");fetch.page(2,"[]");
    std::vector<Release> out;std::string error;ASSERT_TRUE(discoverReleases(fetch,out,error));
    ASSERT_EQ(out.size(),1u);EXPECT_EQ(out[0].tag,"v1");EXPECT_EQ(fetch.calls.size(),3u);
    CatalogFetch empty;empty.page(1,"[]");ASSERT_TRUE(discoverReleases(empty,out,error));EXPECT_TRUE(out.empty());
}
TEST(GitHubCatalog, TransportFailureAfterFirstMatchDoesNotPublishPartialCatalog) {
    for(bool manifestFailure:{false,true}) {
        CatalogFetch fetch;fetch.release(1,"v1");
        if(manifestFailure)fetch.page(2,catalogEntry("v2"));
        std::vector<Release> out{{"v99",false}};std::string error;
        EXPECT_FALSE(discoverReleases(fetch,out,error));ASSERT_EQ(out.size(),1u);
        EXPECT_EQ(out[0].tag,"v99");EXPECT_EQ(error,"fixture transport failure");
    }
}
TEST(GitHubCatalog, InvalidPublicResponseIsRejectedWithoutChangingChoices) {
    for(const auto &raw:{std::string("{}"),std::string("[{},{}]"),std::string("[1]garbage"),std::string(32769,' ')}) {
        CatalogFetch fetch;fetch.page(1,raw);std::vector<Release> out{{"v99",false}};std::string error;
        EXPECT_FALSE(discoverReleases(fetch,out,error));ASSERT_EQ(out.size(),1u);EXPECT_EQ(out[0].tag,"v99");
        EXPECT_EQ(fetch.calls.size(),1u);
    }
}
TEST(GitHubCatalog, MixedCatalogScanIsBoundedAndDoesNotClaimOlderReleasesChecked) {
    CatalogFetch fetch;for(unsigned page=1;page<=maxReleasePages;++page)fetch.page(page,catalogEntry("ha-v0.4.0.dev12"));
    std::vector<Release> out{{"v99",false}};std::string error;
    EXPECT_FALSE(discoverReleases(fetch,out,error));ASSERT_EQ(out.size(),1u);EXPECT_EQ(out[0].tag,"v99");
    EXPECT_EQ(fetch.calls.size(),maxReleasePages);EXPECT_NE(error.find("older releases were not checked"),std::string::npos);
    EXPECT_EQ(releasePageUrl(1),"https://api.github.com/repos/dielessen/open_thermostat/releases?per_page=1&page=1");
    EXPECT_TRUE(releasePageUrl(0).empty());EXPECT_TRUE(releasePageUrl(maxReleasePages+1).empty());
}
TEST(GitHubCatalog, LastAllowedPageCanSupplyTheOnlyVerifiedChoice) {
    CatalogFetch fetch;for(unsigned page=1;page<maxReleasePages;++page)fetch.page(page,catalogEntry("ha-v0.4.0.dev12"));
    fetch.release(maxReleasePages,"v1");std::vector<Release> out;std::string error;
    ASSERT_TRUE(discoverReleases(fetch,out,error));ASSERT_EQ(out.size(),1u);EXPECT_EQ(out[0].tag,"v1");
    EXPECT_EQ(fetch.calls.size(),maxReleasePages+1);
}

TEST(GitHubCatalog, LatestPublishedCompatibleReleaseCanFollowTwoOlderMatches) {
    // Actual public API ordering observed23Oct:9,8,7,10. The first two
    // compatible entries are not proof that the newest release was checked.
    CatalogFetch fetch;
    auto dated=[&](unsigned page,const std::string &tag,const std::string &published) {
        fetch.release(page,tag);
        auto raw=catalogEntry(tag);raw.insert(2,"\"published_at\":\""+published+"\",");
        fetch.page(page,raw);
    };
    dated(1,"v0.1.0-e32v2-alpha.9","2026-10-23T04:04:28Z");
    dated(2,"v0.1.0-e32v2-alpha.8","2026-10-23T03:17:27Z");
    dated(3,"v0.1.0-e32v2-alpha.7","2026-10-23T01:57:48Z");
    dated(4,"v0.1.0-e32v2-alpha.10","2026-10-23T06:45:18Z");
    fetch.page(5,"[]");
    std::vector<Release> out;std::string error;
    ASSERT_TRUE(discoverReleases(fetch,out,error));ASSERT_EQ(out.size(),2u);
    EXPECT_EQ(out[0].tag,"v0.1.0-e32v2-alpha.10");
    EXPECT_EQ(out[1].tag,"v0.1.0-e32v2-alpha.9");
    EXPECT_EQ(fetch.calls.size(),9u);
}

TEST(GitHubCatalog, PublicationRankingRejectsMalformedCalendarAndOffsetDates) {
    for(const auto *date:{"2026-10-23T06:45:18Z","2024-02-29T23:59:59Z","2000-02-29T00:00:00Z"})
        EXPECT_TRUE(validReleasePublication(date))<<date;
    for(const auto *date:{"2026-02-29T00:00:00Z","2100-02-29T00:00:00Z","2026-00-01T00:00:00Z", "2026-04-31T00:00:00Z", "2026-10-23T24:00:00Z", "2026-10-23T00:60:00Z", "2026-10-23T00:00:60Z", "2026-10-23T00:00:00+01:00", "2026-10-23T00:00:00Zgarbage", ""})
        EXPECT_FALSE(validReleasePublication(date))<<date;
}
TEST(GitHubCatalog, FailureBeyondTwoMatchesCannotReplacePreviousChoices) {
    CatalogFetch fetch;fetch.release(1,"v1");fetch.release(2,"v2");
    std::vector<Release> out{{"v99",false}};std::string error;
    EXPECT_FALSE(discoverReleases(fetch,out,error));ASSERT_EQ(out.size(),1u);
    EXPECT_EQ(out[0].tag,"v99");EXPECT_EQ(error,"fixture transport failure");
}

TEST(GitHubOta, VerificationObserverRunsBeforeEachBackendGateInOrder) {
    Backend b;VerifiedOta<Backend> transfer(b,manifest());
    ASSERT_TRUE(transfer.begin());const auto bytes=image();
    ASSERT_TRUE(transfer.append(bytes.data(),bytes.size()));
    std::vector<OtaVerificationStep> observed;
    ASSERT_TRUE(transfer.finish([&](OtaVerificationStep step) {
        observed.push_back(step);
        switch(step) {
        case OtaVerificationStep::Hash:EXPECT_EQ(b.hashes,0u);break;
        case OtaVerificationStep::Image:EXPECT_EQ(b.hashes,1u);EXPECT_EQ(b.ends,0u);break;
        case OtaVerificationStep::Readback:EXPECT_EQ(b.ends,1u);EXPECT_EQ(b.reads,0u);break;
        case OtaVerificationStep::Select:EXPECT_EQ(b.reads,1u);EXPECT_EQ(b.selects,0u);break;
        }
    }));
    EXPECT_EQ(observed,(std::vector<OtaVerificationStep>{OtaVerificationStep::Hash,
        OtaVerificationStep::Image,OtaVerificationStep::Readback,OtaVerificationStep::Select}));
    EXPECT_FALSE(transfer.finish([&](OtaVerificationStep){ADD_FAILURE()<<"Repeated completion observed";}));
}
TEST(GitHubOta, FailedGateCannotEmitLaterVerificationCheckpoints) {
    const std::vector<OtaVerificationStep> order{OtaVerificationStep::Hash,
        OtaVerificationStep::Image,OtaVerificationStep::Readback,OtaVerificationStep::Select};
    for(size_t fault=0;fault<order.size();++fault) {
        Backend b;
        if(fault==0)b.hashOk=false;if(fault==1)b.endOk=false;
        if(fault==2)b.readOk=false;if(fault==3)b.selectOk=false;
        VerifiedOta<Backend> transfer(b,manifest());ASSERT_TRUE(transfer.begin());
        const auto bytes=image();ASSERT_TRUE(transfer.append(bytes.data(),bytes.size()));
        std::vector<OtaVerificationStep> observed;
        EXPECT_FALSE(transfer.finish([&](OtaVerificationStep step){observed.push_back(step);}));
        EXPECT_EQ(observed,std::vector<OtaVerificationStep>(order.begin(),order.begin()+fault+1));
        EXPECT_FALSE(transfer.finish([&](OtaVerificationStep){ADD_FAILURE()<<"Failed transfer retried";}));
        EXPECT_EQ(b.selects,fault==3?1u:0u);
    }
}
TEST(GitHubOta, ObserverFailureRetiresTransferBeforeItsBackendOperation) {
    for(unsigned fault=0;fault<4;++fault) {
        Backend b;VerifiedOta<Backend> transfer(b,manifest());ASSERT_TRUE(transfer.begin());
        const auto bytes=image();ASSERT_TRUE(transfer.append(bytes.data(),bytes.size()));
        unsigned observed=0;
        EXPECT_FALSE(transfer.finish([&](OtaVerificationStep){if(observed++==fault)throw 1;}));
        EXPECT_EQ(observed,fault+1);
        EXPECT_EQ(b.hashes,fault>0?1u:0u);EXPECT_EQ(b.ends,fault>1?1u:0u);
        EXPECT_EQ(b.reads,fault>2?1u:0u);EXPECT_EQ(b.selects,0u);
        EXPECT_FALSE(transfer.finish());
    }
}
TEST(GitHubOta, IncompleteImageEmitsNoVerificationCheckpoint) {
    Backend b;VerifiedOta<Backend> transfer(b,manifest());ASSERT_TRUE(transfer.begin());
    const auto bytes=image();ASSERT_TRUE(transfer.append(bytes.data(),bytes.size()-1));
    EXPECT_FALSE(transfer.finish([](OtaVerificationStep){ADD_FAILURE()<<"Incomplete image observed";}));
    EXPECT_EQ(b.hashes,0u);EXPECT_EQ(b.selects,0u);
}

TEST(GitHubOta, ObserverReentryCannotRepeatOrAdvanceVerification) {
    for(unsigned fault=0;fault<4;++fault) {
        Backend b;VerifiedOta<Backend> transfer(b,manifest());ASSERT_TRUE(transfer.begin());
        const auto bytes=image();ASSERT_TRUE(transfer.append(bytes.data(),bytes.size()));
        unsigned observed=0;
        EXPECT_FALSE(transfer.finish([&](OtaVerificationStep){
            if(observed++==fault)EXPECT_FALSE(transfer.finish());
        }));
        EXPECT_EQ(observed,fault+1);EXPECT_EQ(b.hashes,fault>0?1u:0u);
        EXPECT_EQ(b.ends,fault>1?1u:0u);EXPECT_EQ(b.reads,fault>2?1u:0u);
        EXPECT_EQ(b.selects,0u);EXPECT_FALSE(transfer.finish());
    }
}
TEST(GitHubOta, ObserverInvalidAppendCannotBeIgnoredByOuterCompletion) {
    Backend b;VerifiedOta<Backend> transfer(b,manifest());ASSERT_TRUE(transfer.begin());
    const auto bytes=image();ASSERT_TRUE(transfer.append(bytes.data(),bytes.size()));
    EXPECT_FALSE(transfer.finish([&](OtaVerificationStep){
        EXPECT_FALSE(transfer.append(bytes.data(),1));
    }));
    EXPECT_EQ(b.hashes,0u);EXPECT_EQ(b.selects,0u);EXPECT_FALSE(transfer.finish());
}
