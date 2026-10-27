"""Original native HA person reports as logical context, never physical proof.

The reviewed adapter recognises the built-in person platform. It consumes only
native events after startup; reading a State or its mutable last_reported field
does not create or renew evidence. Existing explicitly selected source profiles
retain precedence over this adapter.
"""
from dataclasses import dataclass
from datetime import datetime
import math
from .comfort_sources import CONTEXT_MAX_AGE_MS

MAX_AGE_MS=CONTEXT_MAX_AGE_MS


def is_native_person(reference):
    return (reference is not None and reference.entity_id.startswith('person.')
            and reference.platform=='person' and type(reference.unique_id) is str
            and 1<=len(reference.unique_id)<=256)


@dataclass(frozen=True,slots=True)
class PersonProof:
    state: object
    source_state: object
    source_identity: tuple
    captured_at: float
    age_ms: int
    away: bool


@dataclass(frozen=True,slots=True)
class SourceOrigin:
    identity: tuple
    reported: datetime
    captured_at: float
    age_ms: int
    retired: bool=False


class NativePersonReports:
    def __init__(self,runtime):
        self.runtime=runtime
        self.proofs={}
        self.watermarks={}
        self.source_origins={}

    def _source(self,state):
        from homeassistant.helpers import entity_registry as er
        entity_id=state.attributes.get('source') if state else None
        if type(entity_id) is not str or not entity_id.startswith('device_tracker.') or len(entity_id)>255:
            return None
        row=er.async_get(self.runtime.hass).async_get(entity_id)
        source=self.runtime.hass.states.get(entity_id) if row and row.disabled_by is None else None
        if source is None or source.attributes.get('restored') or source.state in ('unknown','unavailable'):
            return None
        return source,(row.domain,row.platform,row.unique_id)

    def _source_origin(self,room,state,reported=None):
        from homeassistant.util import dt as dt_util
        selected=self._source(state)
        if selected is None:return None
        source,identity=selected;stamp=source.last_reported
        now=self.runtime._measurement_now()
        if now is None:return None
        try:
            if not isinstance(stamp,datetime) or stamp.utcoffset() is None or (reported is not None and stamp>reported):
                return None
            age=math.ceil((dt_util.utcnow()-stamp).total_seconds()*1000)
            if age<0:return None
            old=self.source_origins.get(room.room_id)
            if old is not None:
                if stamp<old.reported or (stamp==old.reported and identity!=old.identity):return None
                if stamp==old.reported:
                    if old.retired or now<old.captured_at:return None
                    # New person output from the SAME cached tracker cannot
                    # reset its original age, including after a wall-clock jump.
                    age=max(age,old.age_ms+math.ceil((now-old.captured_at)*1000))
                    return source,identity,age,now
            self.source_origins[room.room_id]=SourceOrigin(identity,stamp,now,age)
            return source,identity,age,now
        except (TypeError,ValueError,OverflowError):
            return None

    def prime(self,room):
        # Remember cache age without creating evidence. This also prevents a
        # later derived person report from rejuvenating a source seen at start.
        if is_native_person(room.presence):self._source_origin(room,self._current(room))

    def observe(self,room,kind,event):
        from homeassistant.util import dt as dt_util
        runtime=self.runtime
        if not runtime.enabled or not is_native_person(room.presence) or event is None:
            return
        expected={'changed':'state_changed','reported':'state_reported'}.get(kind)
        if expected is None or event.event_type!=expected:
            return
        state=self._current(room)
        if (state is None or event.data.get('entity_id')!=state.entity_id
                or event.data.get('new_state') is not state):
            return
        # For reported events HA mutates State.last_reported in place. The
        # immutable event timestamp is the original report, not a later read.
        reported=event.data.get('last_reported') if kind=='reported' else state.last_updated
        old=self.watermarks.get(room.room_id)
        try:
            if not isinstance(reported,datetime) or reported.utcoffset() is None:
                return
            if old is not None and reported<=old:
                return
            self.proofs.pop(room.room_id,None)
            ages=[(dt_util.utcnow()-time).total_seconds()*1000 for time in (reported,event.time_fired)]
            age=math.ceil(max(ages)) if min(ages)>=0 else MAX_AGE_MS
        except (TypeError,ValueError,OverflowError):
            return
        if not 0<=age<MAX_AGE_MS:
            return
        self.watermarks[room.room_id]=reported
        source=self._source_origin(room,state,reported)
        if source is None or state.attributes.get('restored') or state.state not in ('home','not_home'):
            return
        source_state,identity,source_age,now=source
        age=max(age,source_age)
        if age<MAX_AGE_MS:
            self.proofs[room.room_id]=PersonProof(state,source_state,identity,now,age,state.state=='not_home')

    def _current(self,room):
        from homeassistant.helpers import entity_registry as er
        entity_id=self.runtime.resolved(room.presence)
        row=er.async_get(self.runtime.hass).async_get(entity_id) if entity_id else None
        return self.runtime.hass.states.get(entity_id) if row and row.disabled_by is None else None

    def snapshot(self,room):
        proof=self.proofs.get(room.room_id)
        now=self.runtime._measurement_now()
        if proof is None or now is None or not self.runtime.enabled:
            return None,MAX_AGE_MS
        state=self._current(room)
        source=self._source(state)
        if (state is not proof.state or state.attributes.get('restored')
                or state.state not in ('home','not_home') or (state.state=='not_home')!=proof.away
                or source is None or source[0] is not proof.source_state or source[1]!=proof.source_identity
                or now<proof.captured_at):
            return None,MAX_AGE_MS
        age=proof.age_ms+math.ceil((now-proof.captured_at)*1000)
        return (proof.away,age) if 0<=age<MAX_AGE_MS else (None,MAX_AGE_MS)

    def withdraw(self):
        self.proofs.clear()  # Keep bounded original-report replay watermarks.
        for room_id,old in self.source_origins.items():
            self.source_origins[room_id]=SourceOrigin(old.identity,old.reported,old.captured_at,old.age_ms,True)
