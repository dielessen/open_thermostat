#include "update/VerifiedOta.h"
#include "control/HttpAccessPolicy.h"
#include "control/CaptivePortalPolicy.h"
#include <gtest/gtest.h>
#include <vector>
using namespace heating::update;
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
    EXPECT_FALSE(releaseJson(std::string(24577,' ')));
    EXPECT_FALSE(releaseJson(std::string(17,'[')+std::string(17,']')));
    std::string many="[";for(int i=0;i<3000;++i)many+="0,";many+="0]";EXPECT_FALSE(releaseJson(many));
    EXPECT_FALSE(releaseJson("[\"\\u0000\"]"));EXPECT_FALSE(releaseJson("[\"unterminated]"));
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
      for(auto path:{"/config/reboot","/setup/reenter"})EXPECT_EQ(mutationBlocked(path,working,staged,pending),working);
      EXPECT_FALSE(mutationBlocked("/config/rooms",working,staged,pending));
    }
}
