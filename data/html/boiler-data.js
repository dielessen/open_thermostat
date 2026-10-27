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
  return Object.freeze({subscribe,refresh});
})();
