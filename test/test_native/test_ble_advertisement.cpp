#include "control/BleTemperatureAdvertisement.h"
#include <gtest/gtest.h>
#include <algorithm>
#include <memory>
#include <random>
#include <vector>

namespace {
using heating::control::decodeBleTemperatureAdvertisement;
const std::array<uint8_t,6> address{0xa4,0xc1,0x38,0x12,0x34,0x56};
using Bytes=std::vector<uint8_t>;
void ad(Bytes &out,uint8_t type,const Bytes &data) {
    out.push_back(static_cast<uint8_t>(data.size()+1)); out.push_back(type);
    out.insert(out.end(),data.begin(),data.end());
}
Bytes atcService(){return {0x1a,0x18,0xa4,0xc1,0x38,0x12,0x34,0x56,0xff,0xce,45,99,0x0b,0xb8,7};}
Bytes miService(uint16_t object=0x100d,Bytes value={0xce,0xff,0xc2,0x01}) {
    Bytes b{0x95,0xfe,0x50,0x20,0xaa,0x01,7,0x56,0x34,0x12,0x38,0xc1,0xa4,
        static_cast<uint8_t>(object),static_cast<uint8_t>(object>>8),static_cast<uint8_t>(value.size())};
    b.insert(b.end(),value.begin(),value.end()); return b;
}
Bytes packet(const Bytes &service,bool atc=true,bool serviceFirst=false) {
    const Bytes name=atc ? Bytes{'A','T','C','_','1','2','3','4','5','6'} : Bytes{'M','J','_','H','T','_','V','1'};
    Bytes b{2,1,6};
    if (serviceFirst) ad(b,0x16,service);
    ad(b,0x09,name);
    if (!serviceFirst) ad(b,0x16,service);
    return b;
}
auto decode(const Bytes &b){return decodeBleTemperatureAdvertisement(address,b.data(),b.size());}

TEST(BleAdvertisement, AtcCustomSignedBigEndianAndServiceBeforeName) {
    for(bool first:{false,true}) {
        auto r=decode(packet(atcService(),true,first)); ASSERT_TRUE(r);
        EXPECT_EQ(r->temperature,-500); EXPECT_EQ(r->humidity,4500); EXPECT_EQ(r->battery,99);
    }
}
TEST(BleAdvertisement, XiaomiSignedLittleEndianAndAllLegacyObjectCategories) {
    auto r=decode(packet(miService(),false)); ASSERT_TRUE(r);
    EXPECT_EQ(r->temperature,-500); EXPECT_EQ(r->humidity,4500); EXPECT_FALSE(r->battery);
    r=decode(packet(miService(0x1004,{0xeb,0x00}),false)); ASSERT_TRUE(r);
    EXPECT_EQ(r->temperature,2350); EXPECT_FALSE(r->humidity); EXPECT_FALSE(r->battery);
    r=decode(packet(miService(0x1006,{0xc2,0x01}),false)); ASSERT_TRUE(r);
    EXPECT_FALSE(r->temperature); EXPECT_EQ(r->humidity,4500);
    r=decode(packet(miService(0x100a,{100}),false)); ASSERT_TRUE(r);
    EXPECT_FALSE(r->temperature); EXPECT_FALSE(r->humidity); EXPECT_EQ(r->battery,100);
}
TEST(BleAdvertisement, EveryTruncationAndMalformedSuffixYieldsNoPartialSample) {
    for (auto b:{packet(atcService()),packet(miService(),false)}) {
        for(size_t n=0;n<b.size();++n) EXPECT_FALSE(decodeBleTemperatureAdvertisement(address,b.data(),n))<<n;
        b.insert(b.end(),{9,0x16,0x1a}); EXPECT_FALSE(decode(b));
    }
    auto b=packet(atcService()); b.push_back(0); b.push_back(0); EXPECT_TRUE(decode(b));
    b.push_back(1); EXPECT_FALSE(decode(b));
    EXPECT_FALSE(decodeBleTemperatureAdvertisement(address,nullptr,1));
    EXPECT_FALSE(decode(Bytes(256,0)));
}
TEST(BleAdvertisement, XiaomiExactObjectWidthsTypesAndHeaderFlags) {
    for(const auto &s:{miService(0x1004,{1}),miService(0x1004,{1,0,0}),
                      miService(0x0004,{1,0}),miService(0x100a,{1,0}),
                      miService(0x100d,{1,0,1}),miService(0x1006,{1})})
        EXPECT_FALSE(decode(packet(s,false)));
    for (auto flags:{0x40,0x58,0x70,0x10}) {
        auto s=miService(); s[2]=flags; EXPECT_FALSE(decode(packet(s,false)));
    }
    auto s=miService(); s[4]=0xab; EXPECT_FALSE(decode(packet(s,false)));
    s=miService(); s[15]=3; EXPECT_FALSE(decode(packet(s,false)));
}
TEST(BleAdvertisement, UuidMacNameAndAmbiguousServiceAreNotMeasurementIdentity) {
    for(bool atc:{true,false}) {
        auto s=atc ? atcService() : miService();
        s[0]^=1; EXPECT_FALSE(decode(packet(s,atc)));
        s=atc ? atcService() : miService(); s[atc?2:7]^=1;
        EXPECT_FALSE(decode(packet(s,atc)));
        s=atc ? atcService() : miService(); auto b=packet(s,atc); ad(b,0x16,s);
        EXPECT_FALSE(decode(b));
        b=packet(s,atc); ad(b,0x09,{'O','t','h','e','r'}); EXPECT_FALSE(decode(b));
        b=packet(s,atc); ad(b,0x16,{0x1a}); EXPECT_FALSE(decode(b));
    }
    // Unrelated service first is harmless: select by UUID, not vector position.
    Bytes b; ad(b,0x16,{0x0f,0x18,99}); const auto a=packet(atcService()); b.insert(b.end(),a.begin(),a.end());
    EXPECT_TRUE(decode(b));
}
TEST(BleAdvertisement, RangeChecksHappenBeforeNarrowing) {
    for(const auto &value:{Bytes{0xff,0x7f},Bytes{0x00,0x80},Bytes{0x6f,0xfe},Bytes{0x53,0x03}})
        EXPECT_FALSE(decode(packet(miService(0x1004,value),false)));
    for(const auto &value:{Bytes{0x70,0xfe},Bytes{0x52,0x03}})
        EXPECT_TRUE(decode(packet(miService(0x1004,value),false)));
    EXPECT_FALSE(decode(packet(miService(0x1006,{0xe9,0x03}),false)));
    EXPECT_FALSE(decode(packet(miService(0x100a,{101}),false)));
    auto s=atcService(); s[10]=101; EXPECT_FALSE(decode(packet(s)));
    s=atcService(); s[11]=255; EXPECT_FALSE(decode(packet(s)));
    s=atcService(); s[8]=0x7f; s[9]=0xff; EXPECT_FALSE(decode(packet(s)));
    s=atcService(); s.pop_back(); EXPECT_FALSE(decode(packet(s)));
    s=atcService(); s.push_back(0); EXPECT_FALSE(decode(packet(s)));
}
TEST(BleAdvertisement, SeededMutationAndExactAllocationBoundaries) {
    std::mt19937 random(0xb1e2026);
    for(const auto &golden:{packet(atcService()),packet(miService(),false)}) {
        for(size_t n=0;n<golden.size();++n) {
            auto exact=std::make_unique<uint8_t[]>(n);
            std::copy_n(golden.data(),n,exact.get());
            EXPECT_FALSE(decodeBleTemperatureAdvertisement(address,exact.get(),n));
        }
    }
    for(size_t run=0;run<30000;++run) {
        Bytes b;
        if(run%3==0) {
            b.resize(random()%257);
            for(auto &v:b) v=static_cast<uint8_t>(random());
        } else {
            b=run%3==1 ? packet(atcService()) : packet(miService(),false);
            for(size_t mutations=1+random()%4;mutations;--mutations) b[random()%b.size()]=static_cast<uint8_t>(random());
        }
        // Exact allocations let ASan detect access even one byte past this input.
        auto exact=std::make_unique<uint8_t[]>(b.size());
        std::copy(b.begin(),b.end(),exact.get());
        const auto r=decodeBleTemperatureAdvertisement(address,exact.get(),b.size());
        if(r) {
            ASSERT_TRUE(r->temperature || r->humidity || r->battery);
            if(r->temperature) { EXPECT_GE(*r->temperature,-4000); EXPECT_LE(*r->temperature,8500); }
            if(r->humidity) { EXPECT_GE(*r->humidity,0); EXPECT_LE(*r->humidity,10000); }
            if(r->battery) { EXPECT_GE(*r->battery,0); EXPECT_LE(*r->battery,100); }
        }
    }
}
}
