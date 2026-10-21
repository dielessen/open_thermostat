"""Explicit source-stage API2 bounded graph owner, no extra MQTT/worker/timer."""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
import math
import re
import secrets
from homeassistant.exceptions import HomeAssistantError

from .graph_shadow_validation import (
    GraphValidationContext,GraphValidationError,canonical,digest,raw_document,obj)
from .graph_wire_codec import TRANSPORT
from .session_grant import register_grant_proof,consume_grant_proof

_ID=re.compile(r"[A-Za-z0-9_-]{1,32}")
_HEX=re.compile(r"[0-9a-f]{64}")
PROFILE="bounded_shadow_1r1f1b"
BASE="api controller_id boot_id epoch config_revision config_digest mapping_revision mapping_digest"
SESSION=BASE+" adapter_id adapter_session_id grant_id grant_sequence"


def require(value,code):
    if not value:raise GraphValidationError(code)


def identifier(value):
    return type(value) is str and _ID.fullmatch(value) is not None


def integer(value,low=0):
    return type(value) is int and low<=value<=4294967295


@dataclass(frozen=True)
class GraphSourceProfile:
    """Source-owned pins, NOT granted by an incoming manifest or HA draft."""
    controller_id:str
    qualification_digest:str
    draft_source:object|None=None
    entry_unique_id:str|None=None

    def validate(self):
        require(identifier(self.controller_id),"identity")
        require(self.entry_unique_id is None or identifier(self.entry_unique_id),"identity")
        require(type(self.qualification_digest) is str
                and bool(_HEX.fullmatch(self.qualification_digest)),"qualification")
        if self.draft_source is not None:
            from .graph_draft_compile import GraphDraftSource
            require(isinstance(self.draft_source,GraphDraftSource),"qualification")
            self.draft_source.validate(self.qualification_digest)


class GraphShadowClient:
    def __init__(self,runtime,adapter_id,send,journal,profile,clock):
        profile.validate()
        require(identifier(adapter_id),"identity")
        require(journal.qualification_digest==profile.qualification_digest,"qualification")
        self.runtime,self.adapter_id,self.send=runtime,adapter_id,send
        self.journal,self.profile,self.clock=journal,profile,clock
        self.identity=self.session=self.open_request=None
        self._hello_base=None
        self.open_sent=self.grant_until=self.lease_until=0.0
        self.sequence=defaultdict(int);self._proofs={};self._heartbeats={}
        self._capability=None;self._cap_received=0.0;self._cap_highwater=0
        self._snapshot=None;self._readback_key=None;self._last_heartbeat=-math.inf;self._last_clock=None
        self.closed=False;self.error="graph_not_connected";self._close_io=None
        self._nonce=lambda:secrets.token_hex(12)
        self._open_last=0.0;self._open_tries=0
        self._config_attempt=None;self._device_result=None

    @property
    def ready(self):
        # Config DATA readback is NOT running source/control/device admission.
        return False

    @property
    def verified(self):
        return self.journal.verified

    @property
    def graph_ready(self):
        try:return self.journal.verified and self._fresh()
        except GraphValidationError:return False

    @property
    def graph_status(self):
        state=self.journal.state or {"accepted":None,"staged":None}
        return dict(profile=PROFILE,transport=TRANSPORT,status=self.error,
            journal_status=self.journal.status,readback_verified=self.graph_ready,
            accepted_revision=(state["accepted"]["config"]["revision"] if state["accepted"] else 0),
            staged_revision=(state["staged"]["config"]["revision"] if state["staged"] else None),
            device_result=self._device_result,
            control_contract_supported=False,boiler_output_enabled=False,actuator_output_enabled=False)

    async def async_reviewed_handoff_data(self, expected_review):
        """Exact fresh inert tuple only; cannot select/enable a controller."""
        context = self._context()
        try:
            record = await self.journal.async_reviewed_handoff_data(expected_review, context,
                self._capability, self._cap_received, retained=False)
            require(self.journal.verified and canonical(expected_review) ==
                    canonical(self.journal.review_key(record, self._context())), "session_changed")
            return record
        except GraphValidationError:
            self.journal.invalidate()
            raise

    @property
    def metrics_supported(self):return False
    @property
    def metrics_payload(self):return None
    @property
    def metrics_key(self):return None

    def changed(self):
        self.runtime.diagnostics["transport"]=self.error
        self.runtime.diagnostics["graph_status"]=self.journal.status
        self.runtime._notify()

    def _now(self):
        now=self.clock()
        require(type(now) in (int,float) and math.isfinite(now)
                and (self._last_clock is None or now>=self._last_clock),"invalid_clock")
        self._last_clock=now
        return now

    def reset_session(self):
        self.session=self.open_request=None;self.sequence.clear()
        self._proofs.clear();self._heartbeats.clear();self._snapshot=None;self._readback_key=None
        self._capability=None;self._cap_received=0.0;self._cap_highwater=0
        self.grant_until=self.lease_until=0.0;self.journal.invalidate()
        self._config_attempt=None;self._device_result=None

    async def async_start(self):await self.journal.async_initialize()

    async def async_disconnected(self):
        self.reset_session();self.identity=None;self.error="graph_disconnected";self.changed()

    async def async_close(self):
        if self.closed:return
        self.closed=True
        await self.async_disconnected()
        if self._close_io:await self._close_io()

    def configuration_changed(self):
        self.journal.invalidate();self.error="graph_edit_requires_explicit_stage";self.changed()

    @staticmethod
    def _data_key(p):
        # Inert config DATA under same boot/epoch/session, not a lease/source
        # proof. Grant rotation alone does not change committed config bytes.
        return tuple(p[k] for k in ("controller_id","boot_id","epoch","adapter_session_id",
            "config_revision","config_digest","mapping_revision","mapping_digest"))

    def _scope(self,p):
        return (self.session is not None
                and all(type(p.get(k)) is type(self.session[k]) and p[k]==self.session[k]
                        for k in SESSION.split()))

    def _live(self):
        now=self._now()
        return (not self.closed and self.session is not None
                and now<self.grant_until and now<self.lease_until)

    def _fresh(self):
        return (self._live() and self._capability is not None
                and self._scope(self._capability)
                and 0<=self._now()-self._cap_received<10)

    def _context(self):
        require(self._fresh(),"stale_capability")
        p=self._capability
        return GraphValidationContext(
            controller_id=p["controller_id"],boot_id=p["boot_id"],epoch=p["epoch"],
            adapter_id=self.adapter_id,adapter_session_id=p["adapter_session_id"],
            grant_id=p["grant_id"],grant_sequence=p["grant_sequence"],
            current_revision=p["config_revision"],mapping_revision=p["mapping_revision"],
            mapping_digest=p["mapping_digest"],qualification_digest=self.profile.qualification_digest)

    def _envelope(self,binding):
        require(self.session is not None and self._now()<self.grant_until,"stale_grant")
        sequence=self.sequence[binding]+1;require(integer(sequence,1),"sequence_exhausted")
        return {k:self.session[k] for k in (
            "api","controller_id","boot_id","epoch","adapter_id","adapter_session_id",
            "grant_id","grant_sequence","config_revision")}|dict(binding_id=binding,sequence=sequence)

    async def _heartbeat(self):
        p=self._envelope("adapter");now=self._now()
        nonce=f"g{p['sequence']:08x}{self._nonce()[:20]}"
        require(identifier(nonce),"identity")
        p["grant_request_nonce"]=nonce;raw=canonical(p);raw_document(raw)
        self.sequence["adapter"]=p["sequence"]
        self._heartbeats[p["sequence"]]=(now,p["grant_id"],p["grant_sequence"])
        while len(self._heartbeats)>8:self._heartbeats.pop(next(iter(self._heartbeats)))
        register_grant_proof(self._proofs,nonce,now)
        self._last_heartbeat=now
        await self.send("ha/heartbeat",raw)

    async def _request_snapshot(self):
        p=self._envelope("snapshot");now=self._now()
        self.sequence["snapshot"]=p["sequence"]
        self._snapshot=dict(sequence=p["sequence"],raw=canonical(p),sent=now,last=now,
            grant_id=p["grant_id"],grant_sequence=p["grant_sequence"],tries=1)
        await self.send("ha/snapshot_request",self._snapshot["raw"])

    async def receive(self,topic,raw,*,retained=False):
        if self.closed or retained:return
        if topic=="fw/availability":
            if raw=="offline":await self.async_disconnected()
            # Online is NOT a grant, lease, config or source proof. Actual
            # ModernTransport publishes it after hello; do not reset opening.
            return
        try:
            now=self._now();p=raw_document(raw)
            if topic=="fw/hello":
                obj(p,BASE+" challenge_id mode transport profile qualification_digest lease_ms grant_ms storage_fault")
                require(type(p["api"]) is int and p["api"]==2
                    and p["mode"]=="shadow_graph" and p["transport"]==TRANSPORT
                    and p["profile"]==PROFILE,"unsupported_transport")
                require(p["controller_id"]==self.profile.controller_id
                    and identifier(p["boot_id"]) and identifier(p["challenge_id"])
                    and integer(p["epoch"],1),"identity")
                require(p["qualification_digest"]==self.profile.qualification_digest,"qualification")
                require(type(p["lease_ms"]) is int and p["lease_ms"]==15000
                    and type(p["grant_ms"]) is int and p["grant_ms"]==10000
                    and type(p["storage_fault"]) is bool,"unsupported_transport")
                require(integer(p["config_revision"]) and integer(p["mapping_revision"]),"revision_conflict")
                if p["config_revision"]==0:
                    require(p["config_digest"]==p["mapping_digest"]==""
                            and p["mapping_revision"]==0,"revision_conflict")
                else:
                    require(p["mapping_revision"]>0
                        and type(p["config_digest"]) is str and bool(_HEX.fullmatch(p["config_digest"]))
                        and type(p["mapping_digest"]) is str and bool(_HEX.fullmatch(p["mapping_digest"])),"revision_conflict")
                if p["storage_fault"]:
                    self.reset_session();self.error="graph_firmware_storage_fault";self.changed();return
                identity=(p["controller_id"],p["boot_id"],p["epoch"])
                if self.identity and identity[:2]==self.identity[:2] and identity[2]<self.identity[2]:return
                same_config=(self.session and all(p[k]==self.session[k] for k in
                    ("config_revision","config_digest","mapping_revision","mapping_digest")))
                if identity!=self.identity or self.session and not same_config:
                    self.reset_session();self.identity=identity
                if self.session or self.open_request:return
                self._hello_base={k:p[k] for k in BASE.split()}
                request={k:p[k] for k in ("api","controller_id","boot_id","epoch","challenge_id")}
                request.update(adapter_id=self.adapter_id,adapter_session_id=self._nonce(),
                               client_nonce=self._nonce(),transport=TRANSPORT)
                require(identifier(request["adapter_session_id"]) and identifier(request["client_nonce"]),"identity")
                self.open_request=request;self.open_sent=self._open_last=now;self._open_tries=1
                await self.send("ha/open_session",canonical(request))
                return
            if not self.identity or not (
                type(p.get("api")) is int and p.get("api")==2
                and (p.get("controller_id"),p.get("boot_id"),p.get("epoch"))==self.identity):
                # capability wrapper has scope in its exact inner object.
                if topic!="fw/graph_capability":return
            if topic=="fw/session":
                keys=SESSION+" client_nonce grant_ms transport profile"
                obj(p,keys+(" grant_request_nonce" if "grant_request_nonce" in p else ""))
                require(self.open_request is not None
                    and p["client_nonce"]==self.open_request["client_nonce"]
                    and p["adapter_id"]==self.adapter_id
                    and p["adapter_session_id"]==self.open_request["adapter_session_id"]
                    and p["transport"]==TRANSPORT and p["profile"]==PROFILE
                    and identifier(p["grant_id"]) and integer(p["grant_sequence"],1)
                    and type(p["grant_ms"]) is int and p["grant_ms"]==10000,"identity")
                require(self._hello_base is not None and all(
                    type(p[k]) is type(self._hello_base[k]) and p[k]==self._hello_base[k]
                    for k in BASE.split()),"identity")
                if self.session:
                    if p["grant_sequence"]<=self.session["grant_sequence"]:return
                    require(all(p[k]==self.session[k] for k in BASE.split()),"revision_conflict")
                    deadline=min(now+10,self.grant_until+5*(p["grant_sequence"]-self.session["grant_sequence"]))
                    proved=consume_grant_proof(self._proofs,p.get("grant_request_nonce"),now)
                    if proved is not None:deadline=max(deadline,proved)
                else:
                    # Initial lease/grant proof is ORIGINAL open send, never receipt.
                    require(all(p[k]==self.open_request[k] for k in ("api","controller_id","boot_id","epoch")),"identity")
                    deadline=self.open_sent+10
                require(now<deadline,"stale_grant")
                self.session=p;self.grant_until=deadline
                self._capability=None;self._snapshot=None
                self.error="graph_session_readback_required"
                await self._heartbeat();self.changed();return
            if topic=="fw/graph_capability":
                obj(p,"api capability sequence")
                require(type(p["api"]) is int and p["api"]==2 and integer(p["sequence"],1),"schema")
                if not self._live() or p["sequence"]<=self._cap_highwater:return
                cap=p["capability"]
                if type(cap) is not dict or not self._scope(cap):return
                ctx=GraphValidationContext(controller_id=cap["controller_id"],boot_id=cap["boot_id"],
                    epoch=cap["epoch"],adapter_id=self.adapter_id,
                    adapter_session_id=cap["adapter_session_id"],grant_id=cap["grant_id"],
                    grant_sequence=cap["grant_sequence"],current_revision=cap["config_revision"],
                    mapping_revision=cap["mapping_revision"],mapping_digest=cap["mapping_digest"],
                    qualification_digest=self.profile.qualification_digest)
                self.journal._capability(ctx,cap,now,False)
                self._cap_highwater=p["sequence"];self._capability=cap;self._cap_received=now
                if self._readback_key!=self._data_key(cap) and self._snapshot is None:
                    await self._request_snapshot()
                return
            if topic=="fw/config_result":
                # Presentation only: the actual core reports the NEW committed
                # DATA tuple using the original request's owner/grant. It cannot
                # satisfy _scope (which still has the old revision). Do not feed
                # this result to reconcile, grants, leases, sources or admission.
                obj(p,SESSION+" sequence status")
                attempt=self._config_attempt
                if (attempt is None or not self._live()
                    or not integer(p["sequence"],1) or p["sequence"]!=attempt["sequence"]
                    or not 0<=now-attempt["sent"]<10
                    or any(type(p[k]) is not type(v) or p[k]!=v
                           for k,v in attempt["owner"].items())):return
                result=None
                if (p["status"]=="graph_committed_no_admission"
                    and all(type(p[k]) is type(v) and p[k]==v
                            for k,v in attempt["target"].items())):
                    result="acknowledged_unverified"
                elif (p["status"] in ("revision_conflict","mapping_conflict")
                    and self._scope(p)):
                    result="conflict"
                    self.journal.invalidate();self.journal.status="graph_remote_conflict"
                    self.error="graph_remote_conflict"
                if result is not None and self._device_result!=result:
                    self._device_result=result;self.changed()
                return
            if not self._scope(p):return
            if topic=="fw/heartbeat_result":
                obj(p,SESSION+" binding_id sequence status")
                require(p["binding_id"]=="adapter" and integer(p["sequence"],1)
                    and p["status"] in ("accepted","duplicate"),"schema")
                proof=self._heartbeats.pop(p["sequence"],None)
                if proof and (proof[1],proof[2])==(p["grant_id"],p["grant_sequence"]):
                    # ACK can prove only original-send+lease; duplicate consumed once.
                    require(0<=now-proof[0]<15 and now<self.grant_until,"stale_grant")
                    self.lease_until=max(self.lease_until,proof[0]+15)
                return
            if topic=="fw/config_snapshot":
                obj(p,SESSION+" request_sequence config mapping boiler_output_enabled actuator_output_enabled")
                require(p["boiler_output_enabled"] is False and p["actuator_output_enabled"] is False,"outputs_not_locked")
                if not self._fresh() or self._snapshot is None:return
                pending=self._snapshot
                if (p["request_sequence"]!=pending["sequence"]
                    or type(p["request_sequence"]) is not int
                    or (p["grant_id"],p["grant_sequence"])!=(pending["grant_id"],pending["grant_sequence"])
                    or not 0<=now-pending["sent"]<10):return
                self._snapshot=None
                if p["config_revision"]==0:
                    require(p["config"] is None and p["mapping"] is None,"revision_conflict")
                    require(self.journal.state["accepted"] is None,"readback_required")
                    self.error="graph_staged_not_applied" if self.journal.state["staged"] else "graph_empty"
                else:
                    require(type(p["mapping"]) is dict
                        and digest(p["mapping"])==p["mapping_digest"],"mapping_conflict")
                    await self.journal.async_reconcile(p["config"],self._context(),self._capability,
                        self._cap_received,retained=False)
                    self.error=self.journal.status
                self._readback_key=self._data_key(p)
                self.changed()
            # Results/ACKs alone NEVER accept/apply configuration or refresh any
            # grant/lease/source/learning/readiness. Only actual scoped readback.
        except (GraphValidationError,ValueError,TypeError,KeyError,OverflowError):
            self.reset_session();self.error="graph_invalid_or_unsupported_wire";self.changed()

    async def poll(self):
        if self.closed:return
        now=self._now()
        if self.session:
            if now>=self.grant_until or self.lease_until and now>=self.lease_until:
                self.reset_session();self.error="graph_session_expired";self.changed();return
            if now-self._last_heartbeat>=2:await self._heartbeat()
            if self._snapshot:
                p=self._snapshot
                if now-p["sent"]>=10:
                    self._snapshot=None;self.journal.invalidate()
                elif now-p["last"]>=2 and p["tries"]<3:
                    p["last"]=now;p["tries"]+=1
                    await self.send("ha/snapshot_request",p["raw"]) # Exact original bytes.
        elif self.open_request and now-self._open_last>=3:
            if now-self.open_sent>=10 or self._open_tries>=3:
                self.open_request=None;self.error="graph_open_unconfirmed";self.changed()
            else:
                self._open_last=now;self._open_tries+=1
                await self.send("ha/open_session",canonical(self.open_request))

    async def async_stage(self,raw,mapping):
        ctx=self._context()
        candidate=await self.journal.async_stage(raw,mapping,ctx,self._capability,
            self._cap_received,retained=False)
        self.error=self.journal.status;self.changed();return candidate

    def review_candidate(self):
        ctx=self._context()
        state=self.journal.state
        require(state is not None and state["staged"] is not None,"nothing_staged")
        return self.journal.review_key(state["staged"],ctx)

    async def async_apply(self,reviewed=None):
        ctx=self._context()
        sequence=self.sequence["config"]+1;require(integer(sequence,1),"sequence_exhausted")
        self.sequence["config"]=sequence
        self._readback_key=None # Explicit mutation needs actual new readback.
        key=self.review_candidate()
        mapping_revision=self.journal.state["staged"]["mapping"]["mapping_revision"]
        pending=dict(sequence=sequence,sent=self._now(),
            owner={k:getattr(ctx,k) for k in ("controller_id","boot_id","epoch","adapter_id",
                "adapter_session_id","grant_id","grant_sequence")},
            target=dict(config_revision=key["revision"],config_digest=key["config_digest"],
                mapping_revision=mapping_revision,mapping_digest=key["mapping_digest"]))
        try:
            raw=await self.journal.async_apply_tuple(self.send,ctx,self._capability,
                self._cap_received,sequence,retained=False,transport=TRANSPORT,reviewed=reviewed)
        finally:
            # A duplicate/rejected call must not overwrite the first send's ACK
            # correlation. The same worker consumes replies only after this call.
            if self.journal.apply_attempt==(key,sequence):
                self._config_attempt=pending;self._device_result=None
        self.error=self.journal.status;self.changed();return raw

    async def async_observation(self,*args,**kwargs):
        return # No active graph source/actuator execution or cached-source promotion.

    async def async_setpoint(self,*args,**kwargs):
        raise HomeAssistantError("graph_control_contract_unavailable")
