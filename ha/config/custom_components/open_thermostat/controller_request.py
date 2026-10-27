"""Last completed Ecomline trial command; never a boiler measurement or write API."""
from collections import deque
from copy import deepcopy
import re
import time
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN

PROFILE = 'ecomline-classic-separate-pressure-v1'
KEYS = {'schema','profile_id','source','boot_id','observed_at_ms','known','boiler_readback',
        'value_c','emitted_at_ms','sequence'}

def supported(payload):
    row=payload.get('controller_request')
    return payload.get('protocolProfile')=='classic' and isinstance(row,dict) and row.get('profile_id')==PROFILE

def parse(payload):
    row=payload.get('controller_request')
    if not supported(payload) or set(row)!=KEYS or type(row['schema'])is not int or row['schema']!=1:
        raise ValueError('unsupported_command_snapshot')
    if (row['source']!='controller_uart_transmit' or row['boiler_readback']is not False
            or type(row['known'])is not bool or not isinstance(row['boot_id'],str)
            or re.fullmatch('[0-9a-f]{16}',row['boot_id'])is None):
        raise ValueError('invalid_command_source')
    for name,upper in [('observed_at_ms',9007199254740991),('sequence',4294967295)]:
        if type(row[name])is not int or not 0<=row[name]<=upper:raise ValueError('invalid_command_clock')
    if row['known']:
        if (type(row['value_c'])is not int or row['value_c']not in (0,*range(40,51))
                or type(row['emitted_at_ms'])is not int or not 0<=row['emitted_at_ms']<=row['observed_at_ms']
                or row['sequence']==0):raise ValueError('invalid_completed_command')
    elif row['value_c']is not None or row['emitted_at_ms']is not None or row['sequence']!=0:
        raise ValueError('unknown_command_has_value')
    return deepcopy(row)

class ControllerRequestSensor(SensorEntity):
    _attr_should_poll=False
    _attr_has_entity_name=True
    _attr_translation_key='controller_requested_flow_temperature'
    _attr_device_class=SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement='°C'
    # A command is not a measured temperature/statistic.
    _attr_state_class=None
    snapshot_ttl_seconds=90

    def __init__(self,prefix,clock=time.monotonic):
        self._attr_unique_id=f'{prefix}_controller_requested_flow_temperature_v1'
        self._attr_device_info=DeviceInfo(identifiers={(DOMAIN,prefix)})
        self.clock=clock;self.row=None;self.received=None;self.online=False
        self._fence=None;self._last_receipt=None;self._retired_boots=deque(maxlen=8)
        self.reason='not_received';self._last_published=None;self._expiry=None

    @property
    def available(self):
        elapsed=None if self.received is None else self.clock()-self.received
        return bool(self.online and self.row is not None and elapsed is not None
                    and 0<=elapsed<self.snapshot_ttl_seconds)

    @property
    def native_value(self):
        return self.row['value_c'] if self.available and self.row['known'] else None

    @property
    def extra_state_attributes(self):
        row=self.row;age=None
        if row and row['known'] and self.received is not None:
            age=row['observed_at_ms']-row['emitted_at_ms']+max(0,int((self.clock()-self.received)*1000))
        return {'data_role':'last_controller_transmitted_request','scope':'attended_ecomline_trial',
                'boiler_readback':False,'control_qualified':False,'physical_validation':False,
                'source_boot_id':row['boot_id']if row else None,'sequence':row['sequence']if row else None,
                'emitted_at_ms':row['emitted_at_ms']if row else None,'last_command_age_ms':age,
                'age_basis':'firmware_command_age_plus_local_elapsed; transit_unmeasured',
                'availability_reason':self.reason if self.row is None else
                    'offline'if not self.online else 'fresh_status'if self.available else 'status_expired'}

    def _arm_expiry(self):
        if self._expiry is not None:self._expiry.cancel();self._expiry=None
        if getattr(self,'hass',None) is not None and self.received is not None:
            remaining=max(0,self.snapshot_ttl_seconds-(self.clock()-self.received))
            self._expiry=self.hass.loop.call_later(remaining,self.refresh)

    async def async_added_to_hass(self):
        await super().async_added_to_hass();self._arm_expiry()

    async def async_will_remove_from_hass(self):
        if self._expiry is not None:self._expiry.cancel();self._expiry=None
        await super().async_will_remove_from_hass()

    def refresh(self):
        row=self.row
        identity=None if row is None else tuple(row[k] for k in
            ('boot_id','known','sequence','emitted_at_ms','observed_at_ms'))
        state=(self.available,self.native_value,self.reason,identity)
        if self.entity_id is not None and state!=self._last_published:
            self._last_published=state;self.async_write_ha_state()

    def set_online(self,online):
        self.online=online;self.refresh()

    def update_payload(self,payload,online,*,retained=False):
        self.online=online;now=self.clock()
        try:
            if retained:raise ValueError('retained_command_status')
            if self._last_receipt is not None and now<self._last_receipt:raise ValueError('local_clock_reversed')
            row=parse(payload)
            if row['boot_id']in self._retired_boots:raise ValueError('retired_command_boot')
            previous=self._fence
            if previous and row['boot_id']==previous['boot_id']:
                if row['observed_at_ms']==previous['observed_at_ms']:
                    if row==previous:self.refresh();return
                    raise ValueError('changed_duplicate_status')
                if row['observed_at_ms']<previous['observed_at_ms']:raise ValueError('old_command_status')
                if row['known']and previous['known']:
                    if row['sequence']<previous['sequence']:raise ValueError('old_command_sequence')
                    if row['sequence']==previous['sequence']and any(row[k]!=previous[k]for k in ['value_c','emitted_at_ms']):
                        raise ValueError('changed_command_sequence')
            if previous and row['boot_id']!=previous['boot_id']:self._retired_boots.append(previous['boot_id'])
            self._fence=deepcopy(row);self._last_receipt=now
            self.row=row;self.received=now;self.reason='received'
        except (ValueError,TypeError,KeyError)as error:
            self.row=None;self.received=None;self.reason=str(error)
        self._arm_expiry();self.refresh()
