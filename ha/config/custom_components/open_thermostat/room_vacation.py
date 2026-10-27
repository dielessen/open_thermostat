"""Read-only vacation date resolution and expected room scope, no command IO."""
from datetime import datetime,timezone
import re
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError

import probatio as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN,CONF_TOPIC_PREFIX
from .product import configuration_snapshot
from .v1_wire import digest


def local_end_candidates(value,zone_name,now):
    if type(value) is not str or len(value) not in (16,19) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?',value):
        raise ValueError('vacation_date_invalid')
    try:
        local=datetime.fromisoformat(value);zone=ZoneInfo(zone_name)
        if not isinstance(now,datetime) or now.utcoffset() is None:raise ValueError
        if not 1970<=local.year<2100:raise ValueError
        current=int(now.timestamp())
    except ZoneInfoNotFoundError:
        raise ValueError('vacation_timezone_unavailable') from None
    except (TypeError,ValueError,OverflowError):
        raise ValueError('vacation_date_invalid') from None
    valid={}
    for fold in (0,1):
        aware=local.replace(tzinfo=zone,fold=fold);utc=aware.astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None)!=local:continue
        stamp=int(utc.timestamp())
        valid[stamp]={'iso':aware.isoformat(timespec='seconds'),'until_utc':stamp,
                      'utc_offset':aware.strftime('%z')}
    if not valid:raise ValueError('vacation_nonexistent_time')
    candidates=[row for stamp,row in sorted(valid.items()) if current<stamp<=current+366*86400 and stamp<4102444800]
    if not candidates:raise ValueError('vacation_date_range')
    return candidates


def room_command_scope(hass,entry_id,room_id,token,time_zone):
    from .week_planner import _target
    entry,_,room=_target(hass,entry_id,room_id)
    if type(token) is not str or re.fullmatch(r'[a-f0-9]{64}',token) is None or digest(configuration_snapshot(entry))!=token:
        raise ValueError('setup_changed')
    if time_zone!=hass.config.time_zone:raise ValueError('vacation_timezone_changed')
    state=hass.data.get(DOMAIN,{}).get(entry_id,{})
    runtime=state.get('v1_runtime')
    if (runtime is None or runtime.entry is not entry or not runtime.enabled or not runtime.transport_ready
            or runtime.rooms.get(room_id)!=room or room.comfort is None
            or not runtime.room_control_supported(room_id)
            or not getattr(runtime._transport,'comfort_supported',False)):
        raise ValueError('comfort_controller_unavailable')
    journal=getattr(runtime._transport,'journal',None)
    if isinstance(journal,dict) and journal.get('staged') is not None:
        raise ValueError('controller_plan_pending')
    registry=er.async_get(hass)
    entity_id=registry.async_get_entity_id('climate',DOMAIN,f"{entry.data.get(CONF_TOPIC_PREFIX,'')}_room_{room_id}_climate")
    row=registry.async_get(entity_id) if entity_id else None
    climate=hass.states.get(entity_id) if row and row.disabled_by is None else None
    if (climate is None or climate.state in ('unknown','unavailable')
            or climate.attributes.get('entry_id')!=entry_id or climate.attributes.get('room_id')!=room_id):
        raise ValueError('comfort_controller_unavailable')
    return entry,room,runtime,entity_id


def preview_vacation(hass,entry_id,room_id,token,local_end,time_zone):
    _,_,_,entity_id=room_command_scope(hass,entry_id,room_id,token,time_zone)
    candidates=local_end_candidates(local_end,time_zone,dt_util.utcnow())
    return {'entry_id':entry_id,'room_id':room_id,'entity_id':entity_id,'token':token,
            'time_zone':time_zone,'local_end':local_end,'candidates':candidates}


@websocket_api.websocket_command({vol.Required('type'):'open_thermostat/room/vacation_preview',
    vol.Required('entry_id'):str,vol.Required('room_id'):str,vol.Required('token'):vol.Match(r'^[a-f0-9]{64}$'),
    vol.Required('local_end'):str,vol.Required('time_zone'):str})
@websocket_api.require_admin
@callback
def ws_vacation_preview(hass,connection,msg):
    try:
        result=preview_vacation(hass,msg['entry_id'],msg['room_id'],msg['token'],msg['local_end'],msg['time_zone'])
    except (KeyError,ValueError) as err:
        connection.send_error(msg['id'],str(err) if isinstance(err,ValueError) else 'room_changed','Vacation date could not be checked')
    else:connection.send_result(msg['id'],result)
