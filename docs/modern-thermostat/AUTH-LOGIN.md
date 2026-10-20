# Mark11732 — web login diagnosis (separate from graph validators)

## Observed, not inferred

Read-only native HTTP GET window: **2026-10-20 19:24:10.610–19:24:10.940 UTC** (21:24 CEST), the owner's local E32.

- Anonymous `/status/version`: HTTP401, `WWW-Authenticate: Digest realm="OpenThermostat"`; **not Basic**.
- Proper standard Python `HTTPDigestAuthHandler`: `/status/version`, `/config/device`, `/config/rooms` all200. The already configured owner-selected login was accepted. No credential values reproduced here.
- Runtime version label: `v0.1.0-e32v2-alpha.4`. GET version SHA256 `fddb73844e50612470cb94277e0fd077a3f6d0ee2274c963b6c432be2fb31e46`. Public release metadata independently reports that tag published2026-10-20T12:10:08Z.
- The current endpoint also reports SDK-looking project/date metadata (`arduino-lib-builder`, March2024). It does **not** expose a trustworthy source commit; do not label the running binary e16c4e6 or this candidate.
- Native device/settings GETs were privately snapshotted. Network addresses, config fingerprints and private settings are excluded from this public source document. Settings and credentials were not changed.

## Proven source mechanism; mobile incident still unproven

Current `REST.h::authorize()` uses native Arduino Digest challenges. The pinned Arduino ESP32 **2.0.17** `WebServer.cpp` lines170–177 compares each Digest nonce/opaque to the **single server object's latest pair**. Lines227–245 generate a new pair on **every** challenge. Thus challengeA → challengeB → responseA fails the exact implemented nonce comparison. Parallel pages/tabs/devices can invalidate each other's pending authentication. This is a concrete source-level mechanism, not proof of the precise mobile event: no mobile request capture/browser URL/cache record was available, and the proper Digest client succeeded during our observation.

Pinned maintained reference: <https://github.com/espressif/arduino-esp32/blob/2.0.17/libraries/WebServer/src/WebServer.cpp#L130> and <https://github.com/espressif/arduino-esp32/blob/2.0.17/libraries/WebServer/src/WebServer.cpp#L227>.

No claim that the password is wrong, that the running device uses Basic auth, or that Mark's browser is definitively at fault.

## Repair direction

Replace the E32 challenge/cache interaction with one ordinary English login page and bounded independent boot-local cookie sessions on the **existing WebServer**. No new backend/service. Keep configured credentials, AP-only onboarding interface checks, method/origin validation, updater-busy gates, HA-managed writer exclusion and all TX/output locks. Add explicit CSRF proofs on mutations including uploads and recovery. Session reads do not renew the absolute deadline; logout revokes only that browser. Failed mutation is never automatically replayed. Add source/web hash to future version readback.

Raw source/anonymous headers and redacted observations are preserved in the separate tracking dossier. Private config snapshots stay0700/0600 and are excluded from public manifests/packages.

---

# Auth11732 — exact acceptance and release boundary

## Source acceptance in this package

Actual shipped C++ session/admission core is compiled and tested with real googletest; existing HTTP/AP/modern-writer policy tests retained. Actual shipped JavaScript is executed under official Node with explicit DOM/network unit boundaries. Exact native REST is type-checked with the pinned Xtensa compiler/SDK, not replacement headers. Full firmware build result is reported separately: no source/type-check result is silently called a link/board/browser PASS.

No WebSocket or SSE implementation exists in this webstack; these are N/A, not invented session tests. Existing status polling, fetch writes, jQuery GET fragment navigation and native XHR upload/recovery paths are covered by source and unit checks. The latter require a later real browser/device acceptance.

## Later, after source review and separately authorized build/install

Device must remain disconnected from EMS/ketel and normal Tado unchanged. No heating GO follows from login tests.

1. Record installed version + new `source`/`web_sha256`, prior private device/rooms/programs settings and actual addressing. Build all required target/recovery checks and retain the prior available release image/settings before any authorized update. Respect the existing original-flash-backup waiver; do not turn this into a new full-flash-backup permission/input gate.
2. On real desktop and real mobile, open the same stable LAN device address. Anonymous root must show the English login form, not an OS browser authentication dialog. API/config GET without cookie returns401 JSON with **no** `WWW-Authenticate`; mutating endpoints require both session and CSRF.
3. Correct existing login succeeds, incorrect login stays in the form with an error; no prompt loop. The login client does not put credentials in URL/history. Unredacted native HTTP verbose logging (CORE_DEBUG_LEVEL>=5) is compile-time blocked; the existing owner-requested USB startup credential display is unchanged. Five failures within30seconds temporarily rate-limit new logins only; existing sessions keep working.
4. Keep desktop and mobile sessions active concurrently; reload pages/assets, open Rooms/Programs/Network/Update and navigate from two tabs. Cached legacy HTTP Authorization headers, if still sent by the browser, confer no access and must not trigger a new challenge.
5. Close/reopen browser: persistent cookie remains valid on the **same running boot**, at most7days absolute. Reload is not a new login. Device reboot intentionally requires one new form login; no persistence/NVS claim across reboot. Test mode/network partition and recovery do not silently revive a session.
6. Sign out on desktop: its subsequent API requests fail; mobile remains signed in. After expiry or invalid session, fetch **and jQuery fragment load** return to login once; a failed mutation/upload is not replayed. Network/503 errors alone must not sign a user out.
7. Check no cookie/token appears via ordinary JS (HttpOnly); CSRF is retrieved only through authenticated `/auth/session`. Cross-site/missing/incorrect CSRF mutation is rejected, including OTA/recovery upload. No arbitrary JSON/config write should be used merely to test login.
8. Test AP-only setup on its real local interface/canonical host; the LAN cannot obtain that exception by a forged Host. Existing settings, HA-managed mode/writer gates and update-busy rejection stay unchanged. Test recovery/upload only in an independently prepared safe update bench, not during this task.
9. Compare settings/programs and update/TX-lock/rollback proofs. Only then mark physical mobile/desktop acceptance complete.

## API migration (no action executed)

Native admin clients use POST `/auth/login` with exactly two form fields `username`,`password`, content-type `application/x-www-form-urlencoded`; retain the returned host-only cookie privately. GET `/auth/session` returns CSRF and remaining lifetime, never the cookie/password. Send `X-OpenThermostat-CSRF` with every mutation, including uploads and POST `/auth/logout`. GET reads use only the cookie. No legacy HTTP Basic/Digest fallback writer is kept. This concerns E32 admin HTTP only; HA MQTT wire/session/profile contracts are unchanged.

## Safety/limitations

Pinned Arduino HTTP parsing logs headers and bodies at VERBOSE. This candidate refuses that build mode explicitly, instead of silently leaking login bodies when framework tracing is enabled; ordinary application logging is not changed.

Existing local HTTP transport is not TLS; this fix does not claim confidentiality on an untrusted network. Host-only HttpOnly SameSite=Strict cookie, four simultaneous sessions,7days absolute; no active-session eviction. Boot-seeded mbedTLS CSPRNG is initialized before RF/ADC/I2S and retained without runtime entropy-source/radio changes. Cookie tokens and passwords are never written to NVS. Four live distinct browsers produce a clear capacity error, not random eviction. No new password policy or global HA language change.
