#include "control/SessionAdmission.h"
#include <gtest/gtest.h>

namespace {
using namespace heating::control;
class SessionTest : public ::testing::Test {
protected:
    SessionIdentity identity{"e32-lab","boot-a","ha-one","session-a",1,4};
    SessionAdmission gate{"ha-one"};
    const char *bindings[3]{"system","sensor-a","zone-a"};
    const StreamKind kinds[3]{StreamKind::heartbeat,StreamKind::observation,StreamKind::user_command};
    void SetUp() override {
        ASSERT_TRUE(gate.begin(identity));
        for (size_t i=0;i<3;++i) ASSERT_TRUE(gate.bind(i,bindings[i],kinds[i]));
        ASSERT_TRUE(gate.issueGrant("grant-a",1,1000,10000));
        ASSERT_EQ(gate.admit(0,message(0,1),1000).code,AdmissionCode::accepted);
    }
    Envelope message(size_t stream,uint32_t sequence) const {
        Envelope e;
        e.kind=kinds[stream]; e.binding=bindings[stream];
        e.controller=identity.controller; e.boot=identity.boot; e.adapter=identity.adapter;
        e.session=identity.session; e.epoch=identity.epoch; e.revision=identity.revision;
        e.grant="grant-a"; e.grantSequence=1; e.sequence=sequence;
        e.payloadDigest.fill(7);
        return e;
    }
};

TEST_F(SessionTest, DuplicatePreservesOriginalDeadlineAndCannotRepeatAnEffect) {
    auto e=message(2,10);
    auto first=gate.admit(2,e,1100,9000);
    EXPECT_EQ(first.code,AdmissionCode::accepted);
    auto duplicate=gate.admit(2,e,2100,10000);
    EXPECT_EQ(duplicate.code,AdmissionCode::duplicate);
    EXPECT_EQ(duplicate.originalResult,9000u);
    e.payloadDigest[0]=8;
    EXPECT_EQ(gate.admit(2,e,2200).code,AdmissionCode::changed_duplicate);
}

TEST_F(SessionTest, OldCommandAfterCacheEvictionStaysOldAcrossGrantRotation) {
    EXPECT_EQ(gate.admit(2,message(2,10),1100,9000).code,AdmissionCode::accepted);
    EXPECT_EQ(gate.admit(2,message(2,11),1200,10000).code,AdmissionCode::accepted);
    EXPECT_EQ(gate.admit(2,message(2,10),1300).code,AdmissionCode::old_sequence);
    ASSERT_TRUE(gate.issueGrant("grant-b",2,2000,10000));
    auto old=message(2,10); old.grant="grant-b"; old.grantSequence=2;
    EXPECT_EQ(gate.admit(2,old,2100).code,AdmissionCode::old_sequence);
    EXPECT_TRUE(gate.bind(2,"zone-a",StreamKind::user_command)); // idempotent, no reset
    EXPECT_EQ(gate.admit(2,old,2200).code,AdmissionCode::old_sequence);
}

TEST_F(SessionTest, FutureGenerationAndABANonceReuseCannotRefreshOldPackets) {
    auto e=message(1,1);
    e.grantSequence=2;
    EXPECT_EQ(gate.admit(1,e,1100).code,AdmissionCode::expired_grant);
    ASSERT_TRUE(gate.issueGrant("grant-b",2,2000,1000));
    ASSERT_TRUE(gate.issueGrant("grant-a",3,3000,1000));
    auto ancient=message(1,1); // same nonce text, old generation
    EXPECT_EQ(gate.admit(1,ancient,3100).code,AdmissionCode::expired_grant);
    EXPECT_FALSE(gate.issueGrant("grant-c",2,3100,1000));
    ancient.grantSequence=3;
    EXPECT_EQ(gate.admit(1,ancient,3100).code,AdmissionCode::accepted);
}

TEST_F(SessionTest, DeliveryAtExpiryOrBeforeIssueCannotStartANewWindow) {
    EXPECT_EQ(gate.admit(1,message(1,1),999).code,AdmissionCode::expired_grant);
    EXPECT_EQ(gate.admit(1,message(1,1),11000).code,AdmissionCode::expired_grant);
    EXPECT_EQ(gate.grantElapsed(10500),9500u);
    EXPECT_EQ(gate.grantDeadline(10500),11000u);
    EXPECT_EQ(gate.grantElapsed(11000),UINT64_MAX);
    EXPECT_EQ(gate.grantDeadline(11000),0u);
}

TEST_F(SessionTest, WrongIdentityVersionRevisionAndBindingHaveNoAdmissionSideEffect) {
    auto original=message(1,1), e=original;
    e.major=2; EXPECT_EQ(gate.admit(1,e,1100).code,AdmissionCode::wrong_version);
    e=original; e.boot="old-boot"; EXPECT_EQ(gate.admit(1,e,1100).code,AdmissionCode::wrong_identity);
    e=original; e.adapter="another-ha"; EXPECT_EQ(gate.admit(1,e,1100).code,AdmissionCode::wrong_identity);
    e=original; ++e.epoch; EXPECT_EQ(gate.admit(1,e,1100).code,AdmissionCode::wrong_identity);
    e=original; ++e.revision; EXPECT_EQ(gate.admit(1,e,1100).code,AdmissionCode::wrong_revision);
    e=original; e.binding="another-sensor"; EXPECT_EQ(gate.admit(1,e,1100).code,AdmissionCode::unknown_binding);
    e=original; e.kind=StreamKind::user_command; EXPECT_EQ(gate.admit(1,e,1100).code,AdmissionCode::unknown_binding);
    EXPECT_EQ(gate.admit(1,original,1100).code,AdmissionCode::accepted);
}

TEST_F(SessionTest, ExpiredLeaseIsSeparateFromAStillCurrentGrant) {
    SessionIdentity next=identity; next.epoch=2;
    ASSERT_TRUE(gate.begin(next,1000));
    ASSERT_TRUE(gate.bind(0,"system",StreamKind::heartbeat));
    ASSERT_TRUE(gate.bind(1,"sensor-a",StreamKind::observation));
    ASSERT_TRUE(gate.issueGrant("grant-a",1,1000,10000));
    auto hb=message(0,1); hb.epoch=2;
    ASSERT_EQ(gate.admit(0,hb,1000).code,AdmissionCode::accepted);
    auto sample=message(1,1); sample.epoch=2;
    EXPECT_EQ(gate.admit(1,sample,2000).code,AdmissionCode::lease_expired);
    EXPECT_EQ(gate.admit(0,hb,1900).code,AdmissionCode::duplicate);
    EXPECT_FALSE(gate.alive(2000)); // duplicate did not extend lease
    hb.sequence=2;
    EXPECT_EQ(gate.admit(0,hb,2000).code,AdmissionCode::accepted);
    EXPECT_TRUE(gate.alive(2999));
}

TEST_F(SessionTest, DisconnectRequiresNewCompositeEpochAndCannotResetWatermarksInPlace) {
    ASSERT_EQ(gate.admit(1,message(1,10),1100).code,AdmissionCode::accepted);
    gate.invalidateTransport();
    EXPECT_FALSE(gate.alive(1101));
    EXPECT_EQ(gate.admit(1,message(1,11),1101).code,AdmissionCode::not_configured);
    EXPECT_FALSE(gate.issueGrant("grant-b",2,1200,1000));
    EXPECT_FALSE(gate.begin(identity));
    auto next=identity; next.epoch=2; next.session="session-b";
    EXPECT_TRUE(gate.begin(next));
    EXPECT_FALSE(gate.begin(identity)); // old session may not roll the epoch back
}

TEST_F(SessionTest, SequenceZeroWrapAndBindingReassignmentAreRejected) {
    EXPECT_EQ(gate.admit(1,message(1,0),1100).code,AdmissionCode::invalid_sequence);
    EXPECT_EQ(gate.admit(1,message(1,UINT32_MAX),1100).code,AdmissionCode::accepted);
    EXPECT_EQ(gate.admit(1,message(1,1),1200).code,AdmissionCode::old_sequence);
    EXPECT_FALSE(gate.bind(1,"replacement-sensor",StreamKind::observation));
    EXPECT_FALSE(gate.bind(4,"sensor-a",StreamKind::observation));
    EXPECT_FALSE(gate.bind(SessionAdmission::maximumStreams,"x",StreamKind::observation));
}

TEST_F(SessionTest, HaReceiverAlsoRejectsDelayedFirmwareActuatorCommands) {
    SessionAdmission ha("ha-one",Direction::fw_to_ha);
    ASSERT_TRUE(ha.begin(identity));
    ASSERT_TRUE(ha.bind(0,"system",StreamKind::heartbeat));
    ASSERT_TRUE(ha.bind(1,"trv-a",StreamKind::actuator_command));
    ASSERT_TRUE(ha.issueGrant("ha-grant",1,1000,5000));
    auto hb=message(0,1); hb.direction=Direction::fw_to_ha; hb.grant="ha-grant";
    ASSERT_EQ(ha.admit(0,hb,1000).code,AdmissionCode::accepted);
    auto action=message(1,1); action.kind=StreamKind::actuator_command;
    action.binding="trv-a"; action.direction=Direction::fw_to_ha; action.grant="ha-grant";
    EXPECT_EQ(ha.admit(1,action,6000).code,AdmissionCode::expired_grant);
    EXPECT_EQ(ha.admit(1,action,5999,ha.grantDeadline(5999)).code,AdmissionCode::accepted);
}

TEST(SessionAdmission, OwnerPairingAndInitialRevisionAreFailClosed) {
    SessionIdentity identity{"e32","boot","ha-one","session",1,0};
    SessionAdmission unpaired(""); EXPECT_FALSE(unpaired.begin(identity));
    SessionAdmission other("ha-two"); EXPECT_FALSE(other.begin(identity));
    SessionAdmission g("ha-one"); ASSERT_TRUE(g.begin(identity));
    ASSERT_TRUE(g.bind(0,"system",StreamKind::heartbeat));
    ASSERT_TRUE(g.bind(1,"sensor-a",StreamKind::observation));
    ASSERT_TRUE(g.issueGrant("g",1,1000,1000));
    Envelope e; e.controller="e32";e.boot="boot";e.adapter="ha-one";e.session="session";
    e.epoch=1;e.revision=0;e.grant="g";e.grantSequence=1;e.sequence=1;
    e.binding="system";e.kind=StreamKind::heartbeat;
    EXPECT_EQ(g.admit(0,e,1000).code,AdmissionCode::accepted);
    e.binding="sensor-a";e.kind=StreamKind::observation;
    EXPECT_EQ(g.admit(1,e,1000).code,AdmissionCode::wrong_revision);
}

TEST(SessionAdmission, InvalidIdsAndOverflowingClockWindowsAreRejected) {
    EXPECT_FALSE(SessionAdmission::validId("sensor.badkamer"));
    EXPECT_FALSE(SessionAdmission::validId(std::string(33,'a')));
    SessionAdmission g("ha-one");
    SessionIdentity id{"e32","boot","ha-one","session",1,1};
    ASSERT_TRUE(g.begin(id));
    EXPECT_FALSE(g.issueGrant("g",1,UINT64_MAX-5,10));
    EXPECT_FALSE(g.issueGrant("g",1,1000,15001));
    EXPECT_FALSE(g.issueGrant("g",0,1000,1000));
}
}
