'use strict';
window.EMSDevicesPage=(()=>{
  // Reference data is a separate native gzip asset. A missing reference never
  // hides the actual local readings or invents a product identification.
  const emptyReference={aliases:{},entities:[],groups:{},devices:[],telegrams:{},
    library:{},libraryFields:[],telegramMetadata:{},boilerNames:{}};
  let reference=window.OT_EMS_METADATA||emptyReference;
  const settingFields={
    heatingactivated:['heating_enabled','Heating enabled','bool',0,1,0],
    heatingtemp:['configured_heating_temperature','Maximum heating temperature','degC',0,90,1],
    burnminperiod:['minimum_burner_period','Minimum burner period','min',0,120,6],
    pumpdelay:['pump_run_on','Pump run-on','min',0,60,8]
  };
  function validSettings(s){
    return s?.schema===1&&typeof s.boot_id==='string'&&/^[a-f0-9]{16}$/.test(s.boot_id)
      &&number(s.revision)&&typeof s.available==='boolean'&&typeof s.active==='boolean'
      &&typeof s.write_attempted==='boolean'&&s.physical_validation===false
      &&typeof s.reason==='string'&&/^[a-z_]{1,64}$/.test(s.reason)
      &&Array.isArray(s.settings)&&s.settings.length===4&&new Set(s.settings.map(d=>d?.entity)).size===4
      &&s.settings.every(d=>{const expected=settingFields[d?.entity];return Object.hasOwn(settingFields,d?.entity)&&expected&&d.unit===expected[2]
        &&d.minimum===expected[3]&&d.maximum===expected[4]&&d.offset===expected[5]&&d.telegram_type===22;});
  }
  function validOperation(s){
    if(!validSettings(s)||typeof s.transport_fault!=='boolean'||typeof s.owned_by_requester!=='boolean'
      ||!['idle','queued_write','waiting_write_status','queued_read','waiting_response','completed','failed'].includes(s.phase))return false;
    if(s.available&&(s.active||s.transport_fault))return false;
    if(s.active!==['queued_write','waiting_write_status','queued_read','waiting_response'].includes(s.phase))return false;
    if(s.phase==='completed'&&s.reason!=='setting_read_back')return false;
    if(s.revision===0)return s.phase==='idle'&&s.request===null&&s.response_at_ms===null;
    if(s.phase==='idle'||s.phase==='completed'&&!s.write_attempted)return false;
    const r=s.request,spec=settingFields[r?.entity];
    return Object.hasOwn(settingFields,r?.entity)&&Number.isInteger(r.value)&&r.value>=spec[3]&&r.value<=spec[4]
      &&(s.phase==='completed'?number(s.response_at_ms):s.response_at_ms===null);
  }
  let active=null,refreshActiveActions=null;
  const text=s=>uiText(s), hex=n=>'0x'+n.toString(16).toUpperCase().padStart(2,'0');
  const number=n=>Number.isSafeInteger(n)&&n>=0;
  const nullable=n=>n===null||number(n);
  const states={valid:'Received',stale:'Expired',invalid:'Invalid',unknown:'Not received'};
  const quality={reported:'Reported',unreliable:'Unreliable',inferred:'Inferred'};
  const units={degC:'°C',uA:'µA',bool:'',bits:'',text:'',code:''};
  const roles={8:'Boiler',16:'Thermostat',23:'Thermostat'};
  const brands={1:'Bosch',2:'Junkers',3:'Buderus',4:'Nefit',5:'Sieger',11:'Worcester',13:'IVT'};
  function deviceReference(d) {
    if(d.product_id===null)return null;
    const candidates=reference.devices.filter(v=>v.product_id===d.product_id);
    const expected=d.address===8?'boiler':[16,23].includes(d.address)?'thermostat':null;
    const matched=expected?candidates.filter(v=>v.type===expected):candidates;
    // Product IDs are reused between device categories; ambiguous IDs are not identified.
    return matched.length===1?matched[0]:null;
  }
  function deviceTitle(d) {
    const known=deviceReference(d),role=text(roles[d.address]||'EMS device');
    const brand=brands[d.brand_id]||'';
    const boilerNames=known?.type==='boiler'&&brand?reference.boilerNames[d.product_id]?.[brand]:null;
    return (boilerNames?.length?boilerNames.join(' / '):known?((brand?brand+' ':'')+known.name):role)+' '+hex(d.address);
  }
  function valid(s){
    const i=s?.inventory,f=s?.boiler?.fields;
    if(typeof s?.enabled!=='boolean'||i?.schema!==1||i.capacity!==16||!number(i.untracked_frames)||!Array.isArray(i.devices)||i.devices.length>16||!f||typeof f!=='object'||Array.isArray(f)||Object.keys(f).length>100)return false;
    const addresses=new Set();
    for(const d of i.devices){
      if(!d||typeof d!=='object'||!number(d.address)||d.address<1||d.address>127||addresses.has(d.address)||!number(d.frames)||d.frames<1||!nullable(d.age_ms)||!nullable(d.product_id)||d.product_id>254||!nullable(d.brand_id)||d.brand_id>254||!number(d.untracked_types)||!(d.version===null||typeof d.version==='string'&&/^\d{1,3}\.\d{1,3}$/.test(d.version))||!Array.isArray(d.telegram_types)||d.telegram_types.length>64||new Set(d.telegram_types).size!==d.telegram_types.length||!d.telegram_types.every(t=>number(t)&&t<=65535))return false;
      addresses.add(d.address);
    }
    for(const [id,r] of Object.entries(f)){
      if(!/^[a-z][a-z0-9_]{0,79}$/.test(id)||!r||!Object.hasOwn(states,r.state)||!Object.hasOwn(quality,r.quality)||r.source_address!==8||!number(r.source_type)||r.source_type>65535||!nullable(r.age_ms)||typeof r.unit!=='string'||r.unit.length>16||!(r.value===null||typeof r.value==='number'&&Number.isFinite(r.value)||typeof r.value==='string'&&r.value.length<=32)||r.state!=='valid'&&r.value!==null)return false;
      if((r.state==='valid'&&r.value===null)||(r.value!==null&&(
          r.unit==='bool'?r.value!==0&&r.value!==1:
          r.unit==='text'?typeof r.value!=='string':typeof r.value!=='number')))return false;
    }
    return true;
  }
  const label=id=>text(id.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase()));
  const age=ms=>ms===null?text('Unknown'):(ms/1000).toLocaleString(OpenThermostatLanguage.locale,{maximumFractionDigits:1})+' s';
  const update=(node,value)=>{if(node.textContent!==value)node.textContent=value;};
  const el=(tag,value,className)=>{const e=document.createElement(tag);if(value!==undefined)e.textContent=value;if(className)e.className=className;return e;};
  function unmount(){if(active){active.abort();active=null;}refreshActiveActions=null;}
  function mount(root,actions={}){
    unmount();const owner=new AbortController();active=owner;
    reference=window.OT_EMS_METADATA||emptyReference;
    let snapshot=null,settingsSnapshot=null,settingsPolicy=null,ownAddress=null,measurementFresh=false,busy=false;
    let editor=null,metadataAt=-Infinity,expiryTimer=0,editGeneration=0,interrupted=false;
    let writeBusy=false,pendingSetting=null,mutation=null,operationNote='',confirmUntil=0,confirmTimer=null;
    const get=id=>root.querySelector('#'+id),list=get('ems-device-list'),status=get('ems-devices-status');
    const alive=()=>!owner.signal.aborted&&root.isConnected;
    const removal=new MutationObserver(()=>{if(!root.isConnected)owner.abort();});
    removal.observe(document.body,{childList:true,subtree:true});
    owner.signal.addEventListener('abort',()=>{removal.disconnect();if(active===owner){active=null;refreshActiveActions=null;}},{once:true});
    const records=new Map(),labels=new Map(),identifyButtons=new Map();
    refreshActiveActions=()=>{
      if(!alive())return;
      for(const r of records.values())if(r.identify)r.identify.disabled=!actions.canIdentify?.();
      for(const button of identifyButtons.values())button.disabled=!actions.canIdentify?.();
    };
    const format=new Intl.NumberFormat(OpenThermostatLanguage.locale,{maximumFractionDigits:2,useGrouping:false});
    const description=id=>{if(!labels.has(id))labels.set(id,label(id));return labels.get(id);};
    const visible=()=>document.visibilityState==='visible';
    const fresh=()=>performance.now()>=metadataAt&&performance.now()-metadataAt<30000;
    const nativeFields=Object.fromEntries(Object.entries(settingFields).map(([entity,spec])=>[spec[0],entity]));
    function nativeSupport(entity){
      if(entity==='selflowtemp')return text('Manual Classic trial only');
      if(!Object.hasOwn(settingFields,entity))return text('Not implemented on E32');
      if(settingsPolicy?.transmit_compiled===false)return text('Read only in this firmware');
      if(!settingsSnapshot)return text('Classic setting; availability unknown');
      return text(validOperation(settingsSnapshot)&&settingsSnapshot.available&&fresh()&&measurementFresh
        ?'Classic editor available':'Classic setting; changes blocked');
    }
    function fieldAccess(id,d){
      const known=d&&deviceReference(d),group=known&&reference.groups[known.type+':'+d.product_id];
      const alias=reference.aliases[id],spec=group?.fields.map(i=>reference.entities[i]).find(v=>v[0]===alias);
      if(spec?.[4]&&!Object.hasOwn(nativeFields,id)&&id!=='reported_selected_flow_temperature')
        return {kind:'write',label:text('Configurable in EMS-ESP')+' · '+text('Read only on E32')};
      if(Object.hasOwn(nativeFields,id))return {kind:'write',label:text('Configurable settings')};
      if(id==='reported_selected_flow_temperature')return {kind:'command',label:text('Manual Classic trial only')};
      return {kind:'read',label:text('Read only on E32')};
    }
    function badge(access,label){const node=el('span',label,'ems-access');node.dataset.access=access;return node;}
    function clearConfirmations(){confirmUntil=0;clearTimeout(confirmTimer);if(editor){editor.exclusive.checked=false;editor.stop.checked=false;}}
    const confirmed=()=>performance.now()<confirmUntil&&editor?.exclusive.checked&&editor?.stop.checked;
    function resetDraft(){if(editor){editor.entity.value='';editor.value.value='';editor.boolean.value='';}clearConfirmations();}
    function readyToPrepare(){return alive()&&visible()&&!interrupted&&!busy&&fresh()&&validOperation(settingsSnapshot)
      &&settingsPolicy?.transmit_compiled!==false
      &&measurementFresh&&settingsSnapshot.available&&!settingsSnapshot.active&&!settingsSnapshot.transport_fault&&!pendingSetting;}
    function draft(){
      if(!editor||!Object.hasOwn(settingFields,editor.entity.value))return null;
      const spec=settingFields[editor.entity.value],raw=spec[2]==='bool'?editor.boolean.value:editor.value.value;
      const value=Number(raw);
      return raw.trim()!==''&&Number.isInteger(value)&&value>=spec[3]&&value<=spec[4]?{entity:editor.entity.value,value}:null;
    }
    function ensureEditor(){
      if(editor)return;
      const box=get('ems-settings-editor'),entity=el('select'),value=el('input'),boolean=el('select'),exclusive=el('input'),stop=el('input'),submit=el('button',text('Send one settings change'),'btn btn-primary');
      entity.id='ems-setting-entity';value.id='ems-setting-value';boolean.id='ems-setting-bool';submit.id='ems-setting-submit';
      const addOption=(select,key,name)=>{const option=el('option',text(name));option.value=key;select.append(option);};
      addOption(entity,'','Choose a setting');for(const [id,spec] of Object.entries(settingFields))addOption(entity,id,spec[1]);
      addOption(boolean,'','Choose a value');addOption(boolean,'0','Off');addOption(boolean,'1','On');
      value.type='number';value.step='1';value.className=boolean.className=entity.className='form-control';
      exclusive.type=stop.type='checkbox';exclusive.id='ems-setting-exclusive';stop.id='ems-setting-stop';submit.type='button';
      const field=(name,input)=>{const label=el('label');if(input.type==='checkbox')label.append(input,document.createTextNode(text(name)));else label.append(document.createTextNode(text(name)),input);return label;};
      const numberLabel=field('New value',value),booleanLabel=field('New value',boolean);
      box.append(field('Setting to change',entity),numberLabel,booleanLabel,
        field('I confirm that the other controller is disconnected from control.',exclusive),
        field('I am present and can stop the boiler independently.',stop),submit);
      editor={entity,value,boolean,exclusive,stop,submit,numberLabel,booleanLabel};
      entity.addEventListener('change',()=>{value.value='';boolean.value='';clearConfirmations();if(!pendingSetting)operationNote='';renderEditor();},{signal:owner.signal});
      for(const input of [value,boolean,exclusive,stop])input.addEventListener('input',()=>{if(!pendingSetting&&!writeBusy&&(input===value||input===boolean))operationNote='';renderEditor();},{signal:owner.signal});
      for(const input of [exclusive,stop])input.addEventListener('change',()=>{
        if(!confirmUntil){confirmUntil=performance.now()+30000;confirmTimer=setTimeout(()=>{clearConfirmations();if(alive())renderEditor();},30000);}
        renderEditor();
      },{signal:owner.signal});
      submit.addEventListener('click',sendSetting,{signal:owner.signal});
    }
    function renderEditor(){
      const available=validOperation(settingsSnapshot)&&settingsSnapshot.available;
      if(available)ensureEditor();
      get('ems-settings-editor').hidden=!available||!editor?.entity.value;
      get('ems-settings-operation').textContent=operationNote?text(operationNote):available&&!fresh()?text('Refresh to prepare a settings change.'):'';
      if(!editor)return;
      const spec=settingFields[editor.entity.value],boolean=spec?.[2]==='bool',ready=readyToPrepare()&&!writeBusy;
      editor.numberLabel.hidden=!spec||boolean;editor.booleanLabel.hidden=!spec||!boolean;editor.value.hidden=!spec||boolean;editor.boolean.hidden=!spec||!boolean;
      if(spec){editor.value.min=spec[3];editor.value.max=spec[4];}
      for(const input of [editor.entity,editor.value,editor.boolean,editor.exclusive,editor.stop])input.disabled=!ready;
      editor.submit.disabled=!ready||!draft()||!confirmed();
    }
    function reconcileSetting(){
      if(!pendingSetting||!validOperation(settingsSnapshot))return;
      const s=settingsSnapshot,p=pendingSetting;
      if(s.boot_id!==p.boot){pendingSetting=null;resetDraft();operationNote='The boiler restarted. Review the new status before preparing another change.';return;}
      if(s.revision===p.revision&&s.owned_by_requester&&s.request?.entity===p.entity&&s.request.value===p.value){
        if(s.phase==='completed'&&s.reason==='setting_read_back'&&number(s.response_at_ms)){
          pendingSetting=null;resetDraft();operationNote='The requested setting was read back from the boiler.';
        }else if(s.phase==='failed'){
          pendingSetting=null;resetDraft();operationNote='The settings change failed or was not confirmed. Review the status before another attempt.';
        }
      }
    }
    function interruptEditor(){
      ++editGeneration;interrupted=true;clearConfirmations();
      if(mutation){operationNote='The request outcome is uncertain. Refresh to inspect the status; do not repeat the request.';mutation.abort();}
      if(alive())renderEditor();
    }
    document.addEventListener('visibilitychange',()=>{if(!visible())interruptEditor();},{signal:owner.signal});
    window.addEventListener('pagehide',interruptEditor,{signal:owner.signal});
    owner.signal.addEventListener('abort',()=>{clearTimeout(expiryTimer);clearTimeout(confirmTimer);mutation?.abort();},{once:true});
    async function sendSetting(){
      if(writeBusy||!readyToPrepare()||!draft()||!confirmed())return;
      const intent={...draft(),boot:settingsSnapshot.boot_id,revision:settingsSnapshot.revision+1,generation:editGeneration};
      const stillValid=()=>readyToPrepare()&&editGeneration===intent.generation&&settingsSnapshot.boot_id===intent.boot
        &&settingsSnapshot.revision+1===intent.revision&&draft()?.entity===intent.entity&&draft()?.value===intent.value
        &&confirmed();
      writeBusy=true;get('ems-refresh').disabled=true;renderEditor();let timeout=0;
      try{
        if(!window.OpenThermostatAuth)throw Error('session');
        const auth=await OpenThermostatAuth.ready();if(auth.legacy||!stillValid())return;
        const spec=settingFields[intent.entity],target=spec[2]==='bool'?text(intent.value?'On':'Off'):intent.value+' '+(spec[2]==='degC'?'°C':text('min'));
        if(!window.confirm(text('Send one persistent boiler settings change?')+'\n'+text(spec[1])+': '+target)){clearConfirmations();return;}
        if(!stillValid()){clearConfirmations();operationNote='Preparation was interrupted. Refresh and confirm the setup again.';return;}
        pendingSetting=intent;metadataAt=-Infinity;clearConfirmations();
        mutation=new AbortController();timeout=setTimeout(()=>mutation?.abort(),5000);
        operationNote='Sending one settings request.';renderEditor();
        const response=await fetch('/boiler/settings/write',{method:'POST',cache:'no-store',signal:mutation.signal,
          headers:{'Content-Type':'application/json'},body:JSON.stringify({schema:1,boot_id:intent.boot,revision:intent.revision,
            entity:intent.entity,value:intent.value,exclusive_owner_confirmed:true,independent_stop_confirmed:true})});
        if(!alive())return;
        if([400,401,403,409,413].includes(response.status)){
          pendingSetting=null;operationNote='The settings request was rejected. Refresh before preparing another change.';return;
        }
        const raw=await response.text();if(raw.length>8192)throw Error('size');const result=JSON.parse(raw),s=result.settings;
        if(![200,202].includes(response.status)||result.accepted!==true||!validOperation(s)||!s.owned_by_requester
          ||s.boot_id!==intent.boot||s.revision!==intent.revision||s.request?.entity!==intent.entity||s.request.value!==intent.value)throw Error('result');
        operationNote='The request was accepted. Refresh to check the boiler readback.';
      }catch(_){if(alive())operationNote=pendingSetting?'The request outcome is uncertain. Refresh to inspect the status; do not repeat the request.':'Preparation was interrupted. Refresh and confirm the setup again.';}
      finally{clearTimeout(timeout);mutation=null;writeBusy=false;if(alive()){clearConfirmations();get('ems-refresh').disabled=false;renderEditor();}}
    }
    function renderSettings(){
      renderEditor();
      const note=get('ems-settings-status');
      note.textContent=settingsPolicy?.transmit_compiled===false?text('Boiler settings are read-only in this firmware. The separate heating test remains available when its preparation is complete.')
        :!settingsSnapshot?text('Settings control is unavailable.')
        :settingsSnapshot.available?'':text('Changing settings is unavailable. Protocol ranges do not confirm support by your boiler.');
    }
    function fields(d){return d.address===8?Object.entries(snapshot.boiler.fields):[];}
    function render(){
      if(!snapshot||!alive())return;
      const search=get('ems-search').value.trim().toLocaleLowerCase(),access=get('ems-access').value;
      // Raw sender addresses are not identified devices. Keep undecoded,
      // unidentified traffic in diagnostics rather than an empty second card.
      const devices=snapshot.inventory.devices.filter(d=>d.address!==ownAddress&&(d.address===8||d.product_id!==null));
      const unknown=snapshot.inventory.devices.filter(d=>d.address!==ownAddress&&d.address!==8&&d.product_id===null);
      const diagnostic=get('ems-unidentified');
      if(diagnostic){diagnostic.hidden=!unknown.length;diagnostic.querySelector('[data-unidentified-traffic]').textContent=
        unknown.map(d=>hex(d.address)+' · '+text('Observed telegrams')+': '+d.telegram_types.map(t=>hex(t)).join(', ')).join(' / ');
        // One explicit version read per observed device; never a scan of unseen addresses.
        const wanted=new Set(unknown.map(d=>d.address));
        for(const [address,button] of identifyButtons)if(!wanted.has(address)){button.remove();identifyButtons.delete(address);}
        for(const d of unknown){
          if(identifyButtons.has(d.address))continue;
          const button=el('button',text('Read device identity')+' '+hex(d.address),'btn btn-outline-secondary');button.type='button';
          button.dataset.identifyAddress=d.address;
          button.addEventListener('click',()=>{if(alive()&&actions.canIdentify?.())actions.onIdentify?.(d.address);},{signal:owner.signal});
          identifyButtons.set(d.address,button);diagnostic.append(button);
        }
        for(const button of identifyButtons.values())button.disabled=!actions.canIdentify?.();}
      const ids=new Set(devices.map(d=>d.address));
      for(const [id,r] of records)if(!ids.has(id)){r.box.remove();records.delete(id);}
      if(!ids.size){list.replaceChildren(el('p',text(snapshot.enabled?'No EMS device reports received yet.':'EMS reception is disabled.')));return;}
      for(const d of [...devices].sort((a,b)=>a.address-b.address)){
        let r=records.get(d.address);
        if(!r){
          if(!records.size)list.replaceChildren();
          const box=el('details'),summary=el('summary'),title=el('span'),badge=el('span',undefined,'ems-device-status'),body=el('div',undefined,'ems-device-body'),meta=el('p',undefined,'ems-device-meta'),wrap=el('div',undefined,'ems-table-wrap'),table=el('table'),head=el('thead'),tr=el('tr'),rows=el('tbody'),empty=el('p'),telegrams=el('p',undefined,'ems-device-meta');
          for(const name of ['Entity','Value','Access','Status'])tr.append(el('th',text(name)));
          head.append(tr);table.append(head,rows);wrap.append(table);body.append(meta,wrap,empty,telegrams);
          summary.append(title,badge);box.append(summary,body);box.dataset.address=d.address;
          box.open=d.address===8;list.append(box);
          r={box,title,badge,meta,rows,empty,wrap,telegrams};records.set(d.address,r);
          if(d.address===8){
            const identify=el('button',text('Read device identity'),'btn btn-outline-secondary');identify.type='button';
            identify.addEventListener('click',()=>{if(alive()&&actions.canIdentify?.())actions.onIdentify?.(8);},{signal:owner.signal});
            r.identify=identify;meta.after(identify);
          }

        }
        const entries=fields(d),received=entries.filter(([,v])=>v.state!=='unknown').length;
        r.rowCache??=new Map();
        const known=new Set(entries.map(([id])=>id));
        for(const [id,row] of r.rowCache)if(!known.has(id)){row.remove();r.rowCache.delete(id);}
        for(const id of labels.keys())if(!Object.hasOwn(snapshot.boiler.fields,id))labels.delete(id);
        r.device=d;
        if(r.identify){r.identify.hidden=d.product_id!==null;r.identify.disabled=!actions.canIdentify?.();}
        r.title.textContent=deviceTitle(d);
        r.badge.textContent=received+' '+text('received entities')+' · '+(d.age_ms===null?text('Unknown'):d.age_ms>=30000?text('No recent report'):text('Report received'));
        r.meta.textContent=text('Product ID')+': '+(d.product_id===null?text('Unknown'):d.product_id)+' · '+text('Version')+': '+(d.version??text('Unknown'))+' · '+text('Brand ID')+': '+(d.brand_id===null?text('Unknown'):d.brand_id)+' · '+text('Last report')+': '+age(d.age_ms)+' · '+text('Frames')+': '+d.frames;
        const visible=entries.filter(([id,v])=>v.state!=='unknown'&&(access==='all'||fieldAccess(id,d).kind===access)&&(id+' '+(reference.aliases[id]||'')+' '+description(id)).toLocaleLowerCase().includes(search));
        const wanted=new Set(visible.map(([id])=>id));
        for(const row of [...r.rows.children])if(!wanted.has(row.dataset.field))row.remove();
        let position=r.rows.firstElementChild;
        for(const [id,v] of visible){
          let row=r.rowCache.get(id);
          if(!row){
            row=el('tr');row.dataset.field=id;
            const name=el('td',description(id));name.append(el('code',reference.aliases[id]||id));
            row.append(name,el('td',undefined,'ems-value'),el('td'),el('td'));r.rowCache.set(id,row);
          }
          let value='—';
          if(v.value!==null){value=v.unit==='bool'?text(v.value?'On':'Off'):typeof v.value==='number'?format.format(v.value):v.value;const unit=Object.hasOwn(units,v.unit)?units[v.unit]:v.unit;if(unit)value+=' '+unit;}
          const cells=row.children;
          update(cells[1],measurementFresh?value:'—');
          update(cells[3],text(measurementFresh?states[v.state]:'Snapshot unavailable')+' · '+age(v.age_ms)
            +(v.quality==='reported'?'':' · '+text(quality[v.quality])));
          cells[3].title=(v.source_type?hex(v.source_type):'')+' · '+id;
          const local=fieldAccess(id,d),editable=Object.hasOwn(nativeFields,id)&&readyToPrepare();
          const accessKey=JSON.stringify([local.kind,local.label,editable]);
          if(row.dataset.accessKey!==accessKey){
            row.dataset.accessKey=accessKey;cells[2].replaceChildren(badge(local.kind,local.label));
            if(Object.hasOwn(nativeFields,id)){
              const edit=el('button',text('Edit'),'btn btn-sm btn-outline-primary');edit.type='button';
              edit.disabled=!editable;
              edit.title=editable?text('Edit'):nativeSupport(nativeFields[id]);
              edit.addEventListener('click',()=>{
                if(!readyToPrepare())return;ensureEditor();editor.entity.value=nativeFields[id];
                editor.value.value=editor.boolean.value='';clearConfirmations();renderEditor();
                get('ems-settings-editor').scrollIntoView({block:'nearest'});editor.entity.focus();
              },{signal:owner.signal});cells[2].append(edit);
            }else if(local.kind==='command'){
              const trial=el('a',text('Boiler test'),'btn btn-sm btn-outline-primary');trial.href='#boiler-test-controls';cells[2].append(trial);
            }
          }
          if(row!==position)r.rows.insertBefore(row,position);position=row.nextElementSibling;
        }
        r.wrap.hidden=!visible.length;r.empty.hidden=!!visible.length;
        r.empty.textContent=text(entries.length?'No entities match this filter.':'Reports observed; entity decoding for this device is not available yet.');
        r.telegrams.textContent=text('Observed telegrams')+': '+d.telegram_types.map(t=>hex(t)).join(', ')+(d.untracked_types?' · '+text('Additional telegram types not listed')+': '+d.untracked_types:'');
        r.box.hidden=!!search&&!!entries.length&&!visible.length;
      }
      // Newly observed lower addresses are inserted in order without rebuilding
      // existing details or moving already ordered/focused elements.
      let position=list.firstElementChild;
      for(const d of [...devices].sort((a,b)=>a.address-b.address)){
        const box=records.get(d.address).box;
        if(box!==position)list.insertBefore(box,position);position=box.nextElementSibling;
      }
    }
    function receive(data,error){
      if(!alive())return;
      if(error||!data){
        measurementFresh=false;settingsSnapshot=null;metadataAt=-Infinity;clearConfirmations();
        root.dataset.failed='true';status.textContent=text('Refresh failed. Previously displayed values are an older snapshot.');
        render();renderSettings();return;
      }
      const next={enabled:data.transport.enabled,inventory:data.inventory,boiler:{fields:data.fields}};
      if(!valid(next)){
        measurementFresh=false;metadataAt=-Infinity;clearConfirmations();root.dataset.failed='true';
        status.textContent=text('EMS device snapshot unavailable.');render();renderSettings();return;
      }
      const previousBoot=settingsSnapshot?.boot_id,previousRevision=settingsSnapshot?.revision;
      const identity=data.manual_bus_identity;
      ownAddress=identity?.matches_reviewed_address===true&&identity.source_conflict===false
        &&number(identity.source_address)&&identity.source_address>0&&identity.source_address<128
        ?identity.source_address:null;
      settingsPolicy=data.settings_policy;
      settingsSnapshot=validSettings(data.settings)?data.settings:null;
      if(previousBoot&&settingsSnapshot&&previousBoot!==settingsSnapshot.boot_id)resetDraft();
      else if(previousRevision!==undefined&&settingsSnapshot&&previousRevision!==settingsSnapshot.revision)clearConfirmations();
      metadataAt=settingsSnapshot?performance.now():-Infinity;
      // A snapshot renews measurement metadata, never confirmations/drafts or
      // operation identity. State changes still require the scoped write path.
      snapshot=next;measurementFresh=true;root.dataset.failed='false';
      reconcileSetting();render();renderSettings();
      status.textContent=text('Received devices and values');
    }
    async function refresh(){
      if(busy||writeBusy||!alive())return;
      busy=true;interrupted=false;clearConfirmations();get('ems-refresh').disabled=true;
      try{await BoilerData.refresh();}finally{busy=false;if(alive()){render();renderSettings();get('ems-refresh').disabled=false;}}
    }
    get('ems-search').addEventListener('input',render,{signal:owner.signal});
    get('ems-access').addEventListener('change',render,{signal:owner.signal});
    get('ems-refresh').addEventListener('click',refresh,{signal:owner.signal});
    BoilerData.subscribe(receive,{signal:owner.signal});
  }
  return Object.freeze({mount,unmount,refreshActions:()=>refreshActiveActions?.()});
})();
