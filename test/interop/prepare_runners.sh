#!/bin/bash
# Build the native firmware peers that the HA interop tests talk to (shadow
# session, graph, actuator, schedule and room observation runners) into out/.
# CI jobs home-assistant-native and home-assistant-compat and
# scripts/final_check.sh share this list. Run from the repository root after
# `pio pkg install -e native`.
set -euo pipefail
mkdir -p out
g++ -std=c++20 -O1 -Isrc -Itest/test_native/include -I.pio/libdeps/native/cJSON test/interop/shadow_runner.cpp .pio/libdeps/native/cJSON/cJSON.c -o out/shadow-runner
gcc -std=c11 -O0 -g -I.pio/libdeps/native/cJSON -c .pio/libdeps/native/cJSON/cJSON.c -o out/graph-cjson.o
g++ -std=c++17 -O0 -g -Wall -Wextra -Werror -Isrc -Itest/test_native/include -I.pio/libdeps/native/cJSON test/interop/graph_validation_runner.cpp out/graph-cjson.o -ldl -o out/graph-validation-runner
g++ -std=c++17 -O0 -g -Wall -Wextra -Werror -Isrc -Itest/test_native/include -I.pio/libdeps/native/cJSON test/interop/graph_configuration_runner.cpp out/graph-cjson.o -ldl -o out/graph-configuration-runner
g++ -std=c++17 -O0 -g -Wall -Wextra -Werror -Isrc -Itest/test_native/include -I.pio/libdeps/native/cJSON test/interop/graph_session_runner.cpp out/graph-cjson.o -ldl -o out/graph-session-runner
g++ -std=c++17 -O0 -g -Wall -Wextra -Werror -Isrc -I.pio/libdeps/native/cJSON test/interop/actuator_intent_runner.cpp out/graph-cjson.o -o out/actuator-intent-runner
g++ -std=c++17 -O0 -g -Wall -Wextra -Werror -Isrc -I.pio/libdeps/native/cJSON test/interop/actuator_dispatch_runner.cpp out/graph-cjson.o -o out/actuator-dispatch-runner
g++ -std=c++17 -O0 -g -Wall -Wextra -Werror -Isrc -I.pio/libdeps/native/cJSON test/interop/actuator_channel_runner.cpp out/graph-cjson.o -o out/actuator-channel-runner
g++ -std=c++17 -O0 -g -Wall -Wextra -Werror -Isrc -Itest/test_native/include -I.pio/libdeps/native/cJSON test/interop/graph_control_projection_runner.cpp out/graph-cjson.o -ldl -o out/graph-control-projection-runner
g++ -std=c++17 -O0 -g -Wall -Wextra -Werror -Isrc -Itest/test_native/include -I.pio/libdeps/native/cJSON test/interop/packed_schedule_runner.cpp out/graph-cjson.o -ldl -o out/packed-schedule-runner
g++ -std=c++17 -O0 -g -Wall -Wextra -Werror -Isrc -Itest/test_native/include -I.pio/libdeps/native/cJSON test/interop/topology_review_runner.cpp out/graph-cjson.o -ldl -o out/topology-review-runner
g++ -std=c++17 -O0 -Isrc -Itest/test_native/include -I.pio/libdeps/native/esp32_utilities/src -c src/EMS/EmsTelegram.cpp -o out/room-ems-parser.o
g++ -std=c++17 -O0 -Wall -Wextra -Werror -Wno-dangling-else -pthread -Isrc -Itest/test_native/include -I.pio/libdeps/native/esp32_utilities/src test/interop/room_observation_runner.cpp out/room-ems-parser.o -o out/room-observation-peer
out/room-observation-peer > out/room-observation-wire.json
