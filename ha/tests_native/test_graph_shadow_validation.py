"""Exact shared graph-shadow fixtures: independent Python and actual C++ validators."""
import json
import os
from pathlib import Path
import subprocess

import pytest

from custom_components.open_thermostat.graph_shadow_validation import (
    GraphValidationContext, GraphValidationError, validate_graph_shadow)

ROOT=Path(__file__).resolve().parents[2]
CASES=[json.loads(line) for line in (ROOT/"test/fixtures/graph-shadow-validation.jsonl").read_text().splitlines()]
RUNNER=Path(os.environ.get("OPENTHERMOSTAT_GRAPH_VALIDATOR_RUNNER",str(ROOT/"out/graph-validation-runner")))

@pytest.mark.parametrize("case",CASES,ids=lambda c:c["name"])
def test_shared_python_verdict(case):
    context=GraphValidationContext(**case["context"])
    try:
        result=validate_graph_shadow(case["raw"],case["mapping_raw"],context)
        code="valid_shadow_candidate"
        assert result.actuator_output_enabled is False
        assert result.boiler_output_enabled is False
        assert result.stream_count==7
        assert result.total_transitions<=8
    except GraphValidationError as err:
        code=err.code
    assert code==case["expected"]

def test_shared_actual_cpp_matches_all_explicit_fixtures():
    assert RUNNER.is_file(), "Build test/interop/graph_validation_runner.cpp; no fake C++ validator fallback"
    result=subprocess.run([str(RUNNER)],input="\n".join(json.dumps(c) for c in CASES)+"\n",
        capture_output=True,text=True,timeout=30,check=True)
    rows=[json.loads(x) for x in result.stdout.splitlines()]
    assert len(rows)==len(CASES)
    for case,row in zip(CASES,rows,strict=True):
        assert row["name"]==case["name"]
        assert row["code"]==case["expected"]
        assert row["actuator_output_enabled"] is False and row["boiler_output_enabled"] is False
        if row["code"]=="valid_shadow_candidate":
            python_result=validate_graph_shadow(case["raw"],case["mapping_raw"],GraphValidationContext(**case["context"]))
            assert row["streams"]==python_result.stream_count==7
            assert row["transitions"]==python_result.total_transitions<=8
            assert row["revision"]==python_result.revision
            assert row["mapping_revision"]==python_result.mapping_revision
    if output:=os.environ.get("OPENTHERMOSTAT_GRAPH_ALLOCATION_EVIDENCE"):
        Path(output).write_text(json.dumps(rows,indent=2)+"\n")

def test_validator_not_imported_by_any_active_runtime_or_api():
    component=ROOT/"ha/config/custom_components/open_thermostat"
    for p in component.glob("*.py"):
        if p.name in ("graph_shadow_validation.py", "graph_shadow_storage.py"):
            continue
        assert "graph_shadow_validation" not in p.read_text(),p.name
    for p in (ROOT/"src").rglob("*"):
        if p.is_file() and p.suffix in (".h",".cpp") and p.name!="GraphShadowValidation.h":
            assert "GraphShadowValidation" not in p.read_text(),str(p)


@pytest.mark.parametrize("case",[c for c in CASES if c["name"].startswith("gv_r1_")],ids=lambda c:c["name"])
def test_gv_r1_wrong_channel_type_is_typed_reference_failure_without_candidate(case):
    # No broad catch: TypeError or another programming exception must fail this test.
    not_returned=object()
    candidate=not_returned
    with pytest.raises(GraphValidationError,match="^reference$") as caught:
        candidate=validate_graph_shadow(case["raw"],case["mapping_raw"],GraphValidationContext(**case["context"]))
    assert caught.value.code=="reference"
    assert candidate is not_returned


def test_real_cpp_allocation_failure_sweep_is_leak_free_and_recoverable():
    case={**CASES[0],"fault_sweep":True}
    completed=subprocess.run([str(RUNNER)],input=json.dumps(case)+"\n",
        capture_output=True,text=True,timeout=30,check=True)
    result=json.loads(completed.stdout)
    assert result["fault_sweep"] is True and result["allocation_positions"]>526
    assert result["leaked_runs"]==result["leaked_cjson_blocks"]==0
    assert result["valid_on_fault"]==result["untriggered"]==result["bad_output_flags"]==0
    assert result["inputs_intact"] is True
    assert result["recovery_code"]=="valid_shadow_candidate"
    assert [x["index"] for x in result["original_leak_sites"]]==[416,472,500,526]
    assert all(x["code"]=="allocation" for x in result["original_leak_sites"])
    if output:=os.environ.get("OPENTHERMOSTAT_GRAPH_FAULT_EVIDENCE"):
        Path(output).write_text(json.dumps(result,indent=2)+"\n")
