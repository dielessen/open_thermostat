'use strict';
// One in-flight GET and one polling timer per document, shared by all boiler
// views. A subscriber never owns a bus reader or a control/supervision lease.
window.BoilerData = (() => {
  const listeners = new Set();
  let pending=null, controller=null, timer=null, generation=0, current=null;
  const valid=data=>data&&typeof data==='object'&&!Array.isArray(data)
    &&data.fields&&typeof data.fields==='object'&&!Array.isArray(data.fields)
    &&Object.keys(data.fields).length<=96&&data.reception&&data.transport;
  function notify(listener,data,error) {
    try { listener(data,error); }
    catch(failure) {
      // A failed optional panel must not turn a successful HTTP response into
      // a connection failure for every consumer. Keep the render error visible
      // through the browser's normal error reporting.
      if(typeof window.reportError==='function')window.reportError(failure);
    }
  }
  function publish(data,error) {
    current=data;
    for(const listener of listeners)notify(listener,data,error);
  }
  function refresh() {
    if(pending)return pending;
    if(!listeners.size||document.visibilityState==='hidden')return Promise.resolve(null);
    clearTimeout(timer);
    const own=generation,request=new AbortController();controller=request;
    const deadline=setTimeout(()=>request.abort(),4000);
    const job=(async()=>{
      try {
        const response=await fetch('/status/ems/telemetry',{cache:'no-store',signal:request.signal});
        if(!response.ok)throw Error('Boiler snapshot unavailable');
        const body=await response.text();if(body.length>131072)throw Error('Boiler snapshot too large');
        const data=JSON.parse(body);if(!valid(data))throw Error('Invalid boiler snapshot');
        if(own===generation&&listeners.size)publish(data,null);
        return data;
      }catch(error){
        if(own===generation&&listeners.size)publish(null,error);
        return null;
      }finally{
        clearTimeout(deadline);
        if(own===generation){
          pending=null;controller=null;
          if(listeners.size&&document.visibilityState!=='hidden')timer=setTimeout(refresh,5000);
        }
      }
    })();
    pending=job;return job;
  }
  function subscribe(listener,{signal}={}) {
    if(signal?.aborted)return ()=>{};
    listeners.add(listener);
    const unsubscribe=()=>{
      signal?.removeEventListener('abort',unsubscribe);
      listeners.delete(listener);
      if(!listeners.size){
        generation++;clearTimeout(timer);controller?.abort();
        pending=null;controller=null;current=null;
      }
    };
    signal?.addEventListener('abort',unsubscribe,{once:true});
    if(current)notify(listener,current,null);
    else refresh();
    return unsubscribe;
  }
  document.addEventListener('visibilitychange',()=>{
    if(document.visibilityState==='hidden')clearTimeout(timer);
    else if(listeners.size)refresh();
  });
  // A setting the boiler sends only when asked (request_only, EMS/ClassicBoilerMonitor.h) stays shown
  // until a newer read replaces it, with when it was read: "read at start-up" for a value from the E32's
  // first 15 minutes, else its age. '' for any other field, or without a value.
  const startupMs=900000;
  function readRemark(field){
    const count=n=>Number.isSafeInteger(n)&&n>=0;
    if(field?.request_only!==true||field.value===null||field.value===undefined||!count(field.age_ms))return '';
    if(count(field.observed_at_ms)&&field.observed_at_ms<startupMs)return uiText("read at start-up");
    if(field.age_ms<60000)return uiText("read just now");
    return field.age_ms<3600000?uiText("read {n} min ago").replace('{n}',Math.floor(field.age_ms/60000))
      :uiText("read {n} h ago").replace('{n}',Math.round(field.age_ms/3600000));
  }
  return Object.freeze({subscribe,refresh,readRemark});
})();
