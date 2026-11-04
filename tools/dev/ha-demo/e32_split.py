"""The firmware's split of /status/heating into its MQTT topics, as the HA tests mirror it.

Loads ha/tests_native/e32_telemetry.py (split_status mirrors src/control/HeatingStateTopics.h) by path, so the
demo reuses the test helper as it is.
"""
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[3] / "ha" / "tests_native" / "e32_telemetry.py"
_SPEC = importlib.util.spec_from_file_location("openthermostat_e32_telemetry", _PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
split_status = _MODULE.split_status
