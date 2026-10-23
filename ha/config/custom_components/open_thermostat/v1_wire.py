
"""Bounded TEST-WIRE v1 shadow client; no actuator execution.

All timeouts use the receiver's local monotone clock, never FW milliseconds.
Native MQTT and Store are supplied by v1_mqtt; injected IO enables actual FW tests.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
import re
import secrets

from homeassistant.exceptions import HomeAssistantError

from .v1_model import Observation, RoomDecision
from .session_grant import register_grant_proof, consume_grant_proof, MAX_GRANT_PROOFS
from .boiler_fields import CAPABILITY as BOILER_CAPABILITY, BoilerFieldCache, MAX_BYTES as MAX_BOILER_BYTES
from .metric_snapshot import CAPABILITY,MAX_BYTES as MAX_METRIC_BYTES,EXPIRY_SECONDS,valid_snapshot

_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")
_HEX = re.compile(r"[0-9a-f]{64}")
MAX_BYTES = 8192
GRANT_NONCE_CAPABILITY = "session.grant_nonce.v1"
ROOM_NAMES_CAPABILITY = "display.room_names.v1"
COMFORT_CAPABILITY = "comfort.target.v1"
COMFORT_MODES = {"auto","off","temporary","boost","away","vacation","frost"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("ascii")).hexdigest()


def integer(value, low=0, high=4294967295):
    return type(value) is int and low <= value <= high


def identifier(value):
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def parse(raw):
    """Wire is ASCII without escapes; reject duplicates, deep/oversize trees."""
    if not isinstance(raw, str) or len(raw) > MAX_BYTES or not raw.isascii() or "\\" in raw:
        raise ValueError("invalid wire bytes")
    # Bound nesting before JSON allocation. Strings on this profile contain no escapes.
    depth = 0
    quoted = False
    for char in raw:
        if char == '"':
            quoted = not quoted
        elif not quoted:
            if char in "[{":
                depth += 1
                if depth > 12:
                    raise ValueError("wire depth")
            elif char in "]}":
                depth -= 1
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate member")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("non-finite number")
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    def nodes(item):
        if isinstance(item, dict):
            return 1 + sum(1 + nodes(x) for x in item.values())
        if isinstance(item, list):
            return 1 + sum(nodes(x) for x in item)
        return 1
    if not isinstance(value, dict) or nodes(value) > 512:
        raise ValueError("wire shape/budget")
    return value


class ShadowClient:
    def __init__(self, runtime, adapter_id, send, store, desired, mapping, clock,*,control_plan=None):
        if not identifier(adapter_id):
            raise ValueError("invalid local adapter owner")
        self.runtime, self.adapter_id = runtime, adapter_id
        self.controller_policy=getattr(runtime,"controller_policy_source_profile",None)
        if self.controller_policy is not None:
            self.controller_policy.validate()
            if self.controller_policy.adapter_id!=adapter_id:raise ValueError("controller_policy_owner_mismatch")
        self.source_policy_matched=False
        self.graph_source_review_required=False
        self.send, self.store, self.clock = send, store, clock
        self.desired, self.mapping = json.loads(canonical(desired)), json.loads(canonical(mapping))
        self.native_plan_source=getattr(runtime,"native_plan_source",None)
        self.native_plan_template=json.loads(canonical(control_plan)) if control_plan is not None else None
        self.native_plan_fenced=False
        self._native_entry_state=None
        self._native_snapshot_scope=None
        self._native_snapshot_at=0.0
        self._native_snapshot_request=None
        self._native_remote_known=False
        self._native_refresh_pending=False
        self._native_horizon_inhibit=False
        self._native_review=None
        self._native_apply_sent=False
        self._native_apply_scope=None
        self._native_state_receipt=None
        self._native_device_result=None
        self._native_legacy_supported=False
        self._native_legacy_verified=False
        if self.native_plan_source is not None:
            from .native_plan import NativePlanSource,native_entry_state
            if (type(self.native_plan_source) is not NativePlanSource
                    or self.controller_policy!=self.native_plan_source.policy
                    or control_plan is None):
                raise ValueError("native_plan_source_binding")
            self.native_plan_source.validate_plan(control_plan)
            if control_plan["zones"]!=self.desired or control_plan["mapping"]!=self.mapping:
                raise ValueError("native_plan_template_binding")
            self._native_entry_state=native_entry_state(runtime.entry)
        elif control_plan is not None:
            raise ValueError("native_plan_source_required")
        self.journal = {"accepted": None, "staged": None}
        self.identity = None
        self.session = None
        self.open_request = None
        self.open_sent = 0.0
        self.grant_until = 0.0
        self.lease_until = 0.0
        self.last_rx = 0.0
        self.sequence = defaultdict(int)
        self.pending = {}
        self.verified = False
        self.closed = False
        self.error = "not_connected"
        self._nonce = lambda: secrets.token_hex(12)
        self._close_io = None
        self.room_names_supported=False
        self.grant_nonce_supported=False
        self._grant_proofs={}
        self.boiler_fields_supported=False
        self.boiler_fields=BoilerFieldCache()
        self.metrics_supported=False
        self.comfort_supported=False
        self._metrics=None
        self._metrics_received=0.0
        self._metrics_highwater=0

    @property
    def metrics_payload(self):
        if (not self.ready or not self.metrics_supported or self._metrics is None
                or not 0<=self.clock()-self._metrics_received<EXPIRY_SECONDS):
            return None
        return dict(self._metrics) # Flat schema, no caller can mutate cached data.

    @property
    def metrics_key(self):
        return (self.session.get("adapter_session_id") if self.session else None,
                self._metrics_highwater,self.metrics_payload is not None)

    @property
    def ready(self):
        now = self.clock()
        return (not self.closed and not self.graph_source_review_required
                and not self._native_horizon_inhibit
                and (self.native_plan_source is None or self.native_source_current()) and self.verified and (self.controller_policy is None or self.source_policy_matched) and self.session is not None
                and self.session.get("mapping_ready") is True
                and now < self.grant_until and now < self.lease_until
                and now - self.last_rx < 15)

    def changed(self):
        self.runtime.diagnostics["transport"] = self.error
        self.runtime.diagnostics["controller_policy"]=("default_api1" if self.controller_policy is None else
            "source_identity_verified_shadow_only" if self.source_policy_matched else "source_identity_unverified")
        self.runtime._notify()

    async def async_start(self):
        stored = await self.store.async_load()
        if stored is not None:
            if not isinstance(stored, dict) or set(stored) != {"accepted", "staged"}:
                raise ValueError("invalid durable mapping journal")
            for record in stored.values():
                if record is not None and not self.valid_record(record):
                    raise ValueError("invalid durable mapping record")
            self.journal = stored
        if self.native_plan_source is not None:
            for record in self.journal.values():
                if record is not None:
                    if record["config"].get("schema")==1:
                        self.native_plan_source.validate_legacy_config(record["config"])
                        parse(canonical(record["mapping"])) # Bound old local mapping before any remote IO.
                    elif self.native_plan_source.is_predecessor_config(record["config"]):
                        self.native_plan_source.validate_predecessor_config(record["config"])
                        if record["config"]["mapping"]!=record["mapping"]:raise ValueError("native_plan_mapping_journal")
                    else:
                        self.native_plan_source.validate_plan(record["config"])
                        if record["config"]["mapping"]!=record["mapping"]:raise ValueError("native_plan_mapping_journal")
            self._native_apply_sent=self.journal["staged"] is not None

    def native_source_current(self):
        if self.native_plan_source is None:return False
        from . import (_selected_native_plan_source,_selected_graph_data_profile,
            _selected_graph_controller_source,_selected_controller_policy_source_profile)
        from .native_plan import native_entry_state
        try:
            source=self.native_plan_source;entry=self.runtime.entry
            if (self.closed or self.native_plan_fenced
                or self.runtime.hass.config_entries.async_get_entry(entry.entry_id) is not entry
                or entry.disabled_by is not None
                or self.runtime.native_plan_source!=source or self.controller_policy!=source.policy
                or self.runtime.controller_policy_source_profile!=source.policy
                or self.adapter_id!=source.policy.adapter_id
                or native_entry_state(entry)!=self._native_entry_state
                or _selected_native_plan_source(entry)!=source
                or _selected_graph_data_profile(entry) is not None
                or _selected_graph_controller_source(entry) is not None
                or _selected_controller_policy_source_profile(entry) is not None):
                return False
            source.validate_native(self.runtime.hass,entry)
            return True
        except Exception:
            return False

    def require_native_plan_review(self):
        if self.native_plan_source is None:raise ValueError("native_plan_not_selected")
        self.native_plan_fenced=True
        self.reset_session();self.error="native_plan_source_or_entry_changed";self.changed()

    def native_context(self):
        from .graph_shadow_validation import GraphValidationError
        if (not self.native_source_current() or not self.identity or not self.session
                or not self.source_policy_matched or self.clock()>=self.grant_until
                or self.clock()>=self.lease_until or self.clock()-self.last_rx>=15):
            raise GraphValidationError("native_plan_live_readback_required")
        return (self.identity,self.session["adapter_session_id"],self.session["config_revision"],
                self.session["config_digest"],self.controller_policy.profile_digest,self._native_entry_state)

    def native_desired_matches(self,config):
        if self.native_plan_template is None:return False
        expected=json.loads(canonical(self.native_plan_template))
        expected["revision"]=config.get("revision")
        return config==expected

    @property
    def graph_status(self):
        if self.native_plan_source is None:raise ValueError("native_plan_not_selected")
        accepted=self.journal["accepted"];staged=self.journal["staged"]
        return dict(status=self.error,journal_status=self.error,
            accepted_revision=accepted["config"]["revision"] if accepted else 0,
            staged_revision=staged["config"]["revision"] if staged else None,
            readback_verified=self.ready,device_result=self._native_device_result,data_scope=self.native_plan_source.profile_version,
            control_review_status="native_shadow_only_no_physical_authority")

    def review_candidate(self):
        from .graph_shadow_validation import GraphValidationError
        scope=self.native_context()
        staged=self.journal["staged"]
        if (staged is None or self._native_review is None or self._native_review[0]!=scope
                or self._native_review[1]!=staged["config_digest"] or self._native_apply_sent
                or not 0<=self.clock()-self._native_review[2]<300):
            raise GraphValidationError("native_plan_review_changed")
        return (scope,staged["config_digest"],self._native_review[2])

    @property
    def native_plan_readback_ready(self):
        """Read-only presentation of the existing prepare prerequisites.

        No grant, journal change, stage or implicit review is created here.
        The worker independently rechecks these prerequisites when preparing.
        """
        from .graph_shadow_validation import GraphValidationError
        if self.native_plan_source is None:
            return False
        try:
            scope=self.native_context()
        except GraphValidationError:
            return False
        return (self._native_remote_known and self._native_snapshot_scope==scope
            and 0<=self.clock()-self._native_snapshot_at<15 and not self._native_apply_sent)

    @property
    def current_native_room_state_verified(self):
        """A current validated wire-state receipt, not temperature qualification."""
        if not self.ready or self.native_plan_source is None or self._native_state_receipt is None:
            return False
        from .graph_shadow_validation import GraphValidationError
        try:
            scope=self.native_context()
        except GraphValidationError:
            return False
        received_scope,received_at=self._native_state_receipt
        return received_scope==scope and 0<=self.clock()-received_at<15

    async def async_request_native_plan_readback(self):
        """Explicit read-only refresh on the owning worker; never stage or apply."""
        from .graph_shadow_validation import GraphValidationError
        self.native_context()
        if self.journal['staged'] is not None or self._native_apply_sent:
            raise GraphValidationError('controller_plan_pending')
        if not any(key[0]=='fw/snapshot_result' for key in self.pending):
            await self.message('ha/snapshot_request','snapshot',{})

    async def async_prepare_native_plan(self):
        from .graph_shadow_validation import GraphValidationError
        scope=self.native_context()
        if (not self._native_remote_known or self._native_snapshot_scope!=scope
                or not 0<=self.clock()-self._native_snapshot_at<15 or self._native_apply_sent):
            raise GraphValidationError("native_plan_current_readback_required")
        config,mapping=await self.native_plan_source.async_configuration(self.runtime.hass,self.runtime.entry)
        if self.native_context()!=scope:raise GraphValidationError("native_plan_owner_changed")
        current_revision=self.session["config_revision"]
        if current_revision>=4294967295:raise GraphValidationError("revision_exhausted")
        config["revision"]=current_revision+1
        self.native_plan_source.validate_plan(config)
        record=dict(config=config,config_digest=digest(config),mapping=mapping)
        probe=self.envelope("config");probe.update(expected_revision=current_revision,config_digest=record["config_digest"],config=config)
        parse(canonical(probe))
        current=await self.store.async_load()
        if current is None:current={"accepted":None,"staged":None}
        if current!=self.journal or self.native_context()!=scope:
            raise GraphValidationError("native_plan_source_changed_before_stage")
        # Complete native entry/profile/registry fence runs after FINAL Store await.
        self.native_plan_template=json.loads(canonical(config))
        self.desired,self.mapping=json.loads(canonical(config["zones"])),json.loads(canonical(mapping))
        self._native_horizon_inhibit=False # Explicit review or previously authorized unchanged-week refresh.
        accepted=self.journal["accepted"]
        if accepted is not None and self.native_desired_matches(accepted["config"]) and self.journal["staged"] is None:
            self.error="native_plan_already_applied";self.changed();return None
        await self.save({**self.journal,"staged":record})
        if self.native_context()!=scope:raise GraphValidationError("native_plan_source_changed_after_stage")
        self._native_review=(scope,record["config_digest"],self.clock())
        self.verified=False;self.error="native_plan_staged_not_applied";self.changed()
        return record

    async def async_request_native_horizon_refresh(self):
        """Existing daily callback, fresh exact readback before any new stage.

        Only a previously explicitly applied local week can be regenerated.
        Helper exports and changed/pending/unknown plans still require review.
        """
        from .graph_shadow_validation import GraphValidationError
        accepted=self.journal["accepted"]
        if (not self.native_plan_source.policy.week_reviewed or accepted is None
                or self._native_horizon_inhibit
                or self.journal["staged"] is not None or self._native_apply_sent
                or any(room.schedule is not None for room in self.runtime.rooms.values())):
            raise GraphValidationError("native_horizon_review_required")
        self.native_context() # Current owner/session/grant, never restored permission.
        self._native_refresh_pending=True
        self.verified=False
        await self.message("ha/snapshot_request","snapshot",{})
        self.error="native_plan_horizon_readback_required";self.changed()

    async def async_refresh_native_horizon(self,config,scope):
        from datetime import UTC,datetime
        from homeassistant.util import dt as dt_util
        from .graph_shadow_validation import GraphValidationError
        windows={(z["schedule"]["valid_from_utc"],z["schedule"]["valid_until_utc"])
                 for z in config["zones"] if z["schedule"] is not None}
        if not windows:return False
        if len(windows)!=1:raise GraphValidationError("native_horizon_review_required")
        start,end=next(iter(windows))
        today=dt_util.utcnow().replace(hour=0,minute=0,second=0,microsecond=0)
        if int(today.timestamp())<=start:return False # No writes for same day/backward clock.
        if int(today.timestamp())>=end:raise GraphValidationError("native_horizon_expired_review_required")
        if (self.journal["staged"] is not None or self.journal["accepted"]["config"]!=config
                or self._native_apply_sent or self.native_context()!=scope
                or any(room.schedule is not None for room in self.runtime.rooms.values())):
            raise GraphValidationError("native_horizon_review_required")
        # Recompile the OLD interval from the unchanged saved local weeks.
        # Exact equality proves the new horizon cannot silently apply edits.
        reference,_=await self.native_plan_source.async_configuration(
            self.runtime.hass,self.runtime.entry,start=datetime.fromtimestamp(start,UTC))
        reference["revision"]=config["revision"]
        if reference!=config or self.native_context()!=scope:
            raise GraphValidationError("native_horizon_intent_changed")
        await self.async_prepare_native_plan() # Same Store lock/final-await fences and wire bounds.
        await self.async_apply(self.review_candidate()) # No new owner, journal, scheduler or retry policy.
        return True

    async def async_apply(self,reviewed=None):
        from .graph_shadow_validation import GraphValidationError
        key=self.review_candidate()
        if reviewed!=key:raise GraphValidationError("native_plan_review_changed")
        scope=self.native_context();record=self.journal["staged"]
        current=await self.store.async_load()
        if current!=self.journal or self.native_context()!=scope or self.review_candidate()!=key:
            raise GraphValidationError("native_plan_source_changed_before_send")
        self.native_plan_source.validate_plan(record["config"])
        self._native_apply_sent=True;self._native_apply_scope=scope
        self.verified=False;self.error="native_plan_send_unconfirmed";self.changed()
        # Exact already durable reviewed tuple; no raw profile/admission input.
        await self.message("ha/config","config",dict(expected_revision=self.session["config_revision"],
            config_digest=record["config_digest"],config=record["config"]))
        self.error="native_plan_awaiting_readback";self.changed()
        return "native_plan_send_unconfirmed"

    def native_config_result(self,p):
        """Current-request ACK presentation ONLY. True means consume/ignore.

        A successful config result uses the NEW revision with the OLD session.
        It therefore cannot pass same_config and is NEVER readback/admission.
        """
        expected={"api","controller_id","boot_id","epoch","config_revision","config_digest",
                  "adapter_session_id","binding_id","sequence","status"}
        if (set(p)!=expected or not integer(p["sequence"],1) or p["binding_id"]!="config"
                or not integer(p["config_revision"]) or not self.native_source_current()
                or self.session is None or p["adapter_session_id"]!=self.session["adapter_session_id"]):
            return True
        item=self.pending.get(("fw/config_result","config",p["sequence"]))
        now=self.clock()
        if item is None or not 0<=now-item["sent"]<8 or not now<item["deadline"]:
            return True
        request=json.loads(item["raw"]) # Existing bounded local outbound bytes.
        if p["status"] in ("applied","duplicate"):
            if (p["config_revision"]==request["config"]["revision"]
                    and p["config_digest"]==request["config_digest"]):
                self._native_device_result="acknowledged_unverified"
                self.changed()
            return True # No journal, ready, last_rx, grant, lease or sample change.
        if p["status"] in ("conflict","mapping_conflict","rejected","storage_fault") and self.same_config(p):
            self._native_device_result=("conflict" if p["status"] in ("conflict","mapping_conflict") else p["status"])
            return False # Preserve existing failure/STOP handling, never success.
        return True

    async def native_snapshot(self,p):
        from .graph_shadow_validation import GraphValidationError
        expected={"api","controller_id","boot_id","epoch","config_revision","config_digest","config",
            "adapter_id","adapter_session_id","grant_id","grant_sequence","request_sequence",
            "profile_digest","plan_contract","boiler_output_enabled","actuator_output_enabled"}
        proof=self._native_snapshot_request
        if not proof:return
        scope=self.native_context()
        if (set(p)!=expected or proof[0]!=scope or not self.clock()<proof[4]
            or not integer(p["request_sequence"],1) or p["request_sequence"]!=proof[1]
            or not integer(p["grant_sequence"],1) or p["adapter_id"]!=self.adapter_id
            or p["adapter_session_id"]!=self.session["adapter_session_id"]
            or p["grant_id"]!=proof[2] or p["grant_sequence"]!=proof[3]
            or p["plan_contract"]!=self.native_plan_source.profile_version or p["profile_digest"]!=self.controller_policy.profile_digest
            or p["boiler_output_enabled"] is not False or p["actuator_output_enabled"] is not False):
            return # No grant/lease/sample/last_rx renewal from stale/unrequested readback.
        self._native_snapshot_request=None
        refresh_requested=self._native_refresh_pending
        self._native_refresh_pending=False
        self.last_rx=self.clock();config=p["config"]
        self._native_snapshot_scope=scope;self._native_snapshot_at=self.clock()
        if config is None:
            if p["config_revision"]!=0 or p["config_digest"]!="":raise GraphValidationError("native_empty_snapshot")
            self._native_remote_known=True;self.verified=False
            if self._native_apply_sent and self._native_apply_scope==scope:
                self.error="native_plan_apply_unconfirmed"
            else:
                self._native_apply_sent=False
                self.error="native_plan_recovery_review_required" if self.journal["staged"] else "native_plan_unconfigured_review_required"
            self.changed();return
        predecessor=self.native_plan_source.is_predecessor_config(config)
        if config.get("schema")==1 or predecessor:
            if predecessor:self.native_plan_source.validate_predecessor_config(config)
            else:
                self.native_plan_source.validate_legacy_config(config)
                if not self._native_legacy_supported:raise GraphValidationError("native_legacy_capability_required")
            if digest(config)!=p["config_digest"] or config["revision"]!=p["config_revision"]:
                raise GraphValidationError("native_legacy_readback_digest")
            record=self.known(p["config_revision"],p["config_digest"])
            if record is None or record["config"]!=config:
                self._native_remote_known=False;self.verified=False
                self.error="native_plan_remote_conflict";self.changed();return
            self._native_remote_known=True;self._native_legacy_verified=True;self.verified=False
            if self.journal["staged"]==record:
                await self.save({"accepted":record,"staged":None})
                if self.native_context()!=scope:raise GraphValidationError("native_legacy_owner_changed_after_readback")
            if self._native_apply_sent and self._native_apply_scope==scope:
                self.error="native_plan_apply_unconfirmed"
            else:
                self._native_apply_sent=False
                self.error="native_plan_recovery_review_required" if self.journal["staged"] else (
                    "native_plan_profile_review_required" if predecessor else "native_plan_legacy_review_required")
            self.changed();return # READONLY metadata, never control/admission.
        self._native_legacy_verified=False
        self.native_plan_source.validate_plan(config)
        if digest(config)!=p["config_digest"] or config["revision"]!=p["config_revision"]:
            raise GraphValidationError("native_plan_readback_digest")
        record=self.known(p["config_revision"],p["config_digest"])
        if record is None or record["config"]!=config or record["mapping"]!=config["mapping"]:
            self._native_remote_known=False;self.verified=False;self.error="native_plan_remote_conflict";self.changed();return
        self._native_remote_known=True
        if self.journal["staged"]==record:
            await self.save({"accepted":record,"staged":None})
            if self.native_context()!=scope:raise GraphValidationError("native_plan_source_changed_after_readback")
            self._native_apply_sent=False;self._native_apply_scope=None;self._native_review=None
        elif self.journal["staged"] is not None:
            # Snapshot of OLD config must never erase a durable newer stage or
            # pretend an in-flight/ambiguous config was rolled back.
            self.verified=False
            if self._native_apply_sent and self._native_apply_scope==scope:
                self.error="native_plan_apply_unconfirmed"
            else:
                self._native_apply_sent=False;self.error="native_plan_recovery_review_required" if self._native_review is None else "native_plan_staged_not_applied"
            self.changed();return
        if not self.native_desired_matches(config):
            self.verified=False;self.error="native_plan_draft_changes_not_applied"
        elif self._native_horizon_inhibit:
            self.verified=False;self.error="native_plan_horizon_review_required"
        else:
            self.verified=self.session["mapping_ready"]
            self.error="shadow_ready" if self.verified else "mapping_not_admitted"
        if refresh_requested:
            try:
                if await self.async_refresh_native_horizon(config,scope):return
            except (ValueError,HomeAssistantError):
                self._native_horizon_inhibit=True
                self.verified=False;self.error="native_plan_horizon_review_required"
        self.changed()

    async def async_stage_graph_source_readback(self):
        source=getattr(self.runtime,"graph_controller_source",None)
        if source is None or self.controller_policy!=source.controller:
            raise ValueError("graph_control_source_invalid")
        source.validate()
        # SOURCE validation awaits native DATA. Snapshot the actual entry and
        # independently selected role now, then fence them AFTER its final
        # await, immediately BEFORE the first mirror stage. A plan digest does
        # not include adapter/entry/prefix/options ownership.
        from . import (_selected_graph_data_profile,_selected_graph_controller_source,
                       _selected_controller_policy_source_profile)
        entry=self.runtime.entry
        def entry_state():
            return canonical(dict(entry_id=entry.entry_id,unique_id=entry.unique_id,
                data=dict(entry.data),options=dict(entry.options),
                subentries={key:dict(kind=sub.subentry_type,data=dict(sub.data))
                    for key,sub in entry.subentries.items()}))
        before=entry_state()
        policy=_selected_controller_policy_source_profile(entry)
        def source_current():
            return (self.runtime.entry is entry and entry_state()==before
                and entry.unique_id==source.controller.entry_unique_id
                and entry.options.get("adapter_id",entry.data.get("adapter_id"))==self.adapter_id==source.controller.adapter_id
                and self.runtime.graph_controller_source==source
                and self.runtime.controller_policy_source_profile==self.controller_policy==source.controller
                and _selected_graph_controller_source(entry)==source
                and _selected_graph_data_profile(entry) is None
                and _selected_controller_policy_source_profile(entry)==policy
                and policy in (None,source.controller))
        if not source_current():
            raise ValueError("graph_control_source_changed_before_stage")
        config=source.projection()
        record={"config":config,"config_digest":digest(config),"mapping":source.record()["mapping"]}
        current=await self.store.async_load()
        # Same never-configured representation already used by async_start.
        if current is None:current={"accepted":None,"staged":None}
        if current!=self.journal:
            raise ValueError("graph_control_existing_journal_drift")
        # The mirror Store await may have yielded to a native/config/registry
        # edit. Check the SAME SOURCE/native DATA again BEFORE any mirror save,
        # not merely before subscriptions after staging.
        fresh_config,fresh_mapping=await source.async_configuration(self.runtime.hass,self.runtime.entry)
        if (fresh_config!=config or fresh_mapping!=record["mapping"]
                or self.closed or self.graph_source_review_required
                or self.journal!=current or not source_current()):
            raise ValueError("graph_control_source_changed_before_stage")
        if self.journal["accepted"]==record and self.journal["staged"] is None:return
        if self.journal["accepted"] is not None or self.journal["staged"] not in (None,record):
            raise ValueError("graph_control_existing_journal_conflict")
        # Explicit known SOURCE tuple is only STAGED. A fresh matching device
        # snapshot, not this Store save/ACK/graph_ready, performs reconciliation.
        await self.save({"accepted":None,"staged":record})
        if await self.store.async_load()!=self.journal:
            raise ValueError("graph_control_stage_readback_failed")

    @staticmethod
    def valid_record(record):
        try:
            return (set(record) == {"config", "config_digest", "mapping"}
                    and digest(record["config"]) == record["config_digest"]
                    and digest(record["mapping"]) == record["config"]["mapping_digest"]
                    and integer(record["config"]["revision"], 1))
        except (KeyError, TypeError, ValueError):
            return False

    def known(self, revision, config_digest):
        return next((record for record in self.journal.values()
                     if record and record["config"]["revision"] == revision
                     and record["config_digest"] == config_digest), None)

    async def save(self, journal):
        # Native Store's awaited atomic save completes BEFORE any config publish.
        snapshot = json.loads(canonical(journal))
        await self.store.async_save(snapshot)
        self.journal = snapshot

    def reset_session(self):
        self._native_state_receipt=None
        self._native_refresh_pending=False
        self._native_legacy_supported=False
        self._native_legacy_verified=False
        self._native_device_result=None
        self._native_snapshot_scope=None
        self._native_snapshot_request=None
        self._native_remote_known=False
        self._native_review=None
        self.source_policy_matched=False
        for item in self.pending.values():
            if item["future"] is not None and not item["future"].done():
                item["future"].cancel()
        self.session = None
        self.sequence.clear()
        self.pending.clear()
        self.open_request = None
        self.room_names_supported = False
        self.grant_nonce_supported = False
        self.comfort_supported = False
        self._grant_proofs.clear()
        self.verified = False
        self.grant_until = self.lease_until = 0
        self.runtime.decisions.clear()
        self.runtime.invalidate_context_sources()
        self._metrics=None
        self._metrics_received=0.0
        self._metrics_highwater=0
        self.boiler_fields.reset()

    def require_graph_source_review(self):
        if getattr(self.runtime,"graph_controller_source",None) is None:
            raise ValueError("graph_control_source_not_selected")
        self.graph_source_review_required=True
        self.reset_session()
        self.error="graph_control_source_review_required"
        self.changed()

    async def async_disconnected(self):
        self.reset_session()
        self.identity = None
        self.error = "disconnected"
        self.changed()

    async def receive(self, topic, raw, *, retained=False, received_at=None):
        if self.closed or retained or self.graph_source_review_required or self.native_plan_fenced:
            return
        if topic == "fw/telemetry/boiler_fields":
            self.receive_boiler_fields(raw,received_at)
            return # Read-only: never renew a control lease or a room measurement.
        if topic == "fw/telemetry/ems_metrics":
            self.receive_metrics(raw)
            return # No last_rx/lease/sample/control update, even for valid telemetry.
        if topic == "fw/availability" and raw in ("online", "offline"):
            # The actual PubSubClient transport uses plain LWT tokens. Neither
            # token establishes a session, source sample or fresh heat request.
            await self.async_disconnected()
            self.error = "firmware_offline" if raw == "offline" else "awaiting_firmware_handshake"
            self.changed()
            return
        try:
            payload = parse(raw)
            await self._receive(topic, payload)
        except (ValueError, KeyError, TypeError, OverflowError):
            self.reset_session()
            self.error = "invalid_firmware_message"
            self.changed()

    def receive_boiler_fields(self, raw, received_at=None):
        if not self.ready or not self.boiler_fields_supported:
            return
        try:
            if not isinstance(raw,str) or len(raw)>MAX_BOILER_BYTES:
                raise ValueError("boiler bytes")
            p=parse(raw)
            if (not self.same_identity(p) or not self.same_config(p)
                    or p.get("adapter_id")!=self.adapter_id
                    or p.get("adapter_session_id")!=self.session["adapter_session_id"]
                    or p.get("grant_id")!=self.session["grant_id"]
                    or p.get("grant_sequence")!=self.session["grant_sequence"]):
                return
            expected={"api","controller_id","boot_id","epoch","config_revision","config_digest","mode",
                      "adapter_id","adapter_session_id","grant_id","grant_sequence","sequence","group",
                      "boiler_output_enabled","actuator_output_enabled","values"}
            if (set(p)!=expected or p["mode"]!="shadow" or p["boiler_output_enabled"] is not False
                    or p["actuator_output_enabled"] is not False or not integer(p["sequence"],1)
                    or type(p["grant_sequence"]) is not int):
                raise ValueError("boiler envelope")
            now=self.clock()
            if received_at is None:
                received_at=now
            if (type(received_at) not in (int,float) or not math.isfinite(received_at)
                    or not 0<=now-received_at<15):
                raise ValueError("boiler local queue age")
            self.boiler_fields.accept(p["values"],p["group"],p["sequence"],received_at)
            self.runtime.diagnostics["boiler_fields"]="read_only_not_control_qualified"
        except (ValueError,TypeError,KeyError,OverflowError):
            self.boiler_fields.invalid=True
            self.runtime.diagnostics["boiler_fields"]="invalid_read_only_fields"
        self.runtime._notify()

    def receive_metrics(self,raw):
        if not self.ready or not self.metrics_supported:
            return
        try:
            if not isinstance(raw,str) or len(raw)>MAX_METRIC_BYTES:
                raise ValueError("metric budget")
            p=parse(raw)
            # Foreign/stale scope cannot disturb a legitimate current display.
            if (not self.same_identity(p) or not self.same_config(p)
                    or p.get("adapter_id")!=self.adapter_id
                    or p.get("adapter_session_id")!=self.session["adapter_session_id"]
                    or p.get("grant_id")!=self.session["grant_id"]
                    or p.get("grant_sequence")!=self.session["grant_sequence"]):
                return
            expected={"api","controller_id","boot_id","epoch","config_revision","config_digest","mode",
                      "adapter_id","adapter_session_id","grant_id","grant_sequence","sequence",
                      "boiler_output_enabled","actuator_output_enabled","metrics"}
            if (set(p)!=expected or p["mode"]!="shadow" or p["boiler_output_enabled"] is not False
                    or p["actuator_output_enabled"] is not False or not integer(p["sequence"],1)
                    or type(p["grant_sequence"]) is not int or not valid_snapshot(p["metrics"])):
                raise ValueError("metric shape")
            if p["sequence"]<=self._metrics_highwater:
                return # Duplicate/reorder can never refresh age or revive expired data.
            self._metrics=dict(p["metrics"]);self._metrics_highwater=p["sequence"]
            self._metrics_received=self.clock()
            self.runtime.diagnostics["metrics"]="read_only_snapshot_not_control_qualified"
        except (ValueError,TypeError,KeyError,OverflowError):
            self._metrics=None # Preserve high-water and valid CONTROL session.
            self.runtime.diagnostics["metrics"]="invalid_read_only_snapshot"
        self.runtime._notify()

    def same_identity(self, p):
        return (self.identity and type(p.get("api")) is int and p.get("api") == 1
                and p.get("controller_id") == self.identity[0]
                and p.get("boot_id") == self.identity[1]
                and integer(p.get("epoch"), 1) and p.get("epoch") == self.identity[2])

    def same_config(self, p):
        return (self.session is not None and
                integer(p.get("config_revision")) and p.get("config_revision") == self.session["config_revision"] and
                p.get("config_digest") == self.session["config_digest"])

    def source_policy_matches(self,p):
        if self.controller_policy is None:
            if "source_policy" not in p:return True
            self.reset_session();self.error="controller_policy_not_selected";self.changed();return False
        if not self.controller_policy.matches(p):
            self.reset_session();self.error="controller_policy_mismatch";self.changed();return False
        self.source_policy_matched=True
        return True

    async def _receive(self, topic, p):
        if topic == "fw/hello":
            if (not integer(p.get("api"), 1, 1) or p.get("mode") != "shadow"
                or not all(identifier(p.get(k)) for k in ("controller_id", "boot_id", "challenge_id"))
                or not integer(p.get("epoch"), 1)
                or not integer(p.get("config_revision"))
                or not isinstance(p.get("config_digest"), str)
                or (p["config_revision"] == 0 and p["config_digest"] != "")
                or (p["config_revision"] != 0 and not _HEX.fullmatch(p["config_digest"]))
                or p.get("lease_ms") != 15000 or p.get("grant_ms") != 10000
                or type(p.get("storage_fault", False)) is not bool):
                raise ValueError("hello")
            new_identity = (p["controller_id"], p["boot_id"], p["epoch"])
            if self.identity and new_identity[:2] == self.identity[:2] and new_identity[2] < self.identity[2]:
                return
            if p.get("storage_fault"):
                self.reset_session()
                self.error = "firmware_storage_fault"
                self.changed()
                return
            if new_identity != self.identity or (self.session and not self.same_config(p)):
                self.reset_session()
                self.identity = new_identity
            if not self.source_policy_matches(p):return
            session_caps=p.get("session_capabilities",[])
            self.grant_nonce_supported=(type(session_caps) is list and len(session_caps)<=8
                and all(isinstance(cap,str) and len(cap)<=64 for cap in session_caps)
                and GRANT_NONCE_CAPABILITY in session_caps)
            if not self.grant_nonce_supported:
                self._grant_proofs.clear()
            comfort_caps=p.get("control_capabilities",[])
            self.room_names_supported = (self.native_plan_source is not None
                and type(comfort_caps) is list and len(comfort_caps)<=8
                and all(type(cap) is str and len(cap)<=64 for cap in comfort_caps)
                and ROOM_NAMES_CAPABILITY in comfort_caps)
            if self.native_plan_source is not None:
                if (type(comfort_caps) is not list or len(comfort_caps)>8 or self.native_plan_source.profile_version not in comfort_caps):
                    self.reset_session();self.error="native_plan_capability_unavailable";self.changed();return
                from .native_plan import LEGACY_CAPABILITY,EVOLUTION_CAPABILITY
                if self.native_plan_source.predecessor is not None and EVOLUTION_CAPABILITY not in comfort_caps:
                    self.reset_session();self.error="native_profile_evolution_capability_required";self.changed();return
                self._native_legacy_supported=LEGACY_CAPABILITY in comfort_caps
                if self.native_plan_source.policy.legacy_readback_reviewed and not self._native_legacy_supported:
                    self.reset_session();self.error="native_legacy_capability_required";self.changed();return
            self.comfort_supported=(type(comfort_caps) is list and len(comfort_caps)<=8
                and all(isinstance(cap,str) and len(cap)<=64 for cap in comfort_caps)
                and COMFORT_CAPABILITY in comfort_caps)
            if any("comfort" in z for z in self.desired) and not self.comfort_supported:
                self.reset_session();self.error="comfort_capability_unavailable";self.changed();return
            caps=p.get("read_only_capabilities",[])
            self.boiler_fields_supported=(type(caps) is list and len(caps)<=8
                and all(isinstance(cap,str) and len(cap)<=64 for cap in caps) and BOILER_CAPABILITY in caps)
            if not self.boiler_fields_supported:
                self.boiler_fields.reset()
            self.metrics_supported=(type(caps) is list and len(caps)<=8
                and all(isinstance(cap,str) and len(cap)<=64 for cap in caps) and CAPABILITY in caps)
            if not self.metrics_supported:
                self._metrics=None
            self.last_rx = self.clock()
            if self.session:
                return
            known = self.known(p["config_revision"], p["config_digest"])
            if self.native_plan_source is not None and known is not None and not self.native_desired_matches(known["config"]):
                known=None # Config-only session; old samples cannot run a dirty desired plan.
            # Unknown remote revision is diagnostic-only: never silently adopt.
            revision, known_digest = ((p["config_revision"], p["config_digest"])
                                      if known else (0, ""))
            if (self.native_plan_source is not None and self.open_request is not None
                    and self.open_request["challenge_id"] != p["challenge_id"]):
                # Same-identity lease expiry rotates the firmware challenge. A
                # pending request is NOT authority and must not replay the old
                # challenge. Fresh nonce and unchanged independent SOURCE policy.
                self.open_request = None
            if self.open_request is None:
                self.open_request = dict(
                    api=1, controller_id=p["controller_id"], boot_id=p["boot_id"],
                    epoch=p["epoch"], challenge_id=p["challenge_id"],
                    adapter_id=self.adapter_id, client_nonce=self._nonce(),
                    known_revision=revision, known_digest=known_digest)
                if self.native_plan_source is not None:
                    self.open_request.update(source_profile_digest=self.controller_policy.profile_digest,plan_contract=self.native_plan_source.profile_version)
                elif self.controller_policy is not None:
                    self.open_request.update(source_profile_digest=self.controller_policy.profile_digest,
                                             source_config_pin=self.controller_policy.config_digest)
                self.open_sent = self.clock()
            elif self.clock() - self.open_sent >= 10:
                self.open_request = None
                return  # Next fresh hello; no cached-challenge admission.
            await self.send("ha/open_session", canonical(self.open_request))
            return

        if not self.same_identity(p):
            return
        if topic == "fw/session":
            if (not self.open_request or p.get("client_nonce") != self.open_request["client_nonce"]
                or p.get("adapter_id") != self.adapter_id
                or not all(identifier(p.get(k)) for k in ("adapter_session_id", "grant_id"))
                or not integer(p.get("grant_sequence"), 1)
                or p.get("grant_ms") != 10000 or type(p.get("mapping_ready")) is not bool
                or not integer(p.get("config_revision"))):
                raise ValueError("session")
            if self.session:
                if p["adapter_session_id"] != self.session["adapter_session_id"]:
                    return
                if p["grant_sequence"] <= self.session["grant_sequence"]:
                    return  # Repeated status may NOT extend a grant.
                if not self.same_config(p):
                    raise ValueError("session config changed")
                # Safe old-peer fallback: minimum5s per rotation, NOT receipt+10.
                grant_deadline = min(self.clock() + 10, self.grant_until +
                                     5 * (p["grant_sequence"] - self.session["grant_sequence"]))
                proof=p.get("grant_request_nonce")
                if self.grant_nonce_supported and identifier(proof):
                    deadline=consume_grant_proof(self._grant_proofs,proof,self.clock())
                    if deadline is not None:
                        # SAME original-send proof used by explicit graph owner.
                        grant_deadline=max(grant_deadline,deadline)
                delay_bound = self.clock() + 10 - grant_deadline
            else:
                delay_bound = self.clock() - self.open_sent
            if delay_bound < 0 or delay_bound >= 10:
                raise ValueError("late grant")
            self.session = p
            self.grant_until = self.clock() + 10 - delay_bound
            self.last_rx = self.clock()
            await self.message("ha/heartbeat", "adapter", {})
            self.changed()
            return

        if (self.native_plan_source is not None and topic=="fw/config_result"
                and self.native_config_result(p)):
            return
        if self.session is None or not self.same_config(p):
            return
        if topic=="fw/state/zones" and not self.source_policy_matches(p):return
        if not(self.native_plan_source is not None and topic=="fw/config_snapshot"):
            self.last_rx = self.clock()
        if topic.endswith("_result"):
            if p.get("adapter_session_id") != self.session["adapter_session_id"]:
                return
            key = (topic, p.get("binding_id"), p.get("sequence"))
            pending = self.pending.get(key)
            if pending is None:
                return
            if p.get("status") not in {"accepted", "duplicate", "applied", "conflict", "rejected", "storage_fault", "mapping_conflict"}:
                raise ValueError("result")
            self.pending.pop(key)
            status = p["status"]
            if status in {"rejected", "conflict", "storage_fault", "mapping_conflict"}:
                self.error = status
                if topic == "fw/user_command_result" and not pending["future"].done():
                    pending["future"].set_exception(HomeAssistantError("Firmware rejected shadow command"))
                if status == "storage_fault":
                    self.reset_session()
                self.changed()
                return
            if topic == "fw/heartbeat_result":
                # Use original publish timestamp, not receipt, as conservative start.
                self.lease_until = pending["sent"] + 15
                if not self.verified:
                    await self.message("ha/snapshot_request", "snapshot", {})
            if topic == "fw/user_command_result" and not pending["future"].done():
                pending["future"].set_result(None)
            return

        if topic == "fw/config_snapshot":
            await self.snapshot(p)
            return
        if topic == "fw/state/zones":
            if (p.get("mode") != "shadow" or p.get("boiler_output_enabled") is not False
                or p.get("actuator_output_enabled") is not False
                or type(p.get("adapter_alive")) is not bool or not isinstance(p.get("zones"), list)):
                raise ValueError("not shadow state")
            if not self.ready or not p["adapter_alive"]:
                self._native_state_receipt=None
                self.runtime.decisions.clear()
                self.changed()
                return
            rows = p["zones"]
            if len(rows) != len(self.runtime.rooms) or {r.get("zone_id") for r in rows} != set(self.runtime.rooms):
                raise ValueError("state room mismatch")
            decisions = {}
            for row in rows:
                if (row["zone_id"] in decisions or not isinstance(row.get("reason"), str)
                    or len(row["reason"]) > 64 or not integer(row.get("sample_state"), 0, 6)
                    or row.get("target_source") not in ({"base","schedule","temporary","off","boost","away","vacation","frost","window","presence","limit"} if self.comfort_supported else {"base","schedule","temporary","off"})
                    or (row.get("sample_age_ms") is not None and not integer(row["sample_age_ms"], 0, 9007199254740991))
                    or (row.get("temperature_centi_c") is not None and
                        (row.get("sample_state") != 1 or row.get("sample_age_ms") is None
                         or row["sample_age_ms"] >= self.runtime.rooms[row["zone_id"]].maximum_age_ms))
                    or (row.get("demand") is True and (row.get("temperature_centi_c") is None or row.get("target_centi_c") is None))):
                    raise ValueError("state quality/duplicate")
                room=self.runtime.rooms[row["zone_id"]]
                if room.comfort is not None and (not self.comfort_supported or row.get("comfort_mode") not in COMFORT_MODES
                    or not integer(row.get("override_remaining_ms"),0,43200000)
                    or not integer(row.get("vacation_until_utc"),0,4102444800)
                    or type(row.get("learning_allowed")) is not bool
                    or (row.get("target_centi_c") is not None and
                        not room.minimum_target_centi_c<=row["target_centi_c"]<=room.maximum_target_centi_c)):
                    raise ValueError("comfort state")
                decisions[row["zone_id"]] = RoomDecision(
                    row["target_centi_c"], row["temperature_centi_c"], row["demand"], row["reason"],
                    row["target_source"],row.get("comfort_mode"),row.get("override_remaining_ms",0),row.get("vacation_until_utc",0))
            if self.native_plan_source is not None:
                self._native_state_receipt=(self.native_context(),self.clock())
            self.runtime.decisions = decisions
            self.error = "shadow_ready"
            self.changed()

    async def snapshot(self, p):
        if self.native_plan_source is not None:
            return await self.native_snapshot(p)
        config = p.get("config")
        if config is None:
            if p["config_revision"] != 0 or p["config_digest"] != "":
                raise ValueError("empty snapshot")
            await self.propose(0)
            return
        if digest(config) != p["config_digest"] or config.get("revision") != p["config_revision"]:
            raise ValueError("snapshot digest")
        if self.controller_policy is not None and p["config_digest"]!=self.controller_policy.config_digest:
            self.reset_session();self.error="controller_policy_config_mismatch";self.changed();return
        record = self.known(p["config_revision"], p["config_digest"])
        if record is None or record["config"] != config:
            self.error = "mapping_conflict"
            self.verified = False
            self.changed()
            return
        if self.journal["accepted"] != record or self.journal["staged"] is not None:
            await self.save({"accepted": record, "staged": None})
        if config["mapping_digest"] != digest(self.mapping) or config["zones"] != self.desired:
            await self.propose(config["revision"])
            return
        self.verified = self.session["mapping_ready"]
        self.error = "shadow_ready" if self.verified else "mapping_not_admitted"
        self.changed()

    async def propose(self, current_revision):
        if self.native_plan_source is not None:
            self.verified=False;self.error="native_plan_explicit_review_required";self.changed();return
        if getattr(self.runtime,"graph_controller_source",None) is not None:
            # This route consumes a reviewed graph projection readback only.
            # Unknown/empty remote config must never become an API1 write path.
            self.require_graph_source_review()
            return
        if current_revision >= 4294967295:
            raise ValueError("revision exhausted")
        config = {"schema": 1, "mode": "shadow", "revision": current_revision + 1,
                  "mapping_digest": digest(self.mapping), "zones": json.loads(canonical(self.desired))}
        if len(canonical(config).encode("ascii")) > 4096:
            raise ValueError("configuration budget exceeded")
        record = {"config": config, "config_digest": digest(config), "mapping": json.loads(canonical(self.mapping))}
        if self.controller_policy is not None and record["config_digest"]!=self.controller_policy.config_digest:
            self.reset_session();self.error="controller_policy_config_mismatch";self.changed();return
        # Also validate full wire budget BEFORE staging.
        probe = self.envelope("config")
        probe.update(expected_revision=current_revision, config_digest=record["config_digest"], config=config)
        parse(canonical(probe))
        await self.save({**self.journal, "staged": record})
        await self.message("ha/config", "config", {
            "expected_revision": current_revision, "config_digest": record["config_digest"], "config": config})
        self.verified = False
        self.error = "awaiting_config_readback"
        self.changed()

    def envelope(self, binding):
        if self.native_plan_source is not None and not self.native_source_current():
            self.require_native_plan_review()
            raise HomeAssistantError("Native installation/entry/registry changed")
        if self.session is None or self.clock() >= self.grant_until:
            raise HomeAssistantError("No fresh firmware grant")
        return dict(api=1, controller_id=self.identity[0], boot_id=self.identity[1],
                    epoch=self.identity[2], adapter_id=self.adapter_id,
                    adapter_session_id=self.session["adapter_session_id"],
                    grant_id=self.session["grant_id"], grant_sequence=self.session["grant_sequence"],
                    config_revision=self.session["config_revision"], binding_id=binding,
                    sequence=self.sequence[binding] + 1)

    async def message(self, topic, binding, body, future=None):
        p = self.envelope(binding)
        p.update(body)
        if topic=="ha/heartbeat" and self.room_names_supported and self.ready:
            names=[]
            for room_id in sorted(self.runtime.rooms):
                name=self.runtime.rooms[room_id].name
                # A display-only UTF-8 prefix; the actual saved name is retained.
                label=''.join(c for c in name.strip() if ord(c)>=32 and ord(c)!=127)
                label=label.encode('utf-8',errors='ignore')[:80].decode('utf-8',errors='ignore')
                if not label:
                    names=[];break
                names.append({'zone_id':room_id,'name_utf8_hex':label.encode('utf-8').hex()})
            if 1<=len(names)<=2:p['room_names']=names
        if topic=="ha/heartbeat" and self.grant_nonce_supported:
            # Session-local HB sequence prevents reuse even if a test RNG repeats.
            p["grant_request_nonce"]=f"g{p['sequence']:08x}{self._nonce()[:20]}"
            if not identifier(p["grant_request_nonce"]):
                raise HomeAssistantError("Invalid grant request nonce")
        raw = canonical(p)
        parse(raw)
        self.sequence[binding] += 1
        result_topic = {"ha/heartbeat": "fw/heartbeat_result", "ha/config": "fw/config_result",
                        "ha/observations": "fw/observation_result", "ha/user_command": "fw/user_command_result",
                        "ha/snapshot_request": "fw/snapshot_result"}[topic]
        key = (result_topic, binding, p["sequence"])
        sent=self.clock()
        self.pending[key] = {"topic": topic, "raw": raw, "sent": sent, "last": sent,
                             "tries": 1, "future": future, "deadline": self.grant_until}
        if len(self.pending) > 48:
            self.pending.pop(key)
            raise HomeAssistantError("Bounded shadow command queue full")
        if topic=="ha/heartbeat" and self.grant_nonce_supported:
            register_grant_proof(self._grant_proofs,p["grant_request_nonce"],sent)
        if self.native_plan_source is not None and topic=="ha/config":
            self._native_device_result=None
        if self.native_plan_source is not None and topic=="ha/snapshot_request":
            self._native_snapshot_request=(self.native_context(),p["sequence"],p["grant_id"],p["grant_sequence"],self.grant_until)
        await self.send(topic, raw)

    async def async_observation(self, room_id, observation: Observation):
        if not self.ready:
            return
        room = self.runtime.rooms[room_id]
        age = observation.source_age_ms or 0
        if observation.observed_monotonic is not None:
            age += math.ceil(max(0, self.clock() - observation.observed_monotonic) * 1000)
        usable = (observation.quality == "qualified" and observation.temperature_c is not None
                  and age < room.maximum_age_ms)
        binding=f"s_{room_id}"
        if self.native_plan_source is not None:
            # The complete accepted plan owns the actual sensor stream ID.
            # Never infer a legacy naming convention from the HA room UUID.
            binding=next(z["sensor_id"] for z in self.desired if z["zone_id"]==room_id)
        await self.message("ha/observations", binding, {
            "zone_id": room_id, "source_available": usable,
            "temperature_c": observation.temperature_c if usable else 0,
            "source_sample_age_ms": age if usable else 0,
            "evidence": "physical_report" if usable else "unverified",
            **(self.runtime.comfort_context(room) if room.comfort is not None else {})})

    async def async_setpoint(self, room_id, centi_c):
        if not self.ready or room_id not in self.runtime.rooms or not integer(centi_c, 500, 3500):
            raise HomeAssistantError("Shadow mapping not ready")
        if self.runtime.rooms[room_id].comfort is not None:
            await self.async_comfort(room_id,"temporary",temperature=centi_c/100)
            return
        future = self.runtime.hass.loop.create_future()
        await self.message("ha/user_command", room_id, {
            "mode": "temporary", "temperature_centi_c": centi_c, "duration_ms": 3600000}, future)
        await future  # Bounded by poll(); teardown cancels unresolved futures.

    async def async_hvac_mode(self, room_id, mode):
        room = self.runtime.rooms.get(room_id)
        if mode not in ("heat", "off") or not self.ready or room is None:
            raise HomeAssistantError("Shadow HVAC mode/mapping unavailable")
        if room.comfort is not None:
            # Keep existing comfort priority/capability/owner validation.
            await self.async_comfort(room_id, "off" if mode == "off" else "auto")
            return
        future = self.runtime.hass.loop.create_future()
        # API1 requires temperature/duration even for off/auto; the controller
        # ignores them in these modes. Use validated base, not an old override.
        await self.message("ha/user_command", room_id, {
            "mode": "off" if mode == "off" else "auto",
            "temperature_centi_c": room.base_centi_c, "duration_ms": 60000}, future)
        await future  # Existing timeout/teardown, never persist/replay.

    async def async_comfort(self,room_id,mode,*,temperature=None,duration_ms=None,vacation_until_utc=0):
        from .v1_model import target_centi
        room=self.runtime.rooms.get(room_id)
        if not self.ready or not self.comfort_supported or room is None or room.comfort is None or mode not in COMFORT_MODES:
            raise HomeAssistantError("Comfort capability/mapping unavailable")
        target=None
        duration=0
        if mode in {"temporary","boost"}:
            try:
                target=target_centi(temperature if temperature is not None else (room.maximum_target_centi_c if mode=="boost" else room.base_centi_c)/100)
            except ValueError as err:
                raise HomeAssistantError(str(err)) from err;
            if not room.minimum_target_centi_c<=target<=room.maximum_target_centi_c:
                raise HomeAssistantError("Comfort target outside room limits")
            duration=duration_ms if duration_ms is not None else min(room.comfort["temporary_ms"],14400000 if mode=="boost" else 43200000)
            if not integer(duration,1000,14400000 if mode=="boost" else 43200000):
                raise HomeAssistantError("Comfort duration invalid")
        elif temperature is not None or duration_ms is not None:
            raise HomeAssistantError("Unexpected comfort target/duration")
        if not integer(vacation_until_utc,0,4102444800) or (mode!="vacation" and vacation_until_utc):
            raise HomeAssistantError("Vacation expiry invalid")
        if mode=="vacation":
            from homeassistant.util import dt as dt_util
            now=int(dt_util.utcnow().timestamp())
            if not now<vacation_until_utc<=now+366*86400:
                raise HomeAssistantError("Vacation needs a bounded future UTC expiry")
        future=self.runtime.hass.loop.create_future()
        await self.message("ha/user_command",room_id,{"mode":mode,"temperature_centi_c":target,
            "duration_ms":duration,"vacation_until_utc":vacation_until_utc},future)
        await future # Only admitted fw/state confirms a target. Never store/replay commands.

    async def poll(self):
        if self.closed:
            return
        if self.native_plan_source is not None and not self.native_source_current():
            self.require_native_plan_review()
            return # No old exact-byte retry after SOURCE/registry/owner drift.
        now = self.clock()
        for key, item in list(self.pending.items()):
            if now >= item["deadline"] or now - item["sent"] >= 8 or item["tries"] >= 3:
                self.pending.pop(key, None)
                if item["future"] is not None and not item["future"].done():
                    item["future"].set_exception(HomeAssistantError("Shadow acknowledgement timed out; effect unknown"))
                self.error = "ack_timeout_effect_unknown"
            elif now - item["last"] >= 2:
                # Critical: exact original complete bytes, including original grant.
                item["tries"] += 1
                item["last"] = now
                await self.send(item["topic"], item["raw"])
        if self.session and now < self.grant_until:
            if not any(k[0] == "fw/heartbeat_result" for k in self.pending):
                await self.message("ha/heartbeat", "adapter", {})
        if self.session and (now - self.last_rx >= 15 or (self.lease_until and now >= self.lease_until)):
            await self.async_disconnected()
        self.changed()

    async def async_close(self):
        self.closed = True
        for item in self.pending.values():
            if item["future"] is not None and not item["future"].done():
                item["future"].cancel()
        self.reset_session()
        if self._close_io:
            await self._close_io()
