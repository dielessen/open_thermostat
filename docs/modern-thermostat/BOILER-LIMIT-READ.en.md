# Review: the E32 reads the boiler's heating limit (0x16) itself

**Status:** beta.19 candidate, 29 October 2026, host-tested only (no bus
recording yet). Owner decision of 29 October: active heating takes its ceiling
from a value the boiler itself reports, not from a stored copy.

## Why

Active heating never asks for more than `min(plan maximum, 80 °C, boiler limit)`.
The boiler limit is the Classic UBAParameters 0x16 heating temperature (offset 1).
Up to beta.18 the E32 only knew it when another master asked for it (the tado)
or after the owner pressed "Read boiler settings". Once the tado is disconnected,
nobody asks any more, so after every E32 restart the limit stayed unknown and
active heating (and frost protection) stayed off (`boiler_limit_unknown`).

## The new bus traffic

| Item | Value |
| --- | --- |
| Frame | `0B 88 16 00 02 CRC`: the E32 (0x0B) reads 2 bytes of 0x16 from offset 0 at the boiler (0x08, read bit set) |
| Encoder | `ClassicConfigurationRead::encode`, the same fixed frame as the attended configuration read |
| Answer | `08 0B 16 00 <heating enabled> <heating temperature> CRC`, closed by the existing private transaction (`ManualClassicTransaction`: exact 7-byte reply from 0x08, 200 ms window, completion byte 0x0B) |
| When | At the first poll of 0x0B after boot; then again once no usable 0x16 report was seen for 6 h (`BoilerLimitRead::refreshMs`). A report the boiler sends to another master (the tado's own read) also counts, so with the tado connected the E32 usually sends nothing |
| Retry | An unanswered or failed read is retried after 5 min (`retryMs`), at most 12 frames per hour while the boiler stays silent |
| Rate when healthy | 1 frame per boot plus 1 per 6 h (4 per day) |
| Route | Only at the boiler's poll of 0x0B, through `transmitManualFrame<true>` (the reviewed manual UART write with echo check) |
| Gates | `board::emsBoilerLimitReadAllowed` (E32V2 only, equal to the reviewed manual route); the reviewed bus identity (0x0B, no source conflict, healthy UART, no transport fault or pending reset); Classic boiler profile; no attended trial, configuration read or settings write running |
| Priority | A pending active-heat 0x1A command takes the poll first; the read only uses a poll without one |
| Not affected | `board::emsActiveHeatAllowed` stays false; boiler settings writes stay disabled; no legacy queue, no EMS+ (0xE6) read |

Source: `src/EMS/BoilerLimitRead.h`, wired in `EmsController::processBoilerTestPoll`.

## What the value does

- `ActiveHeatEnvelope::limitC` uses the latest usable 0x16 report of this boot
  (Classic profile, `reported` quality, type 0x16). The ceiling stays
  `min(plan maximum, 80, limit)` in both `ActiveHeatGuard` and the poll driver.
- Without a value, active heating sends no positive request: the guard's
  command reason is `boiler_limit_unknown` and the warning of the same name is
  set while it owns the boiler (it then asks zero).
- A changed setting at the boiler is picked up by the next 6-hourly read.

## Where it is visible

`/status/heating` and MQTT `fw/telemetry/heating`, in the `active` block:

```json
"boiler_limit": {"flow_c": 60, "age_s": 1234, "reads": 1}
```

`flow_c` is today's boiler maximum (null while unknown), `age_s` the age of the
report it comes from (null while unknown), `reads` the E32's own read requests
this boot.

## Evidence

- Native: `test_boiler_limit_read.cpp` (exact frame, admitted by the private
  transaction, boot read, 6 h refresh, 5 min retry, another master's report
  counts, no write without the route or the build permission, out-of-range
  values are no limit).
- Soak: `test/soak` scenario `active`, case `boiler_limit` (no heat while the
  boiler does not answer, retries, heat once it answers, a lowered setting
  applied by the next refresh) and the read-count bound in every case.
- Still to do on the device: a bus recording after a restart without the tado
  that shows one `0B 88 16 00 02` and the boiler's answer, then nothing for 6 h.
