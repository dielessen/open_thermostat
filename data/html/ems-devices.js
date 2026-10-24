'use strict';
window.EMSDevicesPage=(()=>{
  let active=null;
  const text=s=>uiText(s), hex=n=>'0x'+n.toString(16).toUpperCase().padStart(2,'0');
  const number=n=>Number.isSafeInteger(n)&&n>=0;
  const nullable=n=>n===null||number(n);
  const states={valid:'Received',stale:'Expired',invalid:'Invalid',unknown:'Not received'};
  const quality={reported:'Reported',unreliable:'Unreliable',inferred:'Inferred'};
  const units={degC:'°C',uA:'µA',bool:'',bits:'',text:'',code:''};
  function valid(s){
    const i=s?.inventory,f=s?.boiler?.fields;
    if(typeof s?.enabled!=='boolean'||i?.schema!==1||i.capacity!==16||!number(i.untracked_frames)||!Array.isArray(i.devices)||i.devices.length>16||!f||typeof f!=='object'||Array.isArray(f)||Object.keys(f).length>100)return false;
    const addresses=new Set();
    for(const d of i.devices){
      if(!d||typeof d!=='object'||!number(d.address)||d.address<1||d.address>127||addresses.has(d.address)||!number(d.frames)||d.frames<1||!nullable(d.age_ms)||!nullable(d.product_id)||d.product_id>254||!nullable(d.brand_id)||d.brand_id>254||!number(d.untracked_types)||!(d.version===null||typeof d.version==='string'&&/^\d{1,3}\.\d{1,3}$/.test(d.version))||!Array.isArray(d.telegram_types)||d.telegram_types.length>8||new Set(d.telegram_types).size!==d.telegram_types.length||!d.telegram_types.every(t=>number(t)&&t<=65535))return false;
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
    let snapshot=null,busy=false;
    const get=id=>root.querySelector('#'+id),list=get('ems-device-list'),status=get('ems-devices-status');
    const alive=()=>!owner.signal.aborted&&root.isConnected;
    const records=new Map(),labels=new Map();
    const format=new Intl.NumberFormat(OpenThermostatLanguage.locale,{maximumFractionDigits:2,useGrouping:false});
    const description=id=>{if(!labels.has(id))labels.set(id,label(id));return labels.get(id);};
    function fields(d){return d.address===8?Object.entries(snapshot.boiler.fields):[];}
    function render(){
      if(!snapshot||!alive())return;
      const search=get('ems-search').value.trim().toLocaleLowerCase(),showUnknown=get('ems-show-unknown').checked;
      const ids=new Set(snapshot.inventory.devices.map(d=>d.address));
      for(const [id,r] of records)if(!ids.has(id)){r.box.remove();records.delete(id);}
      if(!ids.size){list.replaceChildren(el('p',text(snapshot.enabled?'No EMS device reports received yet.':'EMS reception is disabled.')));return;}
      for(const d of [...snapshot.inventory.devices].sort((a,b)=>a.address-b.address)){
        let r=records.get(d.address);
        if(!r){
          if(!records.size)list.replaceChildren();
          const box=el('details'),summary=el('summary'),title=el('span'),badge=el('span',undefined,'ems-device-status'),body=el('div',undefined,'ems-device-body'),meta=el('p',undefined,'ems-device-meta'),wrap=el('div',undefined,'ems-table-wrap'),table=el('table'),head=el('thead'),tr=el('tr'),rows=el('tbody'),empty=el('p'),telegrams=el('p',undefined,'ems-device-meta');
          for(const name of ['Entity','Value','Status','Quality','Telegram','Age'])tr.append(el('th',text(name)));head.append(tr);table.append(head,rows);wrap.append(table);body.append(meta,wrap,empty,telegrams);summary.append(title,badge);box.append(summary,body);box.dataset.address=d.address;list.append(box);r={box,title,badge,meta,rows,empty,wrap,telegrams};records.set(d.address,r);
        }
        const entries=fields(d),received=entries.filter(([,v])=>v.state!=='unknown').length;
        r.rowCache??=new Map();
        const known=new Set(entries.map(([id])=>id));
        for(const [id,row] of r.rowCache)if(!known.has(id)){row.remove();r.rowCache.delete(id);}
        for(const id of labels.keys())if(!Object.hasOwn(snapshot.boiler.fields,id))labels.delete(id);
        r.title.textContent=(d.address===8?text('Boiler'):text('EMS device'))+' '+hex(d.address);
        r.badge.textContent=received+' '+text('received entities')+' · '+(d.age_ms===null?text('Unknown'):d.age_ms>=30000?text('No recent report'):text('Report received'));
        r.meta.textContent=text('Product ID')+': '+(d.product_id===null?text('Unknown'):d.product_id)+' · '+text('Version')+': '+(d.version??text('Unknown'))+' · '+text('Brand ID')+': '+(d.brand_id===null?text('Unknown'):d.brand_id)+' · '+text('Last report')+': '+age(d.age_ms)+' · '+text('Frames')+': '+d.frames;
        const visible=entries.filter(([id,v])=>(showUnknown||v.state!=='unknown')&&(id+' '+description(id)).toLocaleLowerCase().includes(search));
        const wanted=new Set(visible.map(([id])=>id));
        for(const row of [...r.rows.children])if(!wanted.has(row.dataset.field))row.remove();
        let position=r.rows.firstElementChild;
        for(const [id,v] of visible){
          let row=r.rowCache.get(id);
          if(!row){
            row=el('tr');row.dataset.field=id;
            const name=el('td',description(id));name.append(el('code',id));
            row.append(name,el('td',undefined,'ems-value'),el('td'),el('td'),el('td'),el('td'));r.rowCache.set(id,row);
          }
          let value='—';
          if(v.value!==null){value=v.unit==='bool'?text(v.value?'On':'Off'):typeof v.value==='number'?format.format(v.value):v.value;const unit=Object.hasOwn(units,v.unit)?units[v.unit]:v.unit;if(unit)value+=' '+unit;}
          const cells=row.children;
          update(cells[1],value);update(cells[2],text(states[v.state]));update(cells[3],text(quality[v.quality]));
          cells[3].className=v.quality==='unreliable'?'ems-warning':'';
          update(cells[4],v.source_type?hex(v.source_type):'—');update(cells[5],age(v.age_ms));
          if(row!==position)r.rows.insertBefore(row,position);position=row.nextElementSibling;
        }
        r.wrap.hidden=!visible.length;r.empty.hidden=!!visible.length;
        r.empty.textContent=text(entries.length?'No entities match this filter.':'Reports observed; entity decoding for this device is not available yet.');
        r.telegrams.textContent=text('Observed telegrams')+': '+d.telegram_types.map(hex).join(', ')+(d.untracked_types?' · '+text('Additional telegram types not listed')+': '+d.untracked_types:'');
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
      if(busy||!alive())return;busy=true;get('ems-refresh').disabled=true;status.textContent=text('Loading EMS devices…');
      const request=new AbortController(),abort=()=>request.abort();owner.signal.addEventListener('abort',abort,{once:true});const deadline=setTimeout(abort,5000);
      try{
        const response=await fetch('/status/ems/devices',{cache:'no-store',signal:request.signal});if(!response.ok)throw Error('http');
        const raw=await response.text();if(raw.length>65536)throw Error('size');const next=JSON.parse(raw);if(!valid(next))throw Error('shape');
        if(!alive())return;snapshot=next;root.dataset.failed='false';render();
        status.textContent=text('Snapshot updated. Refresh to read the latest values.')+(next.inventory.untracked_frames?' '+text('Device list is full; additional reports were not listed.'):'')+(!next.enabled?' '+text('EMS reception is disabled.'):'');
      }catch(_){if(alive()){root.dataset.failed='true';status.textContent=text('Refresh failed. Previously displayed values are an older snapshot.');}}
      finally{clearTimeout(deadline);owner.signal.removeEventListener('abort',abort);busy=false;if(alive())get('ems-refresh').disabled=false;}
    }
    get('ems-search').addEventListener('input',render,{signal:owner.signal});get('ems-show-unknown').addEventListener('change',render,{signal:owner.signal});get('ems-refresh').addEventListener('click',refresh,{signal:owner.signal});refresh();
  }
  return Object.freeze({mount,unmount});
})();
