#pragma once
#include <array>
#include <cstdint>
#include <string_view>

namespace heating::control {
// Pure bounded policy; entropy comes from the E32 hardware RNG in REST, not here.
// Sessions are deliberately boot-local: no credentials/tokens written to NVS.
class WebAuthSession {
public:
    static constexpr std::size_t maximumSessions = 4;
    static constexpr uint64_t lifetimeMs = 7ULL * 24 * 60 * 60 * 1000;
    static constexpr uint64_t idleTimeoutMs = 30ULL * 60 * 1000;
    static constexpr const char *cookieName = "OTSESSION";
    enum class SettingsScope : uint8_t { network=0, bluetooth=1 };
    struct SettingsFence { std::array<char,65> hash{}, tag{}; };
    struct Session {
        std::array<char,65> token{}, csrf{};
        // Boot/session-local readback fence. Only the random tag is returned;
        // never expose a hash of settings containing broker/weather secrets.
        std::array<SettingsFence,2> settings{};
        uint64_t issued = 0, until = 0, lastSeen = 0;
        bool occupied = false;
    };
    static bool hexToken(std::string_view value) {
        if (value.size() != 64) return false;
        for (char c : value) if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
        return true;
    }
    static bool equal(std::string_view a, std::string_view b) {
        if (a.size() != b.size()) return false;
        unsigned char difference = 0;
        for (std::size_t i = 0; i < a.size(); ++i) difference |= static_cast<unsigned char>(a[i] ^ b[i]);
        return difference == 0;
    }
    // Refuse duplicate session cookies instead of selecting an ambiguous first/last.
    static std::string_view cookieToken(std::string_view header) {
        if (header.size() > 2048) return {};
        for (unsigned char c : header) if (c < 0x20 || c == 0x7f) return {};
        std::string_view found;
        bool seen = false;
        while (!header.empty()) {
            const auto separator = header.find(';');
            auto part = header.substr(0,separator);
            while (!part.empty() && part.front() == ' ') part.remove_prefix(1);
            while (!part.empty() && part.back() == ' ') part.remove_suffix(1);
            const auto equals = part.find('=');
            if (part.substr(0,equals) == cookieName) {
                if (seen || equals == std::string_view::npos) return {};
                seen = true; found = part.substr(equals + 1);
                if (!hexToken(found)) return {};
            }
            if (separator == std::string_view::npos) break;
            header.remove_prefix(separator + 1);
        }
        return found;
    }
    const Session *find(std::string_view token,uint64_t now) const {
        if (!hexToken(token)) return nullptr;
        for (const auto &session : sessions_) if (live(session,now) && equal(token,view(session.token))) return &session;
        return nullptr;
    }
    // Call only after the HTTP method, origin, authentication and CSRF gates.
    // Lookups alone must not renew sessions or revive an expired token.
    bool touch(std::string_view token,uint64_t now) {
        if (!hexToken(token)) return false;
        for (auto &session : sessions_) if (live(session,now) && equal(token,view(session.token))) {
            session.lastSeen = now;
            return true;
        }
        return false;
    }
    uint64_t remainingMs(std::string_view token,uint64_t now) const {
        const auto* session = find(token,now);
        if (!session) return 0;
        const auto idleRemaining = idleTimeoutMs-(now-session->lastSeen);
        return session->until-now < idleRemaining ? session->until-now : idleRemaining;
    }
    bool csrf(std::string_view token,std::string_view proof,uint64_t now) const {
        const auto *session = find(token,now);
        return session && hexToken(proof) && equal(proof,view(session->csrf));
    }
    std::string_view settingsReadback(std::string_view token,std::string_view hash,
            std::string_view randomTag,uint64_t now,SettingsScope scope=SettingsScope::network) {
        if (!validScope(scope)||!hexToken(hash)||!hexToken(randomTag))return {};
        const auto selected=static_cast<std::size_t>(scope);
        for(const auto& session:sessions_) {
            if(!live(session,now))continue;
            if(equal(randomTag,view(session.token))||equal(randomTag,view(session.csrf)))return {};
            for(std::size_t i=0;i<session.settings.size();++i)
                if(equal(randomTag,view(session.settings[i].tag))
                        && !(equal(token,view(session.token))&&i==selected))return {};
        }
        for(auto& session:sessions_) {
            if(!live(session,now)||!equal(token,view(session.token)))continue;
            auto& fence=session.settings[selected];
            if(hexToken(view(fence.tag))&&equal(hash,view(fence.hash)))return view(fence.tag);
            if(equal(randomTag,view(fence.tag)))return {};
            for(std::size_t i=0;i<64;++i){fence.hash[i]=hash[i];fence.tag[i]=randomTag[i];}
            return view(fence.tag);
        }
        return {};
    }
    bool settingsReadbackMatches(std::string_view token,std::string_view quotedTag,
            std::string_view currentHash,uint64_t now,SettingsScope scope=SettingsScope::network) const {
        const auto* session=find(token,now);
        if(!session||!validScope(scope))return false;
        const auto& fence=session->settings[static_cast<std::size_t>(scope)];
        return hexToken(currentHash)&&quotedTag.size()==66&&quotedTag.front()=='"'&&quotedTag.back()=='"'
            &&hexToken(view(fence.tag))&&equal(quotedTag.substr(1,64),view(fence.tag))&&equal(currentHash,view(fence.hash));
    }
    const Session *issue(std::string_view token,std::string_view proof,uint64_t now,std::string_view replacing = {}, bool revokeAll = false) {
        if (!hexToken(token) || !hexToken(proof) || equal(token,proof) || now > UINT64_MAX-lifetimeMs) return nullptr;
        Session *slot = nullptr;
        for (auto &session : sessions_) {
            // Never issue a token/proof that aliases another live session.
            if (live(session,now) && (equal(token,view(session.token)) || equal(proof,view(session.csrf)) ||
                equal(token,view(session.csrf)) || equal(proof,view(session.token)) ||
                tagAliases(session,token) || tagAliases(session,proof))) return nullptr;
            if (live(session,now) && equal(replacing,view(session.token))) slot = &session;
        }
        // Only the credential-verified, explicit recovery route may request this.
        // Validate entropy, clock and aliases above before invalidating any session.
        if (revokeAll) { sessions_ = {}; slot = &sessions_[0]; }
        if (!slot) for (auto &session : sessions_) if (!live(session,now)) { slot = &session; break; }
        if (!slot) return nullptr; // Do not evict another browser to admit a new one.
        *slot = Session{};
        for (std::size_t i = 0; i < 64; ++i) { slot->token[i] = token[i]; slot->csrf[i] = proof[i]; }
        slot->issued = now; slot->lastSeen = now; slot->until = now+lifetimeMs; slot->occupied = true;
        return slot;
    }
    void revoke(std::string_view token) {
        for (auto &session : sessions_) if (equal(token,view(session.token))) session = Session{};
    }
    // After a password change: every other browser and Home Assistant must sign in again.
    void revokeOthers(std::string_view keep) {
        for (auto &session : sessions_) if (!hexToken(keep) || !equal(keep,view(session.token))) session = Session{};
    }
    bool loginAllowed(uint64_t now) const {
        return failed_ < 5 || (now >= failedFrom_ && now-failedFrom_ >= 30000);
    }
    void loginFailed(uint64_t now) {
        if (!failed_ || now < failedFrom_ || now-failedFrom_ >= 30000) { failed_ = 0; failedFrom_ = now; }
        if (failed_ < 5) ++failed_;
    }
    void loginSucceeded() { failed_ = 0; }
    static std::string_view view(const std::array<char,65> &s) { return {s.data(),64}; }
private:
    static bool validScope(SettingsScope scope) {return scope==SettingsScope::network||scope==SettingsScope::bluetooth;}
    static bool tagAliases(const Session& session,std::string_view value) {
        for(const auto& fence:session.settings)if(equal(value,view(fence.tag)))return true;
        return false;
    }
    static bool live(const Session &session,uint64_t now) {
        return session.occupied && now >= session.issued && now < session.until
            && now >= session.lastSeen && now-session.lastSeen < idleTimeoutMs;
    }
    std::array<Session,maximumSessions> sessions_{};
    uint64_t failedFrom_ = 0;
    unsigned failed_ = 0;
};

static_assert(sizeof(WebAuthSession)<=2048,"Web session memory budget changed");
inline bool publicAuthResource(std::string_view path) {
    return path == "/login" || path == "/login.js" || path == "/ui-language.js" || path == "/ui-messages.js" || path == "/auth-client.js" || path == "/auth/login";
}
inline bool loginDocument(std::string_view path) {
    return path == "/" || path == "/index.html" || path == "/recovery" || path == "/setup" || path == "/setup.html";
}
enum class WebAuthDecision { allow, redirect_login, authentication_required, csrf_required };
// Called only AFTER socket-local AP, method, origin and initialization checks.
inline WebAuthDecision webAuthDecision(const WebAuthSession &sessions,std::string_view path,
    std::string_view method,std::string_view token,std::string_view proof,uint64_t now,bool setupException) {
    if (publicAuthResource(path) || setupException) return WebAuthDecision::allow;
    if (!sessions.find(token,now)) return method == "GET" && loginDocument(path) ?
        WebAuthDecision::redirect_login : WebAuthDecision::authentication_required;
    if (method != "GET" && !sessions.csrf(token,proof,now)) return WebAuthDecision::csrf_required;
    return WebAuthDecision::allow;
}
}
