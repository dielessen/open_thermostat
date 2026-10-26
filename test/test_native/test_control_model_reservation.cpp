#include "control/ControlModelStorageReservation.h"
#include <gtest/gtest.h>
using namespace heating::control;
TEST(ControlModelStorageReservation, OnlyItsOwnerCanHoldOrReleaseTheSelectedBudget) {
    ControlModelStorageReservation resource;int owner=0,other=0;
    EXPECT_EQ(ControlPartitionBudget::modelEntries(resource.current()),0u);
    ASSERT_TRUE(resource.claim(&owner,{1,1,1}));EXPECT_TRUE(resource.matches(&owner,{1,1,1}));
    EXPECT_FALSE(resource.claim(&other,{1,0,0}));EXPECT_FALSE(resource.claim(&owner,{1,1,1}));
    resource.release(&other);EXPECT_EQ(ControlPartitionBudget::modelEntries(resource.current()),63u);
    resource.release(&owner);EXPECT_EQ(ControlPartitionBudget::modelEntries(resource.current()),0u);
    EXPECT_TRUE(resource.claim(&other,{1,0,0}));
}
TEST(ControlModelStorageReservation, UnknownEmptyOrOversubscribedPlansCannotBecomeAReservation) {
    ControlModelStorageReservation resource;int owner=0;
    EXPECT_FALSE(resource.claim(nullptr,{1,0,0}));EXPECT_FALSE(resource.claim(&owner,{}));
    EXPECT_FALSE(resource.claim(&owner,{8,8,8}));EXPECT_FALSE(resource.claim(&owner,{SIZE_MAX,0,0}));
    EXPECT_EQ(ControlPartitionBudget::modelEntries(resource.current()),0u);
    EXPECT_FALSE(resource.matches(nullptr,{}));EXPECT_FALSE(resource.matches(&owner,{}));
}
