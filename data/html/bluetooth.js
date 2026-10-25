'use strict';
window.BluetoothPage = (() => {
  const reveal=async()=>{try{const session=await OpenThermostatAuth.ready();document.querySelectorAll('[data-bluetooth-settings]').forEach(node=>{node.hidden=session.legacy;});}catch{}};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',reveal,{once:true});else reveal();
  let active;
  const t = s => uiText(s), el = (tag, text) => {const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
  const states={waiting:'Waiting for a Bluetooth report',key_required:'Bindkey required',received:'Bluetooth report received',stale:'Bluetooth readings expired',malformed:'Unsupported or invalid Bluetooth report',authentication_failed:'Bluetooth key verification failed',encryption_required:'Encrypted Bluetooth report required',crypto_unavailable:'Bluetooth decryption unavailable',pending_restart:'Restart required to apply Bluetooth settings',configuration_invalid:'Stored Bluetooth settings are invalid',clock_invalid:'Bluetooth clock check failed; restart required'};
  const errors={bluetooth_storage_full:'Not enough device storage for this change. The saved Bluetooth settings were not changed.',invalid_device_address:"Enter a Bluetooth address with six hexadecimal pairs.",duplicate_device_address:"Each Bluetooth address can be added only once.",invalid_device_key:"Enter exactly 32 hexadecimal characters for the bindkey.",invalid_device_name:"Use a single-line name of at most 40 UTF-8 bytes.",invalid_device_encryption:"Select the encryption offered for this device profile.",unsupported_device_profile:"This Bluetooth device profile is not supported.",invalid_device_count:"You can add at most 8 Bluetooth devices.",invalid_device_key_action:"Select whether to keep, replace or clear the bindkey.",invalid_bluetooth_settings:"Bluetooth settings were rejected. Check the device fields.",bluetooth_resources_unavailable:"Bluetooth is temporarily unavailable. Wait for the device, then try again.",bluetooth_settings_unavailable:'Bluetooth settings could not be read. Existing data was kept.',device_settings_changed:'Settings changed elsewhere. Your draft is kept. Reload saved settings before saving again.',device_settings_too_large:'Bluetooth settings are too large. Remove a device or shorten names.',bluetooth_save_unconfirmed:'Saving was not confirmed. Reception is paused. Read back the settings before retrying.',bluetooth_scan_not_started:'Search did not start. A scan may already be running, disabled, cooling down or unavailable.',stored_bluetooth_config_invalid:'Stored Bluetooth settings are invalid. Existing settings were kept.'};
  const profiles={shelly_ht_display:'Shelly BLU H&T Display',xiaomi_monitor_3:'Xiaomi Monitor 3 (MJWSD05MMC)',shelly_blu_trv:'Shelly BLU TRV (SBTR-001AEU)'};
  const allowedEncryption=(profile,value)=>profile==='xiaomi_monitor_3'?value==='mibeacon_v4_v5':['shelly_ht_display','shelly_blu_trv'].includes(profile)&&['none','bthome_v2'].includes(value);
  const hexAddress=s=>typeof s==='string'&&/^[0-9a-f]{12}$/.test(s);
  function valid(s) {
    if(s?.schema!==1||typeof s.pending_restart!=='boolean'||typeof s.scan_pending!=='boolean'||typeof s.discovery_full!=='boolean'||typeof s.config_error!=='string'||!Number.isSafeInteger(s.queue_drops)||s.queue_drops<0||!Array.isArray(s.devices)||s.devices.length>8||!Array.isArray(s.nearby)||s.nearby.length>32||!s.nearby.every(hexAddress))return false;
    const seen=new Set();
    for(const d of s.devices) {
      if(!hexAddress(d?.address)||seen.has(d.address)||!Object.hasOwn(profiles,d.profile)||!allowedEncryption(d.profile,d.encryption)||typeof d.name!=='string'||new TextEncoder().encode(d.name).length>40||typeof d.key_stored!=='boolean'||typeof d.message_integrity!=='boolean'||d.control_qualified!==false||d.measurement_qualified!==false||!Object.hasOwn(states,d.status))return false;
      seen.add(d.address);
      if(!Number.isSafeInteger(d.old_counter_drops)||d.old_counter_drops<0||d.old_counter_drops>4294967295||![d.battery_low,d.light].every(v=>v===null||typeof v==='boolean'))return false;
      if(d.status!=='received'&&[d.temperature,d.humidity,d.battery,d.battery_low,d.light,d.light_level,d.button,d.target_temperature,d.external_temperature,d.state_revision].some(v=>v!==null))return false;
      for(const [key,min,max] of [['temperature',-4000,8500],['humidity',0,10000],['battery',0,100],['temperature_age_ms',0,4294967295],['humidity_age_ms',0,4294967295],['battery_age_ms',0,4294967295],['last_accepted_age_ms',0,4294967295],['counter',0,4294967295],['rssi',-127,20],['declared_device_type',0,65535],['firmware_32',0,4294967295],['firmware_24',0,16777215],['light_level',0,2],['button',0,d.profile==='shelly_blu_trv'?255:1],['target_temperature',-4000,8500],['external_temperature',-4000,8500],['state_revision',0,255],['target_temperature_age_ms',0,4294967295],['external_temperature_age_ms',0,4294967295],['state_revision_age_ms',0,4294967295]])if(d[key]!==null&&(!Number.isSafeInteger(d[key])||d[key]<min||d[key]>max))return false;
    }
    return true;
  }
  function unmount(){active?.abort();active=null;}
  function mount(root) {
    unmount();const owner=new AbortController();active=owner;
    const get=id=>root.querySelector('#'+id), status=get('ble-status'), rows=get('ble-rows');
    let etag=null, storedInvalid=false, dirty=false, saving=false, loading=false, polling=false, timer=null, savedRows=new Map();
    const alive=()=>!owner.signal.aborted&&root.isConnected;
    owner.signal.addEventListener('abort',()=>{clearTimeout(timer);for(const input of rows.querySelectorAll('input[type=password]'))input.value='';},{once:true});
    const say=text=>{if(alive())status.textContent=t(text);};
    const enable=()=>{get('ble-add').disabled=!etag||storedInvalid||saving||loading||rows.children.length>=8;get('ble-save').disabled=!etag||storedInvalid||saving||loading;get('ble-reset').disabled=!etag||saving||loading;get('ble-reload').disabled=saving||loading;};
    const draft=()=>{dirty=true;enable();};
    function field(label,node,parent) {const wrap=el('label');wrap.className='d-block mb-2';wrap.append(el('span',t(label)),node);parent.append(wrap);node.className='form-control';return node;}
    function option(select,value,label){const o=el('option',t(label));o.value=value;select.append(o);}
    function addRow(device={address:'',name:'',profile:'shelly_ht_display',encryption:'bthome_v2',key_stored:false}) {
      if(rows.children.length>=8)return;
      const box=el('fieldset');box.className='border rounded p-3 mb-2';const legend=el('legend',t('Bluetooth device'));box.append(legend);
      const profile=field('Device profile',el('select'),box);profile.dataset.bleField='profile';for(const [value,label] of Object.entries(profiles))option(profile,value,label);profile.value=device.profile;
      const address=field('BLE address',el('input'),box);address.value=device.address.match(/.{1,2}/g)?.join(':')??'';address.maxLength=17;address.required=true;address.autocomplete='off';
      const name=field('Name',el('input'),box);name.value=device.name;name.maxLength=40;
      const encryption=field('Bluetooth encryption',el('select'),box);encryption.dataset.bleField='encryption';
      const fillEncryption=value=>{encryption.replaceChildren();if(profile.value==='xiaomi_monitor_3')option(encryption,'mibeacon_v4_v5','MiBeacon v4/v5 encrypted');else{option(encryption,'bthome_v2','BTHome v2 encrypted');option(encryption,'none','Unencrypted');}if(allowedEncryption(profile.value,value))encryption.value=value;legend.textContent=t(profiles[profile.value]);};fillEncryption(device.encryption);
      const action=field('Bindkey action',el('select'),box);action.dataset.bleField='key_action';option(action,'keep',device.key_stored?'Keep stored key':'No stored key');option(action,'set','Replace key');option(action,'clear','Clear key');
      const key=field('Bindkey (32 hexadecimal characters)',el('input'),box);key.type='password';key.maxLength=32;key.autocomplete='new-password';key.spellcheck=false;key.hidden=true;
      const readings=el('p',t('Waiting for a Bluetooth report'));readings.className='small';readings.dataset.readings='';box.append(readings);
      const details=el('details'), extra=el('p');details.append(el('summary',t('Bluetooth reception details')),extra);extra.dataset.extra='';extra.className='small';box.append(details);box.dataset.savedAddress=device.address;
      const remove=el('button',t('Remove'));remove.type='button';remove.className='btn btn-outline-danger';box.append(remove);
      remove.addEventListener('click',()=>{key.value='';box.remove();draft();},{signal:owner.signal});
      const normalizedAddress=()=>address.value.replaceAll(':','').toLowerCase();
      box.isSavedBinding=()=>Boolean(device.address)&&normalizedAddress()===device.address&&profile.value===device.profile&&encryption.value===device.encryption&&(encryption.value==='none'||action.value==='keep');
      const adjust=()=>{
        action.disabled=encryption.value==='none';if(action.disabled)action.value='clear';
        key.hidden=action.value!=='set'||encryption.value==='none';key.closest('label').hidden=key.hidden;key.required=!key.hidden;if(key.hidden)key.value='';
        const same=normalizedAddress()===device.address&&profile.value===device.profile&&encryption.value===device.encryption;
        action.querySelector('option[value="keep"]').textContent=t(same&&device.key_stored?'Keep stored key':'No stored key');
      };
      for(const input of [address,name,profile,encryption,action,key])input.addEventListener('input',()=>{
        if(input===profile){fillEncryption();action.value='keep';key.value='';}
        if(input===encryption){action.value='keep';key.value='';}
        adjust();draft();
        if(!box.isSavedBinding()){readings.textContent=t('Save and restart to receive data for this device.');extra.textContent='—';}
      },{signal:owner.signal});adjust();
      box.readDraft=()=>{const value={address:address.value,profile:profile.value,encryption:encryption.value,name:name.value,key_action:action.value};if(action.value==='set')value.bindkey=key.value;return value;};
      rows.append(box);enable();return box;
    }
    function render(s) {
      savedRows=new Map(s.devices.map(d=>[d.address,d]));
      for(const box of rows.children) {
        const d=savedRows.get(box.dataset.savedAddress), node=box.querySelector('[data-readings]');
        node.textContent=!box.isSavedBinding()?t('Save and restart to receive data for this device.'):d?t(states[d.status])+' · '+t(d.profile==='shelly_blu_trv'?'Calculated TRV temperature':'Temperature')+': '+(d.temperature===null?'—':(d.temperature/100).toLocaleString(OpenThermostatLanguage.locale)+' °C')+(d.profile==='shelly_blu_trv'?'':' · '+t('Humidity')+': '+(d.humidity===null?'—':d.humidity/100+'%'))+' · '+t('Battery')+': '+(d.battery===null?'—':d.battery+'%')+' · '+t('Temperature report age')+': '+(d.temperature_age_ms===null?'—':Math.floor(d.temperature_age_ms/1000)+' s'):'—';
      }
      for(const box of rows.children) {
        const d=savedRows.get(box.dataset.savedAddress), extra=box.querySelector('[data-extra]');
        if(!d||!box.isSavedBinding()){extra.textContent='—';continue;}
        const show=value=>value===null||value===undefined?'—':typeof value==='boolean'?t(value?'Yes':'No'):String(value);
        const labels=[['Message integrity (last accepted report)','message_integrity'],['Signal strength (dBm)','rssi'],['Battery low','battery_low'],['Light detected','light'],['Light level (0–2)','light_level'],[d.profile==='shelly_blu_trv'?'Button event (raw)':'Button event (0–1)','button'],['Declared device type','declared_device_type'],['Firmware declaration (32-bit raw)','firmware_32'],['Firmware declaration (24-bit raw)','firmware_24'],['Last accepted counter','counter'],['Old-counter drops','old_counter_drops']];
        if(d.profile==='shelly_blu_trv')labels.push(['Reported target (°C)','target_temperature'],['External sensor temperature (°C)','external_temperature'],['Reported state revision (diagnostic)','state_revision'],['Target report age (ms)','target_temperature_age_ms'],['External report age (ms)','external_temperature_age_ms'],['State revision age (ms)','state_revision_age_ms']);
        extra.textContent=labels.map(([label,key])=>t(label)+': '+show(['target_temperature','external_temperature'].includes(key)&&d[key]!==null?d[key]/100:d[key])).join(' · ');
      }
      const nearby=get('ble-nearby');
      const value=s.nearby.map(a=>a.match(/../g).join(':')).join(', ')+(s.discovery_full?' · '+t('Discovery list full'):'');
      if(nearby.textContent!==value)nearby.textContent=value;
      get('ble-scan').disabled=s.scan_pending||saving;
      if(s.config_error!=='none')say('Stored Bluetooth settings are invalid. Existing settings were kept.');
      else if(s.pending_restart)say('Restart required to apply Bluetooth settings');
    }
    async function request(path, options={}) {
      const abort=new AbortController(), cancel=()=>abort.abort();owner.signal.addEventListener('abort',cancel,{once:true});const timeout=setTimeout(cancel,10000);
      try {
        const response=await fetch(path,{cache:'no-store',credentials:'same-origin',...options,signal:abort.signal});
        if(!response.ok) {let code='';try{code=(await response.json()).error;}catch{}throw new Error(t(errors[code]??'Bluetooth request failed. Check the device before retrying.'));}
        const data=await response.json();return {data,etag:response.headers.get('ETag')};
      } finally {clearTimeout(timeout);owner.signal.removeEventListener('abort',cancel);}
    }
    async function load() {
      if(loading)return;loading=true;etag=null;for(const box of rows.children)box.disabled=true;enable();
      try {
        const response=await request('/config/bluetooth'), s=response.data, tag=response.etag;
        if(!alive())return;if(!valid(s)||!tag||!/^"[0-9a-f]{64}"$/.test(tag))throw new Error(t('Invalid Bluetooth status received.'));
        for(const input of rows.querySelectorAll('input[type=password]'))input.value='';rows.replaceChildren();
        etag=tag;storedInvalid=s.config_error!=='none';get('ble-reset').hidden=!storedInvalid;for(const d of s.devices)addRow(d);dirty=false;say('Bluetooth settings loaded.');render(s);enable();
      } catch(error){say(error.message);}
      finally {loading=false;for(const box of rows.children)box.disabled=saving;enable();}
    }
    async function poll() {
      if(!alive()||polling)return;polling=true;
      try {const response=await request('/bluetooth/status'),s=response.data;if(!valid(s))throw new Error(t('Invalid Bluetooth status received.'));if(alive())render(s);}
      catch(error){if(alive()){for(const node of rows.querySelectorAll('[data-readings],[data-extra]'))node.textContent=t('Bluetooth readings unavailable.');say(error.message);}}
      finally {polling=false;if(alive())timer=setTimeout(poll,5000);}
    }
    get('ble-add').addEventListener('click',()=>{addRow();draft();},{signal:owner.signal});
    get('ble-reload').addEventListener('click',()=>{if(!saving&&(!dirty||confirm(t('Discard your unsaved Bluetooth changes?'))))load();},{signal:owner.signal});
    get('ble-scan').addEventListener('click',async()=>{
      get('ble-scan').disabled=true;
      try {const headers=await OpenThermostatAuth.headers();await request('/config/bluetooth/scan',{method:'POST',headers});say('Bluetooth search started.');}
      catch(error){say(error.message);}finally{if(alive())get('ble-scan').disabled=false;}
    },{signal:owner.signal});
    get('ble-reset').addEventListener('click',async()=>{
      if(!etag||saving||!storedInvalid||!confirm(t('Clear only the invalid Bluetooth device list? Other settings will be kept.')))return;
      saving=true;enable();
      try{const headers={...await OpenThermostatAuth.headers(),'Content-Type':'application/json','If-Match':etag};await request('/config/bluetooth',{method:'POST',headers,body:JSON.stringify({devices:[],reset_invalid:true})});if(alive())await load();}
      catch(error){say(error.message);}finally{saving=false;enable();}
    },{signal:owner.signal});
    get('ble-form').addEventListener('submit',async event=>{
      event.preventDefault();if(!etag||storedInvalid||saving)return;
      const devices=Array.from(rows.children,box=>box.readDraft());
      if(devices.some(d=>new TextEncoder().encode(d.name).length>40||d.key_action==='set'&&!/^[0-9a-fA-F]{32}$/.test(d.bindkey))) {say('Use names of at most 40 UTF-8 bytes and keys of exactly 32 hexadecimal characters.');return;}
      saving=true;for(const box of rows.children)box.disabled=true;enable();
      try {const headers={...await OpenThermostatAuth.headers(),'Content-Type':'application/json','If-Match':etag};await request('/config/bluetooth',{method:'POST',headers,body:JSON.stringify({devices})});if(alive()){await load();say('Bluetooth settings saved. Restart the device in Settings to apply changes.');}}
      catch(error){say(error.message);}
      finally {for(const input of rows.querySelectorAll('input[type=password]'))input.value='';for(const box of rows.children)box.disabled=false;saving=false;enable();}
    },{signal:owner.signal});
    load().then(()=>{if(alive())timer=setTimeout(poll,5000);});
  }
  return {mount,unmount};
})();
