"""Atomic API2 config+opaque mapping wire; no listener/client/storage ownership.

A codec alone neither advertises capability nor establishes a session/physical
readiness. The existing owner must negotiate this exact transport before use.
"""
from .graph_shadow_validation import (
    canonical,digest,raw_document,obj,validate_graph_shadow,GraphValidationError,
)

TRANSPORT = "atomic_mapping_tuple.v1"
FIELDS = ("api controller_id boot_id epoch adapter_id adapter_session_id grant_id "
          "grant_sequence config_revision binding_id sequence expected_revision config_digest config")

def encode_graph_tuple(message_raw,mapping_raw,context):
    # Reuse exact shared semantic/privacy/ref/qualification validator BEFORE send.
    validate_graph_shadow(message_raw,mapping_raw,context)
    message,mapping=raw_document(message_raw),raw_document(mapping_raw)
    obj(message,FIELDS)
    wire=canonical({**message,"mapping":mapping})
    raw_document(wire)  # TOTAL wire budget, not two separate8192B promises.
    return wire

def decode_graph_tuple(wire):
    # Syntax/integrity separation ONLY; never substitutes shared validation or
    # session/grant/lease/owner admission. Never echo untrusted input on errors.
    message=raw_document(wire);obj(message,FIELDS+" mapping")
    if type(message["api"]) is not int or message["api"]!=2:
        raise GraphValidationError("unsupported_schema")
    mapping=message.pop("mapping")
    if type(mapping) is not dict or type(message["config"]) is not dict:
        raise GraphValidationError("schema")
    if message["config"].get("mapping_digest")!=digest(mapping):
        raise GraphValidationError("mapping_conflict")
    return canonical(message),canonical(mapping)
