"""Selected devices' cached native HA battery reports. No control evidence or IO."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import math

from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN

MAX_DEVICES=9
MAX_AGE_MS=86400000


def _label(value,fallback):
    return value if type(value) is str and 0<len(value)<=160 and all(ord(c)>=32 and ord(c)!=127 for c in value) else fallback[:160]


def _unknown(status):
    return {'status':status,'value':None,'entity_id':None,'reported_at':None,'age_ms':None}


def _report(hass,candidates,disabled,kind,now):
    if len(candidates)>1:return _unknown('ambiguous')
    if not candidates:return _unknown('disabled' if disabled else 'missing')
    row=candidates[0];result=_unknown('unavailable');result['entity_id']=row.entity_id
    state=hass.states.get(row.entity_id)
    if state is None or state.state in ('unknown','unavailable'):return result
    restored=state.attributes.get('restored')
    if restored is not None and restored is not False:
        result['status']='restored';return result
    try:
        stamp=state.last_reported
        if not isinstance(stamp,datetime) or stamp.utcoffset() is None or now.utcoffset() is None:raise ValueError
        seconds=(now-stamp).total_seconds()
        if seconds<0:raise ValueError
        age=math.ceil(seconds*1000)
        if not 0<=age<=2**53-1:raise ValueError
        result['reported_at']=stamp.astimezone(timezone.utc).isoformat(timespec='seconds')
        result['age_ms']=age
    except (TypeError,ValueError,OverflowError,AttributeError):
        result['status']='clock_unknown';return result
    if kind=='battery':
        try:
            value=Decimal(state.state)
            if state.attributes.get('unit_of_measurement')!='%' or not value.is_finite() or not 0<=value<=100:raise ValueError
            number=0.0 if value.is_zero() else float(value)
            if value!=0 and number==0:raise ValueError
            result['value']=number
        except (InvalidOperation,ValueError,TypeError,OverflowError):
            result['status']='invalid';return result
    else:
        if state.state not in ('on','off'):
            result['status']='invalid';return result
        result['value']=state.state=='on'
    result['status']='stale' if age>=MAX_AGE_MS else 'reported'
    return result


def read_selected_power(hass,references):
    """One registry pass; at most nine devices, two source kinds per device.

    HA report age is diagnostic cache age, not original hardware acquisition.
    Stable selected identities and native device/config-entry ownership constrain
    discovery. Never infer a battery from a friendly name or reused entity ID.
    """
    result={'schema':1,'scope':'native_ha_cached_state_only','physical_control_qualified':False,
            'devices':[],'unresolved_sources':[]}
    if not 1<=len(references)<=MAX_DEVICES:return result
    registry=er.async_get(hass);devices=dr.async_get(hass);selected={}
    for ref in references:
        entity_id=(registry.async_get_entity_id(ref.entity_id.split('.')[0],ref.platform,ref.unique_id)
                   if ref.platform and ref.unique_id else None)
        row=registry.async_get(entity_id) if entity_id else None
        device=devices.async_get(row.device_id) if row and row.device_id else None
        if (row is None or row.platform==DOMAIN or row.disabled_by is not None
                or device is None or device.disabled_by is not None):
            result['unresolved_sources'].append(ref.entity_id);continue
        if device.id not in selected:
            selected[device.id]={'label':_label(device.name_by_user or device.name,row.entity_id),
                'selected_entities':[],'origins':set(),'battery':[],'battery_low':[],
                'disabled_battery':False,'disabled_battery_low':False}
        item=selected[device.id]
        if row.entity_id not in item['selected_entities']:item['selected_entities'].append(row.entity_id)
        item['origins'].add((row.platform,row.config_entry_id))
    for row in registry.entities.values():
        item=selected.get(row.device_id)
        if item is None or (row.platform,row.config_entry_id) not in item['origins']:continue
        domain=row.entity_id.split('.')[0]
        if domain not in ('sensor','binary_sensor'):continue
        state=hass.states.get(row.entity_id)
        device_class=(state.attributes.get('device_class') if state else None) or row.device_class or row.original_device_class
        if device_class!='battery':continue
        kind='battery' if domain=='sensor' else 'battery_low'
        if row.disabled_by is not None:item['disabled_'+kind]=True
        elif len(item[kind])<2:item[kind].append(row) # Two already prove ambiguity.
    now=dt_util.utcnow()
    for item in selected.values():
        result['devices'].append({'label':item['label'],'selected_entities':item['selected_entities'],
            **{kind:_report(hass,item[kind],item['disabled_'+kind],kind,now) for kind in ('battery','battery_low')}})
    return result
