#include "control/JsonString.h"
#include <cJSON.h>
#include <gtest/gtest.h>
#include <iomanip>
#include <memory>
#include <random>
#include <sstream>

namespace {
using heating::control::writeJsonString;
void roundtrip(const std::string& input) {
    std::ostringstream out; writeJsonString(out, input);
    auto bytes = out.str();
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> value(cJSON_ParseWithOpts(bytes.c_str(), nullptr, true), cJSON_Delete);
    ASSERT_TRUE(value) << bytes;
    ASSERT_TRUE(cJSON_IsString(value.get()));
    EXPECT_EQ(std::string(value->valuestring), input);
}
TEST(JsonString, JsonParserRoundtripsControlsQuotesSlashesAndUtf8) {
    roundtrip(""); roundtrip("Room \"north\"\\one\n\r\tZoë 🚀");
    for (unsigned byte = 1; byte < 128; ++byte) roundtrip(std::string(1, char(byte)));
    std::ostringstream zero; writeJsonString(zero, std::string_view("\0", 1));
    EXPECT_EQ(zero.str(), "\"\\u0000\"");
}
TEST(JsonString, DoesNotChangeTheCallersFormattingFlags) {
    std::ostringstream out; out << std::hex << std::setfill('x');
    const auto flags = out.flags(); const auto fill = out.fill();
    writeJsonString(out, "\n");
    EXPECT_EQ(out.flags(), flags); EXPECT_EQ(out.fill(), fill);
    out << 31; EXPECT_EQ(out.str(), "\"\\u000a\"1f");
}
TEST(JsonString, BoundedAsciiMutationCorpusRoundtripsThroughRealJsonParser) {
    std::mt19937 random(7291);
    for (unsigned test = 0; test < 1000; ++test) {
        std::string input;
        for (unsigned n = random() % 81; n; --n) input += char(1 + random() % 127);
        roundtrip(input);
    }
}
}
