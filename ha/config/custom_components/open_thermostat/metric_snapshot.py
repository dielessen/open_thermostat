"""Fixed read-only metrics schema. Never source/control/model admission."""
import math

CAPABILITY="metrics.observation_total.v2"
MAX_BYTES=2048
EXPIRY_SECONDS=345  # the E32 sends ems_metrics every 5 minutes
LEGACY=("totalEnergyUsedKwh","heatingEnergyUsedKwh","warmWaterEnergyUsedKwh","unattributedEnergyUsedKwh",
        "warmWaterUsage","warmWaterAvgFlow","warmWaterFlow","observedBurnerSeconds")
VERSIONED=tuple(key+"V2" for key in LEGACY)
LITERALS={"metricsSchema":2,"counterDefinition":"observation-total-v2","counterScope":"boot",
          "energyQuality":"estimated_nominal_modulation","protocolScope":"plus","flowQuality":"reported_integrated"}

def finite(value):
    try:
        return type(value) in (int,float) and math.isfinite(value)
    except OverflowError:
        return False

def valid_snapshot(value):
    if type(value) is not dict or set(value)!=set(LITERALS)|set(LEGACY)|set(VERSIONED)|{"powerFresh","outdoorTemperature"}:
        return False
    if type(value["metricsSchema"]) is not int or any(value[key]!=expected for key,expected in LITERALS.items()):
        return False
    if any(value[key] is not None for key in LEGACY):
        return False
    if any(v is not None and (not finite(v) or v<0) for key in VERSIONED for v in [value[key]]):
        return False
    outdoor=value["outdoorTemperature"]
    return type(value["powerFresh"]) is bool and (outdoor is None or finite(outdoor) and -100<=outdoor<=100)
