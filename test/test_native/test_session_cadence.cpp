#include "ShadowControllerFixture.h"

// The session protocol within the telemetry budget (TELEMETRIEBUDGET.nl.md,
// "Sessieprotocol"), and its recovery without waiting on a stale lease.

TEST(SessionCadence, HelloIsSlowInASessionAndAtOnceWhenTheSessionIsLost) {
    Fixture f;
    f.ready();
    // The fixture keeps the last publication per topic: erase, step, look.
    const auto hellos = [&](uint64_t ms) {
        unsigned n = 0;
        for (uint64_t t = 0; t < ms; t += 1000) {
            f.output.erase("fw/hello");
            f.now += 1000; f.tick(); f.syncSession(); f.heartbeat(unsigned(100 + f.now / 1000));
            n += f.output.count("fw/hello");
        }
        return n;
    };
    EXPECT_LE(hellos(120000), 2u);                         // every 60 s while the session lives (was every 3 s)
    // HA goes silent: the lease ends after leaseMs and the hello comes at once.
    unsigned silentHellos = 0;
    uint64_t firstHelloAfterLoss = 0;
    const uint64_t silentFrom = f.now;
    for (uint64_t t = 0; t < 2 * ShadowController::leaseMs; t += 1000) {
        f.output.erase("fw/hello");
        f.now += 1000; f.tick();
        if (f.output.count("fw/hello")) { ++silentHellos; if (!firstHelloAfterLoss) firstHelloAfterLoss = f.now; }
    }
    EXPECT_GT(firstHelloAfterLoss, silentFrom);
    EXPECT_LE(firstHelloAfterLoss - silentFrom, uint64_t(ShadowController::leaseMs) + 1000);
    EXPECT_GE(silentHellos, 5u);                           // every 3 s without a session
}

TEST(SessionCadence, ZoneStateIsPublishedOnAChangeOrEveryThirtySeconds) {
    Fixture f;
    f.ready();
    auto sample = f.observation(1, 19.0);
    f.send("ha/observations", sample.get());
    unsigned published = 0;
    for (unsigned i = 0; i < 60; ++i) {                    // 60 s, nothing changes but ages
        f.output.erase("fw/state/zones");
        f.now += 1000; f.tick(); f.syncSession(); f.heartbeat(10 + i);
        published += f.output.count("fw/state/zones");
    }
    EXPECT_LE(published, 2u);                              // the 30 s refresh (was 20 times)
    EXPECT_GE(published, 1u);
    // A real change goes out with the next evaluation.
    f.output.erase("fw/state/zones");
    auto warmer = f.observation(2, 21.5);
    f.send("ha/observations", warmer.get());
    ASSERT_TRUE(f.output.count("fw/state/zones"));
    EXPECT_EQ(uintField(Fixture::row(f.state()), "temperature_centi_c"), 2150u);
    // A snapshot request always answers with the state.
    f.output.erase("fw/state/zones");
    auto snapshot = f.envelope("snapshot", 1);
    f.send("ha/snapshot_request", snapshot.get());
    EXPECT_TRUE(f.output.count("fw/state/zones"));
}

TEST(SessionCadence, AFreshOpenWithTheCurrentChallengeReplacesAStaleSession) {
    Fixture f;
    f.ready();
    const auto oldSession = f.session;
    // A restarted HA: it opens with the challenge of the current hello while the
    // E32 still holds the old session (its lease has not run out).
    f.output.erase("fw/session");
    auto hello = f.get("fw/hello");
    auto o = objectJson();
    cJSON_AddNumberToObject(o.get(), "api", 1); cJSON_AddStringToObject(o.get(), "controller_id", "e32_lab");
    cJSON_AddStringToObject(o.get(), "boot_id", f.boot.c_str()); cJSON_AddNumberToObject(o.get(), "epoch", f.epoch);
    cJSON_AddStringToObject(o.get(), "adapter_id", "ha1"); cJSON_AddStringToObject(o.get(), "client_nonce", "restarted");
    cJSON_AddStringToObject(o.get(), "challenge_id", stringField(hello.get(), "challenge_id").c_str());
    cJSON_AddNumberToObject(o.get(), "known_revision", f.rev); cJSON_AddStringToObject(o.get(), "known_digest", f.digest.c_str());
    // An old challenge first: no session, but the current hello at once.
    auto stale = parseControlJson(printJson(o.get()));
    cJSON_ReplaceItemInObjectCaseSensitive(stale.get(), "challenge_id", cJSON_CreateString("old_challenge"));
    f.output.erase("fw/hello");
    f.send("ha/open_session", stale.get());
    EXPECT_FALSE(f.output.count("fw/session"));
    ASSERT_TRUE(f.output.count("fw/hello"));
    // With the current challenge it gets a new session right away.
    cJSON_ReplaceItemInObjectCaseSensitive(o.get(), "challenge_id", cJSON_CreateString(stringField(f.get("fw/hello").get(), "challenge_id").c_str()));
    f.send("ha/open_session", o.get());
    ASSERT_TRUE(f.output.count("fw/session"));
    f.syncSession();
    EXPECT_NE(f.session, oldSession);
    EXPECT_EQ(stringField(f.get("fw/session").get(), "client_nonce"), "restarted");
    // The hello reply to stale opens is rate-limited (at most once a second).
    f.output.erase("fw/hello");
    f.send("ha/open_session", stale.get()); f.send("ha/open_session", stale.get());
    EXPECT_LE(f.output.count("fw/hello"), 1u);
}
