#include <gtest/gtest.h>
#include "control/EffectiveTarget.h"
using namespace heating::control;
namespace {
ComfortProfile profile() {
    ComfortProfile p;p.reviewed=true;p.windowSupported=true;p.presenceSupported=true;
    p.minimumCentiC=1000;p.maximumCentiC=2500;p.awayCentiC=1600;
    p.maximumTemporaryMs=86400000;p.maximumBoostMs=3600000;
    p.maximumWindowAgeMs=60000;p.maximumPresenceAgeMs=60000;return p;
}
ComfortInputs input(uint64_t now=100) {
    ComfortInputs in;in.ownerAdmitted=true;in.windowKnown=in.presenceKnown=true;
    in.windowAt=in.presenceAt=now;in.automaticCentiC=2000;in.automaticSource="schedule";
    in.utc=1790812800;in.clockTrusted=true;return in;
}
TEST(EffectiveTarget, Api1ExistingAutomaticTemporaryOffAndUnknownScheduleSemantics) {
    auto a=EffectiveTarget::api1(1900,"schedule",false,2200,2000,1000);
    EXPECT_EQ(a.target,2200);EXPECT_STREQ(a.source,"temporary");EXPECT_FALSE(a.learningAllowed);
    EXPECT_FALSE(EffectiveTarget::api1(1900,"schedule",true,2200,2000,1000).target);
    EXPECT_FALSE(EffectiveTarget::api1({},"schedule",false,2200,2000,2000).target);
    EXPECT_EQ(EffectiveTarget::api1(1900,"base",false,2200,2000,2000).target,1900);
}
TEST(EffectiveTarget, UnreviewedProfileRejectsNewModesAndTemperatureLimitsRejectAtomically) {
    EffectiveTarget defaults;EXPECT_FALSE(defaults.command(ComfortMode::away,{},100));
    EXPECT_FALSE(defaults.evaluate(100,input()).target);
    EffectiveTarget t(profile());ASSERT_TRUE(t.command(ComfortMode::boost,2200,100,1000));
    EXPECT_FALSE(t.command(ComfortMode::boost,3000,101,1000));
    EXPECT_EQ(t.evaluate(102,input()).target,2200);
    EXPECT_FALSE(t.command(ComfortMode::automatic,2100,103));
    EXPECT_FALSE(t.command(static_cast<ComfortMode>(-1),{},103));
    EXPECT_FALSE(t.command(ComfortMode::temporary,2100,103,1));
    EXPECT_FALSE(t.command(ComfortMode::boost,2200,UINT64_MAX-500,1000));
}
TEST(EffectiveTarget, ManualBoostWinsPresenceAwayButNeverOpenOrUnknownWindow) {
    EffectiveTarget t(profile());auto in=input();in.away=true;
    EXPECT_EQ(t.evaluate(100,in).target,1600);
    ASSERT_TRUE(t.command(ComfortMode::boost,2200,100,10000));
    EXPECT_EQ(t.evaluate(101,in).target,2200);
    in.windowOpen=true;EXPECT_FALSE(t.evaluate(102,in).target);
    in.windowOpen=false;in.windowKnown=false;EXPECT_FALSE(t.evaluate(103,in).target);
    ASSERT_TRUE(t.command(ComfortMode::off,{},104));
    EXPECT_STREQ(t.evaluate(105,in).source,"off");
}
TEST(EffectiveTarget, TemporaryAndBoostExpireExactlyAtMonotonicDeadline) {
    for(auto mode:{ComfortMode::temporary,ComfortMode::boost}) {
        EffectiveTarget t(profile());auto in=input();ASSERT_TRUE(t.command(mode,2200,100,1000));
        EXPECT_EQ(t.evaluate(1099,in).target,2200);EXPECT_EQ(t.evaluate(1100,in).target,2000);
        in.utc-=86400;EXPECT_EQ(t.evaluate(1101,in).target,2000);
    }
}
TEST(EffectiveTarget, WindowBlockingDoesNotDeferOverrideExpiryAndStateDoesNotReplay) {
    EffectiveTarget t(profile());auto in=input();ASSERT_TRUE(t.command(ComfortMode::boost,2200,100,1000));
    in.windowOpen=true;EXPECT_FALSE(t.evaluate(1200,in).target);
    in.windowOpen=false;EXPECT_EQ(t.evaluate(1201,in).target,2000);
}
TEST(EffectiveTarget, OwnerLossDropsOverridesAndPresenceSourceStalenessFailsClosed) {
    EffectiveTarget t(profile());auto in=input();ASSERT_TRUE(t.command(ComfortMode::boost,2200,100,10000));
    in.ownerAdmitted=false;EXPECT_FALSE(t.evaluate(101,in).target);
    in.ownerAdmitted=true;EXPECT_EQ(t.evaluate(102,in).target,2000);
    in.presenceKnown=false;EXPECT_FALSE(t.evaluate(103,in).target);
    in.presenceKnown=true;in.windowAt=60100;
    EXPECT_FALSE(t.evaluate(60100,in).target); // exactly stale presence, not silently home.
}
TEST(EffectiveTarget, VacationNeedsTrustedBoundedFutureUtcAndExpiresWithoutBackwardReplay) {
    EffectiveTarget t(profile());auto in=input();
    EXPECT_FALSE(t.command(ComfortMode::vacation,{},100,0,in.utc+3600,in.utc,false));
    EXPECT_FALSE(t.command(ComfortMode::vacation,{},100,0,in.utc-1,in.utc,true));
    EXPECT_FALSE(t.command(ComfortMode::vacation,{},100,0,in.utc+400LL*86400,in.utc,true));
    ASSERT_TRUE(t.command(ComfortMode::vacation,{},100,0,in.utc+3600,in.utc,true));
    EXPECT_EQ(t.evaluate(101,in).target,1600);in.clockTrusted=false;EXPECT_FALSE(t.evaluate(102,in).target);
    in.clockTrusted=true;in.utc+=3600;EXPECT_EQ(t.evaluate(103,in).target,2000);
    in.utc-=3600;EXPECT_EQ(t.evaluate(104,in).target,2000);
}
TEST(EffectiveTarget, VacationTimeReversalAndMonotonicReversalDoNotExtendOrReviveBoost) {
    EffectiveTarget t(profile());auto in=input();ASSERT_TRUE(t.command(ComfortMode::vacation,{},100,0,in.utc+3600,in.utc,true));
    --in.utc;EXPECT_FALSE(t.evaluate(101,in).target);
    EffectiveTarget b(profile());ASSERT_TRUE(b.command(ComfortMode::boost,2200,100,10000));
    EXPECT_FALSE(b.evaluate(99,input()).target);EXPECT_FALSE(b.evaluate(101,input()).target);
    EXPECT_FALSE(b.command(ComfortMode::boost,2200,98,1000));
}
TEST(EffectiveTarget, FreshAutomaticOnlyAllowsLearningNoUnknownScheduleOrOffDemand) {
    EffectiveTarget t(profile());auto in=input();EXPECT_TRUE(t.evaluate(100,in).learningAllowed);
    in.automaticCentiC.reset();EXPECT_FALSE(t.evaluate(101,in).target);
    ASSERT_TRUE(t.command(ComfortMode::away,{},102));EXPECT_FALSE(t.evaluate(103,in).learningAllowed);
}
}
