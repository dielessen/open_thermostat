#!/bin/bash
# The hand-written native harnesses that `pio test -e native` does not build:
# echo/UART, sockets, MQTT, BLE crypto, web sign-in, manual OTA, onboarding,
# logging and boiler display. CI and scripts/final_check.sh both use this file,
# so a harness cannot be compiled one way locally and another way in CI.
#
#   test/native_harnesses.sh build   compile and link every harness, in parallel, without running
#                                    them (CI job "harnesses": a stale test stub fails in minutes)
#   test/native_harnesses.sh run     build and run each harness in order (CI job "build (native)")
#   test/native_harnesses.sh build onboarding web_auth    only the named harnesses
#
# Run from the repository root after `pio pkg install -e native` (and, for run,
# after `pio test -e native`, whose googletest library is reused when present).
# Needs libmbedtls-dev for the BLE crypto harness and pio for PubSubClient.
set -euo pipefail
mode=${1:-}
case "$mode" in build|run) ;; *) echo "usage: $0 build|run [harness...]" >&2; exit 2 ;; esac
shift
OUT=${HARNESS_OUT:-/tmp/open-thermostat-harnesses}
MQTT_SRC=${MQTT_SRC:-/tmp/open-thermostat-mqtt-source}
mkdir -p "$OUT" "$MQTT_SRC"
D=.pio/libdeps/native
GT=$D/googletest/googletest
# shellcheck disable=SC2054 # one flag: -fsanitize=address,undefined
SAN=(-fsanitize=address,undefined -fno-omit-frame-pointer)
STRICT=(-std=c++17 -O1 -g -Wall -Wextra -Werror "${SAN[@]}")

# --- shared inputs -------------------------------------------------------------
prepare(){
  [ -d "$MQTT_SRC/PubSubClient" ] || pio pkg install --global --library knolleary/PubSubClient@2.8.0 --storage-dir "$MQTT_SRC" --skip-dependencies
  gcc -std=c11 -O1 -g "${SAN[@]}" -I$D/cJSON -c $D/cJSON/cJSON.c -o "$OUT/cjson.o"
  g++ -std=c++17 -O1 -g -Wall -Wextra "${SAN[@]}" -Itest/deadline_write/include -I"$MQTT_SRC/PubSubClient/src" -c "$MQTT_SRC/PubSubClient/src/PubSubClient.cpp" -o "$OUT/pinned-mqtt.o"
  g++ -std=c++17 -Wall -Wextra -include cstdint -I$D/esp32_utilities/src -c $D/esp32_utilities/src/logger/Logger.cpp -o "$OUT/vendor-logger.o"
  # googletest: the library of `pio test -e native` when it exists, else built here once.
  GTEST=$(ls .pio/build/native/lib*/libgoogletest.a 2>/dev/null | head -1 || true)
  if [ -z "$GTEST" ]; then
    GTEST=$OUT/libgoogletest.a
    if [ ! -f "$GTEST" ]; then
      g++ -std=c++17 -O1 -g -I$GT/include -I$GT -c $GT/src/gtest-all.cc -o "$OUT/gtest-all.o"
      ar rcs "$GTEST" "$OUT/gtest-all.o"
    fi
  fi
  MAIN=$GT/src/gtest_main.cc
}

# --- one function per harness: build_<name> creates $OUT/<name> ----------------
build_ems_readers(){ g++ "${STRICT[@]}" -Wvla -Isrc -I$D/esp32_utilities/src -I$D/cJSON -I$GT/include test/test_native/test_ems_readers.cpp test/test_native/test_ble_device_discovery.cpp src/EMS/EmsTelegram.cpp src/EMS/UBADeviceVersion.cpp $MAIN "$OUT/cjson.o" "$GTEST" -lpthread -o "$OUT/ems_readers"; }
build_shadow_contacts(){ g++ "${STRICT[@]}" -Isrc -Itest/test_native/include -I$D/cJSON -I$GT/include test/test_native/test_shadow_contacts.cpp test/test_native/test_shadow_manual_target.cpp $MAIN "$OUT/cjson.o" "$GTEST" -ldl -lpthread -o "$OUT/shadow_contacts"; }
build_boiler_poll(){ g++ "${STRICT[@]}" -Isrc -Itest/test_native/include -I$D/esp32_utilities/src -I$D/cJSON -I$GT/include test/test_native/test_response_buffer.cpp test/test_native/test_loop_intervals.cpp test/test_native/test_classic_boiler_test_encoder.cpp test/test_native/test_classic_boiler_settings_encoder.cpp test/test_native/test_classic_boiler_setting_transaction.cpp test/test_native/test_classic_setting_bus_exchange.cpp test/test_native/test_classic_boiler_settings_service.cpp test/test_native/test_classic_setting_uart_write.cpp test/test_native/test_classic_settings_pipeline.cpp test/test_native/test_classic_settings_runtime_gate.cpp test/test_native/test_boiler_test_poll.cpp test/test_native/test_boiler_test_session.cpp test/test_native/test_boiler_test_service.cpp test/test_native/test_classic_echo_uart_write.cpp test/test_native/test_ems_poll.cpp test/test_native/test_ems_echo_rx_debt.cpp test/test_native/test_manual_classic_uart_write.cpp test/test_native/test_manual_bus_identity.cpp test/test_native/test_boiler_site_confirmation.cpp test/test_native/test_boiler_fault_closure.cpp test/test_native/test_classic_heat_trial_envelope.cpp test/test_native/test_ecomline_commissioning.cpp test/test_native/test_classic_configuration_read.cpp test/test_native/test_manual_classic_transaction.cpp src/EMS/EmsTelegram.cpp $MAIN "$OUT/cjson.o" "$GTEST" -lpthread -o "$OUT/boiler_poll"; }
build_echo_adapter(){ g++ "${STRICT[@]}" -Itest/echo_write/include -Isrc -I$GT/include test/echo_write/adapter.cpp $MAIN "$GTEST" -lpthread -o "$OUT/echo_adapter"; }
build_actuator(){ g++ "${STRICT[@]}" -Isrc -I$D/cJSON -I$GT/include test/test_native/test_actuator_intent.cpp test/test_native/test_actuator_dispatch.cpp test/test_native/test_actuator_channel.cpp test/test_native/test_actuator_channels.cpp test/test_native/test_deadline_write.cpp $MAIN "$OUT/cjson.o" "$GTEST" -lpthread -o "$OUT/actuator"; }
build_deadline_socket(){ g++ "${STRICT[@]}" -DOPENTHERMOSTAT_E32V2 -Itest/deadline_write/include -Isrc -I$D/cJSON -I$GT/include test/deadline_write/adapter.cpp test/test_native/test_mqtt_outbox.cpp $MAIN "$OUT/cjson.o" "$GTEST" -lpthread -o "$OUT/deadline_socket"; }
build_pending_tcp(){ g++ "${STRICT[@]}" -DOPENTHERMOSTAT_E32V2 -Itest/pending_tcp/include -Itest/deadline_write/include -Isrc -I"$MQTT_SRC/PubSubClient/src" -I$GT/include test/pending_tcp/adapter.cpp "$OUT/pinned-mqtt.o" $MAIN "$GTEST" -lpthread -o "$OUT/pending_tcp"; }
build_pending_tcp_offset(){ g++ "${STRICT[@]}" -DOPENTHERMOSTAT_E32V2 -DLWIP_SOCKET_OFFSET=2 -DLWIP_SELECT_MAXNFDS=FD_SETSIZE -Itest/pending_tcp/include -Itest/deadline_write/include -Isrc -I"$MQTT_SRC/PubSubClient/src" -I$GT/include test/pending_tcp/adapter.cpp "$OUT/pinned-mqtt.o" $MAIN "$GTEST" -lpthread -o "$OUT/pending_tcp_offset"; }
build_async_dns(){ g++ "${STRICT[@]}" -DOPENTHERMOSTAT_E32V2 -Itest/async_broker_dns/include -Isrc -I$GT/include test/async_broker_dns/adapter.cpp $MAIN "$GTEST" -lpthread -o "$OUT/async_dns"; }
build_update_checkpoint(){ g++ -std=c++17 -O1 -g "${SAN[@]}" -Isrc -I$D/cJSON -I$GT/include test/test_native/test_github_update.cpp test/test_native/test_update_checkpoint.cpp $MAIN "$OUT/cjson.o" "$GTEST" -lpthread -o "$OUT/update_checkpoint"; }
build_shelly_ht(){ g++ "${STRICT[@]}" -Isrc -I$GT/include test/test_native/test_shelly_ht_advertisement.cpp $MAIN "$GTEST" -lpthread -o "$OUT/shelly_ht"; }
build_ble_crypto(){ g++ "${STRICT[@]}" -Isrc -I$GT/include test/ble_crypto/mbedtls.cpp test/ble_crypto/mibeacon.cpp test/ble_crypto/backup_cipher.cpp $MAIN "$GTEST" -Wl,--wrap=calloc -Wl,-Bstatic -lmbedcrypto -Wl,-Bdynamic -lpthread -o "$OUT/ble_crypto"; }
build_ble_owner(){ g++ "${STRICT[@]}" -Isrc -I$D/cJSON -I$GT/include test/test_native/test_ble_device_settings.cpp test/test_native/test_managed_ble_observer.cpp test/test_native/test_mibeacon_monitor3.cpp test/test_native/test_shelly_trv.cpp $MAIN "$OUT/cjson.o" "$GTEST" -lpthread -o "$OUT/ble_owner"; }
build_ble_storage(){ g++ "${STRICT[@]}" -Isrc -Itest/bluetooth_storage/include -Itest/onboarding/include test/bluetooth_storage/main.cpp test/bluetooth_storage/allocation.cpp -o "$OUT/ble_storage"; }
build_web_auth_unit(){ g++ "${STRICT[@]}" -Isrc -I$GT/include test/test_native/test_web_auth.cpp $MAIN "$GTEST" -lpthread -o "$OUT/web_auth_unit"; }
build_onboarding(){ g++ -std=c++20 -g "${SAN[@]}" -Itest/onboarding/include -Isrc -I$D/cJSON -I$D/esp32_utilities/src test/onboarding/firmware.cpp $D/cJSON/cJSON.c -o "$OUT/onboarding"; }
build_boiler_display(){ g++ -std=c++17 -Wall -Wextra -Werror -Isrc -Itest/boiler_display/include test/boiler_display/firmware.cpp -o "$OUT/boiler_display"; }
build_logging(){ g++ -std=c++17 -Wall -Wextra -Werror -pthread -DOPENTHERMOSTAT_E32V2 -Isrc -Itest/logging_runtime/include -Itest/boiler_display/include -I$D/esp32_utilities/src -I$D/cJSON test/logging_runtime/main.cpp src/diagnostics/NativeLog.cpp src/EMS/EmsTelegram.cpp "$OUT/vendor-logger.o" $D/cJSON/cJSON.c -o "$OUT/logging"; }
# The two Python harnesses compile their own handlers; OT_HARNESS_BUILD_ONLY=1 stops before running.
build_manual_ota(){ OT_HARNESS_BUILD_ONLY=1 python3 test/manual_ota/run.py; }
build_web_auth(){ OT_HARNESS_BUILD_ONLY=1 python3 test/web_auth/run.py; }

# The CI order of the original native step.
HARNESSES=(ems_readers shadow_contacts boiler_poll echo_adapter actuator deadline_socket pending_tcp
           pending_tcp_offset async_dns update_checkpoint shelly_ht ble_crypto ble_owner ble_storage
           web_auth_unit manual_ota web_auth onboarding boiler_display logging)
if [ $# -gt 0 ]; then
  for name in "$@"; do [[ " ${HARNESSES[*]} " == *" $name "* ]] || { echo "unknown harness $name" >&2; exit 2; }; done
  HARNESSES=("$@")
fi

prepare
if [ "$mode" = run ]; then
  for name in "${HARNESSES[@]}"; do
    echo "== $name"
    case "$name" in
      manual_ota) python3 test/manual_ota/run.py ;;
      web_auth) python3 test/web_auth/run.py ;;
      *) "build_$name"; "$OUT/$name" ;;
    esac
  done
  exit 0
fi

# build: all harnesses in parallel, every failure reported with its compiler output.
JOBS=${HARNESS_JOBS:-$(nproc)}
failed=()
declare -A pids=()
for name in "${HARNESSES[@]}"; do
  while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do wait -n || true; done
  ( "build_$name" ) > "$OUT/$name.build.log" 2>&1 &
  pids[$name]=$!
done
for name in "${HARNESSES[@]}"; do
  if wait "${pids[$name]}"; then echo "BUILT $name"; else failed+=("$name"); echo "FAILED $name"; cat "$OUT/$name.build.log"; fi
done
if [ ${#failed[@]} -gt 0 ]; then
  [ -n "${GITHUB_ACTIONS:-}" ] && for name in "${failed[@]}"; do
    echo "::error title=Native harness does not build: $name::$(tail -c 3000 "$OUT/$name.build.log" | awk '{gsub(/%/,"%25");gsub(/\r/,"");printf "%s%%0A",$0}')"
  done
  exit 1
fi
echo "PASS all ${#HARNESSES[@]} native harnesses build"
