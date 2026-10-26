'use strict';
window.EMSDevicesPage=(()=>{
  // Reference data is a separate native gzip asset. A missing reference never
  // hides the actual local readings or invents a product identification.
  const reference=window.OT_EMS_REFERENCE||{entities:[],groups:{},devices:[],telegrams:{},
    library:{},libraryFields:[],telegramMetadata:{},boilerNames:{}};
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
  let active=null;
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
  function unmount(){if(active){active.abort();active=null;}}
  function mount(root){
    unmount();const owner=new AbortController();active=owner;
    let snapshot=null,settingsSnapshot=null,measurementFresh=false,busy=false;
    let editor=null,metadataAt=-Infinity,expiryTimer=0,editGeneration=0,interrupted=false;
    let writeBusy=false,pendingSetting=null,mutation=null,operationNote='';
    const get=id=>root.querySelector('#'+id),list=get('ems-device-list'),status=get('ems-devices-status');
    const alive=()=>!owner.signal.aborted&&root.isConnected;
    const records=new Map(),labels=new Map();
    const format=new Intl.NumberFormat(OpenThermostatLanguage.locale,{maximumFractionDigits:2,useGrouping:false});
    const description=id=>{if(!labels.has(id))labels.set(id,label(id));return labels.get(id);};
    const visible=()=>document.visibilityState==='visible';
    const fresh=()=>performance.now()>=metadataAt&&performance.now()-metadataAt<30000;
    const nativeFields=Object.fromEntries(Object.entries(settingFields).map(([entity,spec])=>[spec[0],entity]));
    function nativeSupport(entity){
      if(entity==='selflowtemp')return text('Manual Classic trial only');
      if(!Object.hasOwn(settingFields,entity))return text('Not implemented on E32');
      if(!settingsSnapshot)return text('Classic setting; availability unknown');
      return text(validOperation(settingsSnapshot)&&settingsSnapshot.available&&fresh()&&measurementFresh
        ?'Classic editor available':'Classic setting; changes blocked');
    }
    function fieldAccess(id){
      if(Object.hasOwn(nativeFields,id))return {kind:'write',label:nativeSupport(nativeFields[id])};
      if(id==='reported_selected_flow_temperature')return {kind:'command',label:text('Manual Classic trial only')};
      return {kind:'read',label:text('Read only on E32')};
    }
    function badge(access,label){const node=el('span',label,'ems-access');node.dataset.access=access;return node;}
    const catalogue=new Map();
    const models=Object.entries(reference.groups).filter(([key])=>key.startsWith('boiler:'))
      .sort((a,b)=>a[1].name.localeCompare(b[1].name));
    const modelSelect=get('ems-catalog-model');
    modelSelect.append(el('option',text('All boiler model references')));modelSelect.firstChild.value='all';
    for(const [key,group] of models){
      const option=el('option',group.name+' · '+key.split(':')[1]);option.value=key;modelSelect.append(option);
      for(const index of group.fields){
        if(!catalogue.has(index))catalogue.set(index,{index,entity:reference.entities[index],models:[]});
        catalogue.get(index).models.push({key,name:group.name});
      }
    }
    const catalogueRows=[...catalogue.values()].sort((a,b)=>a.entity[0].localeCompare(b.entity[0])||a.index-b.index);
    let catalogueLimit=50;
    function renderCatalogue(){
      const query=get('ems-catalog-search').value.trim().toLocaleLowerCase(),access=get('ems-catalog-access').value,model=modelSelect.value;
      const matches=catalogueRows.filter(row=>{
        const spec=row.entity,kind=spec[4]?(spec[2].startsWith('cmd')?'command':'write'):'read';
        return (access==='all'||kind===access)&&(model==='all'||row.models.some(m=>m.key===model))
          &&(spec.slice(0,4).join(' ')+' '+row.models.map(m=>m.name).join(' ')).toLocaleLowerCase().includes(query);
      });
      const body=get('ems-catalog-rows');body.replaceChildren();
      for(const row of matches.slice(0,catalogueLimit)){
        const [id,name,type,unit,writable]=row.entity,kind=writable?(type.startsWith('cmd')?'command':'write'):'read';
        const tr=el('tr');tr.dataset.entity=id;tr.dataset.access=kind;
        const title=el('td',name);title.append(el('code',id));
        const accessCell=el('td');accessCell.append(badge(kind,text(kind==='command'?'Command':kind==='write'?'Configurable in EMS-ESP':'Read only in EMS-ESP')));
        const numeric=type.match(/^(u?int\d+|float) \(>=(-?\d+(?:\.\d+)?)<=(-?\d+(?:\.\d+)?)\)$/);
        const typeLabel=type.startsWith('boolean')?text('Off')+' / '+text('On')
          :numeric?numeric[1]+' · '+numeric[2]+' … '+numeric[3]:type.replaceAll('\\|',' / ');
        const modelCell=el('td'),modelDetails=el('details',undefined,'ems-models');
        modelDetails.append(el('summary',row.models.length+' '+text('model references')),
          el('p',row.models.map(m=>m.name+' ['+m.key.split(':')[1]+']').join(' · ')));
        modelCell.append(modelDetails);
        tr.append(title,accessCell,el('td',typeLabel+(unit?' · '+(unit==='C'?'°C':unit):'')),
          el('td',writable?nativeSupport(id):text('Read only on E32')),modelCell);
        for(const [index,label] of ['EMS-ESP access','Type, options and limits','E32 support','Models'].entries())
          tr.children[index+1].dataset.label=text(label);
        body.append(tr);
      }
      get('ems-catalog-status').textContent=catalogueRows.length
        ?Math.min(catalogueLimit,matches.length)+' / '+matches.length+' '+text('matching entity definitions')+' · '+catalogueRows.length+' '+text('total boiler entity definitions')
        :text('EMS reference unavailable; received readings remain available.');
      get('ems-catalog-more').hidden=catalogueLimit>=matches.length;
    }
    for(const input of [get('ems-catalog-search'),get('ems-catalog-access'),modelSelect])
      input.addEventListener(input.tagName==='INPUT'?'input':'change',()=>{catalogueLimit=50;renderCatalogue();},{signal:owner.signal});
    get('ems-catalog-more').addEventListener('click',()=>{catalogueLimit+=50;renderCatalogue();},{signal:owner.signal});
    renderCatalogue();
    function clearConfirmations(){if(editor){editor.exclusive.checked=false;editor.stop.checked=false;}}
    function resetDraft(){if(editor){editor.entity.value='';editor.value.value='';editor.boolean.value='';}clearConfirmations();}
    function readyToPrepare(){return alive()&&visible()&&!interrupted&&!busy&&fresh()&&validOperation(settingsSnapshot)
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
      submit.addEventListener('click',sendSetting,{signal:owner.signal});
    }
    function renderEditor(){
      const available=validOperation(settingsSnapshot)&&settingsSnapshot.available;
      if(available)ensureEditor();
      get('ems-settings-editor').hidden=!available;
      get('ems-settings-operation').textContent=operationNote?text(operationNote):available&&!fresh()?text('Refresh to prepare a settings change.'):'';
      if(!editor)return;
      const spec=settingFields[editor.entity.value],boolean=spec?.[2]==='bool',ready=readyToPrepare()&&!writeBusy;
      editor.numberLabel.hidden=!spec||boolean;editor.booleanLabel.hidden=!spec||!boolean;editor.value.hidden=!spec||boolean;editor.boolean.hidden=!spec||!boolean;
      if(spec){editor.value.min=spec[3];editor.value.max=spec[4];}
      for(const input of [editor.entity,editor.value,editor.boolean,editor.exclusive,editor.stop])input.disabled=!ready;
      editor.submit.disabled=!ready||!draft()||!editor.exclusive.checked||!editor.stop.checked;
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
    owner.signal.addEventListener('abort',()=>{clearTimeout(expiryTimer);mutation?.abort();},{once:true});
    async function sendSetting(){
      if(writeBusy||!readyToPrepare()||!draft()||!editor.exclusive.checked||!editor.stop.checked)return;
      const intent={...draft(),boot:settingsSnapshot.boot_id,revision:settingsSnapshot.revision+1,generation:editGeneration};
      const stillValid=()=>readyToPrepare()&&editGeneration===intent.generation&&settingsSnapshot.boot_id===intent.boot
        &&settingsSnapshot.revision+1===intent.revision&&draft()?.entity===intent.entity&&draft()?.value===intent.value
        &&editor.exclusive.checked&&editor.stop.checked;
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
      renderCatalogue();
      for(const r of records.values())for(const [id,row] of r.rowCache??[]){
        const access=fieldAccess(id);row.children[6].replaceChildren(badge(access.kind,access.label));
      }
      const message=get('ems-settings-status'),wrap=get('ems-settings-table'),rows=get('ems-settings-rows');
      wrap.hidden=!settingsSnapshot;
      if(!settingsSnapshot){message.textContent=text('Boiler setting definitions are unavailable. Received EMS readings remain below.');return;}
      message.textContent=text(validOperation(settingsSnapshot)&&settingsSnapshot.available?'Each change needs a fresh confirmation. Protocol ranges are not installation advice.':'Changing settings is unavailable. Protocol ranges do not confirm support by your boiler.');
      if(!measurementFresh)message.textContent+=' '+text('No fresh snapshot. Refresh to read reported settings.');
      for(const [id,[field,name,unit,min,max]] of Object.entries(settingFields)){
        let row=rows.querySelector('[data-setting="'+id+'"]');
        if(!row){row=el('tr');row.dataset.setting=id;const title=el('td',text(name));title.append(el('code',id));
          row.append(title,el('td'),el('td'),el('td'),el('td'),el('td'));
          for(const [index,label] of ['Reported value','Status','Age','Protocol range','E32 access'].entries())row.children[index+1].dataset.label=text(label);
          rows.append(row);}
        const sample=measurementFresh&&snapshot?.inventory.devices.some(d=>d.address===8)?snapshot.boiler.fields[field]:null;
        const usable=sample?.state==='valid'&&sample.quality==='reported'&&sample.source_type===22&&sample.unit===unit&&sample.age_ms!==null&&sample.age_ms<600000;
        let value='—';
        if(usable){value=unit==='bool'?text(sample.value?'On':'Off'):format.format(sample.value)+' '+(unit==='degC'?'°C':text('min'));}
        update(row.children[1],value);
        update(row.children[2],text(!measurementFresh?'Snapshot unavailable':!sample?'Not received':sample.quality!=='reported'?quality[sample.quality]:sample.state==='valid'&&!usable?'Unverified reading':states[sample.state]));
        update(row.children[3],sample?age(sample.age_ms):'—');
        update(row.children[4],unit==='bool'?text('Off')+' / '+text('On'):min+' … '+max+' '+(unit==='degC'?'°C':text('min')));
        row.children[5].replaceChildren(badge('write',nativeSupport(id)));
      }
    }
    function fields(d){return d.address===8?Object.entries(snapshot.boiler.fields):[];}
    function renderLibrary(r,d) {
      const key=d.telegram_types.join(',');if(r.libraryKey===key)return;r.libraryKey=key;
      r.libraryBody.replaceChildren(el('p',text('Protocol reference for observed telegram types. Offsets and limits are documentation, not decoded measurements or permission to send commands.')));
      for(const type of d.telegram_types){
        const box=el('details'),heading=el('summary',hex(type)+' '+(reference.telegrams[type]||text('Unknown')));box.append(heading);
        box.addEventListener('toggle',()=>{
          if(!box.open||box.dataset.loaded)return;box.dataset.loaded='true';
          const meta=reference.telegramMetadata[type];
          if(meta)box.append(el('p',meta.description),el('p',[meta.class,meta.emsCategory,meta.distribution].filter(Boolean).join(' · ')));
          const fields=reference.library[type];
          if(!fields){box.append(el('p',text('No byte-offset definition is available in this reference.')));return;}
          for(const index of fields){
            const [offset,name,min,max,resolution,unit,comment]=reference.libraryFields[index];
            const row=el('details'),title=el('summary',text('Offset')+' '+offset+' · '+name);
            row.append(title,el('p',text('Range')+': '+min+' … '+max+' · '+text('Resolution')+': '+resolution+' · '+unit),el('p',comment));box.append(row);
          }
        });r.libraryBody.append(box);
      }
    }
    function renderReference(r,d) {
      const known=deviceReference(d),key=known?known.type+':'+d.product_id:'';
      if(r.referenceKey===key)return;r.referenceKey=key;r.refBody.replaceChildren();
      r.refBody.append(el('p',text('Reference only: listed entities are not confirmed readings or enabled commands. Writable means writable in EMS-ESP; command support in this firmware is separate.')));
      const group=reference.groups[key];
      if(!group){r.refBody.append(el('p',text(window.OT_EMS_REFERENCE?'Exact product identification is required to list reference entities.':'EMS reference unavailable; received readings remain available.')));return;}
      const toolbar=el('div'),search=el('input'),access=el('select'),items=el('div'),count=el('p');
      search.type='search';search.maxLength=80;search.placeholder=text('Search entities');search.setAttribute('aria-label',text('Search entities'));
      for(const [value,name] of [['all','All entities'],['write','Writable'],['read','Read only']]){const option=el('option',text(name));option.value=value;access.append(option);}
      access.setAttribute('aria-label',text('Access'));toolbar.append(search,access);r.refBody.append(toolbar,count,items);
      function filter(){
        const query=search.value.trim().toLocaleLowerCase();items.replaceChildren();
        const rows=group.fields.map(i=>reference.entities[i]).filter(v=>(access.value==='all'||v[4]===(access.value==='write'))&&v.slice(0,4).join(' ').toLocaleLowerCase().includes(query));
        count.textContent=rows.length+' / '+group.fields.length;
        for(const [id,name,type,unit,writable] of rows){
          const row=el('p'),title=el('strong',name+' ('+id+')');row.append(title,el('span',' — '+text(writable?'Writable':'Read only')+' · '+type+(unit?' · '+unit:'')));items.append(row);
        }
      }
      search.addEventListener('input',filter);access.addEventListener('change',filter);filter();
    }
    function render(){
      if(!snapshot||!alive())return;
      const search=get('ems-search').value.trim().toLocaleLowerCase(),showUnknown=get('ems-show-unknown').checked,access=get('ems-access').value;
      const ids=new Set(snapshot.inventory.devices.map(d=>d.address));
      for(const [id,r] of records)if(!ids.has(id)){r.box.remove();records.delete(id);}
      if(!ids.size){list.replaceChildren(el('p',text(snapshot.enabled?'No EMS device reports received yet.':'EMS reception is disabled.')));return;}
      for(const d of [...snapshot.inventory.devices].sort((a,b)=>a.address-b.address)){
        let r=records.get(d.address);
        if(!r){
          if(!records.size)list.replaceChildren();
          const box=el('details'),summary=el('summary'),title=el('span'),badge=el('span',undefined,'ems-device-status'),body=el('div',undefined,'ems-device-body'),meta=el('p',undefined,'ems-device-meta'),wrap=el('div',undefined,'ems-table-wrap'),table=el('table'),head=el('thead'),tr=el('tr'),rows=el('tbody'),empty=el('p'),telegrams=el('p',undefined,'ems-device-meta');
          for(const name of ['Entity','Value','Status','Quality','Telegram','Age','E32 access'])tr.append(el('th',text(name)));head.append(tr);table.append(head,rows);wrap.append(table);body.append(meta,wrap,empty,telegrams);summary.append(title,badge);box.append(summary,body);box.dataset.address=d.address;list.append(box);const ref=el('details'),refTitle=el('summary',text('EMS-ESP entity reference')),refBody=el('div');
          ref.className='ems-reference';ref.append(refTitle,refBody);
          const library=el('details'),libraryTitle=el('summary',text('Telegram library')),libraryBody=el('div');
          library.className='ems-library';library.append(libraryTitle,libraryBody);body.append(ref,library);
          library.addEventListener('toggle',()=>{if(library.open&&r?.device)renderLibrary(r,r.device);});
          ref.addEventListener('toggle',()=>{if(ref.open&&r?.device)renderReference(r,r.device);});
          r={box,title,badge,meta,rows,empty,wrap,telegrams,ref,refBody,library,libraryBody};records.set(d.address,r);
        }
        const entries=fields(d),received=entries.filter(([,v])=>v.state!=='unknown').length;
        r.rowCache??=new Map();
        const known=new Set(entries.map(([id])=>id));
        for(const [id,row] of r.rowCache)if(!known.has(id)){row.remove();r.rowCache.delete(id);}
        for(const id of labels.keys())if(!Object.hasOwn(snapshot.boiler.fields,id))labels.delete(id);
        r.device=d;
        r.title.textContent=deviceTitle(d);
        if(r.ref.open)renderReference(r,d);
        if(r.library.open)renderLibrary(r,d);
        r.badge.textContent=received+' '+text('received entities')+' · '+(d.age_ms===null?text('Unknown'):d.age_ms>=30000?text('No recent report'):text('Report received'));
        r.meta.textContent=text('Product ID')+': '+(d.product_id===null?text('Unknown'):d.product_id)+' · '+text('Version')+': '+(d.version??text('Unknown'))+' · '+text('Brand ID')+': '+(d.brand_id===null?text('Unknown'):d.brand_id)+' · '+text('Last report')+': '+age(d.age_ms)+' · '+text('Frames')+': '+d.frames;
        const visible=entries.filter(([id,v])=>(showUnknown||v.state!=='unknown')&&(access==='all'||fieldAccess(id).kind===access)&&(id+' '+description(id)).toLocaleLowerCase().includes(search));
        const wanted=new Set(visible.map(([id])=>id));
        for(const row of [...r.rows.children])if(!wanted.has(row.dataset.field))row.remove();
        let position=r.rows.firstElementChild;
        for(const [id,v] of visible){
          let row=r.rowCache.get(id);
          if(!row){
            row=el('tr');row.dataset.field=id;
            const name=el('td',description(id));name.append(el('code',id));
            row.append(name,el('td',undefined,'ems-value'),el('td'),el('td'),el('td'),el('td'),el('td'));r.rowCache.set(id,row);
          }
          let value='—';
          if(v.value!==null){value=v.unit==='bool'?text(v.value?'On':'Off'):typeof v.value==='number'?format.format(v.value):v.value;const unit=Object.hasOwn(units,v.unit)?units[v.unit]:v.unit;if(unit)value+=' '+unit;}
          const cells=row.children;
          update(cells[1],value);update(cells[2],text(states[v.state]));update(cells[3],text(quality[v.quality]));
          cells[3].className=v.quality==='unreliable'?'ems-warning':'';
          update(cells[4],v.source_type?hex(v.source_type):'—');update(cells[5],age(v.age_ms));
          const local=fieldAccess(id);cells[6].replaceChildren(badge(local.kind,local.label));
          if(row!==position)r.rows.insertBefore(row,position);position=row.nextElementSibling;
        }
        r.wrap.hidden=!visible.length;r.empty.hidden=!!visible.length;
        r.empty.textContent=text(entries.length?'No entities match this filter.':'Reports observed; entity decoding for this device is not available yet.');
        r.telegrams.textContent=text('Observed telegrams')+': '+d.telegram_types.map(t=>hex(t)+(reference.telegrams[t]?' '+reference.telegrams[t]:'')).join(', ')+(d.untracked_types?' · '+text('Additional telegram types not listed')+': '+d.untracked_types:'');
        r.box.hidden=!!search&&!!entries.length&&!visible.length;
      }
      // Newly observed lower addresses are inserted in order without rebuilding
      // existing details or moving already ordered/focused elements.
      let position=list.firstElementChild;
      for(const d of [...snapshot.inventory.devices].sort((a,b)=>a.address-b.address)){
        const box=records.get(d.address).box;
        if(box!==position)list.insertBefore(box,position);position=box.nextElementSibling;
      }
    }
    async function refresh(){
      if(busy||writeBusy||!alive())return;const generation=editGeneration;clearConfirmations();busy=true;get('ems-refresh').disabled=true;renderEditor();status.textContent=text('Loading EMS devices…');
      const request=new AbortController(),abort=()=>request.abort();owner.signal.addEventListener('abort',abort,{once:true});const deadline=setTimeout(abort,5000);
      try{
        const read=async(path,limit,validate)=>{
          const response=await fetch(path,{cache:'no-store',signal:request.signal});if(!response.ok)throw Error('http');
          const raw=await response.text();if(raw.length>limit)throw Error('size');const next=JSON.parse(raw);if(!validate(next))throw Error('shape');return next;
        };
        const [devices,settings]=await Promise.allSettled([
          read('/status/ems/devices',65536,valid),read('/status/boiler/settings',8192,validSettings)
        ]);
        if(!alive())return;
        const previousBoot=settingsSnapshot?.boot_id;settingsSnapshot=settings.status==='fulfilled'?settings.value:null;
        clearTimeout(expiryTimer);metadataAt=settingsSnapshot?performance.now():-Infinity;
        if(previousBoot&&settingsSnapshot&&previousBoot!==settingsSnapshot.boot_id)resetDraft();
        if(generation===editGeneration&&visible())interrupted=false;
        reconcileSetting();
        expiryTimer=setTimeout(()=>{if(alive()){clearConfirmations();renderSettings();}},30000);
        if(devices.status!=='fulfilled')throw Error('devices');
        const next=devices.value;measurementFresh=true;
        if(!alive())return;snapshot=next;root.dataset.failed='false';render();
        status.textContent=text('Snapshot updated. Refresh to read the latest values.')+(!window.OT_EMS_REFERENCE?' '+text('EMS reference unavailable; received readings remain available.'):'')+(next.inventory.untracked_frames?' '+text('Device list is full; additional reports were not listed.'):'')+(!next.enabled?' '+text('EMS reception is disabled.'):'');
      }catch(_){if(alive()){measurementFresh=false;root.dataset.failed='true';status.textContent=text('Refresh failed. Previously displayed values are an older snapshot.');}}
      finally{clearTimeout(deadline);owner.signal.removeEventListener('abort',abort);busy=false;if(alive()){renderSettings();get('ems-refresh').disabled=false;}}
    }
    get('ems-search').addEventListener('input',render,{signal:owner.signal});get('ems-access').addEventListener('change',render,{signal:owner.signal});get('ems-show-unknown').addEventListener('change',render,{signal:owner.signal});get('ems-refresh').addEventListener('click',refresh,{signal:owner.signal});refresh();
  }
  return Object.freeze({mount,unmount});
})();
