#include "control/StaticAssetPolicy.h"
#include <gtest/gtest.h>
#include <string>
using namespace heating::control;

TEST(StaticAssetPolicy, NegotiatesCompressionWithoutIgnoringExplicitExclusions) {
    for(const auto value:{"gzip","br, gzip, deflate","GZip;Q=1.000","gzip;q=0.001","*;q=1","*;q=0,gzip"})
        EXPECT_TRUE(acceptsAssetGzip(value))<<value;
    for(const auto value:{"","identity","br","gzip;q=0","gzip;q=0.000","gzip;q=0,*;q=1",
            "gzip;q=0,gzip;q=1","gzip;q=2","gzip;q=1.1","gzip;q=-1","gzip;q=.5",
            "gzip;q=0.1234","gzip;level=9","gzip;q=1;other=yes","xgzip"})
        EXPECT_FALSE(acceptsAssetGzip(value))<<value;
    EXPECT_TRUE(acceptsAssetGzip("",true));
    EXPECT_FALSE(acceptsAssetGzip("identity",true));
    EXPECT_FALSE(acceptsAssetGzip(std::string(1025,' ')+"gzip",true));
    // As served (gzip only): no header accepts gzip, explicit refusals do not.
    for(const auto value:{"identity","identity;q=1,gzip;q=0","*;q=0","gzip;q=0,*;q=1","br"})
        EXPECT_FALSE(acceptsAssetGzip(value,true))<<value;
    EXPECT_TRUE(acceptsAssetGzip("gzip, deflate, br, zstd",true));
}
TEST(StaticAssetPolicy, RevalidatesOnlyTheSelectedRepresentationWithBoundedWeakComparison) {
    const auto etag='"'+std::string(64,'a')+'"';
    const auto other='"'+std::string(64,'b')+'"';
    EXPECT_TRUE(assetNotModified(etag,etag));
    EXPECT_TRUE(assetNotModified("W/"+etag,etag));
    EXPECT_TRUE(assetNotModified(other+", W/"+etag,etag));
    EXPECT_TRUE(assetNotModified(" * ",etag));
    EXPECT_FALSE(assetNotModified(other,etag));
    EXPECT_FALSE(assetNotModified("",etag));
    EXPECT_FALSE(assetNotModified("w/"+etag,etag));
    EXPECT_FALSE(assetNotModified(etag.substr(1,64),etag));
    EXPECT_FALSE(assetNotModified(std::string(2049,' ')+etag,etag));
    EXPECT_FALSE(assetNotModified("*",""));
}
