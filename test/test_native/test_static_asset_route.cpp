#include "control/StaticAssetRoute.h"
#include <gtest/gtest.h>
#include <array>
using namespace heating::control;
namespace {
struct Asset {const char *path;};
constexpr std::array<Asset,5> assets{{{"/index.html"},{"/about.html"},{"/auth-client.js"},{"/deps/bs.min.css.gz"},{"/deps/jquery.min.js.gz"}}};
}
TEST(StaticAssetRoute, ExistingPagesScriptsAndGzipAliasesHaveExplicitMatches) {
 for(const auto path:{"/index.html","/about.html","/auth-client.js","/deps/bs.min.css.gz","/deps/bs.min.css","/deps/jquery.min.js.gz","/deps/jquery.min.js"})EXPECT_TRUE(embeddedAssetPath(path,assets))<<path;
}
TEST(StaticAssetRoute, MissingFilesApiPathsAndUnsafePathsAreNotCaptured) {
 for(const auto path:{"/status","/config/device","/auth/login","/updates/install","/missing.html","/favicon.ico","/index.html/extra","/deps/other.js","/../index.html","/%2e%2e/index.html","/index.html?x=1","index.html",""})EXPECT_FALSE(embeddedAssetPath(path,assets))<<path;
}
TEST(StaticAssetRoute, MatchingDoesNotGrantPostOrChangeLoginPolicy) {
 EXPECT_TRUE(embeddedAssetPath("/auth-client.js",assets));
 EXPECT_FALSE(allowedHttpMethod("/auth-client.js","POST"));
 EXPECT_FALSE(allowedHttpMethod("/index.html","DELETE"));
 EXPECT_TRUE(allowedHttpMethod("/index.html","GET"));
}
