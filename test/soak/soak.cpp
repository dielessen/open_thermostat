// Long-run host soak test of the OpenThermostat E32 control modules.
//
// Drives the pure modules (RoomEngine, RoomDemand, FlowDemand, ShadowComparison,
// FlowLearner, WarmupPlanner, DhwEpisodes, BurnerCycleMonitor, ActiveHeatGuard,
// ManagedBleObserver, HeatingInput, HeatingTelemetry, RoomSchedule and
// diagnostics::SupervisorPolicy) with simulated time and a simulated house for
// weeks, and checks invariants on every step. Nothing here talks to a device.
// See test/soak/README.md for scenarios, invariants and how to run it.
#include "EMS/ActiveHeatPollDriver.h"
#include "EMS/ClassicBoilerMonitor.h"
#include "EMS/EmsTelegram.h"
#include "EMS/ForeignBoilerRequest.h"
#include "control/ActiveHeatGuard.h"
#include "control/BurnerCycleMonitor.h"
#include "control/ControlPartitionBudget.h"
#include "control/DhwEpisodes.h"
#include "control/FlowLearner.h"
#include "control/HeatingInput.h"
#include "control/HeatingTelemetry.h"
#include "control/ManagedBleObserver.h"
#include "control/RoomEngine.h"
#include "control/ShadowComparison.h"
#include "control/WarmupPlanner.h"
#include "diagnostics/SupervisorPolicy.h"
#include <cJSON.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cinttypes>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <deque>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <random>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include <fcntl.h>
#include <sys/wait.h>
#include <unistd.h>

#if defined(__SANITIZE_ADDRESS__)
#define SOAK_ASAN 1
#elif defined(__has_feature)
#if __has_feature(address_sanitizer)
#define SOAK_ASAN 1
#endif
#endif
#ifdef SOAK_ASAN
extern "C" size_t __sanitizer_get_current_allocated_bytes(); // sanitizer/allocator_interface.h
#else
#include <malloc.h>
#endif

using namespace heating::control;
namespace ems = heating::ems;
namespace diag = heating::diagnostics;

namespace {
// ModernTransport.h (ESP-only): fw/telemetry/heating* above this size is dropped.
constexpr size_t heatingTelemetryMaxBytes = 7900;

// ============================================================================
// Reporting
// ============================================================================
struct Context { std::string scenario = "-"; uint64_t uptime = 0; int64_t utc = 0; int64_t startUtc = 0; } ctx;
struct Failure { uint64_t count = 0; std::string first; };
std::map<std::string, Failure> failures;
std::map<std::string, std::string> observations; // not failures: facts worth reporting
std::map<std::string, uint64_t> counters;          // event statistics

std::string isoUtc(int64_t utc) {
    const std::time_t t = static_cast<std::time_t>(utc);
    std::tm tm{};
    gmtime_r(&t, &tm);
    char text[32];
    std::strftime(text, sizeof text, "%Y-%m-%dT%H:%M:%SZ", &tm);
    return text;
}
std::string isoLocal(int64_t utc) {
    const std::time_t t = static_cast<std::time_t>(utc);
    std::tm tm{};
    localtime_r(&t, &tm);
    char text[48];
    std::strftime(text, sizeof text, "%Y-%m-%d %H:%M:%S %Z", &tm);
    return text;
}

void fail(const std::string& id, const char* fmt, ...) __attribute__((format(printf, 2, 3)));
void fail(const std::string& id, const char* fmt, ...) {
    char message[2048];
    va_list ap;
    va_start(ap, fmt);
    std::vsnprintf(message, sizeof message, fmt, ap);
    va_end(ap);
    auto& f = failures[ctx.scenario + ":" + id];
    if (f.count++ < 3) {
        std::fprintf(stderr, "FAIL [%s] %s at day %.4f (uptime %" PRIu64 " ms, %s / %s): %s\n", ctx.scenario.c_str(), id.c_str(),
                     double(ctx.utc - ctx.startUtc) / 86400.0, ctx.uptime, isoUtc(ctx.utc).c_str(), isoLocal(ctx.utc).c_str(), message);
        if (f.first.empty()) f.first = message;
    }
}
#define EXPECT(cond, id, ...) do { if (!(cond)) fail(id, __VA_ARGS__); } while (0)
void observe(const std::string& id, const std::string& text) {
    auto& o = observations[ctx.scenario + ":" + id];
    if (o.empty()) o = text;
}
void count(const std::string& id, uint64_t n = 1) { counters[ctx.scenario + ":" + id] += n; }

// ============================================================================
// Allocation accounting: cJSON hooks count live blocks (exact leak check, and
// allocation-failure injection); the process heap is sampled once per day.
// ============================================================================
std::atomic<long> cjLive{0};
std::atomic<long> cjCalls{0};
long cjFailAt = 0; // fail the n-th cJSON allocation after a reset of cjCalls (0: never)
void* cjMalloc(size_t size) {
    const long n = ++cjCalls;
    if (cjFailAt && n == cjFailAt) return nullptr;
    void* p = std::malloc(size);
    if (p) ++cjLive;
    return p;
}
void cjFree(void* p) {
    if (!p) return;
    --cjLive;
    std::free(p);
}
size_t heapBytes() {
#ifdef SOAK_ASAN
    return __sanitizer_get_current_allocated_bytes();
#else
    return mallinfo2().uordblks;
#endif
}

// localtime_r() calls (the device's newlib parses the POSIX TZ in each call):
// counted per payload when linked with -Wl,--wrap=localtime_r (run.sh does).
uint64_t localtimeCalls = 0;
#ifdef SOAK_WRAP_LOCALTIME
} // namespace
extern "C" struct tm* __real_localtime_r(const time_t*, struct tm*);
extern "C" struct tm* __wrap_localtime_r(const time_t* t, struct tm* out) { ++localtimeCalls; return __real_localtime_r(t, out); }
namespace {
#endif
struct CallStat { uint64_t max = 0, sum = 0, n = 0; int64_t maxUtc = 0; };
std::map<std::string, CallStat> localtimeStats;
void noteLocaltime(const char* what, uint64_t calls, int64_t utc) {
    auto& c = localtimeStats[ctx.scenario + ":" + what];
    if (calls > c.max) { c.max = calls; c.maxUtc = utc; }
    c.sum += calls; ++c.n;
}

std::string printed(const cJSON* o) {
    if (!o) return {};
    char* text = cJSON_PrintUnformatted(o);
    std::string out = text ? text : "";
    cJSON_free(text);
    return out;
}
// Parses the text back; nullptr when it is not exactly one valid JSON document.
cJSON* parseBack(const std::string& text) {
    const char* end = nullptr;
    return cJSON_ParseWithLengthOpts(text.c_str(), text.size() + 1, &end, true);
}
bool validJson(const std::string& text) {
    cJSON* p = parseBack(text);
    const bool ok = p != nullptr;
    cJSON_Delete(p);
    return ok;
}

// Size statistics per payload kind.
struct SizeStat { size_t max = 0, over = 0, n = 0; std::string limitName; size_t limit = 0; };
std::map<std::string, SizeStat> sizes;
// Checks one produced payload: valid JSON, within its limit (0: none).
void checkPayload(const char* kind, const std::string& text, size_t limit, bool emptyAllowed = false) {
    auto& s = sizes[ctx.scenario + ":" + kind];
    s.limit = limit;
    ++s.n;
    if (text.empty()) { EXPECT(emptyAllowed, std::string("json_empty_") + kind, "%s produced no payload", kind); return; }
    s.max = std::max(s.max, text.size());
    EXPECT(validJson(text), std::string("json_invalid_") + kind, "%s is not valid JSON: %.300s", kind, text.c_str());
    if (limit && text.size() > limit) {
        ++s.over;
        fail(std::string("json_too_large_") + kind, "%s is %zu B > %zu B: %.400s", kind, text.size(), limit, text.c_str());
    }
}

// "Always the same shape": the set of key paths (array elements merged).
void keyPaths(const cJSON* o, const std::string& prefix, std::set<std::string>& out) {
    for (const cJSON* c = o ? o->child : nullptr; c; c = c->next) {
        const std::string path = cJSON_IsArray(o) ? prefix + "[]" : prefix + "." + (c->string ? c->string : "?");
        if (cJSON_IsObject(c) || cJSON_IsArray(c)) keyPaths(c, path, out);
        else out.insert(path);
    }
}

// ============================================================================
// Time zone helpers (POSIX TZ strings, as configTzTime() uses on the device)
// ============================================================================
void setTz(const std::string& tz) { setenv("TZ", tz.c_str(), 1); tzset(); }
struct LocalTm { int year, month, day, wday, hour, minute, second; };
LocalTm local(int64_t utc) {
    const std::time_t t = static_cast<std::time_t>(utc);
    std::tm tm{};
    localtime_r(&t, &tm);
    return {tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday, tm.tm_wday, tm.tm_hour, tm.tm_min, tm.tm_sec};
}
// Days since 1970-01-01 of the local date, independent of RoomSchedule (timegm).
int32_t localDayIndex(int64_t utc) {
    const auto l = local(utc);
    std::tm tm{};
    tm.tm_year = l.year - 1900; tm.tm_mon = l.month - 1; tm.tm_mday = l.day; tm.tm_hour = 12;
    return int32_t(timegm(&tm) / 86400);
}
int64_t parseIsoUtc(const std::string& s) {
    std::tm tm{};
    if (std::sscanf(s.c_str(), "%d-%d-%dT%d:%d:%d", &tm.tm_year, &tm.tm_mon, &tm.tm_mday, &tm.tm_hour, &tm.tm_min, &tm.tm_sec) != 6) {
        std::fprintf(stderr, "bad --start %s (want YYYY-MM-DDTHH:MM:SSZ)\n", s.c_str());
        std::exit(2);
    }
    tm.tm_year -= 1900; tm.tm_mon -= 1;
    return timegm(&tm);
}

// Independent week-program lookup from the C library's local time: the last
// switch point at or before now, looking back over earlier days.
std::optional<int16_t> scheduleOracle(const RoomSchedule& s, int64_t utc) {
    const auto l = local(utc);
    const int weekday = (l.wday + 6) % 7, minute = l.hour * 60 + l.minute;
    const auto& today = s.days[weekday];
    std::optional<int16_t> found;
    for (uint8_t i = 0; i < today.count; ++i) if (today.points[i].minute <= minute) found = today.points[i].centiC;
    if (found) return found;
    for (int back = 1; back <= 7; ++back) {
        const auto& d = s.days[(weekday + 7 - back) % 7];
        if (d.count) return d.points[d.count - 1].centiC;
    }
    return std::nullopt;
}

// ============================================================================
// Options
// ============================================================================
struct Options {
    std::string scenario = "chain";
    std::string name;                         // label in the report (default: scenario)
    std::string tz = "CET-1CEST,M3.5.0,M10.5.0/3";
    int64_t startUtc = 1789907690;            // 2026-09-20T12:34:50Z
    double days = 60;
    uint64_t uptime0 = 0;                     // uptime at the start (ms)
    uint64_t seed = 1;
    uint32_t stepMs = 10000;
    uint32_t mqttEveryS = 300, learnedEveryS = 900, fullEveryS = 3600;
    double editEveryH = 4;
    bool liveDhwFlow = false, boilerOutdoor = false, oom = true, activePhases = true;
    std::string outDir = "/tmp";
};
Options opt;

// ============================================================================
// Random
// ============================================================================
std::mt19937_64 rng;
double uniform(double a, double b) { return std::uniform_real_distribution<double>(a, b)(rng); }
int64_t uniformInt(int64_t a, int64_t b) { return std::uniform_int_distribution<int64_t>(a, b)(rng); }
bool chance(double p) { return uniform(0, 1) < p; }
double expo(double mean) { return std::exponential_distribution<double>(1.0 / mean)(rng); }

// ============================================================================
// Synthetic BLE: BTHome v2 adverts (pvvx firmware), with a deterministic stand-in
// for AES-CCM (state machine seam only; real vectors are tested elsewhere).
// ============================================================================
uint64_t bleClockNow = 0;
int bleClockRollback = 0;   // > 0: the next clock read returns 1 s in the past
uint64_t bleClock() {
    if (bleClockRollback > 0) { --bleClockRollback; return bleClockNow >= 1000 ? bleClockNow - 1000 : 0; }
    return bleClockNow;
}
struct SoakCrypto {
    uint64_t calls = 0;
    void clear() noexcept {}
    static uint32_t tag(const BleBindKey& key, const uint8_t* nonce, size_t nonceSize, const uint8_t* c, size_t size) {
        uint32_t h = 2166136261u;
        const auto mix = [&](uint8_t b) { h = (h ^ b) * 16777619u; };
        for (auto b : key) mix(b);
        for (size_t i = 0; i < nonceSize; ++i) mix(nonce[i]);
        for (size_t i = 0; i < size; ++i) mix(c[i]);
        return h;
    }
    BleCcmStatus decrypt(const BleBindKey& key, const uint8_t* nonce, size_t nonceSize, const uint8_t*, size_t,
                         const uint8_t* in, size_t size, const uint8_t* mic, uint8_t* out, size_t capacity) {
        ++calls;
        if (size > capacity) return BleCcmStatus::invalid_argument;
        const uint32_t want = tag(key, nonce, nonceSize, in, size);
        const uint32_t got = uint32_t(mic[0]) | (uint32_t(mic[1]) << 8) | (uint32_t(mic[2]) << 16) | (uint32_t(mic[3]) << 24);
        if (want != got) return BleCcmStatus::authentication_failed;
        for (size_t i = 0; i < size; ++i) out[i] = in[i] ^ key[i % key.size()];
        return BleCcmStatus::authenticated;
    }
};
std::vector<uint8_t> bthomeAdvert(const ManagedBleAddress& address, const std::vector<uint8_t>& objects, bool encrypted,
                                  uint32_t counter, const BleBindKey& key, bool forgeMic = false) {
    std::vector<uint8_t> service{uint8_t(encrypted ? 0x41 : 0x40)};
    if (!encrypted) service.insert(service.end(), objects.begin(), objects.end());
    else {
        std::vector<uint8_t> c(objects.size());
        for (size_t i = 0; i < objects.size(); ++i) c[i] = objects[i] ^ key[i % key.size()];
        std::array<uint8_t, 13> nonce{};
        for (size_t i = 0; i < 6; ++i) nonce[i] = address[i];
        nonce[6] = 0xd2; nonce[7] = 0xfc; nonce[8] = 0x41;
        for (size_t i = 0; i < 4; ++i) nonce[9 + i] = uint8_t(counter >> (8 * i));
        uint32_t mic = SoakCrypto::tag(key, nonce.data(), nonce.size(), c.data(), c.size());
        if (forgeMic) mic ^= 0x5a5a5a5a;
        service.insert(service.end(), c.begin(), c.end());
        for (size_t i = 0; i < 4; ++i) service.push_back(uint8_t(counter >> (8 * i)));
        for (size_t i = 0; i < 4; ++i) service.push_back(uint8_t(mic >> (8 * i)));
    }
    std::vector<uint8_t> ad{0x02, 0x01, 0x06};
    ad.push_back(uint8_t(3 + service.size()));
    ad.push_back(0x16); ad.push_back(0xd2); ad.push_back(0xfc);
    ad.insert(ad.end(), service.begin(), service.end());
    return ad;
}
std::vector<uint8_t> thermometerObjects(int16_t centi, bool centiResolution, uint8_t battery, uint16_t humidity, uint8_t packet) {
    std::vector<uint8_t> o{0x00, packet, 0x01, battery};
    if (centiResolution) { o.push_back(0x02); o.push_back(uint8_t(centi & 0xff)); o.push_back(uint8_t((uint16_t(centi) >> 8) & 0xff)); }
    else { const int16_t d = int16_t(centi / 10); o.push_back(0x45); o.push_back(uint8_t(d & 0xff)); o.push_back(uint8_t((uint16_t(d) >> 8) & 0xff)); }
    o.push_back(0x03); o.push_back(uint8_t(humidity & 0xff)); o.push_back(uint8_t(humidity >> 8));
    return o;
}

// ============================================================================
// EMS telegrams (Classic UBA, big endian words in 0.1 degC), as the boiler sends them
// ============================================================================
ems::EmsTelegram telegram(uint16_t type, std::vector<uint8_t> data, uint8_t source = 0x08, uint8_t destination = 0x00,
                          ems::EmsTelegram::operation_t op = ems::EmsTelegram::BROADCAST) {
    return ems::EmsTelegram(op, source, destination, 0, type, std::move(data));
}
void putWord(std::vector<uint8_t>& d, size_t at, int value) { d[at] = uint8_t((uint16_t(value) >> 8) & 0xff); d[at + 1] = uint8_t(value & 0xff); }

// ============================================================================
// The simulated house
// ============================================================================
struct PhysRoom {
    std::string id, name;
    bool floor = false, heated = true;
    double air = 19.5, emitter = 19.5;
    double a = 0.07, b = 0.035, tauE = 0.3; // emitter coupling (1/h per K), loss (1/h per K), emitter lag (h)
    double trvSetC = 20;                     // radiator TRV setting
    bool trvOpen = true;
    uint64_t windowUntil = 0;
};
struct SimSensor {
    ManagedBleAddress address{};
    std::string hex;
    int room = 0;              // physical room
    bool encrypted = false, centi = false;
    BleBindKey key{};
    double offset = 0;
    uint32_t counter = 1000;
    uint32_t periodMs = 30000;
    uint64_t nextAt = 0, silentUntil = 0, resetAt = 0, faultAt = 0, burstAt = 0;
    bool resetPending = false;
    uint8_t packet = 0;
    std::deque<std::pair<uint64_t, int16_t>> good;   // accepted-eligible frames (at, centi), last 20 min
    std::vector<uint8_t> lastEncryptedFrame;         // for replays
    BleObservationSnapshot prev;
    bool havePrev = false;
    uint64_t lastAcceptedSeenAt = 0;
};

// ============================================================================
// RoomEngine oracle: what RoomDemand/RoomEngine must report, from the plan and
// the delivered readings (kept per room and source, carried over like setPlan).
// ============================================================================
struct OracleRoom {
    std::map<std::pair<int, std::string>, RoomDemand::Reading> readings;
    std::optional<std::pair<int, std::string>> lead;
    RoomDemand::Reading lastUsable{};
    std::optional<int16_t> target;
    uint64_t targetAt = 0;
};

// ============================================================================
// The full chain: house + boiler + tado + HA + BLE + every module of the E32.
// ============================================================================
class Chain {
public:
    explicit Chain(const Options& o) : o_(o) {}
    int run();

private:
    // --- configuration
    const Options& o_;
    uint64_t now_ = 0;   // uptime ms
    int64_t utc_ = 0;    // wall clock (s)
    bool clockKnown_ = false;
    uint64_t bootMs_ = 0;

    // --- the house
    std::vector<PhysRoom> phys_;
    std::vector<SimSensor> sensors_;
    double outdoor_ = 8, weather_ = 0, frostOffset_ = 0;
    uint64_t frostUntil_ = 0;
    // boiler
    double flow_ = 25, dhwTemp_ = 50;
    bool burner_ = false, cyclingOff_ = false;
    uint8_t modulation_ = 0;
    double gasM3_ = 1234.0;
    const double trueNominalKw_ = 24;
    uint64_t busDownUntil_ = 0;
    std::optional<uint8_t> boilerLimit_ = uint8_t(60);
    // the boiler's view of who asks what (latest 0x1A)
    struct Setpoint { uint8_t from = 0; uint8_t flow = 0; uint64_t at = 0; };
    std::optional<Setpoint> boilerSetpoint_;
    // tado
    bool tadoConnected_ = true, tadoHeat_ = false;
    uint8_t tadoFlow_ = 0, tadoPeriodFlow_ = 35;
    uint64_t tadoChangedAt_ = 0, tadoNext1A_ = 0;
    std::optional<std::pair<uint8_t, uint64_t>> tadoLast1A_; // flow, at (what the E32 hears)
    // DHW episodes (generator + oracle)
    enum class Dhw { idle, tap, keepWarm };
    Dhw dhw_ = Dhw::idle;
    uint64_t dhwUntil_ = 0, dhwNextTap_ = 0, dhwStartedAt_ = 0;
    double dhwTapMin_ = 20;
    uint8_t dhwFlowTenths_ = 25;
    struct DhwDay { std::array<uint16_t, 3> count{}; std::array<uint32_t, 3> seconds{}; };
    std::map<int32_t, DhwDay> dhwOracle_;
    bool dhwOracleValid_ = true;
    // burner cycle oracle
    struct Run { uint64_t start; bool dhw; };
    std::deque<Run> burnerRuns_;
    std::optional<bool> lastReportedOn_;
    bool lastReportedGap_ = false;
    uint64_t lastReportAt_ = 0;

    // --- HA
    uint64_t haDownUntil_ = 0, haNextOutage_ = 0, gasNext_ = 0, priceNext_ = 0, outdoorNext_ = 0;
    std::map<std::string, uint64_t> haNext_;
    std::map<std::string, std::pair<double, double>> haSent_; // last temperature/target sent
    bool boilerKwSent_ = false;

    // --- the E32
    RoomEngine engine_;
    ShadowComparison shadow_;
    FlowLearner learner_;
    HeatingInputRoute haRoute_;
    ems::ClassicBoilerMonitor monitor_;
    ems::ForeignBoilerRequest foreign_;
    BurnerCycleMonitor cycles_;
    DhwEpisodes dhwEpisodes_;
    ActiveHeatGuard guard_;
    SoakCrypto crypto_;
    std::unique_ptr<ManagedBleObserver<SoakCrypto>> ble_;
    ManagedBleBindings bindings_;
    RoomRotation rotation_;

    // --- plan
    RoomPlan plan_;
    std::vector<RoomPlan::Room> catalog_; // every physical room's base plan room
    uint64_t nextEdit_ = 0;
    std::map<std::string, OracleRoom> oracle_;
    // guard phases
    enum class Phase { shadow, armingOwner, active, blockedWait };
    Phase phase_ = Phase::shadow;
    uint64_t phaseUntil_ = 0, nextPhase_ = 0;
    std::optional<uint64_t> confirmedAt_;
    std::optional<std::pair<uint8_t, uint64_t>> lastPost_; // flow posted at the previous step
    bool routeReady_ = true;

    // --- oracles and statistics
    int32_t lastDay_ = INT32_MIN;
    std::map<int32_t, uint32_t> daySeconds_;   // seconds credited per local day (oracle)
    std::map<int32_t, uint32_t> dayE32HeatS_;
    std::map<int32_t, uint32_t> dayE32Starts_, dayTadoStarts_;
    std::optional<bool> prevE32Heat_, prevTadoHeat_;
    size_t prevCompleted_ = 0;
    int32_t firstKnownDay_ = INT32_MIN;
    std::vector<std::pair<int32_t, size_t>> heap_;
    std::optional<FlowDemand::Request> prevRequest_;
    uint64_t lastHeatOn_ = 0, lastHeatOff_ = 0, flowRebuiltAt_ = 0;
    bool haveHeatEdge_ = false;
    std::map<std::string, std::string> readinessSeen_;
    std::map<std::string, uint16_t> segmentsSeen_;
    std::map<std::string, RoomPlan::Emitter> emitterSeen_;
    uint16_t periodsSeen_ = 0, gasIntervalsSeen_ = 0;
    uint32_t burnerStartsSeen_ = 0;
    std::set<std::string> shape_;
    bool shapeKnown_ = false;
    uint64_t activeOwningS_ = 0, comfortOutS_ = 0;
    uint64_t nextMqtt_ = 0, nextLearned_ = 0, nextFull_ = 0, nextWarmupCheck_ = 0;
    size_t planTooLarge_ = 0, planRefused_ = 0, planApplied_ = 0, maxPlanBytes_ = 0;
    uint64_t stallUntil_ = 0, lastShadowAt_ = 0;   // loop stalls (an OTA upload blocks the loop for minutes)
    bool haveShadowAt_ = false;
    std::set<int32_t> irregularDays_;              // days with a stall or an NTP step: no exact day length

    // ---------------------------------------------------------------------
    void setupHouse();
    void setupPlan();
    void setupBle();
    RoomPlan::Room baseRoom(size_t i) const;
    void step();
    void weather();
    void physics(double dtH);
    void tado();
    void boiler(double dtH);
    void dhwGenerator();
    void emitTelegrams();
    void haMessages();
    void haSend(const std::string& payload, bool expectAccepted);
    void bleAdverts();
    void stepE32();
    void checkEngine(const FlowDemand::Request& request);
    void checkShadow(const FlowDemand::Request& request, std::optional<uint8_t> tadoFlowC);
    void checkDay();
    void checkBle();
    void checkLearner();
    void checkWarmup();
    void guardPhases();
    void editPlan();
    bool applyPlan(const RoomPlan& candidate, const char* why);
    void oracleSetPlan(const RoomPlan& next);
    void publish(bool mqtt, bool learned, bool full);
    cJSON* heatingStatusJson(bool mqtt);
    LearnedContext learnedContext(std::array<std::optional<int16_t>, RoomPlan::maxRooms>& temperatures) const;
    void oomSweep();
    void finish();
    size_t physIndex(const std::string& id) const {
        for (size_t i = 0; i < phys_.size(); ++i) if (phys_[i].id == id) return i;
        return SIZE_MAX;
    }
};

RoomSchedule weekProgram(std::initializer_list<std::pair<uint16_t, int16_t>> weekday,
                         std::initializer_list<std::pair<uint16_t, int16_t>> weekend) {
    RoomSchedule s;
    for (int d = 0; d < 7; ++d) {
        const auto& points = d < 5 ? weekday : weekend;
        for (const auto& p : points) s.days[d].points[s.days[d].count++] = {p.first, p.second};
    }
    return s;
}

void Chain::setupHouse() {
    const auto room = [&](const char* id, const char* name, bool floor, double air) {
        PhysRoom r; r.id = id; r.name = name; r.floor = floor; r.air = r.emitter = air;
        if (floor) { r.a = 0.12; r.b = 0.035; r.tauE = 2.5; }
        phys_.push_back(r);
    };
    room("woonkamer", "Woonkamer", true, 19.5);
    room("keuken", "Keuken", true, 19.0);
    room("slaapkamer", "Slaapkamer", false, 17.5);
    room("kinderkamer", "Kinderkamer", false, 18.5);
    room("badkamer", "Badkamer", false, 20.0);
    room("studeerkamer", "Studeerkamer \xF0\x9F\x93\x9A \"thuis\"", false, 18.0); // UTF-8 and a quote
    room("hal", "Hal", false, 17.0);
    room("zolder", "Zolder", false, 12.0);
    phys_[7].heated = false; phys_[7].b = 0.06; // unheated attic: frost rule
    phys_[2].trvSetC = 17.5; phys_[3].trvSetC = 19.5; phys_[4].trvSetC = 21.5; phys_[5].trvSetC = 19.5; phys_[6].trvSetC = 18;
}

RoomPlan::Room Chain::baseRoom(size_t i) const {
    RoomPlan::Room r;
    r.id = phys_[i].id; r.name = phys_[i].name;
    r.state = RoomDemand::State::active;
    r.emitter = phys_[i].floor ? RoomPlan::Emitter::floor : RoomPlan::Emitter::radiator;
    const auto ble = [&](int s) { return RoomPlan::Source{RoomPlan::SourceType::ble, sensors_[size_t(s)].hex}; };
    const auto ha = [&](const char* e) { return RoomPlan::Source{RoomPlan::SourceType::ha, e}; };
    switch (i) {
        case 0: r.sources = {ha("climate.woonkamer"), ble(0)}; r.setpointEntity = "climate.woonkamer";
                r.schedule = weekProgram({{390, 2050}, {1350, 1800}}, {{480, 2100}, {1380, 1800}}); break;
        case 1: r.sources = {ble(1), ha("sensor.keuken_temperatuur")};
                r.schedule = weekProgram({{360, 2000}, {1320, 1750}}, {{450, 2050}, {1380, 1750}}); break;
        case 2: r.sources = {ble(2)}; r.fallbackCentiC = 1700;
                r.schedule = weekProgram({{420, 1800}, {1290, 1600}}, {{510, 1800}, {1350, 1600}}); break;
        case 3: r.sources = {ble(3), ha("sensor.kinderkamer_temperatuur")}; r.fallbackCentiC = 1900;
                r.schedule = weekProgram({{150, 1750}, {400, 1950}, {1200, 1800}}, {{150, 1750}, {480, 1950}, {1260, 1800}}); break; // 02:30: in the DST gap
        case 4: r.sources = {ha("sensor.badkamer_temperatuur"), ble(4)}; r.setpointEntity = "climate.badkamer_trv"; r.fallbackCentiC = 2100;
                r.schedule = weekProgram({{330, 2200}, {480, 1900}, {1140, 2150}, {1320, 1800}}, {{450, 2200}, {600, 1950}, {1170, 2150}, {1350, 1800}}); break;
        case 5: r.sources = {ble(5)}; r.state = RoomDemand::State::inactive; r.fallbackCentiC = 1950; break;
        case 6: r.sources = {ble(6)}; r.fallbackCentiC = 1800; break; // no schedule: fallback only
        default: r.sources = {ha("sensor.zolder_temperatuur"), ble(7)}; r.state = RoomDemand::State::inactive; r.fallbackCentiC = 1500; break;
    }
    return r;
}

void Chain::setupBle() {
    for (int i = 0; i < 8; ++i) {
        SimSensor s;
        s.address = {0xa4, 0xc1, 0x38, 0x00, 0x00, uint8_t(i + 1)};
        s.hex = printBleHex(s.address).data();
        s.room = i; // sensor i sits in physical room i
        s.encrypted = i >= 4;
        s.centi = i % 2 == 0;
        for (size_t k = 0; k < s.key.size(); ++k) s.key[k] = uint8_t(0x30 + i * 7 + k);
        s.offset = uniform(-0.3, 0.3);
        s.counter = uint32_t(uniformInt(1000, 50000));
        s.periodMs = 30000;
        s.nextAt = now_ + uint64_t(uniformInt(1000, 30000));
        sensors_.push_back(s);
        auto& b = bindings_.devices[bindings_.count++];
        b.address = s.address; b.profile = ManagedBleProfile::pvvxThermometer;
        b.encryption = s.encrypted ? ManagedBleEncryption::bthomeV2 : ManagedBleEncryption::plain;
        if (s.encrypted) { b.key = s.key; b.hasKey = true; }
        const std::string name = "Thermometer " + std::to_string(i + 1);
        std::copy_n(name.c_str(), name.size(), b.name.begin());
    }
    ble_.reset(new ManagedBleObserver<SoakCrypto>(crypto_, bleClock));
    EXPECT(ble_->initialize(bindings_), "ble_initialize", "bindings refused");
}

void Chain::setupPlan() {
    for (size_t i = 0; i < phys_.size(); ++i) catalog_.push_back(baseRoom(i));
    RoomPlan plan;
    plan.revision = 0; plan.mode = RoomPlan::Mode::shadow; plan.minimumFlowC = 30; plan.maximumFlowC = 60;
    plan.rooms = catalog_;
    // As the firmware loads it: through JSON.
    const auto raw = plan.json();
    RoomPlan parsed;
    cJSON* root = parseBack(raw);
    EXPECT(root && !RoomPlan::parse(root, parsed), "plan_initial_parse", "initial plan does not parse: %s", raw.c_str());
    cJSON_Delete(root);
    oracleSetPlan(parsed);
    engine_.setPlan(parsed); learner_.setPlan(parsed);
    plan_ = parsed;
    maxPlanBytes_ = raw.size();
}

// ----------------------------------------------------------------------------
// Plan edits as HA and the web page send them: a JSON write based on a revision.
// ----------------------------------------------------------------------------
void Chain::oracleSetPlan(const RoomPlan& next) {
    std::map<std::string, OracleRoom> out;
    for (const auto& room : next.rooms) {
        OracleRoom n;
        const RoomPlan::Room* old = plan_.find(room.id);
        const auto it = oracle_.find(room.id);
        if (old && it != oracle_.end()) {
            const auto& o = it->second;
            for (const auto& s : room.sources) {
                const auto key = std::make_pair(int(s.type), s.id);
                const auto r = o.readings.find(key);
                if (r != o.readings.end()) n.readings[key] = r->second;
            }
            n.lastUsable = o.lastUsable;
            n.lead = o.lead;
            if (o.lead && !n.readings.count(*o.lead)) {
                bool present = false;
                for (const auto& s : room.sources) present = present || (int(s.type) == o.lead->first && s.id == o.lead->second);
                if (!present) { n.lead.reset(); n.lastUsable = {}; }
            }
            if (old->setpointEntity == room.setpointEntity) { n.target = o.target; n.targetAt = o.targetAt; }
        }
        out[room.id] = n;
    }
    oracle_ = std::move(out);
}

bool Chain::applyPlan(const RoomPlan& candidate, const char* why) {
    // HeatingController::setHeatingPlan, via the JSON the client sends.
    const auto body = candidate.json();
    cJSON* root = parseBack(body);
    EXPECT(root != nullptr, "plan_json_invalid", "%s: plan JSON invalid", why);
    RoomPlan plan;
    const char* error = root ? RoomPlan::parse(root, plan) : "invalid_json";
    if (!error && (!cJSON_IsNumber(cJSON_GetObjectItemCaseSensitive(root, "revision")) || plan.revision != engine_.plan().revision)) error = "plan_changed";
    cJSON_Delete(root);
    if (error) { ++planRefused_; count(std::string("plan_refused_") + error); return false; }
    if (plan.json() == engine_.plan().json()) { count("plan_unchanged"); return true; }
    plan.revision = engine_.plan().revision + 1;
    const auto raw = plan.json();
    maxPlanBytes_ = std::max(maxPlanBytes_, raw.size());
    if (raw.size() + 1 > ControlPartitionBudget::configBytes) { ++planTooLarge_; count("plan_refused_plan_too_large"); return false; }
    // Stored and loaded back as the next boot would.
    RoomPlan reloaded;
    cJSON* again = parseBack(raw);
    EXPECT(again && !RoomPlan::parse(again, reloaded) && reloaded.json() == raw, "plan_roundtrip", "%s: stored plan does not load back identically", why);
    cJSON_Delete(again);
    const bool flowChanged = plan.minimumFlowC != engine_.plan().minimumFlowC || plan.maximumFlowC != engine_.plan().maximumFlowC;
    oracleSetPlan(plan);
    engine_.setPlan(plan); learner_.setPlan(plan);
    plan_ = plan;
    if (flowChanged) { flowRebuiltAt_ = now_; haveHeatEdge_ = false; } // FlowDemand restarts: no minimum off time
    EXPECT(engine_.plan().json() == raw, "plan_applied_differs", "engine plan differs from the saved plan");
    ++planApplied_;
    count(std::string("plan_edit_") + why);
    return true;
}

void Chain::editPlan() {
    RoomPlan p = engine_.plan();
    const auto pick = [&]() -> RoomPlan::Room* { return p.rooms.empty() ? nullptr : &p.rooms[size_t(uniformInt(0, int64_t(p.rooms.size()) - 1))]; };
    const int kind = int(uniformInt(0, 15));
    RoomPlan::Room* r = pick();
    const char* why = "none";
    switch (kind) {
        case 0: case 1: if (r && r->sources.size() > 1) { std::shuffle(r->sources.begin(), r->sources.end(), rng); why = "reorder_sources"; } break;
        case 2: if (r && r->sources.size() > 1) { r->sources.erase(r->sources.begin() + uniformInt(0, int64_t(r->sources.size()) - 1)); why = "remove_source"; } break;
        case 3: if (r) { // restore the catalog's sources (adds removed ones back)
                    for (const auto& c : catalog_) if (c.id == r->id) r->sources = c.sources;
                    if (chance(0.3) && r->sources.size() < RoomDemand::maxSources) { // and a sensor of another room
                        const auto& s = sensors_[size_t(uniformInt(0, 7))];
                        bool dup = false;
                        for (const auto& x : r->sources) dup = dup || x.id == s.hex;
                        if (!dup) r->sources.push_back({RoomPlan::SourceType::ble, s.hex});
                    }
                    why = "restore_sources"; } break;
        case 4: if (r) { // a temporary pause, or back to active
                    if (r->state == RoomDemand::State::active || chance(0.3)) {
                        r->state = RoomDemand::State::inactive;
                        r->inactiveUntil = clockKnown_ ? uint32_t(utc_ + uniformInt(1800, 2 * 86400)) : 0;
                        if (chance(0.15)) r->inactiveUntil = clockKnown_ ? uint32_t(utc_ - 60) : 0; // already over
                    } else { r->state = RoomDemand::State::active; r->inactiveUntil = 0; }
                    why = "pause"; } break;
        case 5: if (r) { r->setpointEntity = r->setpointEntity.empty() ? (r->id == "woonkamer" ? "climate.woonkamer" : "climate.badkamer_trv") : ""; why = "setpoint_entity"; } break;
        case 6: if (r) { r->fallbackCentiC = int16_t(std::clamp<int>(r->fallbackCentiC + int(uniformInt(-2, 2)) * 50, r->minimumCentiC, r->maximumCentiC)); why = "fallback"; } break;
        case 7: if (r) { // limits: may make the schedule invalid -> refused
                    r->minimumCentiC = int16_t(uniformInt(5, 16) * 100); r->maximumCentiC = int16_t(uniformInt(22, 30) * 100);
                    r->fallbackCentiC = std::clamp(r->fallbackCentiC, r->minimumCentiC, r->maximumCentiC); why = "limits"; } break;
        case 8: if (r) { // a new week program, sometimes with a point in the DST hour
                    RoomSchedule s;
                    for (int d = 0; d < 7; ++d) {
                        const int n = int(uniformInt(0, 4));
                        uint16_t m = 0;
                        for (int k = 0; k < n; ++k) {
                            m = uint16_t(std::min<int64_t>(1439, m + uniformInt(30, 400)));
                            if (s.days[d].count && m <= s.days[d].points[s.days[d].count - 1].minute) break;
                            if (chance(0.1)) m = std::max<uint16_t>(m, 150);
                            s.days[d].points[s.days[d].count++] = {m, int16_t(std::clamp<int64_t>(uniformInt(16, 22) * 100 + uniformInt(0, 1) * 50, r->minimumCentiC, r->maximumCentiC))};
                        }
                    }
                    if (chance(0.15)) s = {}; // remove the program
                    r->schedule = s; why = "schedule"; } break;
        case 9: if (chance(0.25)) { // flow limits (restarts FlowDemand)
                    p.minimumFlowC = uint8_t(uniformInt(25, 35)); p.maximumFlowC = uint8_t(uniformInt(45, FlowDemand::ceilingC)); why = "flow_limits"; } break;
        case 10: if (chance(0.3) && p.rooms.size() > 4) { p.rooms.erase(p.rooms.begin() + uniformInt(0, int64_t(p.rooms.size()) - 1)); why = "remove_room"; }
                 else { for (const auto& c : catalog_) if (!p.find(c.id) && p.rooms.size() < RoomPlan::maxRooms) { p.rooms.push_back(c); why = "add_room"; break; } } break;
        case 11: if (r) { r->name = chance(0.5) ? r->name + "!" : std::string("Kamer \xC3\xA9\xC3\xA9n"); if (r->name.size() > 40) r->name = "Kamer"; why = "rename"; } break;
        case 12: if (r && chance(0.1)) { r->emitter = r->emitter == RoomPlan::Emitter::floor ? RoomPlan::Emitter::radiator : RoomPlan::Emitter::floor; why = "emitter"; } break;
        case 13: { // a write based on an old revision: refused
                    RoomPlan stale = p; stale.revision = p.revision ? p.revision - 1 : 7; stale.minimumFlowC = 31;
                    EXPECT(!applyPlan(stale, "stale_revision") || p.revision == 0, "plan_stale_accepted", "a stale revision was accepted");
                    return; }
        case 14: applyPlan(p, "resend"); return; // unchanged
        default: if (r) { std::reverse(p.rooms.begin(), p.rooms.end()); why = "reorder_rooms"; } break;
    }
    applyPlan(p, why);
}

// ----------------------------------------------------------------------------
// Active-mode phases: plan active, owner disconnects the tado and confirms; the
// tado sometimes comes back (foreign controller), the owner withdraws, etc.
// ----------------------------------------------------------------------------
void Chain::guardPhases() {
    if (!o_.activePhases || now_ < nextPhase_) return;
    switch (phase_) {
        case Phase::shadow: {
            RoomPlan p = engine_.plan(); p.mode = RoomPlan::Mode::active;
            if (applyPlan(p, "mode_active")) { phase_ = Phase::armingOwner; nextPhase_ = now_ + uint64_t(uniformInt(2, 30)) * 60000; count("phase_active"); }
            else nextPhase_ = now_ + 3600000;
            break;
        }
        case Phase::armingOwner:
            if (chance(0.9)) tadoConnected_ = false; // 10 %: the owner confirms but forgot to disconnect
            guard_.confirm(now_, true); confirmedAt_ = now_;
            phase_ = Phase::active; nextPhase_ = now_ + uint64_t(uniformInt(6, 48)) * 3600000;
            if (chance(0.3)) { phaseUntil_ = now_ + uint64_t(uniformInt(1, 5)) * 3600000; } else phaseUntil_ = 0; // tado comes back
            break;
        case Phase::active: case Phase::blockedWait: {
            if (chance(0.3)) { guard_.confirm(now_, false); confirmedAt_.reset(); count("owner_withdraws"); }
            RoomPlan p = engine_.plan(); p.mode = RoomPlan::Mode::shadow;
            applyPlan(p, "mode_shadow");
            confirmedAt_.reset();
            tadoConnected_ = true;
            phase_ = Phase::shadow; nextPhase_ = now_ + uint64_t(expo(4.0 * 86400.0) * 1000) + 6 * 3600000ull;
            break;
        }
    }
}

// ----------------------------------------------------------------------------
// Weather, house, boiler, tado and hot water
// ----------------------------------------------------------------------------
void Chain::weather() {
    const auto l = local(utc_);
    std::tm tm{}; const std::time_t t = utc_; gmtime_r(&t, &tm);
    const double doy = tm.tm_yday, hour = l.hour + l.minute / 60.0;
    const double season = 10 - 7.5 * std::cos(2 * M_PI * (doy - 20) / 365.0);
    const double daily = -3.5 * std::cos(2 * M_PI * (hour - 4) / 24.0);
    weather_ += (-weather_ / (3 * 24 * 360.0)) + uniform(-1, 1) * 0.05; // slow AR(1) drift over days
    weather_ = std::clamp(weather_, -6.0, 6.0);
    if (now_ >= frostUntil_ && chance(1.0 / (12 * 24 * 360.0))) { frostUntil_ = now_ + uint64_t(uniformInt(2, 4)) * 86400000; count("frost_spell"); }
    // One frost spell is guaranteed (day 18..21 of the run) so the frost rules see it.
    const double day = double(utc_ - ctx.startUtc) / 86400.0;
    const bool frost = now_ < frostUntil_ || (day >= 18 && day < 21);
    frostOffset_ += ((frost ? -14.0 : 0.0) - frostOffset_) * 0.0005;
    outdoor_ = season + daily + weather_ + frostOffset_;
}

void Chain::physics(double dtH) {
    const auto l = local(utc_);
    const double hour = l.hour + l.minute / 60.0;
    const bool spaceHeat = boilerSetpoint_ && boilerSetpoint_->flow >= 20 && dhw_ == Dhw::idle; // the pump circulates
    double houseMean = 0;
    for (size_t i = 0; i + 1 < phys_.size(); ++i) houseMean += phys_[i].air;
    houseMean /= double(phys_.size() - 1);
    for (auto& r : phys_) {
        if (!r.floor && r.heated) {
            if (r.air < r.trvSetC - 0.1) r.trvOpen = true;
            else if (r.air > r.trvSetC + 0.3) r.trvOpen = false;
        }
        const bool supply = spaceHeat && r.heated && (r.floor || r.trvOpen);
        const double target = supply ? (r.floor ? r.air + 0.55 * (flow_ - r.air) : flow_) : r.air;
        r.emitter += (target - r.emitter) * std::min(1.0, dtH / (supply ? r.tauE : r.tauE * 2));
        const double sun = (hour > 10 && hour < 16) ? 0.12 * std::sin(M_PI * (hour - 10) / 6) : 0;
        const double window = now_ < r.windowUntil ? 1.2 : 0;
        const double leak = r.heated ? 0 : 0.02 * (houseMean - r.air);
        const double dT = r.a * (r.emitter - r.air) - (r.b + window) * (r.air - outdoor_) + sun + leak + uniform(-0.02, 0.02);
        r.air += dT * dtH;
        if ((r.id == "badkamer" || r.id == "slaapkamer") && now_ >= r.windowUntil && chance(1.0 / (3 * 24 * 360.0))) {
            r.windowUntil = now_ + uint64_t(uniformInt(5, 20)) * 60000; count("window_open");
        }
    }
}

void Chain::tado() {
    if (!tadoConnected_) { tadoHeat_ = false; return; }
    const auto& living = phys_[0];
    const double t = living.air + 0.2;
    const auto target = scheduleOracle(catalog_[0].schedule, utc_).value_or(2000) / 100.0;
    const bool heatBefore = tadoHeat_;
    if (now_ - tadoChangedAt_ >= 600000) {
        if (!tadoHeat_ && t < target - 0.15) tadoHeat_ = true;
        else if (tadoHeat_ && t > target + 0.05) tadoHeat_ = false;
    }
    if (tadoHeat_ != heatBefore) {
        tadoChangedAt_ = now_;
        if (tadoHeat_) { // one flow per heating period: heating curve plus the tado's own offset
            const double curve = 31 + std::max(0.0, 15 - outdoor_) * 0.6 + double(uniformInt(-1, 2)) * 2;
            tadoPeriodFlow_ = uint8_t(std::clamp(curve, 31.0, 43.0));
        }
    }
    if (tadoHeat_ && chance(0.0005)) tadoPeriodFlow_ = uint8_t(std::clamp<int>(tadoPeriodFlow_ + int(uniformInt(-1, 1)), 31, 43));
    tadoFlow_ = tadoHeat_ ? tadoPeriodFlow_ : 0;
}

void Chain::dhwGenerator() {
    if (dhw_ != Dhw::idle) {
        if (now_ >= dhwUntil_) {
            // The episode ends at the last report with the DHW bit (this step's 0x18 is idle again).
            const int kind = dhw_ == Dhw::tap ? 0 : 1; // DhwEpisodes::tapping / keepWarm
            const int32_t day = clockKnown_ ? localDayIndex(utc_) : INT32_MIN;
            if (day != INT32_MIN) {
                auto& d = dhwOracle_[day];
                ++d.count[size_t(kind)];
                d.seconds[size_t(kind)] += uint32_t((now_ - dhwStartedAt_) / 1000);
            } else dhwOracleValid_ = false;
            dhw_ = Dhw::idle; dhwFlowTenths_ = o_.liveDhwFlow ? 0 : 25;
            count(kind == 0 ? "dhw_tap" : "dhw_keep_warm");
        }
        return;
    }
    if (now_ < busDownUntil_ + 120000) return; // episodes only with the bus up (exact oracle)
    if (!dhwNextTap_) dhwNextTap_ = now_ + uint64_t(expo(3.0 * 3600) * 1000);
    if (now_ >= dhwNextTap_ && dhwTemp_ >= 28) {
        dhw_ = Dhw::tap; dhwStartedAt_ = now_; dhwUntil_ = now_ + uint64_t(uniformInt(6, 48)) * 10000;
        dhwTapMin_ = std::min(dhwTemp_ - 11, uniform(12, 35)); // owner logs: taps fell 9-46 K
        dhwFlowTenths_ = o_.liveDhwFlow ? uint8_t(uniformInt(30, 95)) : 25;
        dhwNextTap_ = now_ + uint64_t(expo(2.5 * 3600) * 1000) + 600000;
    } else if (dhwTemp_ < 39 && now_ + 600000 < dhwNextTap_) {
        dhw_ = Dhw::keepWarm; dhwStartedAt_ = now_; dhwUntil_ = now_ + uint64_t(uniformInt(9, 24)) * 10000;
        dhwFlowTenths_ = o_.liveDhwFlow ? 0 : 25;
    }
}

void Chain::boiler(double dtH) {
    // Who asks: the latest 0x1A (tado or E32); a setpoint older than 10 min lapses.
    if (boilerSetpoint_ && now_ - boilerSetpoint_->at > 600000) boilerSetpoint_.reset();
    const uint8_t requested = boilerSetpoint_ ? boilerSetpoint_->flow : 0;
    if (dhw_ != Dhw::idle) {
        burner_ = true; modulation_ = dhw_ == Dhw::tap ? 90 : 45;
        flow_ += (65 - flow_) * std::min(1.0, dtH / 0.05);
        if (dhw_ == Dhw::tap) dhwTemp_ += (dhwTapMin_ - dhwTemp_) * std::min(1.0, dtH / 0.004);
        else dhwTemp_ += (52 - dhwTemp_) * std::min(1.0, dtH / 0.03);
    } else if (requested >= 20) {
        double load = 0;
        for (const auto& r : phys_) if (r.heated && (r.floor || r.trvOpen)) load += r.floor ? 0.25 : 0.1;
        const int wanted = int(std::clamp(load * 100 * std::max(0.2, (requested - 25) / 20.0), 0.0, 100.0));
        if (wanted < 20) { // below the minimum modulation: on/off cycling around the request
            if (!cyclingOff_ && flow_ > requested + 5) cyclingOff_ = true;
            else if (cyclingOff_ && flow_ < requested - 5) cyclingOff_ = false;
        } else cyclingOff_ = false;
        burner_ = !cyclingOff_;
        modulation_ = burner_ ? uint8_t(std::max(20, wanted)) : 0;
        flow_ += burner_ ? (requested + 2 - flow_) * std::min(1.0, dtH / 0.05) : (phys_[0].air + 5 - flow_) * std::min(1.0, dtH / 0.15);
        dhwTemp_ += (20 - dhwTemp_) * dtH / 30.0;
    } else {
        burner_ = false; modulation_ = 0; cyclingOff_ = false;
        flow_ += (phys_[0].air + 2 - flow_) * std::min(1.0, dtH / 0.5);
        dhwTemp_ += (20 - dhwTemp_) * dtH / 30.0;
    }
    if (dhw_ == Dhw::idle && dhwTemp_ > 50.5) dhwTemp_ -= 0.5 * dtH;
    gasM3_ += modulation_ / 100.0 * trueNominalKw_ * dtH / 9.77;
}

void Chain::emitTelegrams() {
    if (now_ < busDownUntil_) return;
    if (dhw_ == Dhw::idle && chance(1.0 / (2 * 24 * 360.0))) { busDownUntil_ = now_ + uint64_t(uniformInt(7, 30)) * 10000; count("bus_dropout"); return; }
    const uint64_t at34 = now_ - 5000, at18 = now_;
    // 0x34 UBAMonitorWW: DHW temperature and flow.
    std::vector<uint8_t> ww(16, 0);
    ww[0] = 55; putWord(ww, 1, int(std::lround(dhwTemp_ * 10))); putWord(ww, 3, 0x8000); ww[8] = 2; ww[9] = dhwFlowTenths_;
    const auto unixAt = [&](uint64_t at) { return clockKnown_ ? std::optional<uint32_t>(uint32_t(utc_ - int64_t((now_ - at) / 1000))) : std::nullopt; };
    monitor_.receive(telegram(0x34, ww), at34);
    dhwEpisodes_.observe(monitor_, at34, unixAt(at34));
    // 0x18 UBAMonitorFast: flow, modulation, state (flame, DHW), return.
    std::vector<uint8_t> fast(22, 0);
    fast[0] = boilerSetpoint_ ? boilerSetpoint_->flow : 0;
    putWord(fast, 1, int(std::lround(flow_ * 10)));
    fast[3] = 100; fast[4] = modulation_;
    const bool heating = boilerSetpoint_ && boilerSetpoint_->flow >= 20;
    fast[5] = uint8_t((burner_ ? 0x08 : 0) | (dhw_ != Dhw::idle ? 0x02 : 0) | (heating ? 0x01 : 0));
    putWord(fast, 9, 0x8000); putWord(fast, 11, 0x8000);
    putWord(fast, 13, int(std::lround((flow_ - (burner_ ? 6 : 2)) * 10)));
    putWord(fast, 15, 0x7D00); fast[17] = 15; fast[18] = '-'; fast[19] = 'H';
    monitor_.receive(telegram(0x18, fast), at18);
    cycles_.observe(monitor_, at18);
    dhwEpisodes_.observe(monitor_, at18, unixAt(at18));
    // Burner cycle oracle: edges between consecutive reports.
    const bool on = burner_;
    if (lastReportedOn_ && on && !*lastReportedOn_) burnerRuns_.push_back({at18, dhw_ != Dhw::idle});
    else if (lastReportedOn_ && on && *lastReportedOn_ && !burnerRuns_.empty() && dhw_ != Dhw::idle) burnerRuns_.back().dhw = true;
    lastReportedOn_ = on; lastReportAt_ = at18;
    while (!burnerRuns_.empty() && at18 - burnerRuns_.front().start >= 2 * BurnerCycleMonitor::windowMs) burnerRuns_.pop_front();
    // 0x16 UBAParameters every 5 min: the heating limit (sometimes 25 or unknown).
    if ((now_ / 10000) % 30 == 0) {
        if (chance(0.02)) boilerLimit_ = chance(0.5) ? std::optional<uint8_t>() : std::optional<uint8_t>(uint8_t(chance(0.3) ? 25 : chance(0.5) ? 55 : 75));
        else if (chance(0.1)) boilerLimit_ = uint8_t(60);
        if (boilerLimit_) {
            std::vector<uint8_t> par(12, 0);
            par[0] = 0xFF; par[1] = *boilerLimit_; par[2] = 100; par[4] = 0xFB; par[5] = 5; par[6] = 10; par[9] = 100; par[10] = 30;
            monitor_.receive(telegram(0x16, par), now_ - 2000);
        }
    }
    if (o_.boilerOutdoor) {
        std::vector<uint8_t> slow(27, 0);
        putWord(slow, 0, int(std::lround(outdoor_ * 10))); putWord(slow, 2, int(std::lround(flow_ * 10))); putWord(slow, 4, 0x8000);
        monitor_.receive(telegram(0x19, slow), now_ - 3000);
    }
    // The tado's 0x1A every 60 s (and at once on a change), while connected.
    if (tadoConnected_ && (now_ >= tadoNext1A_ || (tadoLast1A_ && tadoLast1A_->first != tadoFlow_))) {
        const uint64_t at = now_ - 1000;
        const auto t = telegram(0x1A, {tadoFlow_, 0, 0, 0}, 0x17, 0x08, ems::EmsTelegram::WRITE);
        foreign_.observe(t, at);
        tadoLast1A_ = std::make_pair(tadoFlow_, at);
        boilerSetpoint_ = Setpoint{0x17, tadoFlow_, at};
        tadoNext1A_ = now_ + 60000;
    }
}

// ----------------------------------------------------------------------------
// Home Assistant: ha/heating_input on change and every 5 min; outages; junk.
// ----------------------------------------------------------------------------
void Chain::haSend(const std::string& payload, bool expectAccepted) {
    const bool accepted = haRoute_.accept(payload, now_, engine_, learner_);
    EXPECT(accepted == expectAccepted, "ha_input_acceptance", "payload %s accepted=%d", payload.c_str(), int(accepted));
    count(accepted ? "ha_accepted" : "ha_rejected");
    if (!accepted) return;
    // Oracle: what RoomEngine::haState() must have recorded.
    const auto in = HeatingInput::parse(payload);
    if (!in || in->kind != HeatingInput::Kind::room) return;
    for (const auto& room : engine_.plan().rooms) {
        auto& o = oracle_[room.id];
        for (const auto& s : room.sources)
            if (s.type == RoomPlan::SourceType::ha && s.id == in->entity) o.readings[{int(s.type), s.id}] = {in->temperatureCentiC, now_};
        if (!room.setpointEntity.empty() && room.setpointEntity == in->entity && in->targetCentiC) { o.target = in->targetCentiC; o.targetAt = now_; }
    }
}
void Chain::haMessages() {
    if (!haNextOutage_) haNextOutage_ = now_ + uint64_t(expo(4 * 86400.0) * 1000);
    if (now_ >= haNextOutage_) { haDownUntil_ = now_ + uint64_t(uniformInt(1800, 6 * 3600)) * 1000; haNextOutage_ = haDownUntil_ + uint64_t(expo(4 * 86400.0) * 1000); count("ha_outage"); }
    if (now_ < haDownUntil_) return;
    struct Entity { const char* id; int room; bool target; double offset; };
    static const Entity entities[] = {{"climate.woonkamer", 0, true, 0.2}, {"sensor.keuken_temperatuur", 1, false, -0.1},
        {"sensor.kinderkamer_temperatuur", 3, false, 0.1}, {"sensor.badkamer_temperatuur", 4, false, 0.0},
        {"climate.badkamer_trv", 4, true, 0.4}, {"sensor.zolder_temperatuur", 7, false, 0.0}};
    for (const auto& e : entities) {
        const double t = std::round((phys_[size_t(e.room)].air + e.offset) * (e.target ? 10 : 100)) / (e.target ? 10 : 100);
        double target = 0;
        if (e.target) target = (e.room == 0 ? scheduleOracle(catalog_[0].schedule, utc_).value_or(2000) : (phys_[4].trvSetC * 100)) / 100.0;
        auto& next = haNext_[e.id];
        auto& sent = haSent_[e.id];
        const bool changed = std::fabs(sent.first - t) >= 0.1 || sent.second != target;
        if (now_ < next && !(changed && now_ + 270000 >= next)) continue;
        char payload[200];
        if (e.target) std::snprintf(payload, sizeof payload, R"({"entity":"%s","temperature":%.1f,"target":%.1f})", e.id, t, target);
        else std::snprintf(payload, sizeof payload, R"({"entity":"%s","temperature":%.2f})", e.id, t);
        if (chance(0.003)) std::snprintf(payload, sizeof payload, R"({"entity":"%s","temperature":null})", e.id); // unavailable
        haSend(payload, true);
        sent = {t, target};
        next = now_ + 300000 + uint64_t(uniformInt(-20000, 20000));
    }
    if (now_ >= gasNext_) {
        char payload[160]; std::snprintf(payload, sizeof payload, R"({"kind":"gas_m3","entity":"sensor.gas_meter","value":%.3f})", gasM3_);
        haSend(payload, true); gasNext_ = now_ + 3600000 + uint64_t(uniformInt(-30000, 30000));
    }
    if (now_ >= priceNext_) { haSend(R"({"kind":"gas_price","value":1.32})", true); priceNext_ = now_ + 86400000; }
    if (!boilerKwSent_) { haSend(R"({"kind":"boiler_kw","value":22})", true); haSend(R"({"kind":"gas_kwh_per_m3","value":9.77})", true); boilerKwSent_ = true; }
    if (!o_.boilerOutdoor && now_ >= outdoorNext_) {
        char payload[160]; std::snprintf(payload, sizeof payload, R"({"kind":"outdoor_c","entity":"sensor.outdoor","value":%.1f})", outdoor_);
        haSend(payload, true); outdoorNext_ = now_ + 300000;
    }
    if (chance(0.0005)) { // junk on the topic: always ignored
        static const char* junk[] = {"", "{", "[]", "null", R"({"kind":"gas_price","value":0})", R"({"kind":"outdoor_c","value":5})",
            R"({"kind":"boiler_kw","value":1e9})", R"({"entity":""})", R"({"kind":42,"value":1})", R"({"kind":"gas_m3","entity":"sensor.gas","value":"12"})"};
        haSend(junk[uniformInt(0, 9)], false);
        std::string deep(300, '['); haSend(deep, false);
        std::string nested = R"({"entity":"climate.woonkamer","x":)" + std::string(5, '[') + std::string(5, ']') + "}";
        haSend(nested, false);
    }
}

// ----------------------------------------------------------------------------
// Bluetooth: pvvx adverts every 30 s with faults (counter resets, bad frames,
// replays, downgrades, queue bursts, clock faults, silence).
// ----------------------------------------------------------------------------
void Chain::bleAdverts() {
    bleClockNow = now_;
    const bool stalled = now_ < stallUntil_;
    if (!stalled) for (size_t i = 0; i < ManagedBleObserver<SoakCrypto>::queueCapacity; ++i) ble_->processOne(); // what queued during a stall
    for (auto& s : sensors_) {
        if (now_ >= s.silentUntil && chance(1.0 / (6 * 24 * 360.0))) { s.silentUntil = now_ + uint64_t(uniformInt(20, 90)) * 60000; count("ble_silence"); }
        while (s.nextAt <= now_) {
            const uint64_t at = s.nextAt;
            s.nextAt += s.periodMs + uint64_t(uniformInt(0, 2000));
            if (at < s.silentUntil) continue;
            const double temp = phys_[size_t(s.room)].air + s.offset + uniform(-0.02, 0.02);
            int16_t centi = int16_t(std::lround(temp * 100));
            if (!s.centi) centi = int16_t(std::lround(temp * 10) * 10);
            if (s.encrypted && chance(1.0 / (8 * 24 * 120.0))) { s.counter = uint32_t(uniformInt(0, 20)); s.resetAt = at; s.resetPending = true; count("ble_counter_reset"); }
            ++s.counter; ++s.packet;
            const auto objects = thermometerObjects(centi, s.centi, 87, 5523, s.packet);
            std::vector<uint8_t> frame = bthomeAdvert(s.address, objects, s.encrypted, s.counter, s.key);
            bool good = true;
            uint64_t stamp = at;
            const double fault = uniform(0, 1);
            if (fault < 0.002) { frame.assign(size_t(uniformInt(1, 40)), 0); for (auto& b : frame) b = uint8_t(uniformInt(0, 255)); good = false; count("ble_garbage"); }
            else if (fault < 0.004) { frame[3] = uint8_t(frame[3] + 7); good = false; count("ble_truncated"); }        // AD length past the end
            else if (fault < 0.006) { frame = bthomeAdvert(s.address, thermometerObjects(9000, false, 87, 5523, s.packet), s.encrypted, s.counter, s.key); good = false; count("ble_out_of_range"); }
            else if (fault < 0.008) { auto o = objects; o.push_back(0x77); o.push_back(1); frame = bthomeAdvert(s.address, o, s.encrypted, s.counter, s.key); good = false; count("ble_unknown_object"); }
            else if (fault < 0.010 && s.encrypted) { frame = bthomeAdvert(s.address, thermometerObjects(6660, false, 87, 5523, s.packet), true, s.counter + 5, s.key, true); good = false; count("ble_forged"); }
            else if (fault < 0.012 && s.encrypted) { frame = bthomeAdvert(s.address, thermometerObjects(5550, false, 87, 5523, s.packet), false, 0, s.key); good = false; count("ble_downgrade"); }
            else if (fault < 0.014 && s.encrypted && !s.lastEncryptedFrame.empty()) { frame = s.lastEncryptedFrame; good = false; count("ble_replay"); }
            else if (fault < 0.016) { auto f2 = frame; f2.insert(f2.end(), frame.begin() + 3, frame.end()); frame = f2; good = false; count("ble_duplicate_service"); }
            else if (fault < 0.0165) { stamp = now_ + 5; good = false; s.faultAt = now_; for (auto& x : sensors_) x.faultAt = now_; count("ble_future_stamp"); }
            else if (fault < 0.0170) { bleClockRollback = 1; for (auto& x : sensors_) x.faultAt = now_; count("ble_clock_rollback"); }
            else if (fault < 0.0175) { // event-only advert in between (reed contact): ignored
                frame = bthomeAdvert(s.address, {0x2d, 1}, s.encrypted, s.counter, s.key); good = false; count("ble_event_only"); }
            if (good) s.good.emplace_back(stamp, centi); // eligible (after a counter reset: once re-anchored)
            if (const char* dbg = std::getenv("SOAK_DEBUG_BLE")) if (s.hex == dbg) {
                const auto snap = ble_->snapshot(s.address);
                std::fprintf(stderr, "BLE %s at %" PRIu64 " stamp %" PRIu64 " counter %u centi %d good %d stalled %d fault %.4f reset %d | snap t=%d age=%u counter=%u resets=%u drops=%u\n",
                    s.hex.c_str(), at, stamp, s.counter, centi, int(good), int(stalled), fault, int(s.resetPending), snap.temperature.value_or(-1),
                    snap.temperatureAgeMs.value_or(0), snap.counter.value_or(0), snap.counterResets, snap.oldCounterDrops);
            }
            const int copies = chance(0.003) ? 6 : 1; // a burst overflows the 4-frame queue
            if (copies > 1) { s.burstAt = now_; count("ble_burst"); }
            for (int c = 0; c < copies; ++c) EXPECT(ble_->capture(s.address, -70, frame.data(), frame.size(), stamp), "ble_capture_bound", "bound sensor not captured");
            if (!stalled) for (int c = 0; c < copies; ++c) ble_->processOne();
            // Replays are built only from frames the observer accepted (a frame it dropped would be news to it).
            if (good && s.encrypted && !stalled) { const auto snap = ble_->snapshot(s.address); if (snap.counter == s.counter) s.lastEncryptedFrame = frame; }
        }
        while (!s.good.empty() && now_ - std::min(now_, s.good.front().first) > 1200000) s.good.pop_front();
    }
    // Foreign advert: never captured.
    const ManagedBleAddress other{0xa4, 0xc1, 0x38, 0x00, 0x00, 0x99};
    const auto f = bthomeAdvert(other, thermometerObjects(2000, true, 50, 5000, 1), false, 0, {});
    EXPECT(!ble_->capture(other, -80, f.data(), f.size(), now_), "ble_foreign_captured", "unbound address captured");
}

void Chain::checkBle() {
    for (auto& s : sensors_) {
        const auto snap = ble_->snapshot(s.address);
        if (snap.temperature) {
            EXPECT(snap.temperatureAgeMs && *snap.temperatureAgeMs < ManagedBleObserver<SoakCrypto>::valueLifetimeMs, "ble_age", "age missing or beyond lifetime");
            const uint64_t at = snap.temperatureAgeMs ? now_ - *snap.temperatureAgeMs : 0;
            bool found = false;
            for (const auto& g : s.good) if (g.first == at && g.second == *snap.temperature) { found = true; break; }
            EXPECT(found, "ble_value_not_from_good_frame", "%s reports %d at %" PRIu64 " that no good frame carried", s.hex.c_str(), *snap.temperature, at);
            if (s.resetPending && at >= s.resetAt) { // only a re-anchored counter lets a newer frame in
                s.resetPending = false;
                const uint64_t took = at - s.resetAt;
                counters[ctx.scenario + ":ble_reanchor_max_s"] = std::max<uint64_t>(counters[ctx.scenario + ":ble_reanchor_max_s"], took / 1000);
            }
            s.lastAcceptedSeenAt = std::max(s.lastAcceptedSeenAt, at);
        }
        // Liveness: a sensor that keeps sending good frames is never left behind.
        const uint64_t quietFrom = std::max({s.silentUntil, s.faultAt + 3 * uint64_t(s.periodMs), s.burstAt + 3 * uint64_t(s.periodMs), bootMs_ + 120000,
                                             stallUntil_ + 3 * uint64_t(s.periodMs)});
        const uint64_t resetWindow = ManagedBleObserver<SoakCrypto>::reanchorQuietMs + 5 * uint64_t(s.periodMs) + 60000;
        if (s.resetPending && now_ - s.resetAt > resetWindow)
            fail("ble_counter_reset_hang", "%s: no reading accepted %" PRIu64 " s after its counter restarted", s.hex.c_str(), (now_ - s.resetAt) / 1000);
        if (!s.resetPending && now_ > quietFrom + 3 * uint64_t(s.periodMs) && now_ >= s.silentUntil + 3 * uint64_t(s.periodMs) && now_ - s.resetAt > resetWindow) {
            const bool fresh = snap.temperature && snap.temperatureAgeMs && *snap.temperatureAgeMs <= 5 * uint64_t(s.periodMs) + 10000;
            EXPECT(fresh, "ble_reading_not_refreshed", "%s: status %d, age %s ms", s.hex.c_str(), int(snap.status),
                   snap.temperatureAgeMs ? std::to_string(*snap.temperatureAgeMs).c_str() : "none");
        }
        if (s.havePrev) {
            EXPECT(snap.framesReceived >= s.prev.framesReceived && snap.framesRejected >= s.prev.framesRejected
                   && snap.oldCounterDrops >= s.prev.oldCounterDrops && snap.counterResets >= s.prev.counterResets
                   && snap.framesIgnored >= s.prev.framesIgnored, "ble_counters_monotonic", "%s counters went back", s.hex.c_str());
        }
        s.prev = snap; s.havePrev = true;
    }
}

// ----------------------------------------------------------------------------
// One 10 s step of HeatingController::stepHeating() and the checks around it.
// ----------------------------------------------------------------------------
void Chain::stepE32() {
    // Bluetooth sources into the engine (HeatingController::stepHeating).
    for (const auto& room : engine_.plan().rooms)
        for (const auto& source : room.sources) {
            ManagedBleAddress address{};
            if (source.type != RoomPlan::SourceType::ble || !parseBleHex(source.id, address)) continue;
            const auto snapshot = ble_->snapshot(address);
            if (snapshot.temperature && snapshot.temperatureAgeMs && *snapshot.temperatureAgeMs <= now_) {
                const uint64_t at = now_ - *snapshot.temperatureAgeMs;
                engine_.bleReading(source.id, snapshot.temperature, at);
                for (auto& [id, o] : oracle_) {
                    const auto* pr = engine_.plan().find(id);
                    for (const auto& s : pr->sources) if (s.type == RoomPlan::SourceType::ble && s.id == source.id) o.readings[{int(s.type), s.id}] = {snapshot.temperature, at};
                }
            }
        }
    const std::optional<uint32_t> unixNow = clockKnown_ ? std::optional<uint32_t>(uint32_t(utc_)) : std::nullopt;
    const uint64_t calls0 = localtimeCalls;
    const auto request = engine_.step(now_, unixNow);
    noteLocaltime("room_engine_step", localtimeCalls - calls0, utc_);
    const auto tadoFlowC = tadoLast1A_ && now_ - tadoLast1A_->second <= 150000 ? std::optional<uint8_t>(tadoLast1A_->first) : std::nullopt;
    shadow_.sample(now_, unixNow, request, tadoFlowC);
    // The EMS view (EmsController::activeHeatView).
    const auto modulation = monitor_.value(ems::BoilerField::modulation, now_);
    const auto flow = monitor_.value(ems::BoilerField::flow, now_);
    const auto state = monitor_.value(ems::BoilerField::rawState, now_);
    const auto ret = monitor_.value(ems::BoilerField::returnTemp, now_);
    const std::optional<bool> burnerOn = modulation ? std::optional<bool>(*modulation > 0) : std::nullopt;
    const std::optional<int16_t> flowCentiC = flow ? std::optional<int16_t>(int16_t(*flow)) : std::nullopt;
    const auto outdoorView = haRoute_.outdoor(monitor_.value(ems::BoilerField::outdoor, now_) ? std::optional<int16_t>(int16_t(*monitor_.value(ems::BoilerField::outdoor, now_))) : std::nullopt, now_);
    FlowLearner::Boiler boiler{flowCentiC, burnerOn, state ? std::optional<bool>((*state & 0x02) != 0) : std::nullopt, tadoFlowC,
        outdoorView.centiC, modulation && *modulation >= 0 && *modulation <= 100 ? std::optional<uint8_t>(uint8_t(*modulation)) : std::nullopt,
        ret ? std::optional<int16_t>(int16_t(*ret)) : std::nullopt};
    std::array<FlowLearner::RoomInput, RoomPlan::maxRooms> rooms{};
    const auto& plan = engine_.plan();
    for (size_t i = 0; i < plan.rooms.size(); ++i) {
        const auto fresh = engine_.fresh(i, now_);
        rooms[i] = {fresh.temperature, engine_.result(i).setpoint, fresh.source};
    }
    learner_.sample(now_, boiler, rooms.data(), plan.rooms.size());
    checkEngine(request);
    checkShadow(request, tadoFlowC);

    // ActiveHeatGuard (HeatingController::stepActiveHeat): last step's post is reported first.
    if (lastPost_) {
        const bool ok = routeReady_ && chance(0.95);
        guard_.transmitted(lastPost_->second, ok);
        if (ok) {
            boilerSetpoint_ = Setpoint{0x0b, lastPost_->first, lastPost_->second + 500};
            count("e32_1a_sent");
        } else count("e32_1a_failed");
    }
    lastPost_.reset();
    if (chance(0.0005)) { routeReady_ = !routeReady_; count("route_flap"); }
    if (!routeReady_ && chance(0.01)) routeReady_ = true;
    ActiveHeatGuard::Inputs in;
    in.mode = plan.mode;
    in.request = request;
    for (size_t i = 0; i < plan.rooms.size(); ++i) { in.rooms.add(engine_.result(i)); in.rooms.measured(engine_.freshTemperature(i, now_)); }
    if (foreign_.last) in.foreign = ActiveHeatGuard::Foreign{foreign_.last->address, foreign_.last->receivedAtMs};
    in.uptimeMs = now_ - bootMs_; in.routeReady = routeReady_; in.boilerLimitC = ems::ActiveHeatEnvelope::limitC(monitor_);
    in.boiler = {burnerOn, flowCentiC};
    guard_.setFlowLimits(plan.minimumFlowC, plan.maximumFlowC);
    const bool claimedBefore = guard_.claimsBoiler();
    const auto c = guard_.step(now_, in);
    if (c.send) lastPost_ = std::make_pair(c.flowC, now_);
    // Guard invariants.
    const uint8_t cap = std::min<uint8_t>({plan.maximumFlowC, ActiveHeatGuard::hardMaximumFlowC, in.boilerLimitC.value_or(0)});
    const bool foreignAfterConfirm = confirmedAt_ && foreign_.last && foreign_.last->receivedAtMs > *confirmedAt_;
    if (c.send && c.flowC) {
        EXPECT(plan.mode == RoomPlan::Mode::active, "guard_heat_in_shadow", "positive %u in shadow mode", c.flowC);
        EXPECT(guard_.confirmed() && confirmedAt_, "guard_heat_unconfirmed", "positive %u without confirmation", c.flowC);
        EXPECT(!foreignAfterConfirm, "guard_heat_with_foreign", "positive %u while a foreign 0x1A followed the confirmation", c.flowC);
        EXPECT(routeReady_, "guard_send_route_not_ready", "send with the route not ready");
        EXPECT(c.flowC <= cap, "guard_flow_above_cap", "flow %u > cap %u (plan max %u, limit %s)", c.flowC, cap, plan.maximumFlowC,
               in.boilerLimitC ? std::to_string(*in.boilerLimitC).c_str() : "unknown");
        if (cap >= plan.minimumFlowC) EXPECT(c.flowC >= plan.minimumFlowC, "guard_flow_below_min", "flow %u < plan min %u", c.flowC, plan.minimumFlowC);
        else { count("guard_flow_below_plan_min_by_boiler_limit"); observe("guard_flow_below_plan_min_by_boiler_limit", "boiler limit " + std::to_string(cap) + " below the plan minimum " + std::to_string(plan.minimumFlowC) + ": the guard sends the boiler limit"); }
    }
    if (guard_.owning()) {
        ++activeOwningS_;
        // Frost: any fresh room below 8 degC (also inactive ones) gets at least the minimum flow.
        std::optional<int16_t> coldest;
        for (size_t i = 0; i < plan.rooms.size(); ++i) if (const auto t = engine_.freshTemperature(i, now_)) coldest = coldest ? std::min(*coldest, *t) : *t;
        if (coldest && *coldest < 800 && cap) {
            EXPECT(guard_.command().flowC >= std::min(plan.minimumFlowC, cap), "guard_frost_rule", "coldest %d, flow %u", *coldest, guard_.command().flowC);
            count("guard_frost_steps");
        }
        if (const auto i = std::find_if(plan.rooms.begin(), plan.rooms.end(), [](const RoomPlan::Room& r) { return r.id == "woonkamer"; }); i != plan.rooms.end()) {
            const auto sp = engine_.result(size_t(i - plan.rooms.begin())).setpoint;
            if (sp && std::fabs(phys_[0].air * 100 - *sp) > 150) ++comfortOutS_;
        }
    }
    if (claimedBefore && !guard_.claimsBoiler() && boilerSetpoint_ && boilerSetpoint_->from == 0x0b && boilerSetpoint_->flow > 0)
        fail("guard_released_with_positive_at_boiler", "the guard left %s while the boiler still holds the E32's %u degC (no zero delivered)",
             ActiveHeatGuard::name(guard_.state()), boilerSetpoint_->flow);
    if (guard_.state() == ActiveHeatGuard::State::blockedForeignController && phase_ == Phase::active) {
        count("guard_blocked_foreign");
        phase_ = Phase::blockedWait; nextPhase_ = now_ + uint64_t(uniformInt(30, 120)) * 60000;
    }
    if (phase_ == Phase::active && phaseUntil_ && now_ >= phaseUntil_) { tadoConnected_ = true; phaseUntil_ = 0; count("tado_reconnected"); }
}

void Chain::checkEngine(const FlowDemand::Request& request) {
    const auto& plan = engine_.plan();
    // FlowDemand: within the plan's limits; minimum on/off times.
    if (request.heat) EXPECT(request.flowC >= plan.minimumFlowC && request.flowC <= plan.maximumFlowC && request.flowC <= ActiveHeatGuard::hardMaximumFlowC,
                             "flow_request_out_of_limits", "flow %u outside [%u, %u]", request.flowC, plan.minimumFlowC, plan.maximumFlowC);
    else EXPECT(request.flowC == 0, "flow_request_off_nonzero", "off with flow %u", request.flowC);
    if (prevRequest_ && request.heat != prevRequest_->heat && now_ - flowRebuiltAt_ > 20000) {
        if (request.heat) {
            if (haveHeatEdge_) EXPECT(now_ - lastHeatOff_ >= 300000, "flow_minimum_off", "restart after %" PRIu64 " s off", (now_ - lastHeatOff_) / 1000);
            lastHeatOn_ = now_;
        } else {
            if (request.reason == FlowDemand::Reason::satisfied && haveHeatEdge_)
                EXPECT(now_ - lastHeatOn_ >= 300000, "flow_minimum_on", "stopped after %" PRIu64 " s on", (now_ - lastHeatOn_) / 1000);
            lastHeatOff_ = now_; haveHeatEdge_ = true;
        }
    }
    prevRequest_ = request;
    // RoomDemand / RoomEngine against the oracle.
    bool anyUsable = false;
    for (size_t i = 0; i < plan.rooms.size(); ++i) {
        const auto& room = plan.rooms[i];
        auto& o = oracle_[room.id];
        const auto& r = engine_.result(i);
        const bool pauseEnded = room.inactiveUntil && clockKnown_ && uint32_t(utc_) >= room.inactiveUntil;
        const bool active = room.state == RoomDemand::State::active || pauseEnded;
        if (!active) {
            EXPECT(r.status == RoomDemand::Status::inactive && !r.usable && r.source < 0, "room_inactive", "%s inactive but status %s", room.id.c_str(), RoomDemand::name(r.status));
            o.lead.reset(); // the engine's result has no leading source while inactive
            continue;
        }
        int lead = -1;
        std::optional<int16_t> temperature;
        for (size_t s = 0; s < room.sources.size(); ++s) {
            const auto it = o.readings.find({int(room.sources[s].type), room.sources[s].id});
            if (it == o.readings.end()) continue;
            const auto& rd = it->second;
            if (!rd.centiC || rd.atMs > now_ || now_ - rd.atMs > 900000) continue;
            lead = int(s); temperature = rd.centiC; break;
        }
        RoomDemand::Status status;
        if (lead >= 0) { status = lead == 0 ? RoomDemand::Status::ok : RoomDemand::Status::fallback; o.lead = std::make_pair(int(room.sources[size_t(lead)].type), room.sources[size_t(lead)].id); o.lastUsable = o.readings[*o.lead]; }
        else {
            const bool held = o.lastUsable.centiC && o.lastUsable.atMs <= now_ && now_ - o.lastUsable.atMs < 1800000;
            status = held ? RoomDemand::Status::stale : RoomDemand::Status::lost;
            if (held) temperature = o.lastUsable.centiC;
            o.lead.reset();
        }
        std::optional<int16_t> setpoint;
        if (o.target && o.targetAt <= now_ && now_ - o.targetAt < RoomEngine::setpointMaxAgeMs) setpoint = o.target;
        else if (clockKnown_ && !room.schedule.empty()) setpoint = scheduleOracle(room.schedule, utc_);
        else setpoint = room.fallbackCentiC;
        if (setpoint) setpoint = std::clamp(*setpoint, room.minimumCentiC, room.maximumCentiC);
        EXPECT(r.status == status, "room_status", "%s: status %s, expected %s", room.id.c_str(), RoomDemand::name(r.status), RoomDemand::name(status));
        EXPECT(r.source == lead, "room_lead_source", "%s: lead %d, expected %d", room.id.c_str(), r.source, lead);
        EXPECT(r.temperature == temperature, "room_temperature", "%s: temperature %d, expected %d", room.id.c_str(), r.temperature.value_or(-9999), temperature.value_or(-9999));
        EXPECT(r.setpoint == setpoint, "room_setpoint", "%s: setpoint %d, expected %d", room.id.c_str(), r.setpoint.value_or(-9999), setpoint.value_or(-9999));
        anyUsable = anyUsable || (status != RoomDemand::Status::lost && setpoint);
    }
    EXPECT((request.reason == FlowDemand::Reason::noDemand) == !anyUsable, "flow_no_demand", "reason %s with %s usable room", FlowDemand::name(request.reason), anyUsable ? "a" : "no");
    // The week program's local time against the C library (every step).
    if (clockKnown_) {
        const auto t = RoomSchedule::localAt(utc_);
        const auto l = local(utc_);
        EXPECT(t.weekday == (l.wday + 6) % 7 && t.minute == l.hour * 60 + l.minute, "schedule_local_time",
               "localAt %u/%u, libc %d/%d", t.weekday, t.minute, (l.wday + 6) % 7, l.hour * 60 + l.minute);
    }
}

void Chain::checkShadow(const FlowDemand::Request& request, std::optional<uint8_t> tadoFlowC) {
    const auto& today = shadow_.today();
    if (clockKnown_) {
        const int32_t day = localDayIndex(utc_);
        if (firstKnownDay_ == INT32_MIN) firstKnownDay_ = day;
        EXPECT(today.day == day, "shadow_day", "shadow day %d, local day %d", today.day, day);
        EXPECT(dhwEpisodes_.today().day == day || now_ < busDownUntil_ + 20000, "dhw_day", "dhw day %d, local day %d", dhwEpisodes_.today().day, day);
        EXPECT(RoomSchedule::localDay(utc_) == day, "schedule_local_day", "RoomSchedule::localDay %d, libc %d", RoomSchedule::localDay(utc_), day);
        const uint32_t credit = haveShadowAt_ ? uint32_t(std::min<uint64_t>(now_ - lastShadowAt_, ShadowComparison::maxCreditMs) / 1000) : 0;
        daySeconds_[day] += credit;
        if (request.heat) dayE32HeatS_[day] += credit;
        if (prevE32Heat_ && request.heat && !*prevE32Heat_) ++dayE32Starts_[day];
        const bool tHeat = tadoFlowC && *tadoFlowC >= ShadowComparison::tadoHeatFromC;
        if (tadoFlowC && prevTadoHeat_ && tHeat && !*prevTadoHeat_) ++dayTadoStarts_[day];
        if (day == today.day && day != firstKnownDay_) {
            EXPECT(today.s == daySeconds_[day], "shadow_seconds", "today s %u, oracle %u", today.s, daySeconds_[day]);
            EXPECT(today.e32.heatS == dayE32HeatS_[day], "shadow_e32_heat_s", "e32 heat %u, oracle %u", today.e32.heatS, dayE32HeatS_[day]);
            EXPECT(today.e32.starts == dayE32Starts_[day], "shadow_e32_starts", "e32 starts %u, oracle %u", today.e32.starts, dayE32Starts_[day]);
            EXPECT(today.tado.starts == dayTadoStarts_[day], "shadow_tado_starts", "tado starts %u, oracle %u", today.tado.starts, dayTadoStarts_[day]);
        }
    }
    lastShadowAt_ = now_; haveShadowAt_ = true;
    prevE32Heat_ = request.heat;
    if (tadoFlowC) prevTadoHeat_ = *tadoFlowC >= ShadowComparison::tadoHeatFromC;
    EXPECT(today.s == today.tadoUnknownS + today.bothS + today.neitherS + today.e32OnlyS + today.tadoOnlyS, "shadow_partition",
           "s %u != unknown+both+neither+e32+tado", today.s);
    EXPECT(today.e32.heatS <= today.s && today.tado.heatS <= today.s, "shadow_heat_le_s", "heat seconds above the day");
    if (today.e32.heatS) EXPECT(today.e32.flowMin >= plan_.minimumFlowC - 10 && today.e32.flowMax <= FlowDemand::ceilingC, "shadow_flow_range", "e32 flow %u..%u", today.e32.flowMin, today.e32.flowMax);
}

void Chain::checkDay() {
    if (!clockKnown_) return;
    const int32_t day = localDayIndex(utc_);
    if (lastDay_ == INT32_MIN) { lastDay_ = day; prevCompleted_ = shadow_.completedDays(); return; }
    if (day == lastDay_) return;
    // Exactly one rollover per local midnight.
    EXPECT(day == lastDay_ + 1, "day_skip", "local day jumped from %d to %d", lastDay_, day);
    const size_t completed = shadow_.completedDays();
    EXPECT(completed == std::min<size_t>(prevCompleted_ + 1, ShadowComparison::history), "shadow_rollover_count", "completed %zu after %zu", completed, prevCompleted_);
    if (completed) {
        const auto& y = shadow_.completed(0);
        EXPECT(y.day == lastDay_, "shadow_rollover_day", "completed day %d, expected %d", y.day, lastDay_);
        if (lastDay_ != firstKnownDay_ && !irregularDays_.count(lastDay_)) {
            const uint32_t expected = daySeconds_[lastDay_];
            EXPECT(y.s == expected, "shadow_day_length", "day %d: %u s, oracle %u s", lastDay_, y.s, expected);
            EXPECT(expected == 86400 || expected == 82800 || expected == 90000 || expected == 84600 || expected == 88200,
                   "local_day_length", "local day %d lasted %u s", lastDay_, expected);
            if (expected != 86400) { count("dst_days"); observe("dst_day_" + std::to_string(lastDay_), std::to_string(expected) + " s"); }
        }
    }
    prevCompleted_ = completed;
    // Heap: sampled once per local day after all JSON was freed.
    EXPECT(cjLive == 0, "cjson_leak", "%ld cJSON blocks live at midnight", long(cjLive));
    // The harness's own per-day oracles are pruned first, so only the modules can grow.
    for (auto* m : {&daySeconds_, &dayE32HeatS_, &dayE32Starts_, &dayTadoStarts_})
        for (auto it = m->begin(); it != m->end();) it = it->first < day - 2 ? m->erase(it) : std::next(it);
    for (auto it = dhwOracle_.begin(); it != dhwOracle_.end();) it = it->first < day - 2 ? dhwOracle_.erase(it) : std::next(it);
    for (auto it = irregularDays_.begin(); it != irregularDays_.end();) it = *it < day - 2 ? irregularDays_.erase(it) : std::next(it);
    heap_.emplace_back(day, heapBytes());
    lastDay_ = day;
}

void Chain::checkLearner() {
    const auto& plan = engine_.plan();
    EXPECT(learner_.rooms() == plan.rooms.size(), "learner_rooms", "learner %zu rooms, plan %zu", learner_.rooms(), plan.rooms.size());
    EXPECT(learner_.heatingPeriods() >= periodsSeen_, "learner_periods_monotonic", "heating periods went back");
    periodsSeen_ = learner_.heatingPeriods();
    EXPECT(learner_.gasIntervals() >= gasIntervalsSeen_, "learner_gas_monotonic", "gas intervals went back");
    gasIntervalsSeen_ = learner_.gasIntervals();
    // A room that left the plan is forgotten by the learner (and by this check).
    for (auto it = emitterSeen_.begin(); it != emitterSeen_.end();) {
        if (!plan.find(it->first)) { readinessSeen_.erase(it->first); segmentsSeen_.erase(it->first); it = emitterSeen_.erase(it); count("learner_room_forgotten"); }
        else ++it;
    }
    const float cal = learner_.calibration();
    EXPECT(std::isfinite(cal) && cal >= 0.5f && cal <= 2.0f, "learner_calibration", "calibration %f", double(cal));
    for (size_t i = 0; i < plan.rooms.size(); ++i) {
        const auto& id = plan.rooms[i].id;
        const std::string readiness = learner_.readiness(i);
        const bool sameEmitter = emitterSeen_.count(id) && emitterSeen_[id] == plan.rooms[i].emitter;
        if (sameEmitter) {
            EXPECT(learner_.segments(i) >= segmentsSeen_[id], "learner_segments_monotonic", "%s segments went back", id.c_str());
            if (readinessSeen_[id] == "ready") EXPECT(readiness == "ready", "learner_readiness_regressed", "%s fell back to %s", id.c_str(), readiness.c_str());
        }
        if (readiness == "ready" && readinessSeen_[id] != "ready") observe("ready_" + id, "day " + std::to_string(double(utc_ - ctx.startUtc) / 86400.0));
        readinessSeen_[id] = readiness; segmentsSeen_[id] = learner_.segments(i); emitterSeen_[id] = plan.rooms[i].emitter;
        const auto m = learner_.heatModel(i);
        if (m.lossPerHour) EXPECT(std::isfinite(*m.lossPerHour) && *m.lossPerHour >= 0.002f && *m.lossPerHour <= 0.2f, "learner_loss_range", "%s loss %f", id.c_str(), double(*m.lossPerHour));
        if (m.capacityKwhPerK) EXPECT(std::isfinite(*m.capacityKwhPerK) && *m.capacityKwhPerK > 0, "learner_capacity", "%s capacity %f", id.c_str(), double(*m.capacityKwhPerK));
        for (const int16_t s : {int16_t(-300), int16_t(0), int16_t(50), int16_t(100), int16_t(200), int16_t(800), int16_t(3000)}) {
            const auto a = learner_.advise(i, s, outdoor_ * 100 > -5000 ? std::optional<int16_t>(int16_t(outdoor_ * 100)) : std::nullopt);
            EXPECT(std::isfinite(a.requiredRate) && a.requiredRate >= 0, "learner_required_rate", "%s rate %f", id.c_str(), double(a.requiredRate));
            if (a.flowC) EXPECT(*a.flowC >= plan.minimumFlowC && *a.flowC <= plan.maximumFlowC, "learner_advice_flow", "%s advice %u outside [%u, %u]", id.c_str(), *a.flowC, plan.minimumFlowC, plan.maximumFlowC);
            EXPECT(a.ruleFlowC >= plan.minimumFlowC && a.ruleFlowC <= plan.maximumFlowC, "learner_rule_flow", "%s rule %u", id.c_str(), a.ruleFlowC);
        }
    }
}

// WarmupPlanner::nextRise against a brute-force minute walk of the local clock.
void Chain::checkWarmup() {
    if (!clockKnown_) return;
    const auto& plan = engine_.plan();
    for (size_t i = 0; i < plan.rooms.size(); ++i) {
        const auto& s = plan.rooms[i].schedule;
        if (s.empty()) continue;
        std::optional<WarmupPlanner::Rise> expected;
        auto previous = scheduleOracle(s, utc_);
        WarmupPlanner::Rise r; r.nightUtc = utc_;
        const int64_t minuteUtc = utc_ - utc_ % 60;
        for (int m = 1; m <= 1440 && previous; ++m) {
            const auto now = scheduleOracle(s, minuteUtc + m * 60);
            if (*now < *previous) { r.nightUtc = minuteUtc + m * 60; r.eveningCentiC = previous; }
            if (*now > *previous) { r.atUtc = minuteUtc + m * 60; r.fromCentiC = *previous; r.toCentiC = *now; expected = r; break; }
            previous = now;
        }
        const auto got = WarmupPlanner::nextRise(s, utc_);
        EXPECT(got.has_value() == expected.has_value(), "warmup_next_rise_presence", "%s: planner %d, oracle %d", plan.rooms[i].id.c_str(), int(got.has_value()), int(expected.has_value()));
        if (got && expected)
            EXPECT(got->atUtc == expected->atUtc && got->fromCentiC == expected->fromCentiC && got->toCentiC == expected->toCentiC && got->nightUtc == expected->nightUtc,
                   "warmup_next_rise", "%s: planner rise %s %d->%d (night %s), oracle %s %d->%d (night %s)", plan.rooms[i].id.c_str(),
                   isoLocal(got->atUtc).c_str(), got->fromCentiC, got->toCentiC, isoLocal(got->nightUtc).c_str(),
                   isoLocal(expected->atUtc).c_str(), expected->fromCentiC, expected->toCentiC, isoLocal(expected->nightUtc).c_str());
        const auto outdoor = std::optional<int16_t>(int16_t(outdoor_ * 100));
        const auto start = WarmupPlanner::optimumStart(learner_, i, s, utc_, engine_.freshTemperature(i, now_), outdoor);
        if (start.reason[0] == 'p') {
            EXPECT(start.startUtc <= start.rise.atUtc && start.leadS <= WarmupPlanner::maxLeadS, "warmup_lead", "%s lead %u s start %s rise %s", plan.rooms[i].id.c_str(),
                   start.leadS, isoLocal(start.startUtc).c_str(), isoLocal(start.rise.atUtc).c_str());
            EXPECT(start.flowC >= plan.minimumFlowC && start.flowC <= plan.maximumFlowC, "warmup_flow", "%s flow %u", plan.rooms[i].id.c_str(), start.flowC);
        }
        const auto n = WarmupPlanner::night(learner_, i, s, utc_, engine_.freshTemperature(i, now_), outdoor);
        for (uint8_t k = 0; k < n.count; ++k)
            EXPECT(std::isfinite(n.strategies[k].m3) && n.strategies[k].m3 >= 0, "warmup_night_gas", "%s strategy %s m3 %f", plan.rooms[i].id.c_str(), n.strategies[k].name, double(n.strategies[k].m3));
        EXPECT(std::isfinite(n.savingM3), "warmup_saving_finite", "%s saving %f", plan.rooms[i].id.c_str(), double(n.savingM3));
        if (n.savingM3 < 0) {
            count("warmup_negative_saving");
            char text[200];
            std::snprintf(text, sizeof text, "%s: recommended %s, saving_m3 %.3f (the program's own setback is not on time: the 'saving' is an extra cost)",
                          plan.rooms[i].id.c_str(), n.strategies[n.best].name, double(n.savingM3));
            observe("warmup_negative_saving", text);
        }
    }
}

// ----------------------------------------------------------------------------
// JSON: the firmware's payloads, parsed back and size-checked.
// ----------------------------------------------------------------------------
LearnedContext Chain::learnedContext(std::array<std::optional<int16_t>, RoomPlan::maxRooms>& temperatures) const {
    const auto& plan = engine_.plan();
    for (size_t i = 0; i < plan.rooms.size() && i < temperatures.size(); ++i) temperatures[i] = engine_.freshTemperature(i, now_);
    const auto outdoorRaw = monitor_.value(ems::BoilerField::outdoor, now_);
    const auto outdoor = haRoute_.outdoor(outdoorRaw ? std::optional<int16_t>(int16_t(*outdoorRaw)) : std::nullopt, now_);
    LearnedContext c;
    if (clockKnown_) c.utc = utc_;
    c.temperatures = temperatures.data();
    c.outdoorCentiC = outdoor.centiC; c.outdoorSource = outdoor.source; c.now = now_;
    return c;
}

// Replica of HeatingController::heatingStatusJson (keep in sync with src/HeatingController.h).
cJSON* Chain::heatingStatusJson(bool mqtt) {
    cJSON* root = engine_.json();
    cJSON* sensors = root ? cJSON_AddArrayToObject(root, "ble_sensors") : nullptr;
    const auto cycles = cycles_.summary(now_);
    if (cJSON* burner = root ? cJSON_AddObjectToObject(root, "burner") : nullptr) {
        if (cycles.known) {
            cJSON_AddNumberToObject(burner, "starts_last_hour", double(cycles.starts));
            cJSON_AddNumberToObject(burner, "heating_starts_last_hour", double(cycles.heatingStarts));
            cJSON_AddBoolToObject(burner, "short_cycling", cycles.shortCycling);
        } else cJSON_AddNullToObject(burner, "short_cycling");
    }
    cJSON* shadow = sensors ? shadow_.json() : nullptr;
    if (!shadow || !cJSON_AddItemToObject(root, "shadow", shadow)) { cJSON_Delete(shadow); cJSON_Delete(root); return nullptr; }
    cJSON* active = guard_.json(now_);
    if (active) cJSON_AddBoolToObject(active, "enabled", true);
    if (!active || !cJSON_AddItemToObject(root, "active", active)) { cJSON_Delete(active); cJSON_Delete(root); return nullptr; }
    for (size_t i = 0; i < bindings_.count; ++i) {
        const auto& binding = bindings_.devices[i];
        const auto value = ble_->snapshot(binding.address);
        cJSON* s = cJSON_CreateObject();
        if (!s || !cJSON_AddItemToArray(sensors, s)) { cJSON_Delete(s); cJSON_Delete(root); return nullptr; }
        const auto scaled = [&](const char* key, auto v, double divisor) {
            if (v) cJSON_AddNumberToObject(s, key, *v / divisor); else cJSON_AddNullToObject(s, key);
        };
        cJSON_AddStringToObject(s, "id", printBleHex(binding.address).data());
        cJSON_AddStringToObject(s, "name", binding.name.data());
        cJSON_AddStringToObject(s, "profile", managedBleProfileName(binding.profile));
        scaled("temperature", value.temperature, 100.0);
        scaled("humidity", value.humidity, 100.0);
        scaled("battery", value.battery, 1.0);
        scaled("age_s", value.temperatureAgeMs ? std::optional<uint32_t>(*value.temperatureAgeMs / 1000) : std::nullopt, 1.0);
    }
    if (!addHaLink(root, haRoute_.lastAcceptedMs(), now_, now_ >= haDownUntil_)) { cJSON_Delete(root); return nullptr; }
    if (mqtt) return root;
    std::array<std::optional<int16_t>, RoomPlan::maxRooms> temperatures{};
    cJSON* learned = learnedJson(learner_, engine_.plan(), learnedContext(temperatures));
    if (!learned || !cJSON_AddItemToObject(root, "learned", learned)) { cJSON_Delete(learned); cJSON_Delete(root); return nullptr; }
    cJSON* dhw = dhwEpisodes_.summaryJson();
    if (!dhw || !cJSON_AddItemToObject(root, "dhw", dhw)) { cJSON_Delete(dhw); cJSON_Delete(root); return nullptr; }
    return root;
}

void Chain::publish(bool mqtt, bool learned, bool full) {
    const long before = cjLive;
    if (mqtt) {
        // fw/telemetry/heating (compact, always the same shape)
        cJSON* status = heatingStatusJson(true);
        EXPECT(status != nullptr, "status_null", "heatingStatusJson(true) returned null");
        if (status) compactHeatingTelemetry(status);
        const auto text = printed(status);
        cJSON_Delete(status);
        checkPayload("mqtt_heating", text, heatingTelemetryMaxBytes);
        if (cJSON* back = parseBack(text)) {
            std::set<std::string> paths;
            keyPaths(back, "", paths);
            if (!shapeKnown_) { shape_ = paths; shapeKnown_ = true; }
            else if (paths != shape_) {
                // A documented "{..}|null" value or an empty array is no key change.
                const auto covered = [](const std::set<std::string>& other, const std::string& p) {
                    if (p.size() >= 2 && p.compare(p.size() - 2, 2, "[]") == 0) return true;
                    for (size_t k = p.find('.', 1); k != std::string::npos; k = p.find('.', k + 1)) if (other.count(p.substr(0, k))) return true;
                    for (const auto& q : other) if (q.size() > p.size() && q.compare(0, p.size(), p) == 0 && (q[p.size()] == '.' || q[p.size()] == '[')) return true;
                    return false;
                };
                std::string added, removed;
                for (const auto& p : paths) if (!shape_.count(p) && !covered(shape_, p)) added += p + " ";
                for (const auto& p : shape_) if (!paths.count(p) && !covered(paths, p)) removed += p + " ";
                if (!added.empty() || !removed.empty()) {
                    count("mqtt_shape_change");
                    observe("mqtt_shape_change " + added + "|" + removed, "keys appeared: " + added + " disappeared: " + removed);
                }
                shape_ = paths;
            }
            cJSON_Delete(back);
        }
        // fw/telemetry/heating_summary
        std::array<std::optional<int16_t>, RoomPlan::maxRooms> temperatures{};
        const auto summary = heatingSummaryTelemetry(learner_, learnedContext(temperatures), dhwEpisodes_.summaryJson());
        checkPayload("mqtt_summary", summary, 600);
        // The plan and the per-module status objects.
        checkPayload("plan", engine_.plan().json(), ControlPartitionBudget::configBytes - 1);
        std::ostringstream b; cycles_.writeJSON(b, now_); checkPayload("burner_cycles", b.str(), 0);
        std::ostringstream d; dhwEpisodes_.writeJSON(d, now_); checkPayload("dhw_status", d.str(), 0);
        EXPECT(cycles_.observedStarts() >= burnerStartsSeen_, "burner_starts_monotonic", "observed starts went back");
        burnerStartsSeen_ = cycles_.observedStarts();
        // Burner cycle oracle: starts in the last hour.
        const auto sum = cycles_.summary(now_);
        if (sum.known) {
            size_t starts = 0, heating = 0;
            for (const auto& r : burnerRuns_) if (now_ - r.start < BurnerCycleMonitor::windowMs) { ++starts; if (!r.dhw) ++heating; }
            EXPECT(sum.starts == std::min(starts, BurnerCycleMonitor::capacity), "burner_starts_last_hour", "monitor %zu, oracle %zu", sum.starts, starts);
            EXPECT(sum.heatingStarts <= sum.starts && (sum.heatingStarts < BurnerCycleMonitor::shortCycleStarts || sum.shortCycling), "burner_short_cycling", "heating starts %zu short %d", sum.heatingStarts, int(sum.shortCycling));
            if (sum.shortCycling) count("burner_short_cycling_reports");
        }
        // Hot water oracle: today's counts by kind (the episode counts on the day it ends).
        if (clockKnown_ && dhwOracleValid_) {
            const int32_t day = localDayIndex(utc_);
            const auto& t = dhwEpisodes_.today();
            if (t.day == day && day != firstKnownDay_) {
                const auto& want = dhwOracle_[day];
                EXPECT(t.count[0] == want.count[0] && t.count[1] == want.count[1] && t.count[2] == 0, "dhw_counts",
                       "tapping %u/%u keep warm %u/%u unknown %u", t.count[0], want.count[0], t.count[1], want.count[1], t.count[2]);
                for (int k = 0; k < 2; ++k)
                    EXPECT(t.seconds[size_t(k)] + 12 * t.count[size_t(k)] >= want.seconds[size_t(k)] && t.seconds[size_t(k)] <= want.seconds[size_t(k)] + 12 * t.count[size_t(k)],
                           "dhw_seconds", "kind %d: %u s, oracle %u s", k, t.seconds[size_t(k)], want.seconds[size_t(k)]);
            }
        }
    }
    if (learned) {
        // fw/telemetry/heating_learned/<id>, two rooms per tick
        rotation_.tick(engine_.plan().rooms.size(), 2, [&](size_t room) {
            std::array<std::optional<int16_t>, RoomPlan::maxRooms> temperatures{};
            const uint64_t calls0 = localtimeCalls;
            const auto payload = learnedRoomTelemetry(learner_, engine_.plan(), room, learnedContext(temperatures));
            noteLocaltime("mqtt_learned_room", localtimeCalls - calls0, utc_);
            EXPECT(topicSafeRoomId(engine_.plan().rooms[room].id), "topic_unsafe_id", "room id %s", engine_.plan().rooms[room].id.c_str());
            checkPayload("mqtt_learned_room", payload, 900);
            // The id appears three times; a 32-character id (the plan maximum) would add this much.
            const size_t worst = payload.size() + 3 * (32 - std::min<size_t>(32, engine_.plan().rooms[room].id.size()));
            auto& w = counters[ctx.scenario + ":mqtt_learned_room_max_with_32_char_id"];
            w = std::max<uint64_t>(w, worst);
        });
    }
    if (full) {
        const uint64_t calls0 = localtimeCalls;
        cJSON* status = heatingStatusJson(false);
        noteLocaltime("http_status_heating", localtimeCalls - calls0, utc_);
        EXPECT(status != nullptr, "status_full_null", "heatingStatusJson(false) returned null");
        const auto text = printed(status);
        cJSON_Delete(status);
        checkPayload("http_status_heating", text, 0);
        cJSON* plan = engine_.plan().rooms.empty() ? nullptr : engine_.plan().rooms[0].schedule.json();
        if (plan) { checkPayload("schedule", printed(plan), 0); cJSON_Delete(plan); }
        checkWarmup();
    }
    EXPECT(cjLive == before, "cjson_leak_publish", "%ld cJSON blocks leaked by one publish", long(cjLive - before));
}

// ----------------------------------------------------------------------------
// Allocation-failure sweep: every cJSON allocation of every builder fails once
// (one child process per crash, so a crash is reported and the sweep goes on).
// ----------------------------------------------------------------------------
void Chain::oomSweep() {
    std::array<std::optional<int16_t>, RoomPlan::maxRooms> temperatures{};
    const auto context = learnedContext(temperatures);
    const auto planText = engine_.plan().json();
    struct Builder { const char* name; std::function<std::string()> build; };
    const std::vector<Builder> builders = {
        {"room_engine_json", [&] { cJSON* o = engine_.json(); auto t = printed(o); cJSON_Delete(o); return t; }},
        {"shadow_json", [&] { cJSON* o = shadow_.json(); auto t = printed(o); cJSON_Delete(o); return t; }},
        {"guard_json", [&] { cJSON* o = guard_.json(now_); auto t = printed(o); cJSON_Delete(o); return t; }},
        {"learner_json", [&] { cJSON* o = learner_.json(); auto t = printed(o); cJSON_Delete(o); return t; }},
        {"learned_json_plans", [&] { cJSON* o = learnedJson(learner_, engine_.plan(), context); auto t = printed(o); cJSON_Delete(o); return t; }},
        {"learned_room_telemetry", [&] { return learnedRoomTelemetry(learner_, engine_.plan(), 0, context); }},
        {"summary_telemetry", [&] { return heatingSummaryTelemetry(learner_, context, dhwEpisodes_.summaryJson()); }},
        {"dhw_summary_json", [&] { cJSON* o = dhwEpisodes_.summaryJson(); auto t = printed(o); cJSON_Delete(o); return t; }},
        {"plan_json", [&] { return engine_.plan().json(); }},
        {"schedule_json", [&] { cJSON* o = catalog_[0].schedule.json(); auto t = printed(o); cJSON_Delete(o); return t; }},
        {"status_mqtt_compact", [&] { cJSON* o = heatingStatusJson(true); if (o) compactHeatingTelemetry(o); auto t = printed(o); cJSON_Delete(o); return t; }},
        {"status_full", [&] { cJSON* o = heatingStatusJson(false); auto t = printed(o); cJSON_Delete(o); return t; }},
        {"plan_parse", [&] { cJSON* o = parseBack(planText); RoomPlan p; const char* e = o ? RoomPlan::parse(o, p) : "x"; cJSON_Delete(o); return std::string(e ? "" : "{}"); }},
        {"heating_input_parse", [&] { const auto in = HeatingInput::parse(R"({"entity":"climate.woonkamer","temperature":20.4,"target":21.0})"); return std::string(in ? "{}" : ""); }},
    };
    for (const auto& b : builders) {
        cjCalls = 0; cjFailAt = 0;
        const long live0 = cjLive;
        (void)b.build();
        const long total = cjCalls;
        EXPECT(cjLive == live0, "oom_baseline_leak", "%s leaks without a failure", b.name);
        // Every allocation up to 400, then 400 evenly spread over the rest (large builders).
        std::vector<long> probes;
        for (long k = 1; k <= total; ++k)
            if (k <= 400 || (k - 400) % std::max<long>(1, (total - 400) / 400) == 0 || k == total) probes.push_back(k);
        size_t next = 0;
        int crashes = 0;
        while (next < probes.size() && crashes < 3) {
            int fds[2];
            if (pipe(fds)) { perror("pipe"); return; }
            std::fflush(nullptr);
            const pid_t pid = fork();
            if (pid == 0) {
                close(fds[0]);
                const std::string log = o_.outDir + "/oom-" + (o_.name.empty() ? o_.scenario : o_.name) + "-" + b.name + ".log";
                const int fd = open(log.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
                if (fd >= 0) { dup2(fd, 2); close(fd); }
                for (; next < probes.size(); ++next) {
                    const long k = probes[next];
                    int64_t msg[3] = {1, int64_t(next), 0};
                    if (write(fds[1], msg, sizeof msg) != sizeof msg) _exit(3);
                    const long live = cjLive;
                    cjCalls = 0; cjFailAt = k;
                    const auto text = b.build();
                    cjFailAt = 0;
                    if (cjLive != live) { int64_t m[3] = {2, k, cjLive - live}; if (write(fds[1], m, sizeof m) != sizeof m) _exit(3); }
                    if (!text.empty() && !validJson(text)) { int64_t m[3] = {3, k, 0}; if (write(fds[1], m, sizeof m) != sizeof m) _exit(3); }
                }
                _exit(0);
            }
            close(fds[1]);
            int64_t msg[3], last = int64_t(next);
            bool leakSeen = false, invalidSeen = false;
            while (read(fds[0], msg, sizeof msg) == sizeof msg) {
                if (msg[0] == 1) last = msg[1];
                else if (msg[0] == 2 && !leakSeen) { leakSeen = true; fail(std::string("oom_leak_") + b.name, "allocation #%" PRId64 " of %ld failing leaks %" PRId64 " cJSON blocks", msg[1], total, msg[2]); }
                else if (msg[0] == 3 && !invalidSeen) { invalidSeen = true; fail(std::string("oom_invalid_json_") + b.name, "allocation #%" PRId64 " of %ld failing gives invalid JSON", msg[1], total); }
            }
            close(fds[0]);
            int status = 0;
            waitpid(pid, &status, 0);
            if (WIFEXITED(status) && WEXITSTATUS(status) == 0) break;
            ++crashes;
            // The first frame inside src/ from the sanitizer report.
            std::string where;
            const std::string log = o_.outDir + "/oom-" + (o_.name.empty() ? o_.scenario : o_.name) + "-" + b.name + ".log";
            if (FILE* f = std::fopen(log.c_str(), "r")) {
                char line[1024];
                while (std::fgets(line, sizeof line, f)) {
                    if (where.empty() && std::strstr(line, "/src/") && std::strstr(line, " #")) where = line;
                    if (std::strstr(line, "SUMMARY:")) { where += line; break; }
                }
                std::fclose(f);
            }
            for (auto& ch : where) if (ch == '\n') ch = ' ';
            fail(std::string("oom_crash_") + b.name, "crash when cJSON allocation #%ld of %ld fails: %s (log %s)", probes[size_t(last)], total, where.c_str(), log.c_str());
            next = size_t(last) + 1;
        }
        count(std::string("oom_sweep_allocations_") + b.name, uint64_t(total));
        count(std::string("oom_sweep_probes_") + b.name, probes.size());
    }
}

// ----------------------------------------------------------------------------
void Chain::step() {
    now_ += o_.stepMs;
    utc_ += o_.stepMs / 1000;
    ctx.uptime = now_; ctx.utc = utc_;
    if (!clockKnown_ && now_ - bootMs_ >= 180000) clockKnown_ = true; // NTP after 3 min
    const double dtH = o_.stepMs / 3600000.0;
    weather();
    tado();
    // A firmware upload blocks the loop for minutes: EMS, MQTT and the control step wait.
    if (clockKnown_ && dhw_ == Dhw::idle && now_ >= stallUntil_ && now_ >= busDownUntil_ && chance(1.0 / (5 * 24 * 360.0))) {
        stallUntil_ = now_ + uint64_t(uniformInt(12, 36)) * 10000;
        busDownUntil_ = stallUntil_; // its telegrams are lost (the EMS queue overflows)
        irregularDays_.insert(localDayIndex(utc_)); irregularDays_.insert(localDayIndex(utc_ + 400));
        count("loop_stall");
    }
    // NTP corrects the wall clock by a few seconds (not across a local midnight).
    if (clockKnown_ && chance(1.0 / (2 * 24 * 360.0))) {
        const auto l = local(utc_);
        if (!((l.hour == 23 && l.minute >= 58) || (l.hour == 0 && l.minute <= 1))) {
            utc_ += uniformInt(0, 1) ? uniformInt(1, 20) : -uniformInt(1, 20);
            ctx.utc = utc_;
            irregularDays_.insert(localDayIndex(utc_));
            count("ntp_step");
        }
    }
    const bool stalled = now_ < stallUntil_;
    dhwGenerator();
    boiler(dtH);
    physics(dtH);
    emitTelegrams();
    if (!stalled) haMessages();
    bleAdverts();
    if (stalled) return;
    guardPhases();
    stepE32();
    checkBle();
    if ((now_ / o_.stepMs) % 6 == 0) checkLearner();
    checkDay();
    if (now_ >= nextEdit_) { editPlan(); nextEdit_ = now_ + uint64_t(expo(o_.editEveryH * 3600.0) * 1000) + 60000; }
    const bool mqtt = now_ >= nextMqtt_, learned = now_ >= nextLearned_, full = now_ >= nextFull_;
    if (mqtt) nextMqtt_ = now_ + o_.mqttEveryS * 1000ull;
    if (learned) nextLearned_ = now_ + o_.learnedEveryS * 1000ull;
    if (full) nextFull_ = now_ + o_.fullEveryS * 1000ull;
    if (mqtt || learned || full) publish(mqtt, learned, full);
}

void Chain::finish() {
    // Heap: no growth after the warm-up (days 3..9 against the last 7 days).
    if (heap_.size() >= 14) {
        size_t warm = 0, late = 0;
        for (size_t i = 3; i < 10; ++i) warm = std::max(warm, heap_[i].second);
        for (size_t i = heap_.size() - 7; i < heap_.size(); ++i) late = std::max(late, heap_[i].second);
        counters[ctx.scenario + ":heap_warm_bytes"] = warm;
        counters[ctx.scenario + ":heap_late_bytes"] = late;
        EXPECT(late <= warm + 8192, "heap_growth", "heap grew from %zu B (days 3-9) to %zu B (last 7 days)", warm, late);
    }
    // The learner reaches "ready" in this house.
    std::string ready;
    size_t readyCount = 0;
    for (size_t i = 0; i < engine_.plan().rooms.size(); ++i) {
        ready += engine_.plan().rooms[i].id + "=" + learner_.readiness(i) + "(" + std::to_string(learner_.segments(i)) + ") ";
        if (std::string(learner_.readiness(i)) == "ready") ++readyCount;
    }
    observe("learner_readiness", ready);
    observe("learner_calibration", std::to_string(learner_.calibration()) + " after " + std::to_string(learner_.gasIntervals()) + " gas intervals (truth 24/22 = 1.091)");
    if (o_.days >= 30) EXPECT(readyCount >= 3, "learner_never_ready", "only %zu rooms ready: %s", readyCount, ready.c_str());
    counters[ctx.scenario + ":learner_heating_periods"] = learner_.heatingPeriods();
    counters[ctx.scenario + ":plan_applied"] = planApplied_;
    counters[ctx.scenario + ":plan_refused"] = planRefused_;
    counters[ctx.scenario + ":plan_too_large"] = planTooLarge_;
    counters[ctx.scenario + ":plan_max_bytes"] = maxPlanBytes_;
    counters[ctx.scenario + ":guard_owning_steps"] = activeOwningS_;
    counters[ctx.scenario + ":guard_owning_comfort_out_steps"] = comfortOutS_;
    counters[ctx.scenario + ":ble_decrypt_calls"] = crypto_.calls;
    counters[ctx.scenario + ":ble_queue_drops"] = ble_->queueDrops();
    for (size_t i = 0; i < engine_.plan().rooms.size(); ++i) {
        const auto m = learner_.heatModel(i);
        if (m.lossPerHour || m.capacityKwhPerK)
            observe("heat_model_" + engine_.plan().rooms[i].id, "loss " + std::to_string(m.lossPerHour.value_or(-1)) + "/h capacity " + std::to_string(m.capacityKwhPerK.value_or(-1)) + " kWh/K");
    }
    if (o_.oom) oomSweep();
}

int Chain::run() {
    ctx.startUtc = utc_ = o_.startUtc;
    ctx.utc = utc_;
    now_ = bootMs_ = o_.uptime0;
    heap_.reserve(size_t(o_.days) + 4);
    setupHouse();
    setupBle();
    setupPlan();
    nextEdit_ = now_ + 3600000;
    nextPhase_ = now_ + uint64_t(uniformInt(3, 6)) * 86400000;
    const uint64_t steps = uint64_t(o_.days * 86400000.0 / o_.stepMs);
    const auto t0 = std::chrono::steady_clock::now();
    for (uint64_t i = 0; i < steps; ++i) {
        step();
        if (i && i % (steps / 10 ? steps / 10 : 1) == 0)
            std::fprintf(stderr, "[%s] %3.0f%% day %.1f, %.0f s\n", ctx.scenario.c_str(), 100.0 * double(i) / double(steps), double(utc_ - ctx.startUtc) / 86400.0,
                         std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count());
    }
    counters[ctx.scenario + ":steps"] = steps;
    finish();
    return 0;
}

// ============================================================================
// ActiveHeatGuard: 60 days of synthetic, guard-centric events at the 10 s cadence.
// ============================================================================
void guardScenario() {
    ActiveHeatGuard guard;
    uint64_t now = opt.uptime0;
    const uint64_t steps = uint64_t(opt.days * 86400000.0 / 10000);
    RoomPlan::Mode mode = RoomPlan::Mode::shadow;
    uint8_t planMin = 30, planMax = 60;
    std::optional<uint64_t> confirmedAt;
    bool tadoConnected = true, routeReady = true, claimed = false;
    std::optional<ActiveHeatGuard::Foreign> foreign;
    std::optional<uint8_t> limit = uint8_t(60);
    struct Setpoint { uint8_t from, flow; };
    std::optional<Setpoint> boiler;
    std::optional<std::pair<uint8_t, uint64_t>> post;
    uint64_t nextMode = now + 3600000, nextConfirm = 0, nextLimit = now, lastOkSend = 0, routeOkSince = now, frostUntil = 0, lostUntil = 0;
    double failRate = 0.07;
    bool frostLatch = false, ownedBefore = false;
    bool heat = false; uint8_t flow = 0;
    for (uint64_t i = 0; i < steps; ++i) {
        now += 10000; ctx.uptime = now; ctx.utc = ctx.startUtc + int64_t((now - opt.uptime0) / 1000);
        if (now >= nextMode) {
            mode = mode == RoomPlan::Mode::shadow ? RoomPlan::Mode::active : RoomPlan::Mode::shadow;
            if (mode == RoomPlan::Mode::active) { nextConfirm = now + uint64_t(uniformInt(1, 30)) * 60000; if (chance(0.8)) tadoConnected = false; }
            else { tadoConnected = true; if (chance(0.5)) { guard.confirm(now, false); confirmedAt.reset(); } }
            nextMode = now + uint64_t(expo(8 * 3600.0) * 1000) + 600000;
            count("mode_switch");
        }
        if (nextConfirm && now >= nextConfirm) { guard.confirm(now, true); confirmedAt = now; nextConfirm = 0; count("confirm"); }
        if (mode == RoomPlan::Mode::active && chance(0.0003)) { tadoConnected = !tadoConnected; count(tadoConnected ? "tado_back" : "tado_gone"); }
        if (mode == RoomPlan::Mode::active && chance(0.0002)) { guard.confirm(now, false); confirmedAt.reset(); nextConfirm = now + uint64_t(uniformInt(5, 60)) * 60000; count("withdraw"); }
        if (mode == RoomPlan::Mode::shadow) confirmedAt.reset(); // the guard clears it on leaving active mode
        if (tadoConnected && (i % 6) == 0) { foreign = ActiveHeatGuard::Foreign{0x17, now - 300}; boiler = Setpoint{0x17, uint8_t(chance(0.5) ? 0 : 38)}; }
        if (chance(0.00002)) foreign = ActiveHeatGuard::Foreign{chance(0.5) ? uint8_t(0x0b) : uint8_t(0x08), now - 10}; // own/boiler: ignored
        if (now >= nextLimit) {
            const double r = uniform(0, 1);
            limit = r < 0.6 ? std::optional<uint8_t>(60) : r < 0.7 ? std::optional<uint8_t>(55) : r < 0.75 ? std::optional<uint8_t>(80)
                : r < 0.8 ? std::optional<uint8_t>(75) : r < 0.85 ? std::optional<uint8_t>(25) : std::nullopt;
            nextLimit = now + uint64_t(expo(12 * 3600.0) * 1000);
        }
        if (chance(0.0001)) { planMin = uint8_t(uniformInt(20, 40)); planMax = uint8_t(uniformInt(planMin + 1, ActiveHeatGuard::hardMaximumFlowC)); }
        if (chance(0.0005)) { routeReady = !routeReady; routeOkSince = now; }
        if (!routeReady && chance(0.01)) { routeReady = true; routeOkSince = now; }
        if (chance(0.00005)) failRate = chance(0.5) ? 0.07 : 1.0; // sometimes every write fails for a while
        if (failRate == 1.0 && chance(0.002)) failRate = 0.07;
        if (now >= frostUntil && chance(0.00003)) frostUntil = now + uint64_t(uniformInt(2, 48)) * 3600000;
        if (now >= lostUntil && chance(0.00003)) lostUntil = now + uint64_t(uniformInt(10, 120)) * 60000;
        // The EMS route reports the previous post.
        if (post) {
            const bool ok = routeReady && !chance(failRate);
            guard.transmitted(post->second, ok);
            if (ok) { boiler = Setpoint{0x0b, post->first}; lastOkSend = post->second; }
        }
        post.reset();
        // Rooms: 8, some inactive, frost in an inactive room, measurement loss phases.
        ActiveHeatGuard::Inputs in;
        in.mode = mode;
        const bool lost = now < lostUntil;
        for (int r = 0; r < 8; ++r) {
            RoomDemand::Result res;
            const bool active = r < 6;
            std::optional<int16_t> t = int16_t(1900 + r * 30);
            if (r == 7 && now < frostUntil) t = int16_t(650);
            if (r == 2 && now < frostUntil && chance(0.5)) t = int16_t(850);
            if (active) {
                res.status = lost ? RoomDemand::Status::lost : r == 3 ? RoomDemand::Status::fallback : RoomDemand::Status::ok;
                if (!lost) { res.temperature = t; res.source = 0; res.setpoint = 2000; res.usable = true; }
            }
            in.rooms.add(res);
            if (!lost || r >= 6) in.rooms.measured(t);
        }
        if ((i % 30) == 0) { heat = chance(0.5); flow = uint8_t(uniformInt(planMin, planMax)); }
        in.request = lost ? FlowDemand::Request{false, 0, FlowDemand::Reason::noDemand} : FlowDemand::Request{heat, heat ? flow : uint8_t(0), heat ? FlowDemand::Reason::heating : FlowDemand::Reason::idle};
        in.foreign = foreign;
        in.uptimeMs = now - opt.uptime0;
        in.routeReady = routeReady;
        in.boilerLimitC = limit;
        const bool e32Heat = boiler && boiler->from == 0x0b && boiler->flow > 0;
        in.boiler = {e32Heat && chance(0.9), std::optional<int16_t>(int16_t(e32Heat ? 4500 : 2500))};
        guard.setFlowLimits(planMin, planMax);
        const auto c = guard.step(now, in);
        if (c.send) post = std::make_pair(c.flowC, now);
        const uint8_t cap = std::min<uint8_t>({planMax, ActiveHeatGuard::hardMaximumFlowC, limit.value_or(0)});
        const bool foreignAfter = confirmedAt && foreign && foreign->address != 0x0b && foreign->address != 0x08 && foreign->receivedAtMs > *confirmedAt;
        if (c.send && c.flowC) {
            EXPECT(mode == RoomPlan::Mode::active, "guard_heat_in_shadow", "positive %u in shadow", c.flowC);
            EXPECT(guard.confirmed() && confirmedAt, "guard_heat_unconfirmed", "positive %u unconfirmed", c.flowC);
            EXPECT(!foreignAfter, "guard_heat_with_foreign", "positive %u after a foreign 0x1A", c.flowC);
            EXPECT(routeReady, "guard_send_route_not_ready", "send without route");
            EXPECT(c.flowC <= cap, "guard_flow_above_cap", "flow %u > cap %u", c.flowC, cap);
            EXPECT(in.uptimeMs >= 120000, "guard_boot_holdoff", "heat %" PRIu64 " ms after boot", in.uptimeMs);
            if (cap >= planMin) EXPECT(c.flowC >= planMin, "guard_flow_below_min", "flow %u < min %u", c.flowC, planMin);
            else count("flow_below_plan_min_by_boiler_limit");
        }
        if (mode == RoomPlan::Mode::shadow) EXPECT(!c.send || c.flowC == 0, "guard_shadow_send", "shadow sends %u", c.flowC);
        // Frost rule (oracle latch 8.0 / 9.0 degC, only while owning).
        if (guard.owning()) {
            if (!ownedBefore) frostLatch = false;
            std::optional<int16_t> coldest = in.rooms.coldestCentiC;
            if (coldest && *coldest < 800) frostLatch = true;
            else if (!coldest || *coldest >= 900) frostLatch = false;
            if (frostLatch && cap) EXPECT(guard.command().flowC >= std::min(planMin, cap), "guard_frost_rule", "frost but flow %u (coldest %d)", guard.command().flowC, coldest.value_or(-1));
            if (frostLatch) count("frost_owning_steps");
            // Refresh: while the route works, a successful write at least every 60 s (+ one step).
            if (routeReady && failRate < 1 && now - routeOkSince > 120000 && lastOkSend && now - std::max(lastOkSend, routeOkSince) > 130000)
                count("refresh_gap_steps");
            count("owning_steps");
        }
        ownedBefore = guard.owning();
        // A release must leave the boiler with a zero (or the tado's request).
        if (claimed && !guard.claimsBoiler() && boiler && boiler->from == 0x0b && boiler->flow > 0) {
            fail("guard_released_with_positive_at_boiler", "left %s with the E32's %u degC still at the boiler", ActiveHeatGuard::name(guard.state()), boiler->flow);
        }
        claimed = guard.claimsBoiler();
        if ((i % 360) == 0) { cJSON* j = guard.json(now); checkPayload("guard_json", printed(j), 0); cJSON_Delete(j); }
    }
    counters[ctx.scenario + ":steps"] = steps;
}

// ============================================================================
// FlowDemand alone: random demand flips (schedule switch points, HA targets,
// pauses) far more often than a house produces them, so the minimum on/off
// times, the limits and the integral are exercised hard.
// ============================================================================
void flowScenario() {
    FlowDemand::Params p;
    FlowDemand flow(p);
    uint64_t now = opt.uptime0;
    const uint64_t steps = uint64_t(opt.days * 86400000.0 / 10000);
    bool demand = false, heat = false, haveOff = false;
    std::optional<int16_t> error = int16_t(0);
    uint64_t onAt = 0, offAt = 0, nextFlip = now, demandSince = now;
    for (uint64_t i = 0; i < steps; ++i) {
        now += chance(0.001) ? uint64_t(uniformInt(20, 600)) * 1000 : 10000; // a stalled loop now and then
        ctx.uptime = now; ctx.utc = ctx.startUtc + int64_t((now - opt.uptime0) / 1000);
        if (now >= nextFlip) {
            demand = chance(0.5); if (demand) demandSince = now;
            nextFlip = now + uint64_t(uniformInt(10, 1200)) * 1000;
        }
        if (chance(0.01)) error = chance(0.05) ? std::optional<int16_t>() : std::optional<int16_t>(int16_t(uniformInt(-300, 800)));
        else if (error) error = int16_t(std::clamp<int>(*error + int(uniformInt(-5, 5)), -3000, 3000));
        if (chance(0.00005)) { // a plan edit of the flow limits rebuilds FlowDemand (RoomEngine::setPlan)
            p.minimumFlowC = uint8_t(uniformInt(20, 40)); p.maximumFlowC = uint8_t(uniformInt(p.minimumFlowC + 1, 60));
            flow = FlowDemand(p); haveOff = false; heat = false; count("flow_rebuild");
        }
        const auto r = flow.update(now, demand, error);
        if (r.heat) EXPECT(r.flowC >= p.minimumFlowC && r.flowC <= p.maximumFlowC, "flow_limits", "flow %u outside [%u, %u]", r.flowC, p.minimumFlowC, p.maximumFlowC);
        else EXPECT(r.flowC == 0, "flow_off_nonzero", "off with %u", r.flowC);
        if (!error) EXPECT(!r.heat && r.reason == FlowDemand::Reason::noDemand, "flow_no_error_stop", "no usable room but %s", FlowDemand::name(r.reason));
        if (r.heat && !heat) {
            if (haveOff) EXPECT(now - offAt >= p.minimumOffMs, "flow_minimum_off", "restart %" PRIu64 " s after the stop", (now - offAt) / 1000);
            onAt = now; count("flow_starts");
        }
        if (!r.heat && heat) {
            if (r.reason == FlowDemand::Reason::satisfied) EXPECT(now - onAt >= p.minimumOnMs, "flow_minimum_on", "stopped %" PRIu64 " s after the start", (now - onAt) / 1000);
            offAt = now; haveOff = true;
        }
        // Liveness: demand with a usable room for longer than the minimum off time heats.
        if (demand && error && now - demandSince > p.minimumOffMs + 20000 && haveOff && now - offAt > p.minimumOffMs + 20000)
            EXPECT(r.heat, "flow_stuck_off", "demand for %" PRIu64 " s but %s", (now - demandSince) / 1000, FlowDemand::name(r.reason));
        heat = r.heat;
    }
    counters[ctx.scenario + ":steps"] = steps;
}

// ============================================================================
// SupervisorPolicy: 60 days of network/loop/update/Bluetooth faults with reboots.
// ============================================================================
void supervisorScenario() {
    using P = diag::SupervisorPolicy;
    // Backoff arithmetic for every possible stored counter.
    for (int r = 0; r < 256; ++r) {
        EXPECT(P::backoff(P::wifiLostMs, uint8_t(r)) >= P::wifiLostMs && P::backoff(P::wifiLostMs, uint8_t(r)) <= P::wifiLostMs << P::maximumBackoff, "sup_backoff", "backoff %d", r);
        EXPECT(P::backoff(P::bluetoothSilentMs, uint8_t(r)) <= P::bluetoothSilentMs << P::maximumBackoff, "sup_backoff_bt", "bt backoff %d", r);
        EXPECT(P::networkDeadDelay(uint8_t(r)) >= P::networkDeadMs && P::networkDeadDelay(uint8_t(r)) <= P::networkDeadMaxMs, "sup_network_delay", "delay %d", r);
        if (r) EXPECT(P::networkDeadDelay(uint8_t(r)) >= P::networkDeadDelay(uint8_t(r - 1)), "sup_network_delay_monotonic", "delay %d", r);
    }
    uint64_t wall = 0; // ms since the start
    const uint64_t end = uint64_t(opt.days * 86400000.0);
    uint8_t wifiRestarts = 0, deadRestarts = 0, btRestarts = 0;
    uint64_t boots = 0;
    // The fault lives in wall time: a Wi-Fi outage outlasts a restart; a stuck loop or update does not.
    int fault = 0;
    uint64_t faultEnd = 0, nextEvent = uint64_t(expo(18 * 3600.0) * 1000);
    while (wall < end) {
        ++boots;
        const uint64_t bootWall = wall;
        // A boot: uptime seconds + 1, as monotonicS(); 0 means "never".
        uint64_t wifiDown = 0, brokerDown = 0, quiet = 1, loopAt = 1, updateSince = 0, btQuiet = 1;
        uint32_t probeFailures = 0;
        bool armed = false, brokerSeen = false;
        bool restarted = false;
        while (!restarted) {
            wall += 5000;
            const uint64_t up = wall - bootWall;
            const uint64_t nowS = up / 1000 + 1;
            ctx.uptime = up; ctx.utc = ctx.startUtc + int64_t(wall / 1000);
            if (wall >= end) break;
            if (!fault && wall >= nextEvent) {
                fault = int(uniformInt(1, 6));
                const double minutes = fault == 1 ? (chance(0.7) ? uniform(0.2, 10) : uniform(16, 600)) : fault == 2 ? uniform(1, 40)
                    : fault == 3 ? uniform(1, 30) : fault == 4 ? uniform(5, 7) : fault == 5 ? uniform(2, 30) : uniform(10, 200);
                faultEnd = wall + uint64_t(minutes * 60000);
                count("sup_fault_" + std::to_string(fault));
            }
            if (fault && wall >= faultEnd) { fault = 0; nextEvent = wall + uint64_t(expo(18 * 3600.0) * 1000); }
            const bool wifiUp = fault != 1, brokerUp = fault != 2 && wifiUp, probeOk = fault != 3 && wifiUp;
            const bool loopAlive = fault != 4, update = fault == 5, btHeard = fault != 6;
            if (!wifiUp) { if (!wifiDown) wifiDown = nowS; } else wifiDown = 0;
            if (brokerUp) brokerSeen = true;
            if (!brokerUp && brokerSeen) { if (!brokerDown) brokerDown = nowS; } else brokerDown = 0;
            if (probeOk) { armed = true; probeFailures = 0; quiet = nowS; } else if (wifiUp && (up / 5000) % 2 == 0) ++probeFailures;
            if (loopAlive) loopAt = nowS;
            if (btHeard) { btQuiet = nowS; btRestarts = 0; } // a frame of a bound sensor ends the series
            if (update) { if (!updateSince) updateSince = nowS; } else updateSince = 0;
            P::Inputs in;
            in.now = nowS * 1000; in.loopAt = loopAt * 1000; in.updateRunning = update; in.updateSince = updateSince * 1000;
            in.wifiExpected = true; in.wifiDownSince = wifiDown * 1000;
            in.brokerExpected = brokerSeen; in.brokerDownSince = brokerDown * 1000;
            in.gatewayProbeArmed = armed; in.gatewayProbeFailures = probeFailures; in.networkQuietSince = quiet * 1000;
            in.wifiLostRestarts = wifiRestarts; in.networkDeadRestarts = deadRestarts;
            in.bluetoothExpected = true; in.bluetoothQuietSince = btQuiet * 1000; in.bluetoothRestarts = btRestarts;
            const auto reason = P::decide(in);
            // How long the fault has been visible in this boot.
            const uint64_t visibleS = fault == 1 ? (wifiDown ? nowS - wifiDown : 0) : fault == 2 ? (brokerDown ? nowS - brokerDown : 0)
                : fault == 4 ? nowS - loopAt : fault == 5 ? (updateSince ? nowS - updateSince : 0) : fault == 6 ? nowS - btQuiet : 0;
            const uint64_t faultFor = visibleS * 1000;
            if (!fault) EXPECT(reason == P::Reason::none, "sup_restart_healthy", "restart %s while healthy", P::name(reason));
            if (update) EXPECT(reason == P::Reason::none || (reason == P::Reason::updateStuck && faultFor >= P::updateMaxMs), "sup_restart_during_update",
                               "%s during an update of %" PRIu64 " s", P::name(reason), faultFor / 1000);
            // Liveness: a persisting fault restarts in time (5 s supervisor cadence + margin).
            const uint64_t margin = 10000;
            if (fault == 1 && faultFor > P::backoff(P::wifiLostMs, wifiRestarts) + margin) fail("sup_wifi_no_restart", "wifi down %" PRIu64 " s", faultFor / 1000);
            if (fault == 2 && faultFor > P::brokerLostMs + margin) fail("sup_broker_no_restart", "broker down %" PRIu64 " s", faultFor / 1000);
            if (fault == 4 && faultFor > P::loopStallMs + margin) fail("sup_loop_no_restart", "loop stalled %" PRIu64 " s", faultFor / 1000);
            if (fault == 5 && faultFor > P::updateMaxMs + margin) fail("sup_update_no_restart", "update stuck %" PRIu64 " s", faultFor / 1000);
            if (fault == 6 && btRestarts < P::maximumBackoff && faultFor > P::backoff(P::bluetoothSilentMs, btRestarts) + margin)
                fail("sup_bt_no_restart", "bt silent %" PRIu64 " s", faultFor / 1000);
            if (reason == P::Reason::none) {
                if (up > P::networkStableMs && fault != 1) wifiRestarts = 0; // the network held after this boot
                if (up > P::networkStableMs && fault != 3) deadRestarts = 0;
                continue;
            }
            if (fault == 4) EXPECT(reason == P::Reason::loopStall, "sup_reason", "loop stall gave %s", P::name(reason));
            count(std::string("sup_restart_") + P::name(reason));
            // Consecutive restarts of a kind (BlackBox).
            if (reason == P::Reason::wifiLost) wifiRestarts = uint8_t(std::min(255, wifiRestarts + 1));
            if (reason == P::Reason::networkDead) deadRestarts = uint8_t(std::min(255, deadRestarts + 1));
            if (reason == P::Reason::bluetoothSilent) btRestarts = uint8_t(std::min(255, btRestarts + 1));
            if (fault == 4 || fault == 5) { fault = 0; nextEvent = wall + uint64_t(expo(18 * 3600.0) * 1000); } // a restart cures a stuck loop/update
            restarted = true;
        }
    }
    counters[ctx.scenario + ":boots"] = boots;
}

// ============================================================================
// Payload sizes for large and worst-case valid plans.
// ============================================================================
void sizesScenario() {
    for (int variant = 0; variant < 3; ++variant) {
        RoomPlan plan;
        plan.revision = 12; plan.mode = RoomPlan::Mode::shadow;
        const char* label = variant == 0 ? "realistic_8_rooms" : variant == 1 ? "worst_case_printable" : "worst_case_escaped_names";
        for (size_t i = 0; i < RoomPlan::maxRooms; ++i) {
            RoomPlan::Room r;
            if (variant == 0) {
                r.id = "kamer_" + std::to_string(i); r.name = "Slaapkamer " + std::to_string(i);
                r.sources = {{RoomPlan::SourceType::ha, "sensor.slaapkamer_" + std::to_string(i) + "_temperature"}, {RoomPlan::SourceType::ble, "a4c13800000" + std::to_string(i)}};
                r.setpointEntity = "climate.slaapkamer_" + std::to_string(i);
                r.schedule = weekProgram({{390, 2050}, {480, 1900}, {1020, 2050}, {1350, 1800}}, {{480, 2100}, {1380, 1800}});
            } else {
                r.id = std::string(31, 'r') + char('0' + i);
                r.name.clear();
                if (variant == 1) for (int k = 0; k < 20; ++k) r.name += "\xC3\xA9"; // 40 bytes of UTF-8
                else r.name = std::string(40, '"');                                // 40 bytes, each escaped
                for (int s = 0; s < 4; ++s) r.sources.push_back({RoomPlan::SourceType::ha, "sensor." + std::string(68, char('a' + i)) + "_" + std::to_string(s) + std::string(2, 'x')});
                r.setpointEntity = "climate." + std::string(72, char('a' + i));
            }
            r.state = RoomDemand::State::active;
            plan.rooms.push_back(r);
        }
        const auto raw = plan.json();
        RoomPlan parsed;
        cJSON* back = parseBack(raw);
        const char* error = back ? RoomPlan::parse(back, parsed) : "invalid_json";
        cJSON_Delete(back);
        observe(std::string("plan_bytes_") + label, std::to_string(raw.size()) + " B (store limit " + std::to_string(ControlPartitionBudget::configBytes - 1) + " B)" + (error ? std::string(", parse error ") + error : std::string()));
        if (raw.size() + 1 > ControlPartitionBudget::configBytes)
            observe(std::string("plan_too_large_") + label, "a valid plan of " + std::to_string(raw.size()) + " B is refused with plan_too_large");
        if (error) continue;
        RoomEngine engine; engine.setPlan(parsed);
        uint64_t now = 1000000;
        for (size_t i = 0; i < parsed.rooms.size(); ++i) for (const auto& s : parsed.rooms[i].sources) {
            if (s.type == RoomPlan::SourceType::ha) engine.haState(s.id, int16_t(-1234), int16_t(2150), now);
            else engine.bleReading(s.id, int16_t(-1234), now);
        }
        engine.haState(parsed.rooms[0].setpointEntity, int16_t(2050), int16_t(2150), now);
        engine.step(now, uint32_t(1789907690));
        cJSON* root = engine.json();
        // + 8 BLE sensors with 40-byte names, burner, shadow, active, ha (as heatingStatusJson(true)).
        cJSON* sensors = cJSON_AddArrayToObject(root, "ble_sensors");
        for (int i = 0; i < 8; ++i) {
            cJSON* s = cJSON_CreateObject(); cJSON_AddItemToArray(sensors, s);
            cJSON_AddStringToObject(s, "id", "a4c138000001");
            cJSON_AddStringToObject(s, "name", variant ? std::string(40, 'n').c_str() : "Thermometer 1");
            cJSON_AddStringToObject(s, "profile", "pvvx_thermometer");
            cJSON_AddNumberToObject(s, "temperature", -12.34); cJSON_AddNumberToObject(s, "humidity", 55.23);
            cJSON_AddNumberToObject(s, "battery", 100); cJSON_AddNumberToObject(s, "age_s", 899);
        }
        cJSON* burner = cJSON_AddObjectToObject(root, "burner");
        cJSON_AddNumberToObject(burner, "starts_last_hour", 24); cJSON_AddNumberToObject(burner, "heating_starts_last_hour", 24); cJSON_AddBoolToObject(burner, "short_cycling", true);
        ShadowComparison shadow;
        for (int k = 0; k < 9000; ++k) shadow.sample(uint64_t(k) * 10000, uint32_t(1789907690 + k * 10), {k % 40 < 20, uint8_t(30 + k % 30), FlowDemand::Reason::heating}, uint8_t(k % 50 < 25 ? 40 : 0));
        cJSON_AddItemToObject(root, "shadow", shadow.json());
        ActiveHeatGuard guard; ActiveHeatGuard::Inputs in; in.mode = RoomPlan::Mode::active; in.foreign = ActiveHeatGuard::Foreign{0x17, 5};
        guard.confirm(1, true); guard.step(1000, in); guard.transmitted(1000, true);
        cJSON* active = guard.json(2000000000ull); cJSON_AddBoolToObject(active, "enabled", true); cJSON_AddItemToObject(root, "active", active);
        addHaLink(root, uint64_t(1), 4000000000ull, true);
        compactHeatingTelemetry(root);
        const auto text = printed(root);
        cJSON_Delete(root);
        checkPayload((std::string("mqtt_heating_") + label).c_str(), text, variant == 0 ? heatingTelemetryMaxBytes : 0);
        observe(std::string("mqtt_heating_bytes_") + label, std::to_string(text.size()) + " B (limit " + std::to_string(heatingTelemetryMaxBytes) + " B)");
        if (text.size() > heatingTelemetryMaxBytes)
            fail(std::string("mqtt_heating_exceeds_limit_") + label, "a valid plan gives a %zu B fw/telemetry/heating payload: ModernTransport drops it (heatingTelemetryDropped) and HA gets no heating telemetry", text.size());
    }
}

// ============================================================================
// Deterministic reproducers of findings (run with --scenario=repro).
// ============================================================================
void reproScenario() {
    // R1: ActiveHeatGuard leaves the stop window although no zero was ever delivered.
    {
        ActiveHeatGuard g;
        ActiveHeatGuard::Inputs in;
        in.mode = RoomPlan::Mode::active; in.uptimeMs = 200000; in.routeReady = true; in.boilerLimitC = 60;
        RoomDemand::Result r; r.status = RoomDemand::Status::ok; r.temperature = 1900; r.setpoint = 2100; r.usable = true; r.source = 0;
        in.rooms.add(r);
        in.request = {true, 45, FlowDemand::Reason::heating};
        uint64_t now = 200000;
        g.confirm(now, true);
        uint8_t atBoiler = 0;
        for (int i = 0; i < 6; ++i) { now += 10000; const auto c = g.step(now, in); if (c.send) { g.transmitted(now, true); atBoiler = c.flowC; } }
        EXPECT(atBoiler == 45, "repro_setup", "setup: boiler holds %u", atBoiler);
        g.confirm(now, false); // the owner withdraws the handover (or the plan goes back to shadow)
        std::string trace;
        for (int i = 0; i < 9; ++i) {
            now += 10000;
            const auto c = g.step(now, in);
            trace += std::string(ActiveHeatGuard::name(g.state())) + (c.send ? "/send0" : "") + " ";
            if (c.send) g.transmitted(now, false); // the write fails (bus busy, boiler not polling 0x0B)
        }
        if (!g.claimsBoiler() && atBoiler > 0)
            fail("repro_guard_stop_without_zero", "after 60 s of failed zero writes the guard is %s and stops sending: the boiler keeps %u degC. Trace: %s",
                 ActiveHeatGuard::name(g.state()), atBoiler, trace.c_str());
    }
    // R3: DhwEpisodes: a reheat right after a short tap is counted as a second tap.
    {
        DhwEpisodes d;
        uint64_t t = 0;
        const auto report = [&](uint8_t state, int32_t centi) { t += 10000; d.flow(25); d.temperature(centi, t - 5000); d.state(state, t); };
        for (int i = 0; i < 30; ++i) report(0x00, 5000);                 // idle, plate exchanger at 50 degC
        for (int c : {3500, 2200, 2000, 2000, 2000, 2000}) report(0x0A, c); // a 1-minute tap: cold mains water
        report(0x00, 2000);                                               // tap over
        for (int c : {2000, 2600, 3300, 4000, 4600, 5000, 5200}) report(0x0A, c); // keep warm reheats the exchanger
        report(0x00, 5200);
        const auto& today = d.today();
        if (today.count[DhwEpisodes::tapping] != 1 || today.count[DhwEpisodes::keepWarm] != 1)
            fail("repro_dhw_reheat_counted_as_tap", "one 60 s tap + one reheat 10 s later gives tapping=%u keep_warm=%u (the reheat's 2 min look-back reaches back before the tap)",
                 today.count[DhwEpisodes::tapping], today.count[DhwEpisodes::keepWarm]);
    }
    // R2: RoomEngine::json() under a failing allocation (ha_entities array).
    {
        RoomPlan p; RoomPlan::Room r; r.id = "a"; r.name = "A"; r.state = RoomDemand::State::active;
        r.sources = {{RoomPlan::SourceType::ha, "sensor.a"}}; p.rooms = {r};
        RoomEngine e; e.setPlan(p); e.step(1000, std::nullopt);
        cjCalls = 0; cjFailAt = 0; cJSON_Delete(e.json()); const long total = cjCalls;
        for (long k = 1; k <= total; ++k) {
            std::fflush(nullptr);
            const pid_t pid = fork();
            if (pid == 0) {
                const int fd = open("/dev/null", O_WRONLY);
                if (fd >= 0) { dup2(fd, 2); close(fd); }
                cjCalls = 0; cjFailAt = k; cJSON_Delete(e.json()); _exit(0);
            }
            int status = 0; waitpid(pid, &status, 0);
            if (!(WIFEXITED(status) && WEXITSTATUS(status) == 0))
                fail("repro_room_engine_json_oom", "RoomEngine::json() crashes when cJSON allocation #%ld of %ld fails (cJSON_AddArrayToObject(root, \"ha_entities\") returns null; addEntity reads entities->child)", k, total);
        }
    }
}

void usage() {
    std::fprintf(stderr, "soak --scenario=chain|guard|flow|supervisor|sizes|repro [--name=] [--tz=POSIX] [--start=YYYY-MM-DDTHH:MM:SSZ] [--days=60]\n"
                         "     [--uptime0=ms] [--seed=n] [--step-ms=10000] [--mqtt-s=300] [--learned-s=900] [--full-s=3600] [--edit-h=4]\n"
                         "     [--live-dhw-flow] [--boiler-outdoor] [--no-oom] [--no-active] [--out=/tmp/soak]\n");
}

} // namespace

int main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        const auto value = [&](const char* key) -> const char* { const size_t n = std::strlen(key); return a.compare(0, n, key) == 0 ? a.c_str() + n : nullptr; };
        if (const char* v = value("--scenario=")) opt.scenario = v;
        else if (const char* v = value("--name=")) opt.name = v;
        else if (const char* v = value("--tz=")) opt.tz = v;
        else if (const char* v = value("--start=")) opt.startUtc = parseIsoUtc(v);
        else if (const char* v = value("--days=")) opt.days = std::atof(v);
        else if (const char* v = value("--uptime0=")) opt.uptime0 = std::strtoull(v, nullptr, 0);
        else if (const char* v = value("--seed=")) opt.seed = std::strtoull(v, nullptr, 0);
        else if (const char* v = value("--step-ms=")) opt.stepMs = uint32_t(std::atoi(v));
        else if (const char* v = value("--mqtt-s=")) opt.mqttEveryS = uint32_t(std::atoi(v));
        else if (const char* v = value("--learned-s=")) opt.learnedEveryS = uint32_t(std::atoi(v));
        else if (const char* v = value("--full-s=")) opt.fullEveryS = uint32_t(std::atoi(v));
        else if (const char* v = value("--edit-h=")) opt.editEveryH = std::atof(v);
        else if (const char* v = value("--out=")) opt.outDir = v;
        else if (a == "--live-dhw-flow") opt.liveDhwFlow = true;
        else if (a == "--boiler-outdoor") opt.boilerOutdoor = true;
        else if (a == "--no-oom") opt.oom = false;
        else if (a == "--no-active") opt.activePhases = false;
        else { usage(); return 2; }
    }
    if (opt.stepMs < 1000 || opt.stepMs % 1000 || opt.stepMs > 30000) { std::fprintf(stderr, "--step-ms must be whole seconds in 1..30 s\n"); return 2; }
    cJSON_Hooks hooks{cjMalloc, cjFree};
    cJSON_InitHooks(&hooks);
    rng.seed(opt.seed);
    setTz(opt.tz);
    ctx.scenario = opt.name.empty() ? opt.scenario : opt.name;
    ctx.startUtc = ctx.utc = opt.startUtc;
    std::printf("soak %s: scenario %s, TZ %s, start %s (%s), %.1f days, step %u ms, uptime0 %" PRIu64 " ms, seed %" PRIu64 "\n", ctx.scenario.c_str(), opt.scenario.c_str(),
                opt.tz.c_str(), isoUtc(opt.startUtc).c_str(), isoLocal(opt.startUtc).c_str(), opt.days, opt.stepMs, opt.uptime0, opt.seed);
    const auto t0 = std::chrono::steady_clock::now();
    if (opt.scenario == "chain") { Chain chain(opt); chain.run(); }
    else if (opt.scenario == "guard") guardScenario();
    else if (opt.scenario == "flow") flowScenario();
    else if (opt.scenario == "supervisor") supervisorScenario();
    else if (opt.scenario == "sizes") sizesScenario();
    else if (opt.scenario == "repro") reproScenario();
    else { usage(); return 2; }
    const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("---- %s: %.1f s wall\n", ctx.scenario.c_str(), seconds);
    for (const auto& [k, s] : sizes) std::printf("size  %-40s max %6zu B over %zu/%zu%s\n", k.c_str(), s.max, s.over, s.n, s.limit ? (" (limit " + std::to_string(s.limit) + " B)").c_str() : "");
    for (const auto& [k, v] : counters) std::printf("count %-50s %" PRIu64 "\n", k.c_str(), v);
    for (const auto& [k, v] : observations) std::printf("note  %-50s %s\n", k.c_str(), v.c_str());
    for (const auto& [k, c] : localtimeStats)
        std::printf("tz    %-40s localtime_r calls max %6" PRIu64 " (at %s) mean %.1f\n", k.c_str(), c.max, isoLocal(c.maxUtc).c_str(), c.n ? double(c.sum) / double(c.n) : 0.0);
    for (const auto& [k, f] : failures) std::printf("FAIL  %-50s x%" PRIu64 ": %s\n", k.c_str(), f.count, f.first.c_str());
    std::printf("RESULT %s %s (%zu failing invariants)\n", ctx.scenario.c_str(), failures.empty() ? "PASS" : "FAIL", failures.size());
    return failures.empty() ? 0 : 1;
}
