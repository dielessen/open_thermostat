'use strict';
window.BluetoothPage = (() => {
  let active;
  const t = s => uiText(s), el = (tag, text) => {const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
  const states={waiting:'Waiting for a Bluetooth report',key_required:'Bindkey required',received:'Bluetooth report received',stale:'Bluetooth readings expired',malformed:'Unsupported or invalid Bluetooth report',authentication_failed:'Bluetooth key verification failed',encryption_required:'Encrypted Bluetooth report required',crypto_unavailable:'Bluetooth decryption unavailable',pending_restart:'Restart required to apply Bluetooth settings',configuration_invalid:'Stored Bluetooth settings are invalid',clock_invalid:'Bluetooth clock not valid yet; reception resumes by itself'};
  const errors={bluetooth_storage_full:'Not enough device storage for this change. The saved Bluetooth settings were not changed.',invalid_device_address:"Enter a Bluetooth address with six hexadecimal pairs.",duplicate_device_address:"Each Bluetooth address can be added only once.",invalid_device_key:"Enter exactly 32 hexadecimal characters for the bindkey.",invalid_device_name:"Use a single-line name of at most 40 UTF-8 bytes.",invalid_device_encryption:"Select the encryption offered for this device profile.",unsupported_device_profile:"This Bluetooth device profile is not supported.",invalid_device_count:"You can add at most 8 Bluetooth devices.",invalid_device_key_action:"Select whether to keep, replace or clear the bindkey.",invalid_bluetooth_settings:"Bluetooth settings were rejected. Check the device fields.",bluetooth_resources_unavailable:"Bluetooth is temporarily unavailable. Wait for the device, then try again.",bluetooth_settings_unavailable:'Bluetooth settings could not be read. Existing data was kept.',device_settings_changed:'Settings changed elsewhere. Your draft is kept. Reload saved settings before saving again.',device_settings_too_large:'Bluetooth settings are too large. Remove a device or shorten names.',bluetooth_save_unconfirmed:'Saving was not confirmed. Reception is paused. Read back the settings before retrying.',bluetooth_scan_not_started:'Search did not start. A scan may already be running, disabled, cooling down or unavailable.',stored_bluetooth_config_invalid:'Stored Bluetooth settings are invalid. Existing settings were kept.'};
  const profiles={shelly_ht_display:'Shelly BLU H&T Display',xiaomi_monitor_3:'Xiaomi Monitor 3 (MJWSD05MMC)',shelly_blu_trv:'Shelly BLU TRV (SBTR-001AEU)',pvvx_thermometer:'Thermometer with pvvx firmware (BTHome)'};
  const allowedEncryption=(profile,value)=>profile==='xiaomi_monitor_3'?value==='mibeacon_v4_v5':['shelly_ht_display','shelly_blu_trv','pvvx_thermometer'].includes(profile)&&['none','bthome_v2'].includes(value);
  const hexAddress=s=>typeof s==='string'&&/^[0-9a-f]{12}$/.test(s);
  // A guess from the broadcast name only; the owner confirms it before saving.
  const guess=name=>/^(ATC_|BTE_|BTH|pvvx)/i.test(name)?['pvvx_thermometer','none']:/^(SBHT|SBBT|Shelly)/i.test(name)?['shelly_ht_display','bthome_v2']:/^(LYWSD|MJWSD|MiBeacon)/i.test(name)?['xiaomi_monitor_3','mibeacon_v4_v5']:null;
  const age=ms=>{const s=Math.floor(ms/1000);return s<120?s+' s':s<7200?Math.round(s/60)+' min':Math.round(s/3600)+' h';};
  function valid(s) {
    const capacity=s?.discovery_capacity??32;
    if(s?.schema!==1||!Number.isInteger(capacity)||capacity<1||capacity>128||typeof s.pending_restart!=='boolean'||typeof s.scan_pending!=='boolean'||typeof s.discovery_full!=='boolean'||typeof s.config_error!=='string'||!Number.isSafeInteger(s.queue_drops)||s.queue_drops<0||!Array.isArray(s.devices)||s.devices.length>8||!Array.isArray(s.nearby)||s.nearby.length>capacity||!s.nearby.every(hexAddress)||new Set(s.nearby).size!==s.nearby.length)return false;
    if(s.nearby_devices!==undefined&&(!Array.isArray(s.nearby_devices)||s.nearby_devices.length!==s.nearby.length||!s.nearby_devices.every((d,i)=>d?.address===s.nearby[i]&&typeof d.name==='string'&&new TextEncoder().encode(d.name).length<=40&&!/[\x00-\x1f\x7f]/.test(d.name)&&Number.isInteger(d.rssi)&&d.rssi>=-127&&d.rssi<=20)))return false;
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
    let writeUnconfirmed=false, pollWarning=false, etag=null, storedInvalid=false, dirty=false, saving=false, loading=false, pollRequest=null, timer=null, savedRows=new Map(), nearbyHints=[], nearbyCards=new Map();
    const alive=()=>!owner.signal.aborted&&root.isConnected;
    const visible=()=>document.visibilityState!=='hidden';
    function stopPoll(){clearTimeout(timer);timer=null;const pending=pollRequest;pollRequest=null;if(pending)pending.abort();}
    function schedulePoll(){clearTimeout(timer);timer=null;if(alive()&&visible()&&!pollRequest)timer=setTimeout(poll,5000);}
    owner.signal.addEventListener('abort',()=>{stopPoll();for(const input of rows.querySelectorAll('input[type=password]'))input.value='';},{once:true});
    document.addEventListener('visibilitychange',()=>{if(!visible())stopPoll();else if(alive())poll();},{signal:owner.signal});
    const unconfirmedMessage='Saving could not be confirmed. Your draft is kept. Reload saved settings before retrying.';
    const say=(text,fromPoll=false)=>{if(alive()){status.textContent=t(text);pollWarning=fromPoll;}};
    const saveFailed=error=>{if(!error.httpStatus||(error.httpStatus>=500&&error.httpStatus!==507)){writeUnconfirmed=true;etag=null;say(unconfirmedMessage);}else say(error.message);};
    const enable=()=>{if(!alive())return;get('ble-add').disabled=!etag||storedInvalid||saving||loading||rows.children.length>=8;get('ble-save').disabled=!etag||storedInvalid||saving||loading;get('ble-reset').disabled=!etag||saving||loading;get('ble-reload').disabled=saving||loading;renderNearby();};
    const draft=()=>{dirty=true;enable();};
    function field(label,node,parent,hint) {if(hint)node.dataset.hint=hint;const wrap=el('label');wrap.className='d-block mb-2';wrap.append(el('span',t(label)),node);parent.append(wrap);node.className='form-control';return node;}
    function option(select,value,label){const o=el('option',t(label));o.value=value;select.append(o);}
    function addRow(device={address:'',name:'',profile:'shelly_ht_display',encryption:'bthome_v2',key_stored:false}) {
      if(rows.children.length>=8)return;
      const box=el('fieldset'),legend=el('legend',t('Bluetooth device')),sub=el('p'),grid=el('div');sub.className='ble-sub';grid.className='ble-fields';box.append(legend,sub);
      const readings=el('p',t('Waiting for a Bluetooth report'));readings.className='ble-read';readings.dataset.readings='';box.append(readings,grid);
      const profile=field('Device profile',el('select'),grid,'The sensor type, so the E32 can read its messages.');profile.dataset.bleField='profile';profile.parentElement.classList.add('ble-wide');for(const [value,label] of Object.entries(profiles))option(profile,value,label);profile.value=device.profile;
      const address=field('Bluetooth address',el('input'),grid,'Six pairs, for example 0a:1b:2c:3d:4e:5f. Choose a device above to fill it in.');address.dataset.bleField='address';address.value=device.address.match(/.{1,2}/g)?.join(':')??'';address.maxLength=17;address.required=true;address.autocomplete='off';
      const name=field('Name',el('input'),grid,'Your own name, for example Living room thermometer.');name.dataset.bleField='name';name.value=device.name;name.maxLength=40;
      const encryption=field('Encryption',el('select'),grid,'Encrypted BTHome needs the key; unencrypted readings need none. Xiaomi always uses MiBeacon.');encryption.dataset.bleField='encryption';
      const fillEncryption=value=>{encryption.replaceChildren();if(profile.value==='xiaomi_monitor_3')option(encryption,'mibeacon_v4_v5','MiBeacon v4/v5 encrypted');else{option(encryption,'bthome_v2','BTHome v2 encrypted');option(encryption,'none','Unencrypted');}if(allowedEncryption(profile.value,value))encryption.value=value;title();};const title=()=>{legend.textContent=name.value.trim()||t(profiles[profile.value]);sub.textContent=t(profiles[profile.value]);};fillEncryption(device.encryption);
      const action=field('Encryption key (bindkey)',el('select'),grid,'Keep the stored key, enter a new one or remove it.');action.dataset.bleField='key_action';option(action,'keep',device.key_stored?'Keep stored key':'No stored key');option(action,'set','Replace key');option(action,'clear','Clear key');if(!device.key_stored)action.value='set';
      const key=field('New key (32 hexadecimal characters)',el('input'),grid,"The 32-character bindkey from the sensor's app or settings.");key.type='password';key.maxLength=32;key.autocomplete='new-password';key.spellcheck=false;key.hidden=true;
      const details=el('details'), extra=el('p');details.append(el('summary',t('Bluetooth reception details')),extra);extra.dataset.extra='';extra.className='small';box.append(details);box.dataset.savedAddress=device.address;
      const remove=el('button',t('Remove'));remove.type='button';remove.className='btn btn-outline-danger';box.append(remove);
      remove.addEventListener('click',()=>{key.value='';box.remove();draft();},{signal:owner.signal});
      const normalizedAddress=()=>address.value.replaceAll(':','').toLowerCase();
      const resetKeyAction=()=>{action.value=device.key_stored&&!device.draftOnly&&normalizedAddress()===device.address&&profile.value===device.profile&&encryption.value===device.encryption?'keep':'set';key.value='';};
      box.isSavedBinding=()=>!device.draftOnly&&Boolean(device.address)&&normalizedAddress()===device.address&&profile.value===device.profile&&encryption.value===device.encryption&&(encryption.value==='none'||action.value==='keep');
      const adjust=()=>{
        action.disabled=encryption.value==='none';if(action.disabled)action.value='clear';action.closest('label').hidden=action.disabled;
        key.hidden=action.value!=='set'||encryption.value==='none';key.closest('label').hidden=key.hidden;key.required=!key.hidden;if(key.hidden)key.value='';
        const same=normalizedAddress()===device.address&&profile.value===device.profile&&encryption.value===device.encryption;
        action.querySelector('option[value="keep"]').textContent=t(same&&device.key_stored?'Keep stored key':'No stored key');
      };
      for(const input of [address,name,profile,encryption,action,key])input.addEventListener('input',()=>{
        if(input===profile){fillEncryption();resetKeyAction();}
        if(input===encryption){resetKeyAction();}
        if(input===name)title();
        adjust();draft();
        if(!box.isSavedBinding()){readings.textContent=t('Save and restart to receive data for this device.');extra.textContent='—';}
      },{signal:owner.signal});adjust();
      box.readDraft=()=>{const value={address:address.value,profile:profile.value,encryption:encryption.value,name:name.value,key_action:action.value};if(action.value==='set')value.bindkey=key.value;return value;};
      rows.append(box);enable();return box;
    }
    function renderNearby() {
      const list=get('ble-nearby'),currentAddresses=new Set(nearbyHints.map(d=>d.address));
      for(const [address,card] of nearbyCards)if(!currentAddresses.has(address)){card.node.remove();nearbyCards.delete(address);}
      for(const d of nearbyHints) {
        let card=nearbyCards.get(d.address);
        if(!card) {
          const node=el('div');
          const title=el('strong'),info=el('div'),button=el('button');
          info.className='small';button.type='button';button.className='btn btn-outline-primary btn-block mt-2';button.dataset.bleAddress=d.address;
          node.append(title,info,button);list.append(node);card={node,title,info,button};nearbyCards.set(d.address,card);
          button.addEventListener('click',()=>{
            if(button.disabled)return;
            const current=nearbyHints.find(h=>h.address===d.address);
            const guessed=guess(current?.name??''),[profile,encryption]=guessed??['shelly_ht_display','bthome_v2'];
            const box=addRow({address:d.address,draftOnly:true,name:current?.name??'',profile,encryption,key_stored:false});
            if(!box)return;draft();say(guessed?'Profile guessed from the device name — check it, enter a bindkey if needed, then save.':'Address and name filled in. Check the device profile, enter a bindkey if needed, then save.');
            box.querySelector('[data-ble-field=profile]').focus();box.scrollIntoView({block:'nearest',behavior:'smooth'});
          },{signal:owner.signal});
        }
        card.title.textContent=d.name||t('Unnamed Bluetooth device');
        card.info.textContent=d.address.match(/../g).join(':')+(d.rssi===null?'':' · '+d.rssi+' dBm');
        const added=Array.from(rows.children).some(box=>box.readDraft().address.replaceAll(':','').toLowerCase()===d.address);
        card.button.textContent=t(added?'Already added':'Add');
        card.button.disabled=added||!etag||storedInvalid||saving||loading||rows.children.length>=8;
      }
      if(!nearbyHints.length&&!list.querySelector('[data-empty]')){const empty=el('p',t('No devices found yet. Start a search and wake the sensor if needed.'));empty.dataset.empty='';list.append(empty);}
      if(nearbyHints.length)list.querySelector('[data-empty]')?.remove();
    }
    function render(s) {
      savedRows=new Map(s.devices.map(d=>[d.address,d]));
      for(const box of rows.children) {
        const d=savedRows.get(box.dataset.savedAddress), node=box.querySelector('[data-readings]');
        const n=(v,digits)=>v.toLocaleString(OpenThermostatLanguage.locale,{minimumFractionDigits:digits,maximumFractionDigits:digits});
        if(!box.isSavedBinding()||!d){node.textContent=!box.isSavedBinding()?t('Save and restart to receive data for this device.'):'—';continue;}
        const chip=el('span',t(d.status==='pending_restart'&&s.restart_scheduled===true?'Restarts by itself shortly':states[d.status]));chip.className='ot-chip'+(d.status==='received'?' ot-chip--ok':['waiting','stale','pending_restart'].includes(d.status)?'':' ot-chip--err');
        const big=el('span',d.temperature===null?'—':n(d.temperature/100,1)+' °C');big.className='ot-big';big.title=t(d.profile==='shelly_blu_trv'?'Calculated TRV temperature':'Temperature');
        const lab=el('span',t(d.profile==='shelly_blu_trv'?'Calculated TRV temperature':'Temperature'));lab.className='pd-help';
        const rest=el('span',(d.profile==='shelly_blu_trv'?'':t('Humidity')+': '+(d.humidity===null?'—':n(d.humidity/100,1)+' %'))+(d.profile==='shelly_blu_trv'?'':' · ')+t('Battery')+': '+(d.battery===null?'—':d.battery+' %')+' · '+t('Last update')+': '+(d.temperature_age_ms===null?'—':t('{age} ago').replace('{age}',age(d.temperature_age_ms))));rest.className='pd-help';
        // Why a sensor stays waiting: nothing heard, or heard in another format.
        const why=d.status==='waiting'&&Number.isInteger(d.frames_received)?el('span',t(d.frames_received===0
          ?'Nothing received from this address yet: check distance, battery and the address.'
          :d.frames_ignored===d.frames_received?'Reports arrive but are not in the expected format for this sensor type. Choose another device profile.':'Waiting for a complete report.')):null;
        if(why){why.className='ot-hint';why.dataset.waitingReason='';}
        node.replaceChildren(lab,big,chip,rest,...(why?[why]:[]));
      }
      for(const box of rows.children) {
        const d=savedRows.get(box.dataset.savedAddress), extra=box.querySelector('[data-extra]');
        if(!d||!box.isSavedBinding()){extra.textContent='—';continue;}
        const show=value=>value===null||value===undefined?'—':typeof value==='boolean'?t(value?'Yes':'No'):String(value);
        const labels=[['Message integrity (last accepted report)','message_integrity'],['Signal strength (dBm)','rssi'],['Battery low','battery_low'],['Light detected','light'],['Light level (0–2)','light_level'],[d.profile==='shelly_blu_trv'?'Button event (raw)':'Button event (0–1)','button'],['Declared device type','declared_device_type'],['Firmware declaration (32-bit raw)','firmware_32'],['Firmware declaration (24-bit raw)','firmware_24'],['Last accepted counter','counter'],['Old-counter drops','old_counter_drops']];
        if(d.profile==='shelly_blu_trv')labels.push(['Reported target (°C)','target_temperature'],['External sensor temperature (°C)','external_temperature'],['Reported state revision (diagnostic)','state_revision'],['Target report age (ms)','target_temperature_age_ms'],['External report age (ms)','external_temperature_age_ms'],['State revision age (ms)','state_revision_age_ms']);
        labels.push(['Reports received','frames_received'],['Reports not recognised','frames_ignored'],['Reports rejected','frames_rejected'],['Counter restarts by the sensor','counter_resets']);
        extra.textContent=labels.map(([label,key])=>t(label)+': '+show(['target_temperature','external_temperature'].includes(key)&&d[key]!==null?d[key]/100:d[key])).join(' · ')
          +(typeof d.last_rejection==='string'&&Object.hasOwn(states,d.last_rejection)?' · '+t('Last rejected report')+': '+t(states[d.last_rejection]):'');
      }
      nearbyHints=s.nearby_devices??s.nearby.map(address=>({address,name:'',rssi:null}));
      const count=t('Found:')+' '+nearbyHints.length;
      if(get('ble-found-count').textContent!==count)get('ble-found-count').textContent=count;
      renderNearby();
      get('ble-discovery-full').hidden=!s.discovery_full;
      get('ble-scan').disabled=s.scan_pending||saving;
      if(writeUnconfirmed)say(unconfirmedMessage);
      else if(s.config_error!=='none')say('Stored Bluetooth settings are invalid. Existing settings were kept.');
      else if(s.restart_scheduled===true)say('The E32 restarts by itself shortly to apply the Bluetooth settings.');
      else if(s.pending_restart)say('Restart required to apply Bluetooth settings');
      get('ble-restart').hidden=!(s.pending_restart&&s.restart_scheduled!==true&&window.OpenThermostatRestart);
    }
    async function request(path, options={}) {
      if(!alive())throw new DOMException('Aborted','AbortError');
      // Reads belong to the page; an already submitted write keeps its own
      // deadline through navigation. Neither kind is automatically replayed.
      const mutation=!['GET','HEAD'].includes((options.method||'GET').toUpperCase());
      const abort=new AbortController(), cancel=()=>abort.abort();
      if(!mutation)owner.signal.addEventListener('abort',cancel,{once:true});
      options.signal?.addEventListener('abort',cancel,{once:true});
      if(options.signal?.aborted)cancel();
      const timeout=setTimeout(()=>abort.abort(new DOMException('Deadline','TimeoutError')),10000);
      try {
        const response=await fetch(path,{cache:'no-store',credentials:'same-origin',...options,signal:abort.signal});
        if(!response.ok) {let code='';try{code=(await response.json()).error;}catch{}const error=new Error(t(errors[code]??'Bluetooth request failed. Check the device before retrying.'));error.httpStatus=response.status;throw error;}
        const data=await response.json();if(abort.signal.aborted)throw abort.signal.reason;return {data,etag:response.headers.get('ETag')};
      } catch(error){if(abort.signal.reason?.name==='TimeoutError')throw new Error(t('Bluetooth request failed. Check the device before retrying.'));throw error;}
      finally {clearTimeout(timeout);if(!mutation)owner.signal.removeEventListener('abort',cancel);options.signal?.removeEventListener('abort',cancel);}
    }
    async function load(expected=null) {
      if(loading)return;stopPoll();loading=true;etag=null;for(const box of rows.children)box.disabled=true;enable();
      try {
        const response=await request('/config/bluetooth'), s=response.data, tag=response.etag;
        if(!alive())return;if(!valid(s)||!tag||!/^"[0-9a-f]{64}"$/.test(tag))throw new Error(t('Invalid Bluetooth status received.'));
        if(expected!==null&&(s.config_error!=='none'||s.devices.length!==expected.length||expected.some(wanted=>!s.devices.some(d=>['address','profile','encryption','name','key_stored'].every(key=>d[key]===wanted[key])))))throw new Error(t(unconfirmedMessage));
        for(const input of rows.querySelectorAll('input[type=password]'))input.value='';rows.replaceChildren();
        writeUnconfirmed=false;etag=tag;storedInvalid=s.config_error!=='none';get('ble-reset').hidden=!storedInvalid;for(const d of s.devices)addRow(d);dirty=false;say('Bluetooth settings loaded.');render(s);enable();return true;
      } catch(error){if(expected!==null){writeUnconfirmed=true;say(unconfirmedMessage);}else say(error.message);return false;}
      finally {loading=false;for(const box of rows.children)box.disabled=saving;enable();schedulePoll();}
    }
    async function poll() {
      if(!alive()||!visible()||pollRequest)return;
      if(loading||saving){schedulePoll();return;}
      clearTimeout(timer);timer=null;const current=new AbortController();pollRequest=current;
      const owns=()=>alive()&&visible()&&pollRequest===current;
      try {const response=await request('/bluetooth/status',{signal:current.signal}),s=response.data;if(!valid(s))throw new Error(t('Invalid Bluetooth status received.'));if(owns()){if(pollWarning)say('Bluetooth status updated.');render(s);}}
      catch(error){if(owns()){for(const node of rows.querySelectorAll('[data-readings],[data-extra]'))node.textContent=t('Bluetooth readings unavailable.');if(writeUnconfirmed)say(unconfirmedMessage);else say(error.message,true);}}
      finally {if(pollRequest===current){pollRequest=null;schedulePoll();}}
    }
    get('ble-add').addEventListener('click',()=>{addRow();draft();},{signal:owner.signal});
    get('ble-restart').addEventListener('click',()=>window.OpenThermostatRestart(get('ble-restart'),status),{signal:owner.signal});
    get('ble-reload').addEventListener('click',()=>{if(!saving&&(!dirty||confirm(t('Discard your unsaved Bluetooth changes?'))))load();},{signal:owner.signal});
    get('ble-scan').addEventListener('click',async()=>{
      get('ble-scan').disabled=true;
      try {const headers=await OpenThermostatAuth.headers();await request('/config/bluetooth/scan',{method:'POST',headers});say('Bluetooth search started.');}
      catch(error){say(error.message);}finally{if(alive())get('ble-scan').disabled=false;}
    },{signal:owner.signal});
    get('ble-reset').addEventListener('click',async()=>{
      if(!etag||saving||!storedInvalid||!confirm(t('Clear only the invalid Bluetooth device list? Other settings will be kept.')))return;
      saving=true;stopPoll();enable();
      try{const headers={...await OpenThermostatAuth.headers(),'Content-Type':'application/json','If-Match':etag};await request('/config/bluetooth',{method:'POST',headers,body:JSON.stringify({devices:[],reset_invalid:true})});if(alive())await load([]);}
      catch(error){saveFailed(error);}finally{saving=false;enable();schedulePoll();}
    },{signal:owner.signal});
    get('ble-form').addEventListener('submit',async event=>{
      event.preventDefault();if(!etag||storedInvalid||saving)return;
      const devices=Array.from(rows.children,box=>box.readDraft());
      const expected=devices.map(d=>{
        const address=d.address.replaceAll(':','').toLowerCase(),prior=savedRows.get(address);
        return {address,name:d.name,profile:d.profile,encryption:d.encryption,key_stored:d.key_action==='set'||d.key_action==='keep'&&Boolean(prior?.key_stored&&prior.profile===d.profile&&prior.encryption===d.encryption)};
      });
      if(devices.some(d=>new TextEncoder().encode(d.name).length>40||d.key_action==='set'&&!/^[0-9a-fA-F]{32}$/.test(d.bindkey))) {say('Use names of at most 40 UTF-8 bytes and keys of exactly 32 hexadecimal characters.');return;}
      saving=true;stopPoll();for(const box of rows.children)box.disabled=true;enable();
      try {const headers={...await OpenThermostatAuth.headers(),'Content-Type':'application/json','If-Match':etag};const saved=await request('/config/bluetooth',{method:'POST',headers,body:JSON.stringify({devices})});
        // Newer firmware applies the change with its own restart; older firmware needs a manual one.
        const seconds=saved.data?.restart_scheduled===true&&Number.isSafeInteger(saved.data.restart_in_s)?saved.data.restart_in_s:null;
        if(alive()&&await load(expected))say(seconds!==null?t('The E32 restarts by itself in {s} s to apply the change.').replace('{s}',seconds):'Bluetooth settings saved. Restart the device (System → Restart device) to apply changes.');}
      catch(error){saveFailed(error);}
      finally {for(const input of rows.querySelectorAll('input[type=password]'))input.value='';for(const box of rows.children)box.disabled=false;saving=false;enable();schedulePoll();}
    },{signal:owner.signal});
    load();
  }
  return {mount,unmount};
})();
