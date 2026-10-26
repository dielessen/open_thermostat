#include "update/DownloadFailure.h"
#include <gtest/gtest.h>
using namespace heating::update;

TEST(DownloadFailure, ConnectionRefusalIsNotAnHttpResponseOrAnApiLimit) {
    const auto failure=downloadFailure(-1,0,"https://api.github.com/repos/owner/repo/releases");
    EXPECT_STREQ(failure.kind,"connection");EXPECT_EQ(failure.httpStatus,0);
    EXPECT_EQ(failure.clientCode,-1);EXPECT_EQ(failure.tlsCode,0);
    EXPECT_EQ(downloadFailureMessage(failure),"Could not connect to GitHub.");
}
TEST(DownloadFailure, CapturedTlsErrorRetainsBothNativeCodes) {
    const auto failure=downloadFailure(-1,-9984,"https://github.com/owner/repo/releases");
    EXPECT_STREQ(failure.kind,"tls");EXPECT_EQ(failure.clientCode,-1);
    EXPECT_EQ(failure.tlsCode,-9984);EXPECT_EQ(failure.httpStatus,0);
}
TEST(DownloadFailure, ActualHttpStatusDoesNotInheritAnOldTlsFailure) {
    for(int status:{403,404,429,503}) {
        const auto failure=downloadFailure(status,-9984,"https://api.github.com/repos/a/b");
        EXPECT_STREQ(failure.kind,"http");EXPECT_EQ(failure.httpStatus,status);
        EXPECT_EQ(failure.clientCode,0);EXPECT_EQ(failure.tlsCode,0);
        EXPECT_EQ(downloadFailureMessage(failure),"GitHub returned HTTP "+std::to_string(status)+".");
    }
}
TEST(DownloadFailure, PartialBodyIsATransferFailureDespiteHttp200) {
    const auto failure=downloadFailure(200,0,"https://release-assets.githubusercontent.com/asset?secret=value",true,-12);
    EXPECT_STREQ(failure.kind,"transfer");EXPECT_EQ(failure.httpStatus,200);
    EXPECT_EQ(failure.clientCode,-12);EXPECT_STREQ(failure.host,"release-assets.githubusercontent.com");
}
TEST(DownloadFailure, ShortPositiveBodyDoesNotBecomeAnHttpClientError) {
    const auto failure=downloadFailure(200,0,"https://objects.githubusercontent.com/a",true,1024);
    EXPECT_STREQ(failure.kind,"transfer");EXPECT_EQ(failure.clientCode,0);
}
TEST(DownloadFailure, DiagnosticHostNeverContainsCredentialsOrSignedAssetPaths) {
    EXPECT_STREQ(downloadHost("https://release-assets.githubusercontent.com/private?token=secret"),"release-assets.githubusercontent.com");
    for(const auto url:{"https://github.com.evil/a","https://user:secret@github.com/a","http://github.com/a","https://github.com:443/a"})
        EXPECT_STREQ(downloadHost(url),"");
}
TEST(DownloadFailure, SuccessfulResponseHasNoFailureMessageEvenWithOldTlsError) {
    const auto failure=downloadFailure(200,-9984,"https://github.com/a");
    EXPECT_STREQ(failure.kind,"none");EXPECT_TRUE(downloadFailureMessage(failure).empty());
}
