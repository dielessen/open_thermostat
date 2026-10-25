#include "update/IndexedReleaseCatalog.h"
#include <gtest/gtest.h>
#include <map>
using namespace heating::update;
namespace {
std::string tag(unsigned n){return "v0.1.0-e32v2-alpha."+std::to_string(n);}
std::string sha(unsigned n){return std::string(40,char('a'+n%6));}
std::string ref(unsigned n){return "{\"ref\":\"refs/tags/"+tag(n)+"\",\"object\":{\"type\":\"commit\",\"sha\":\""+sha(n)+"\"}}";}
std::string release(unsigned n){return "{\"tag_name\":\""+tag(n)+"\",\"draft\":false,\"prerelease\":true,\"published_at\":\"2026-10-23T10:00:00Z\",\"assets\":[{\"name\":\"e32v2-update.json\"},{\"name\":\"firmware.bin\"}]}";}
std::string manifest(unsigned n){return "{\"update_schema\":1,\"settings_schema\":1,\"board\":\"bbqkees_e32v2\",\"layout\":\"e32v2-dual-app-spiffs-v1\",\"ui\":\"embedded\",\"asset\":\"firmware.bin\",\"version\":\""+tag(n)+"\",\"source_commit\":\""+sha(n)+"\",\"web_sha256\":\""+std::string(64,'b')+"\",\"sha256\":\""+std::string(64,'c')+"\",\"size\":1024}";}
struct Fetch {
 std::map<std::string,std::pair<int,std::string>> responses;std::vector<std::string> calls;
 bool operator()(const std::string &url,size_t limit,std::string &body,std::string &error,int &status){calls.push_back(url);auto i=responses.find(url);if(i==responses.end()){status=404;error="not found";return false;}status=i->second.first;body=i->second.second;if(status!=200){error="HTTP failure";return false;}if(body.size()>limit){error="over limit";return false;}return true;}
 void add(unsigned n){responses[std::string(releaseApi)+"/tags/"+tag(n)]={200,release(n)};responses[assetUrl(tag(n),"e32v2-update.json")]={200,manifest(n)};}
 void index(const std::string &raw){responses[releaseReferenceApi]={200,raw};}
};
}
TEST(IndexedRelease, CanonicalVersionGrammarAndOverflowAreBounded) {
 std::array<uint32_t,4> v{};ASSERT_TRUE(alphaVersion(tag(10),v));EXPECT_EQ(v,(std::array<uint32_t,4>{0,1,0,10}));
 for(const auto bad:{"v0.1.0-e32v2-alpha.01","v0.1.0-e32v2-alpha.-1","v0.1.0-e32v2-alpha.4294967296","v00.1.0-e32v2-alpha.1","v1.0","v1.0.0-rc.1","v1.0.0-e32v2-alpha.1/x"})EXPECT_FALSE(alphaVersion(bad,v));
}
TEST(IndexedRelease, NumericAlphaOrderUsesOnlyFiveVerifiedRequestsForTwoChoices) {
 Fetch f;f.index("["+ref(9)+","+ref(10)+","+ref(2)+"]");f.add(9);f.add(10);f.add(2);std::vector<Release> out;std::string error;
 ASSERT_EQ(discoverIndexedReleases(f,out,error),IndexedCatalogResult::Complete);ASSERT_EQ(out.size(),2u);EXPECT_EQ(out[0].tag,tag(10));EXPECT_EQ(out[1].tag,tag(9));EXPECT_TRUE(error.empty());EXPECT_EQ(f.calls.size(),5u);
}
TEST(IndexedRelease, UnpublishedTagIsSkippedButPublicManifestFailureDoesNotPublishPartialChoices) {
 Fetch f;f.index("["+ref(12)+","+ref(11)+","+ref(10)+"]");f.add(11);f.add(10);std::vector<Release> out;std::string error;
 ASSERT_EQ(discoverIndexedReleases(f,out,error),IndexedCatalogResult::Complete);EXPECT_EQ(out[0].tag,tag(11));EXPECT_EQ(out[1].tag,tag(10));
 f.responses.erase(assetUrl(tag(10),"e32v2-update.json"));out={{"previous",false}};
 EXPECT_EQ(discoverIndexedReleases(f,out,error),IndexedCatalogResult::Failed);ASSERT_EQ(out.size(),1u);EXPECT_EQ(out[0].tag,"previous");
}
TEST(IndexedRelease, NetworkFailureIsNotAnUnpublishedTag) {
 Fetch f;f.index("["+ref(2)+","+ref(1)+"]");f.add(2);f.add(1);f.responses[std::string(releaseApi)+"/tags/"+tag(1)]={-1,""};std::vector<Release> out{{"previous",false}};std::string error;
 EXPECT_EQ(discoverIndexedReleases(f,out,error),IndexedCatalogResult::Failed);EXPECT_EQ(out[0].tag,"previous");
}
TEST(IndexedRelease, FutureVersionFormatsAndOversizedIndexRetainLegacyDiscovery) {
 const std::vector<std::string> indices={"[]","{}","[{\"ref\":\"refs/tags/v1.0.0\"}]","[{\"ref\":\"refs/heads/v0.1.0-e32v2-alpha.1\"}]", "["+ref(1)+","+ref(1)+"]",std::string(32769,'x')};
 for(const auto &index:indices){Fetch f;f.index(index);std::vector<Release> out{{"previous",false}};std::string error;EXPECT_EQ(discoverIndexedReleases(f,out,error),IndexedCatalogResult::Legacy);EXPECT_EQ(out[0].tag,"previous");}

}
TEST(IndexedRelease, DraftWrongTagMissingAssetsAndInvalidPublicationAreNotOffered) {
 for(const unsigned fault:{0u,1u,2u,3u}){Fetch f;f.index("["+ref(3)+","+ref(2)+","+ref(1)+"]");for(unsigned n=1;n<=3;++n)f.add(n);auto bad=release(3);
 if(fault==0)bad.replace(bad.find("false"),5,"true");
 if(fault==1)bad.replace(bad.find(tag(3)),tag(3).size(),tag(8));
 if(fault==2)bad.replace(bad.find("firmware.bin"),12,"factory.bin");
 if(fault==3)bad.replace(bad.find("2026-10"),7,"2026-99");
 f.responses[std::string(releaseApi)+"/tags/"+tag(3)]={200,bad};std::vector<Release> out;std::string error;ASSERT_EQ(discoverIndexedReleases(f,out,error),IndexedCatalogResult::Complete);EXPECT_EQ(out[0].tag,tag(2));EXPECT_EQ(out[1].tag,tag(1));}
}
TEST(IndexedRelease, TagCommitMustMatchManifestAndMalformedReleaseNeverChangesPreviousChoices) {
 for(bool malformed:{false,true}){Fetch f;f.index("["+ref(2)+"]");f.add(2);if(malformed)f.responses[std::string(releaseApi)+"/tags/"+tag(2)]={200,"[]"};else{auto m=manifest(2);m.replace(m.find(sha(2)),40,std::string(40,'f'));f.responses[assetUrl(tag(2),"e32v2-update.json")]={200,m};}std::vector<Release> out{{"previous",false}};std::string error;EXPECT_EQ(discoverIndexedReleases(f,out,error),IndexedCatalogResult::Failed);EXPECT_EQ(out[0].tag,"previous");}
}
TEST(IndexedRelease, ReferenceAndAttemptLimitsDoNotBecomePartialDiscovery) {
 for(unsigned count:{13u,81u}){Fetch f;std::string index="[";for(unsigned n=1;n<=count;++n){if(n>1)index+=",";index+=ref(n);}index+="]";f.index(index);f.add(1);std::vector<Release> out{{"previous",false}};std::string error;EXPECT_EQ(discoverIndexedReleases(f,out,error),IndexedCatalogResult::Legacy);EXPECT_EQ(out[0].tag,"previous");EXPECT_LE(f.calls.size(),13u);}
}

TEST(IndexedRelease, ExistingAnnotatedTagsAreResolvedOnlyWhenSelected) {
 Fetch f;auto index="["+ref(1)+"]";
 index.replace(index.find("commit"),6,"tag");index.replace(index.find(sha(1)),40,std::string(40,'f'));
 f.index(index);f.add(1);
 const auto url="https://api.github.com/repos/dielessen/open_thermostat/git/tags/"+std::string(40,'f');
 const auto object="{\"sha\":\""+std::string(40,'f')+"\",\"tag\":\""+tag(1)+"\",\"object\":{\"type\":\"commit\",\"sha\":\""+sha(1)+"\"}}";
 f.responses[url]={200,object};std::vector<Release> out;std::string error;
 EXPECT_EQ(discoverIndexedReleases(f,out,error),IndexedCatalogResult::Complete);ASSERT_EQ(out.size(),1u);EXPECT_EQ(out[0].tag,tag(1));EXPECT_EQ(f.calls.size(),4u);
 auto nested=object;nested.replace(nested.find("commit"),6,"tag");f.responses[url]={200,nested};out={{"previous",false}};
 EXPECT_EQ(discoverIndexedReleases(f,out,error),IndexedCatalogResult::Legacy);EXPECT_EQ(out[0].tag,"previous");
 auto wrong=object;wrong.replace(wrong.find(tag(1)),tag(1).size(),tag(9));f.responses[url]={200,wrong};
 EXPECT_EQ(discoverIndexedReleases(f,out,error),IndexedCatalogResult::Failed);EXPECT_EQ(out[0].tag,"previous");
}

TEST(IndexedRelease, AvailabilityIsNumericUpgradeAndNeverDifferentOrOlderTag) {
 EXPECT_EQ(newerAlphaRelease(tag(9),{{tag(8),true},{tag(9),true}}),"");
 EXPECT_EQ(newerAlphaRelease(tag(9),{{tag(10),true},{tag(12),true},{tag(11),true}}),tag(12));
 EXPECT_EQ(newerAlphaRelease(tag(9),{{"ha-v0.4.0.dev99",true},{"vgarbage",false}}),"");
 EXPECT_EQ(newerAlphaRelease("unknown",{{tag(12),true}}),"");
 EXPECT_EQ(newerAlphaRelease(tag(9),{}),"");
}
