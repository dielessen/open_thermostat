#include "update/ManualAppUpload.h"
#include <gtest/gtest.h>
#include <limits>
#include <string>
#include <vector>
using heating::update::ManualAppUpload;
namespace {
struct Backend {
    bool beginOk=true,writeOk=true,endOk=true,selectOk=true;
    int begins=0,writes=0,ends=0,selects=0,aborts=0;
    size_t size=0;
    std::vector<std::string> calls;
    bool begin(size_t n){++begins;size=n;calls.push_back("begin");return beginOk;}
    bool write(const void*,size_t){++writes;calls.push_back("write");return writeOk;}
    bool end(){++ends;calls.push_back("end");return endOk;}
    bool select(){++selects;calls.push_back("select");return selectOk;}
    void abort(){++aborts;calls.push_back("abort");}
};
const char bytes[8]={};
}
TEST(ManualAppUpload, StrictSizeRejectsMissingSignsSuffixWhitespaceAndCapacityOverflowBeforeErase) {
    for(auto text:{"","0","-1","+8"," 8","8 ","8x","1e3","9","4294967296","999999999999999999999999999999999999"}) {
        Backend b;ManualAppUpload s;
        EXPECT_FALSE(s.begin(b,text,8))<<text;
        EXPECT_EQ(b.begins,0)<<text;EXPECT_EQ(b.selects,0);EXPECT_EQ(b.aborts,0);
    }
}
TEST(ManualAppUpload, SizeParsingCannotWrapNativeSizeT) {
    Backend b;ManualAppUpload s;const auto max=std::numeric_limits<size_t>::max();
    ASSERT_TRUE(s.begin(b,std::to_string(max),max));EXPECT_EQ(b.size,max);s.cancel(b);EXPECT_EQ(b.aborts,1);
    s.reset(b);EXPECT_FALSE(s.begin(b,std::to_string(max)+"0",max));EXPECT_EQ(b.begins,1);
}
TEST(ManualAppUpload, ZeroCapacityRejectedAndExactCapacityPassedToNativeErase) {
    Backend b;ManualAppUpload s;EXPECT_FALSE(s.begin(b,"8",0));s.reset(b);
    ASSERT_TRUE(s.begin(b,"8",8));EXPECT_EQ(b.size,8u);s.cancel(b);
}
TEST(ManualAppUpload, FullImageWaitsForFinalHandlerBeforeSelectingAndAllowsEmptyFinalWrite) {
    Backend b;ManualAppUpload s;ASSERT_TRUE(s.begin(b,"8",100));
    ASSERT_TRUE(s.append(b,bytes,3));ASSERT_TRUE(s.append(b,bytes,5));
    ASSERT_TRUE(s.append(b,nullptr,0));ASSERT_TRUE(s.finish(b));
    EXPECT_EQ(b.selects,0);ASSERT_TRUE(s.select(b));s.cancel(b);
    EXPECT_TRUE(s.selected());EXPECT_EQ(b.aborts,0);
    EXPECT_EQ(b.calls,(std::vector<std::string>{"begin","write","write","end","select"}));
}
TEST(ManualAppUpload, TruncationAbortsWithoutValidationOrSelection) {
    Backend b;ManualAppUpload s;ASSERT_TRUE(s.begin(b,"8",8));ASSERT_TRUE(s.append(b,bytes,7));
    EXPECT_FALSE(s.finish(b));EXPECT_EQ(s.error(),ManualAppUpload::Error::incomplete);
    EXPECT_EQ(b.aborts,1);EXPECT_EQ(b.ends,0);EXPECT_FALSE(s.select(b));
    s.cancel(b);EXPECT_EQ(b.aborts,1);EXPECT_EQ(b.selects,0);
}
TEST(ManualAppUpload, ExcessByteRejectedBeforeWriteAndCannotRevive) {
    Backend b;ManualAppUpload s;ASSERT_TRUE(s.begin(b,"8",8));ASSERT_TRUE(s.append(b,bytes,8));
    EXPECT_FALSE(s.append(b,bytes,1));EXPECT_EQ(b.writes,1);EXPECT_EQ(b.aborts,1);
    EXPECT_FALSE(s.finish(b));EXPECT_FALSE(s.select(b));EXPECT_EQ(b.selects,0);
}
TEST(ManualAppUpload, NullNonemptyChunkAborts) {
    Backend b;ManualAppUpload s;ASSERT_TRUE(s.begin(b,"8",8));EXPECT_FALSE(s.append(b,nullptr,1));EXPECT_EQ(b.writes,0);EXPECT_EQ(b.aborts,1);
}
TEST(ManualAppUpload, NativeBeginFailureDoesNotAbortUnownedHandle) {
    Backend b;b.beginOk=false;ManualAppUpload s;EXPECT_FALSE(s.begin(b,"8",8));
    s.cancel(b);EXPECT_EQ(b.aborts,0);EXPECT_FALSE(s.finish(b));EXPECT_FALSE(s.select(b));
}
TEST(ManualAppUpload, NativeWriteFailureReleasesHandleExactlyOnce) {
    Backend b;b.writeOk=false;ManualAppUpload s;ASSERT_TRUE(s.begin(b,"8",8));EXPECT_FALSE(s.append(b,bytes,8));
    s.cancel(b);s.reset(b);EXPECT_EQ(b.aborts,1);EXPECT_EQ(b.ends,0);EXPECT_EQ(b.selects,0);
}
TEST(ManualAppUpload, NativeEndFailureNeverAbortsConsumedHandleOrSelects) {
    Backend b;b.endOk=false;ManualAppUpload s;ASSERT_TRUE(s.begin(b,"8",8));ASSERT_TRUE(s.append(b,bytes,8));
    EXPECT_FALSE(s.finish(b));s.cancel(b);s.reset(b);EXPECT_EQ(b.ends,1);EXPECT_EQ(b.aborts,0);EXPECT_EQ(b.selects,0);
}
TEST(ManualAppUpload, NativeSelectionFailureCannotReportSuccessOrRetryWithinRequest) {
    Backend b;b.selectOk=false;ManualAppUpload s;ASSERT_TRUE(s.begin(b,"8",8));ASSERT_TRUE(s.append(b,bytes,8));ASSERT_TRUE(s.finish(b));
    EXPECT_FALSE(s.select(b));EXPECT_FALSE(s.select(b));EXPECT_FALSE(s.selected());EXPECT_EQ(b.selects,1);EXPECT_EQ(b.aborts,0);
}
TEST(ManualAppUpload, LostAuthorizationOrDisconnectedRequestCancelsAndBlocksLaterCallbacks) {
    for(bool validated:{false,true}) {
        Backend b;ManualAppUpload s;ASSERT_TRUE(s.begin(b,"8",8));
        if(validated){ASSERT_TRUE(s.append(b,bytes,8));ASSERT_TRUE(s.finish(b));}
        s.cancel(b);EXPECT_FALSE(s.append(b,bytes,8));EXPECT_FALSE(s.finish(b));EXPECT_FALSE(s.select(b));
        EXPECT_EQ(b.selects,0);EXPECT_EQ(b.aborts,validated?0:1);
    }
}
TEST(ManualAppUpload, SecondMultipartFileInvalidatesFirstBeforeBootSelection) {
    for(bool validated:{false,true}) {
        Backend b;ManualAppUpload s;ASSERT_TRUE(s.begin(b,"8",8));
        if(validated){ASSERT_TRUE(s.append(b,bytes,8));ASSERT_TRUE(s.finish(b));}
        EXPECT_FALSE(s.begin(b,"8",8));EXPECT_EQ(b.begins,1);EXPECT_FALSE(s.select(b));EXPECT_EQ(b.selects,0);
    }
}
TEST(ManualAppUpload, EmptyRequestAndRepeatedEndCannotSelectStaleImage) {
    Backend b;ManualAppUpload s;EXPECT_FALSE(s.select(b));s.reset(b);
    ASSERT_TRUE(s.begin(b,"8",8));ASSERT_TRUE(s.append(b,bytes,8));ASSERT_TRUE(s.finish(b));
    EXPECT_FALSE(s.finish(b));EXPECT_FALSE(s.select(b));EXPECT_EQ(b.ends,1);EXPECT_EQ(b.selects,0);
}
TEST(ManualAppUpload, NewRequestResetsFailureAndCleansAbandonedHandle) {
    Backend b;ManualAppUpload s;ASSERT_TRUE(s.begin(b,"8",8));s.reset(b);EXPECT_EQ(b.aborts,1);
    ASSERT_TRUE(s.begin(b,"8",8));ASSERT_TRUE(s.append(b,bytes,8));ASSERT_TRUE(s.finish(b));ASSERT_TRUE(s.select(b));
    s.reset(b);EXPECT_FALSE(s.selected());EXPECT_EQ(s.received(),0u);EXPECT_FALSE(s.select(b));EXPECT_EQ(b.selects,1);
}

TEST(ManualAppUpload, EarlierProtocolFailureCannotEraseBeforeExplicitNewRequestReset) {
    Backend b;ManualAppUpload s;EXPECT_FALSE(s.append(b,bytes,1));
    EXPECT_FALSE(s.begin(b,"8",8));EXPECT_EQ(b.begins,0);
    s.reset(b);ASSERT_TRUE(s.begin(b,"8",8));s.cancel(b);EXPECT_EQ(b.aborts,1);
}
namespace {
// An ESP32 app header for the 16 MB flash (as VerifiedOta checks) and room for a marker.
std::string boardImage(const std::string &marker,size_t size=512,size_t at=200) {
    std::string image(size,'\0');image[0]=char(0xe9);image[3]=char(0x40);
    image.replace(at,marker.size(),marker);return image;
}
const std::string marker="OT_E32V2_OTA_V1:v1.0.0-rc.2:"+std::string(40,'a')+":"+std::string(64,'b')+":END";
bool upload(Backend &b,ManualAppUpload &s,const std::string &image,size_t chunk) {
    if(!s.begin(b,std::to_string(image.size()),4096)) return false;
    for(size_t at=0;at<image.size();at+=chunk) if(!s.append(b,image.data()+at,std::min(chunk,image.size()-at))) return false;
    return s.finish(b);
}
}
TEST(ManualAppUpload, BoardBuildRefusesAnImageWithoutTheOpenThermostatMarkerBeforeOtaEnd) {
    // A valid ESP32 app of another project, the marker of another board, a broken marker, and
    // the right marker on a different chip or flash size: all aborted, never ended or selected.
    for(const auto &image:{boardImage(""),boardImage("OT_ESP32_OTA_V1:v1.0.0:"+std::string(40,'a')+":"+std::string(64,'b')+":END"),
                           boardImage(marker.substr(0,marker.size()-1)),boardImage("OT_E32V2_OTA_V1:1.0.0:"+std::string(40,'a')+":"+std::string(64,'b')+":END"),
                           [] { auto i=boardImage(marker);i[12]=char(9);return i; }(),[] { auto i=boardImage(marker);i[3]=char(0x20);return i; }()}) {
        Backend b;ManualAppUpload s(true);
        EXPECT_FALSE(upload(b,s,image,64));
        EXPECT_EQ(s.error(),ManualAppUpload::Error::not_openthermostat);EXPECT_STREQ(s.reason(),"not_openthermostat_image");
        EXPECT_EQ(b.ends,0);EXPECT_EQ(b.aborts,1);EXPECT_FALSE(s.select(b));EXPECT_EQ(b.selects,0);
    }
}
TEST(ManualAppUpload, BoardBuildFindsTheMarkerAcrossChunkBordersAndKeepsTheRestUnchanged) {
    for(size_t chunk:{1,7,64,173,512}) for(size_t at:{size_t(16),size_t(100),512-marker.size()}) {
        Backend b;ManualAppUpload s(true);ASSERT_TRUE(upload(b,s,boardImage(marker,512,at),chunk))<<chunk<<' '<<at;
        ASSERT_TRUE(s.select(b));EXPECT_EQ(b.ends,1);EXPECT_EQ(b.aborts,0);
    }
    // reset() keeps the board rule; a build without it (other boards) accepts any image as before.
    Backend b;ManualAppUpload s(true);s.reset(b);EXPECT_FALSE(upload(b,s,boardImage(""),64));
    Backend other;ManualAppUpload any;EXPECT_TRUE(upload(other,any,std::string(512,'\0'),64));
}
