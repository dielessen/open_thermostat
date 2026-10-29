#include "diagnostics/AtomicPlacement.h"
#include <gtest/gtest.h>
#include <atomic>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
using heating::diagnostics::countAtomicsInPsram;

namespace {
// Stand-in for the PSRAM-resident controller: a large heap object whose
// read-modify-write atomics are static members, as in EmsController.
struct LargeOwner {
    char state[8192]{};
    std::atomic<uint32_t> loadStoreOnly{0};
    static inline std::atomic<uint32_t> counter{0};
    static inline std::atomic<bool> flag{false};
    template<class Visit> static void visitRmwAtomics(Visit&& visit) { visit("counter", &counter); visit("flag", &flag); }
};
}

TEST(AtomicPlacement, CountsAndReportsOnlyExternalAddresses) {
    std::atomic<uint32_t> a{0}, b{0}, c{0};
    std::vector<std::string> reported;
    const auto count = countAtomicsInPsram(
        [&](auto&& visit) { visit("a", &a); visit("b", &b); visit("c", &c); },
        [&](const void* p) { return p == &a || p == &c; },
        [&](const char* name, const void*) { reported.emplace_back(name); });
    EXPECT_EQ(count, 2u);
    EXPECT_EQ(reported, (std::vector<std::string>{"a", "c"}));
}

TEST(AtomicPlacement, HostHasNoExternalRam) {
    std::atomic<uint32_t> local{0};
    auto heap = std::make_unique<LargeOwner>();
    EXPECT_FALSE(heating::diagnostics::inExternalRam(&local));
    EXPECT_FALSE(heating::diagnostics::inExternalRam(heap.get()));
}

TEST(AtomicPlacement, StaticMembersStayOutsideTheLargeHeapOwner) {
    // "External" here = inside the large heap object, like PSRAM on the E32.
    auto owner = std::make_unique<LargeOwner>();
    const auto begin = reinterpret_cast<uintptr_t>(owner.get());
    const auto inOwner = [&](const void* p) { const auto a = reinterpret_cast<uintptr_t>(p); return a >= begin && a < begin + sizeof(LargeOwner); };
    ASSERT_TRUE(inOwner(&owner->loadStoreOnly));
    int reports = 0;
    EXPECT_EQ(countAtomicsInPsram([](auto&& visit) { LargeOwner::visitRmwAtomics(visit); }, inOwner,
        [&](const char*, const void*) { ++reports; }), 0u);
    EXPECT_EQ(reports, 0);
}
