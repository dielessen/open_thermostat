#pragma once
#include <cstdlib>
#include <ctime>
#include <string>
// The process TZ for one test, as configTzTime() sets it on the device from the
// network settings; the previous TZ returns afterwards. Local-time code then
// gives the same results on any host time zone (CI runs in UTC).
class ScopedTz {
public:
    static constexpr const char* amsterdam = "CET-1CEST-2,M3.5.0/02:00:00,M10.5.0/03:00:00"; // packaged default
    static constexpr const char* london = "GMT0BST,M3.5.0/1,M10.5.0";
    static constexpr const char* newYork = "EST5EDT,M3.2.0,M11.1.0";
    explicit ScopedTz(const char* tz) {
        const char* old = std::getenv("TZ");
        had_ = old != nullptr;
        if (old) saved_ = old;
        setenv("TZ", tz, 1); tzset();
    }
    ~ScopedTz() {
        if (had_) setenv("TZ", saved_.c_str(), 1); else unsetenv("TZ");
        tzset();
    }
    ScopedTz(const ScopedTz&) = delete;
    ScopedTz& operator=(const ScopedTz&) = delete;
private:
    std::string saved_;
    bool had_ = false;
};
