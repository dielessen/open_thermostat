'use strict';
window.SystemLogPage = (() => {
  let active = null;
  const levels = ['Off','Error','Warning','Info','Debug','Trace'];
  function mount(root) {
    if(active)active.abort();
    const controller=new AbortController();active=controller;
    const {signal}=controller, get=id=>root.querySelector('#'+id), text=s=>uiText(s);
    const state={rows:[],cursor:0,boot:null,paused:false,busy:false,dirty:false,saving:false,uncertain:false,epoch:0};
    const alive=()=>!signal.aborted&&root.isConnected;
    let timer=null;
    const observer=new MutationObserver(()=>{if(!root.isConnected)controller.abort();});
    observer.observe(document.body,{childList:true,subtree:true});
    signal.addEventListener('abort',()=>{clearTimeout(timer);observer.disconnect();},{once:true});
    const on=(element,event,fn)=>element.addEventListener(event,fn,{signal});
    function options(select,filter=false){
      for(let i=filter?1:0;i<levels.length;i++){const option=document.createElement('option');option.value=i;option.textContent=text(levels[i]);select.append(option);}
      select.value=filter?'5':'3';
    }
    get('log-lines').setAttribute('aria-label',text('System log'));
    options(get('log-filter'),true);options(get('log-web-level'));options(get('log-syslog-level'));
    const sourceOf = row => row.source ?? (/^(EMS|Ems)/.test(row.feature)?'ems':'esp');
    function render(){
      const source=get('log-source').value,level=Number(get('log-filter').value),search=get('log-search').value.toLocaleLowerCase();
      const lines=state.rows.filter(r=>(source==='all'||sourceOf(r)===source)&&r.level<=level&&`${r.feature} ${r.message}`.toLocaleLowerCase().includes(search))
        .map(r=>`${(r.uptime_ms/1000).toFixed(3)}s #${r.sequence} ${text(levels[r.level]).toLocaleUpperCase()} [${sourceOf(r).toUpperCase()}] [${r.feature}] ${r.message}`);
      get('log-lines').textContent=lines.join('\n');
      get('log-pause').textContent=text(state.paused?'Resume':'Pause');
    }
    async function request(url,options={}){
      const timeout=new AbortController(),abort=()=>timeout.abort();
      signal.addEventListener('abort',abort,{once:true});
      const deadline=setTimeout(abort,5000);
      try {
        const response=await fetch(url,{cache:'no-store',...options,signal:timeout.signal});
        if(!response.ok)throw Error(String(response.status));
        return await response.json();
      } finally {clearTimeout(deadline);signal.removeEventListener('abort',abort);}
    }
    async function poll(){
      if(!alive()||state.busy||state.paused)return;
      state.busy=true;const epoch=state.epoch;
      try{
        const data=await request('/status/logs?after='+state.cursor);
        if(!alive()||state.paused||epoch!==state.epoch)return;
        if(!Number.isSafeInteger(data.boot)||data.boot<0||!Number.isSafeInteger(data.latest)||data.latest<0||!Array.isArray(data.records)||data.records.length>8)throw Error('invalid');
        const restarted=state.boot!==null&&state.boot!==data.boot;
        let cursor=restarted?0:state.cursor;
        if(!restarted&&data.latest<cursor)throw Error('invalid');
        // Validate the WHOLE batch before changing history or its cursor. A bad
        // suffix must not consume valid earlier rows and hide them on retry.
        for(const r of data.records){
          if(!r||!Number.isSafeInteger(r.sequence)||r.sequence<=cursor||r.sequence>data.latest||!Number.isFinite(r.uptime_ms)||r.uptime_ms<0||!Number.isInteger(r.level)||r.level<1||r.level>5||typeof r.feature!=='string'||r.feature.length>16||typeof r.message!=='string'||r.message.length>192||(r.source!==undefined&&!['esp','ems'].includes(r.source)))throw Error('invalid');
          cursor=r.sequence;
        }
        // An old-boot cursor can suppress the new boot's first response. Retry
        // from zero instead of treating that empty page as complete history.
        if(data.records.length===0&&!restarted)cursor=Math.max(cursor,data.latest);
        state.rows=(restarted?[]:state.rows).concat(data.records).slice(-256);
        state.cursor=cursor;state.boot=data.boot;
        const count=k=>Number.isSafeInteger(data[k])&&data[k]>=0?data[k]:'?';
        get('log-counters').textContent=`${text('Overwritten')}: ${count('overwritten')} · ${text('Redacted')}: ${count('redacted')} · ${text('Truncated')}: ${count('truncated')} · ${text('Syslog sent (unconfirmed)')}: ${count('syslog_sent')} · ${text('Syslog dropped')}: ${count('syslog_dropped')} · ${text('Busy drops')}: ${count('contention_dropped')}`;
        get('log-status').textContent='';render();
      }catch(error){if(alive())get('log-status').textContent=text('Log unavailable. Retrying.');}
      finally{state.busy=false;if(alive()&&!state.paused)timer=setTimeout(poll,2000);}
    }
    on(get('log-pause'),'click',()=>{state.paused=!state.paused;clearTimeout(timer);render();if(!state.paused)poll();});
    on(get('log-source'),'change',render);on(get('log-filter'),'change',render);on(get('log-search'),'input',render);
    on(get('log-download'),'click',()=>{
      const header=`OpenThermostat boot=${state.boot} — ${text('Received browser history; gaps may exist.')}`;
      const blob=new Blob([header+'\n'+get('log-lines').textContent+'\n'],{type:'text/plain;charset=utf-8'});
      const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='openthermostat-system-log.txt';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    });
    on(get('log-clear'),'click',async()=>{
      if(state.saving)return;
      state.saving=true;get('log-clear').disabled=true;
      try{await request('/logs/clear',{method:'POST'});if(alive()){++state.epoch;state.rows=[];render();}}
      catch{if(alive())get('log-status').textContent=text('Clear failed. Local logs were not confirmed cleared.');}
      finally{state.saving=false;if(alive())get('log-clear').disabled=false;}
    });
    const form=get('log-settings');
    on(form,'input',()=>{state.dirty=true;});
    function fill(s){
      get('log-enabled').checked=s.syslog_enabled;get('log-syslog-esp').checked=s.syslog_esp??true;get('log-syslog-ems').checked=s.syslog_ems??true;get('log-server').value=s.server;
      get('log-port').value=s.port;get('log-syslog-level').value=s.syslog_level;get('log-web-level').value=s.web_level;get('log-mark').value=s.mark_interval_s;
    }
    on(form,'submit',async event=>{
      event.preventDefault();if(state.saving||state.uncertain||!form.reportValidity())return;
      const candidate={syslog_enabled:get('log-enabled').checked,syslog_esp:get('log-syslog-esp').checked,syslog_ems:get('log-syslog-ems').checked,server:get('log-server').value.trim(),port:Number(get('log-port').value),syslog_level:Number(get('log-syslog-level').value),web_level:Number(get('log-web-level').value),mark_interval_s:Number(get('log-mark').value)};
      state.saving=true;for(const input of form.querySelectorAll('input,select,button'))input.disabled=true;
      // No automatic retry of a mutation. Readback must match all requested values.
      try{
        const saved=await request('/config/logging',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(candidate)});
        const actual=await request('/config/logging');
        if(!Object.keys(candidate).every(k=>saved[k]===candidate[k]&&actual[k]===candidate[k]))throw Error('readback');
        if(alive()){state.dirty=false;get('log-settings-status').textContent=text('Logging settings saved and verified.');}
      }catch{state.uncertain=true;if(alive())get('log-settings-status').textContent=text('Logging settings save could not be confirmed. Reload before retrying.');}
      finally{state.saving=false;if(alive()){for(const input of form.querySelectorAll('input,select,button'))input.disabled=false;get('log-save').disabled=state.uncertain;}}
    });
    request('/config/logging').then(s=>{if(alive()){if(!state.dirty&&!state.saving&&!state.uncertain)fill(s);get('log-save').disabled=state.saving||state.uncertain;}})
      .catch(()=>{if(alive())get('log-settings-status').textContent=text('Logging settings unavailable. Reload to retry.');});
    render();poll();
  }
  return {mount};
})();
