#include "control/RoomDisplayNames.h"
#include <gtest/gtest.h>
using namespace heating::control;
TEST(RoomDisplayNames, BoundedAsciiAndUnicodeLabelsUseExistingAsciiWire) {
 for(const auto label:{"4261646b616d6572","5a6fc3ab","f09f9a80","3c696d673e"})EXPECT_TRUE(validRoomDisplayNameHex(label));
 std::string maximum;for(size_t i=0;i<80;++i)maximum+="61";
 EXPECT_TRUE(validRoomDisplayNameHex(maximum));EXPECT_FALSE(validRoomDisplayNameHex(maximum+"61"));
}
TEST(RoomDisplayNames, InvalidEncodingControlsEmptyAndOversizeAreRejected) {
 for(const auto label:{"","0","00","20","202020","0a","7f","c080","eda080","f4908080","f09f","80","zz","AA","f5808080","e08080"})EXPECT_FALSE(validRoomDisplayNameHex(label))<<label;
}
