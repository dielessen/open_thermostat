#include "update/DownloadTextBuffer.h"
#include <gtest/gtest.h>
#include <cstdlib>
#include <limits>
using heating::update::DownloadTextBuffer;
namespace {
size_t allocated=0;unsigned releases=0;
void *allocate(size_t size){allocated=size;return std::malloc(size);}
void release(void *data){++releases;std::free(data);}
void *fail(size_t){return nullptr;}
}
TEST(DownloadTextBuffer, BoundedChunksPreserveBytesAndReleaseSelectedStorage) {
    releases=0;
    {
        DownloadTextBuffer buffer(5,allocate,release);
        ASSERT_TRUE(buffer.ready());EXPECT_EQ(allocated,5u);
        EXPECT_EQ(buffer.append("ab",2),2u);
        EXPECT_EQ(buffer.append("c\0d",3),3u);
        EXPECT_EQ(buffer.text(),std::string("abc\0d",5));
        EXPECT_EQ(buffer.append("e",1),0u);
        EXPECT_EQ(buffer.append("e",std::numeric_limits<size_t>::max()),0u);
        EXPECT_EQ(buffer.text(),std::string("abc\0d",5));
        EXPECT_EQ(releases,0u);
    }
    EXPECT_EQ(releases,1u);
}
TEST(DownloadTextBuffer, FailedExternalAllocationDoesNotFallbackOrAcceptBytes) {
    DownloadTextBuffer buffer(32768,fail,release);
    EXPECT_FALSE(buffer.ready());EXPECT_EQ(buffer.append("x",1),0u);
    EXPECT_TRUE(buffer.text().empty());
}
