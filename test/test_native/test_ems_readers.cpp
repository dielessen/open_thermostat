#include "EMS/DeviceVersion.h"
#include "EMS/UBADeviceVersion.h"
#include <gtest/gtest.h>
#include <cstdarg>
#include <cstdio>
#include <algorithm>

namespace {
using namespace heating::ems;
struct Probe: EmsTelegram {
    using EmsTelegram::EmsTelegram;
    using EmsTelegram::getValueAbs;
    using EmsTelegram::getDataOffset;
    using EmsTelegram::getValue;
    using EmsTelegram::getValueCustomOffset;
};
Probe report(std::vector<uint8_t> bytes,uint8_t offset=0,uint16_t type=2) {
    return {EmsTelegram::BROADCAST,8,0,offset,type,std::move(bytes)};
}
TEST(EmsReaders, DirectPayloadAccessRejectsTruncatedWordsAndCounters) {
    auto empty=report({});EXPECT_FALSE(empty.getValueAbs<uint8_t>(0));EXPECT_FALSE(empty.getValueAbs<bool>(255));
    auto one=report({1});EXPECT_FALSE(one.getValueAbs<uint16_t>(0));EXPECT_FALSE(one.getValueAbs<int32_t>(0));
    auto two=report({1,2});EXPECT_EQ(two.getValueAbs<uint16_t>(0),258);EXPECT_FALSE(two.getValueAbs<uint16_t>(1));
    EXPECT_FALSE(two.getValueAbs<uint32_t>(0));EXPECT_FALSE(two.getValueAbs<uint8_t>(255));
}
TEST(EmsReaders, EveryPayloadPositionAndSupportedWidthHasTheSameBoundedWindow) {
    for(size_t size=0;size<=32;++size) {
        Probe p=report(std::vector<uint8_t>(size,0xAB));
        for(unsigned at=0;at<=255;++at) {
            const auto fits=[&](size_t width){return at<=size&&width<=size-at;};
            EXPECT_EQ(p.getValueAbs<uint8_t>(at).has_value(),fits(1));
            EXPECT_EQ(p.getValueAbs<int8_t>(at).has_value(),fits(1));
            EXPECT_EQ((p.getValueAbs<bool,7>(at).has_value()),fits(1));
            EXPECT_EQ(p.getValueAbs<uint16_t>(at).has_value(),fits(2));
            EXPECT_EQ(p.getValueAbs<int16_t>(at).has_value(),fits(2));
            EXPECT_EQ(p.getValueAbs<uint32_t>(at).has_value(),fits(3));
            EXPECT_EQ(p.getValueAbs<int32_t>(at).has_value(),fits(3));
        }
    }
}
TEST(EmsReaders, ProtocolOffsetsDoNotBecomeIndexesIntoPartialPayloads) {
    EXPECT_EQ(report(std::vector<uint8_t>(200,0)).getDataOffset(128,1),-1);
    EXPECT_EQ(report({1,2,3},254).getDataOffset(255,1),1);
    for(const uint8_t start:{uint8_t(0),uint8_t(1),uint8_t(127),uint8_t(254),uint8_t(255)}) {
        auto p=report({0x12,0x34,0x56},start);
        for(unsigned at=0;at<=255;++at) {
            const auto fits=[&](size_t width){return at>=start&&at-start+width<=3;};
            EXPECT_EQ(p.getValue<uint16_t>(at).has_value(),fits(2));
            EXPECT_EQ(p.getValue<uint32_t>(at).has_value(),fits(3));
            EXPECT_EQ(p.getValueCustomOffset<uint16_t>(at,start).has_value(),fits(2));
        }
    }
}
TEST(EmsReaders, SignedValuesUseExactTwosComplementAtAllBoundaries) {
    EXPECT_EQ(report({0xFF}).getValueAbs<int8_t>(0),-1);
    EXPECT_EQ(report({0x80}).getValueAbs<int8_t>(0),-128);
    EXPECT_EQ(report({0xFF,0xFF}).getValueAbs<int16_t>(0),-1);
    EXPECT_EQ(report({0x80,0}).getValueAbs<int16_t>(0),-32768);
    EXPECT_EQ(report({0x7F,0xFF}).getValueAbs<int16_t>(0),32767);
    EXPECT_EQ(report({0xFF,0xFF,0xFF}).getValueAbs<int32_t>(0),-1);
    EXPECT_EQ(report({0x80,0,0}).getValueAbs<int32_t>(0),-8388608);
    EXPECT_EQ(report({0x7F,0xFF,0xFF}).getValueAbs<int32_t>(0),8388607);
    EXPECT_EQ(report({0xFF,0xFF,0xFF}).getValueAbs<uint32_t>(0),16777215u);
    EXPECT_EQ((report({0x80}).getValueAbs<bool,7>(0)),true);
    EXPECT_EQ((report({0x80}).getValueAbs<bool,0>(0)),false);
}
TEST(EmsVersion, StandardAndLeadingEmptyTupleShareOneCompleteDecoder) {
    for(auto p:{report({77,1,2,0,0,0,0,0,0,4}),report({0,0,0,77,1,2,0,0,0,4})}) {
        const auto v=readDeviceVersion(p);ASSERT_TRUE(v);
        EXPECT_EQ(v->product,77);EXPECT_EQ(v->major,1);EXPECT_EQ(v->minor,2);EXPECT_EQ(v->brand,4);
    }
    const auto noBrand=readDeviceVersion(report({77,0,0}));ASSERT_TRUE(noBrand);
    EXPECT_EQ(noBrand->major,0);EXPECT_EQ(noBrand->minor,0);EXPECT_FALSE(noBrand->brand);
}
TEST(EmsVersion, PartialFragmentsCannotAssembleOrInventIdentity) {
    for(const auto& bytes:std::vector<std::vector<uint8_t>>{{},{77},{77,1},{0,0,0},{0,0,0,77},{0,0,0,77,1}})
        EXPECT_FALSE(readDeviceVersion(report(bytes)));
    EXPECT_FALSE(readDeviceVersion(report({77,1,2},3)));
    EXPECT_FALSE(readDeviceVersion(report({0,0,0,0,1,2})));
}
TEST(EmsVersion, RequestsOtherTypesAndUnknownSentinelsAreNotIdentityReports) {
    EXPECT_FALSE(readDeviceVersion(report({77,1,2},0,0x18)));
    for(auto op:{EmsTelegram::READ,EmsTelegram::READ_WITH_DATA})
        EXPECT_FALSE(readDeviceVersion(EmsTelegram{op,8,16,0,2,{77,1,2}}));
    for(const auto& bytes:std::vector<std::vector<uint8_t>>{{255,1,2},{77,255,2},{77,1,255},{0,0,0,255,1,2}})
        EXPECT_FALSE(readDeviceVersion(report(bytes)));
    auto missingBrand=readDeviceVersion(report({77,1,2,0,0,0,0,0,0,255}));ASSERT_TRUE(missingBrand);EXPECT_FALSE(missingBrand->brand);
}
class CaptureLog final: public ib::logger::LoggerInterface {
public:
    mutable std::string text;
    void printf(LogLevel,const char* format,...)const override {va_list args;va_start(args,format);append(format,args);va_end(args);}
    void printf(LogLevel,LogFeatureType,const char* format,...)const override {va_list args;va_start(args,format);append(format,args);va_end(args);}
    bool doesMeetsLevelCondition(LogLevel)const override{return true;}
    bool doesFeatureMeetsLevelCondition(LogLevel,LogFeatureType)const override{return true;}
    LogLevel getMaxLogLevel()const override{return LogLevel::TRACE;}
    void setLogFeatures(LogFeature)override{}
    LogFeatureType addFeature(std::string,bool)override{return 1;}
    std::string getFeatureName(LogFeatureType)const override{return "EMS";}
    std::unordered_map<LogFeatureType,std::string> getRegisteredFeatures()const override{return {};}
    bool isFeatureEnabled(LogFeatureType)const override{return true;}
    void enableFeature(LogFeatureType,bool)override{}
    void attachSink(std::shared_ptr<ib::logger::LoggerSinkInterface>)override{}
private:
    void append(const char* format,va_list args)const {char bytes[512]{};const int n=std::vsnprintf(bytes,sizeof(bytes),format,args);if(n>0)text.append(bytes,std::min(size_t(n),sizeof(bytes)-1));}
};
TEST(EmsReaders, DiagnosticHexFormattingKeepsValidFramesAndBoundsUnexpectedPayloads) {
    CaptureLog log;report({0x12,0x34,0x56}).logDebug(log,1);
    EXPECT_NE(log.text.find("dataLen: 3 data: 123456"),std::string::npos);
    log.text.clear();report(std::vector<uint8_t>(200,0xAA)).logDebug(log,1);
    EXPECT_NE(log.text.find("dataLen: 200"),std::string::npos);
    EXPECT_NE(log.text.find("..."),std::string::npos);
    EXPECT_LT(log.text.size(),180u);
}
TEST(EmsVersion, ActualDiagnosticLoggerReportsTheAlternativeProductAndVersion) {
    UBADeviceVersion frame(EmsTelegram::BROADCAST,8,0,0,2,{0,0,0,77,1,2,0,0,0,4});
    CaptureLog log;frame.logData(log,1);
    EXPECT_NE(log.text.find("productId: 77"),std::string::npos);
    EXPECT_NE(log.text.find("major: 1"),std::string::npos);
    EXPECT_NE(log.text.find("minor: 2"),std::string::npos);
    EXPECT_NE(log.text.find("vendorId: 4"),std::string::npos);
}
TEST(EmsVersion, ActualLoggerDoesNotReportPartialVersionFragmentsAsCompleteIdentity) {
    UBADeviceVersion frame(EmsTelegram::BROADCAST,8,0,3,2,{77,1,2});
    CaptureLog log;frame.logData(log,1);
    EXPECT_EQ(log.text.find("productId:"),std::string::npos);
    EXPECT_EQ(log.text.find("major:"),std::string::npos);
}
}

TEST(EmsWireValidation, UnsupportedOperationAndReservedMarkerCannotProduceWireBytes) {
    using heating::ems::EmsTelegram;
    EXPECT_TRUE(EmsTelegram(EmsTelegram::READ_WITH_DATA,11,8,0,0x2e0,{1,2}).encodeToRawDataWithCRC().empty());
    EXPECT_TRUE(EmsTelegram(EmsTelegram::WRITE,11,8,0,0xff,{1,2}).encodeToRawDataWithCRC().empty());
}
TEST(EmsWireValidation, OperationMustAgreeWithDestinationAddress) {
    using heating::ems::EmsTelegram;
    EXPECT_TRUE(EmsTelegram(EmsTelegram::READ,11,0,0,0x18,{1}).encodeToRawDataWithCRC().empty());
    EXPECT_TRUE(EmsTelegram(EmsTelegram::WRITE,11,0,0,0x18,{1}).encodeToRawDataWithCRC().empty());
    EXPECT_TRUE(EmsTelegram(EmsTelegram::BROADCAST,11,8,0,0x18,{1}).encodeToRawDataWithCRC().empty());
    EXPECT_TRUE(EmsTelegram(EmsTelegram::WRITE,11,0x88,0,0x18,{1}).encodeToRawDataWithCRC().empty());
}
TEST(EmsWireValidation, ExtendedReadCannotSilentlyIgnoreTrailingPayloadEvenWithValidCrc) {
    using heating::ems::EmsTelegram;
    auto bytes=EmsTelegram(EmsTelegram::READ,11,8,0,0x2e0,{25}).encodeToRawDataWithCRC();
    ASSERT_EQ(bytes.size(),8u);
    EXPECT_NO_THROW(EmsTelegram::fromRawData(bytes.data(),bytes.size()));
    bytes.insert(bytes.end()-1,0x42);
    bytes.back()=EmsTelegram::calculateCRC(bytes.data(),static_cast<uint8_t>(bytes.size()-1));
    EXPECT_THROW(EmsTelegram::fromRawData(bytes.data(),bytes.size()),std::runtime_error);
}
TEST(EmsWireValidation, SupportedOperationsAndTypeBoundariesRoundtripWithoutLoss) {
    using heating::ems::EmsTelegram;
    for(const uint16_t type:{uint16_t(1),uint16_t(0xfe),uint16_t(0x100),uint16_t(0xffff)})
        for(const auto op:{EmsTelegram::READ,EmsTelegram::WRITE,EmsTelegram::BROADCAST})
            for(const uint8_t offset:{uint8_t(0),uint8_t(255)}) {
                const uint8_t destination=op==EmsTelegram::BROADCAST?0:8;
                const EmsTelegram original(op,11,destination,offset,type,{27});
                const auto bytes=original.encodeToRawDataWithCRC();ASSERT_FALSE(bytes.empty());
                const auto decoded=EmsTelegram::fromRawData(bytes.data(),bytes.size());
                EXPECT_EQ(decoded.getOperationType(),op);EXPECT_EQ(decoded.getTypeId(),type);
                EXPECT_EQ(decoded.getSenderId(),11);EXPECT_EQ(decoded.getDestinationId(),destination);
                EXPECT_EQ(decoded.getOffset(),offset);EXPECT_EQ(decoded.dataSize(),1u);EXPECT_EQ(decoded.byteAt(offset),27);
                EXPECT_EQ(decoded.encodeToRawDataWithCRC(),bytes);
            }
}
