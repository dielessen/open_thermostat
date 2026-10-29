# Fuzz tests for external input

These harnesses feed random and mutated input to the E32 code that parses
data from outside the device: EMS bus frames, Bluetooth advertisements, JSON
from Home Assistant/MQTT and from the web pages. They run on the host with
libFuzzer, AddressSanitizer and UndefinedBehaviorSanitizer, so any
out-of-bounds access, use after free, leak, undefined behaviour, uncaught
exception, endless loop (`-timeout=2`) or broken invariant is a finding.
Nothing here contacts a device, the bus, a radio, a broker or GitHub.

| Harness | Production code under test |
| --- | --- |
| `fuzz_ems_frame` | `BreakFrameReader` with a continuous UART FIFO (reset/flush races included), the `EmsController::processTelegram` prefilters (`ManualBusIdentity`, `EmsPoll`), `EmsFrameQueue`, `EmsTelegram::fromRawData`, every observer `decodeTelegram` runs (`EmsDeviceInventory`, `ClassicBoilerMonitor`, `EmsEntityObserver` catalog, `ForeignBoilerRequest`, outdoor temperature, `RoomHeatObservation`, `readDeviceVersion`), the UBA* `logData` processors with a real formatting logger, `EmsMetrics` processors, all status JSON writers, and the encode/decode round trip. |
| `fuzz_ble_advert` | `decodeBleTemperatureAdvertisement`, `findBleServiceData`, `openBthomeV2` (fake CCM and real Mbed TLS CCM), pvvx BTHome and custom 0x181A, Shelly H&T and BLU TRV, MiBeacon v4/v5 envelope + objects, `BleDeviceDiscovery::remember` name hints and its status JSON, BLE address/bindkey text parsers. |
| `fuzz_ble_observer` | `ManagedBleObserver` state machine (capture queue, replay counters, clock faults, snapshots) with five bindings covering every profile, fake or real CCM. |
| `fuzz_ble_settings` | `parseControlJson(deviceSettings)`, `readManagedBleBindings`, `prepareManagedBleSettings`, public/committed projections, redact/retain, and the boot read-back of a saved candidate. |
| `fuzz_room_plan` | `POST /config/heating` and the flash copy (`RoomPlan::parse`, `RoomSchedule::parse`), the plan's JSON round trip, the MQTT `ha/heating_input` route (`control/HeatingInput.h`, the one `HeatingController` uses: room states, gas meter, gas price, outdoor, boiler power), `RoomEngine` steps and the `FlowLearner` with its status. |
| `fuzz_control_json` | `parseControlJson` in both modes: never accept more than 8 levels, 512 nodes, 8192 bytes or over-long strings. |
| `fuzz_shadow` | `ShadowController::receive/tick/connected` for all `ha/*` topics, with session placeholders so sequences get past the handshake. Every publication must be valid JSON. |
| `fuzz_boiler_services` | `BoilerTestService::action`, `ClassicBoilerSettingsService::request/poll/receive`, `ClassicConfigurationRead::request/poll/observe`, `WebAuthSession::cookieToken`, CSRF and `If-Match` checks. |

Input formats are described at the top of each `fuzz_*.cpp`. Seeds are in
`corpus/<harness>/`: the EMS seeds are real frames from the owner's boiler log
(`out/e32-hang-monitor/device-logs.jsonl`, 650 unique frames reduced to 91
seeds plus crafted EMS+ frames), the Bluetooth seeds include the owner's pvvx
adverts (`40 00 09 01 64 02 e1 07 03 af 16` and `40 00 07 0c a8 0c 10 01 11 01`,
service 0xFCD2, A4:C1:38:A3:E8:DB) and the public BTHome/MiBeacon test vectors,
and the JSON seeds come from the native tests. `dict/` holds libFuzzer
dictionaries with the field names of each protocol.

## Running

Linux or WSL with `clang`, `libmbedtls-dev` and the PlatformIO native
dependencies (`.pio/libdeps/native`, created by `pio test -e native`):

```sh
sudo apt-get install -y clang llvm libmbedtls-dev
test/fuzz/run.sh build                    # all harnesses -> /tmp/fz-build
test/fuzz/run.sh smoke 60                 # every harness 60 s, in parallel
test/fuzz/run.sh fuzz shadow 1800 4       # one harness, 30 min, 4 workers
test/fuzz/run.sh all 1500 3               # all harnesses, 25 min, 3 workers each
test/fuzz/run.sh repro ems_frame /tmp/fz-work/artifacts/ems_frame/crash-...
test/fuzz/run.sh cov room_plan            # line coverage of the grown corpus
```

`WORK` (default `/tmp/fz-work`) receives the grown corpus, crash files and logs;
the checked-in seeds are only read. A run exits non-zero when any crash,
timeout, leak or out-of-memory file was written to `$WORK/artifacts/`.
`OTFUZZ_VERBOSE=1` makes `fuzz_shadow` print every publication and
`fuzz_room_plan` print the parse result, which helps when writing seeds.

## CI smoke run

A short run is feasible. Building the eight harnesses takes about one to two
minutes; `run.sh smoke 60` then runs them side by side for 60 s, so the job
takes about three minutes on a 2-core runner. The harnesses do between ~400
(shadow) and ~36,000 (control_json) executions per second per core, so 60 s
replays every seed and finds shallow regressions. Deep bugs need the long runs
above.

The `fuzz-smoke` job in `.github/workflows/build.yml` does exactly this on
every push and gates E32 test releases. A finding fails the job with a public
annotation naming the harness, the artifact file and the input as hex (first
1500 bytes), and the artifacts and logs are kept as the `fuzz-smoke-findings`
workflow artifact. Save the hex to a file (`xxd -r -p`) and rerun it with
`test/fuzz/run.sh repro <harness> <file>`. `slow-unit-*` reports (an input
over 1 s) do not fail a run; hangs over 2 s do (`timeout-*`).

## Limits

- The host stack is 8 MB; the E32 loop task has 8 KB. Deep recursion that
  overflows the E32 stack does not fail here. `fuzz_control_json` checks the
  nesting limit that protects the control paths; raw `cJSON_Parse` callers
  are not bounded (see the fuzzing report).
- `fuzz_shadow` uses a constant hash so the fuzzer never has to forge a
  digest. SHA-256 and digest checks are therefore not under test.
- The fake CCM decryptor returns the ciphertext as plaintext so the decoders
  behind encryption get fuzzed; the real Mbed TLS path is fuzzed with the
  public test key (bit 2 of the first input byte).
- `ha/heating_input` is parsed and routed by `control/HeatingInput.h`, shared
  with `HeatingController`, so the fuzzer runs the device code.

## Results of the first run (2026-10-29, beta.17 working tree)

25 minutes with 3 workers per harness, then 12 minutes with 4 workers and the
dictionaries for the JSON and Bluetooth harnesses. No crash, leak, UBSan report,
timeout (>2 s) or invariant failure; every input ran in under one second.

| Harness | Executions | Edges (libFuzzer cov) | Line coverage of the main files |
| --- | --- | --- | --- |
| ems_frame | 3.3 M | 1694 | BreakFrameReader 100 %, ClassicBoilerMonitor 98 %, EmsTelegram.cpp 86 %, EmsEntityCatalog 87 %, UBA*.cpp 100 % |
| ble_advert | 76 M | 932 | BTHome, pvvx, Shelly H&T/TRV 100 %, MiBeacon 99 %, discovery 95 %, legacy decoder 91 % |
| ble_observer | 51 M | 807 | ManagedBleObserver 94 % |
| ble_settings | 134 M | 1234 | BleDeviceSettings 96 % |
| room_plan | 63 M | 1020 | RoomPlan 100 %, RoomSchedule 94 %, RoomEngine 55 % |
| control_json | 204 M | 476 | parseControlJson 81 % |
| shadow | 2.4 M | 2023 | ShadowController 50 % (no seasonal/hydraulic/native-plan sources), SessionAdmission 93 % |
| boiler_services | 10 M | 1522 | ClassicBoilerSettingsService 95 %, ClassicConfigurationRead 88 %, BoilerTestService 67 % |

One issue is outside what these host runs can show: several handlers call
`cJSON_Parse*` on external bytes without a nesting limit. On the E32 each JSON
nesting level costs 128 bytes of the 8 KB loop task stack (ESP-IDF `libjson.a`,
`parse_value: entry a1, 128`), so a payload like 256 `[` on `ha/heating_input`
overflows the stack. See the fuzzing report for the call sites and the fix.
