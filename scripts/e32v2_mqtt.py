"""E32-only build middleware: retain dependency API and reconnect state machine.

Compile a generated copy, not a modified package/cache. Fail closed if the
upstream WiFi-only gate changes, so library upgrades require a review.
"""
import hashlib
from pathlib import Path

Import("env")


def network_aware_mqtt(build_env, node):
    original = Path(node.srcnode().get_abspath()).read_text()
    expected = "8dd5cfa4e30d7b3ef1915189c117b20a222b64f769eeda2d841b300fe904f1de"
    if hashlib.sha256(original.encode()).hexdigest() != expected:
        raise RuntimeError("Review E32 MQTT middleware for changed ESPPubSubClientWrapper 1.0.2 source")
    needle = "int wifiStatus = WiFi.status();"
    if original.count(needle) != 1:
        raise RuntimeError("ESPPubSubClientWrapper WiFi gate changed; review E32 port")
    patched = '#include "Network.h"\n' + original.replace(
        needle, "int wifiStatus = heating::networkConnected() ? WL_CONNECTED : WL_DISCONNECTED;"
    )
    destination = Path(build_env.subst("$BUILD_DIR")) / "e32v2_mqtt.cpp"
    if not destination.exists() or destination.read_text() != patched:
        destination.write_text(patched)
    return build_env.File(str(destination))


env.AddBuildMiddleware(network_aware_mqtt, "*/ESPPubSubClientWrapper/src/ESPPubSubClientWrapper.cpp")
env.Append(CPPPATH=[env.subst("$PROJECT_SRC_DIR")])
