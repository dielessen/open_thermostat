#include "update/TlsAllocationPolicy.h"
#include <gtest/gtest.h>
using heating::update::allocateTlsMemory;
TEST(TlsAllocationPolicy, OnlyUpdaterUsesExternalMemoryWithoutFallback) {
    unsigned internalCalls=0,externalCalls=0;
    int internalStorage=0,externalStorage=0;
    auto internal=[&](size_t n,size_t s)->void* {++internalCalls;EXPECT_EQ(n,2u);EXPECT_EQ(s,8u);return &internalStorage;};
    auto external=[&](size_t n,size_t s)->void* {++externalCalls;EXPECT_EQ(n,2u);EXPECT_EQ(s,8u);return &externalStorage;};
    EXPECT_EQ(allocateTlsMemory(2,8,false,internal,external),&internalStorage);
    EXPECT_EQ(allocateTlsMemory(2,8,true,internal,external),&externalStorage);
    EXPECT_EQ(internalCalls,1u);EXPECT_EQ(externalCalls,1u);
    EXPECT_EQ(allocateTlsMemory(2,8,true,internal,[](size_t,size_t)->void* {return nullptr;}),nullptr);
    EXPECT_EQ(internalCalls,1u);
}
TEST(TlsAllocationPolicy, OverflowCannotReachEitherAllocator) {
    unsigned calls=0;
    auto allocate=[&](size_t,size_t)->void* {++calls;return nullptr;};
    for(bool updater:{false,true})
        EXPECT_EQ(allocateTlsMemory(std::numeric_limits<size_t>::max(),2,updater,allocate,allocate),nullptr);
    EXPECT_EQ(calls,0u);
}
