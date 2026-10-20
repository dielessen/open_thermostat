'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const ssid=$('ssid'), password=$('password'), status=$('status'), networks=$('networks');
  let scanning=false, joining=false, posting=false, saved=false, finished=false, scanDeadline=0;
  let finishing=false, handoffTarget='', navigateAt=0, closeAt=0, handoffTimer;
  function controls() {
    $('network-fields').hidden=$('intro').hidden=$('remaining').hidden=saved;
    $('heading').textContent=saved?'Verbonden met wifi':'Verbind met je wifi';
    const transferring=finishing||navigateAt>0;
    $('scan').disabled=scanning||joining||finished||transferring;
    $('connect').disabled=scanning||joining||finished||transferring;
    ssid.disabled=password.disabled=networks.disabled=joining||finished||transferring;
  }
  async function request(url, options={}) {
    const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),5000);
    try {
      const r=await fetch(url,{...options,signal:controller.signal,cache:'no-store',credentials:'same-origin'});
      if(!r.ok) {
        const error=Error(await r.text()||'Aanvraag mislukt'); error.httpStatus=r.status; throw error;
      }
      return r;
    } finally { clearTimeout(timeout); }
  }
  async function scan() {
    if(scanning||joining||finished) return;
    scanning=true; scanDeadline=Date.now()+20000; controls();
    $('scan-status').textContent='Zoeken naar 2,4 GHz-netwerken…';
    try { await request('/setup/scan',{method:'POST'}); }
    catch(e) {
      if(e.httpStatus) { scanning=false; controls(); }
      $('scan-status').textContent='Scan nog niet bevestigd. Wacht op verbinding of probeer opnieuw.';
    }
  }
  $('scan').onclick=scan;
  networks.onchange=()=>{if(networks.value) ssid.value=networks.value;};
  $('form').onsubmit=async e=>{
    e.preventDefault(); if(scanning||joining||finished) return;
    const name=ssid.value, secret=password.value;
    if(!name||new TextEncoder().encode(name).length>32||new TextEncoder().encode(secret).length>63||(secret&&new TextEncoder().encode(secret).length<8)) {
      status.textContent='Vul een wifi-naam van maximaal 32 bytes en een wachtwoord van 8–63 bytes in (of leeg voor een open netwerk).'; return;
    }
    joining=true; posting=true; saved=false; $('handoff').hidden=true; controls();
    status.textContent='Verbinding wordt getest (maximaal 30 seconden). Bij een korte onderbreking: blijf bij het OpenThermostat-setupnetwerk; de pagina probeert opnieuw.';
    try {
      await request('/setup/network',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ssid:name,password:secret})});
    } catch(e) {
      // A lost POST response does not mean failure. Status resolves the result
      // without duplicate requests while the single radio changes channel.
      if(e.httpStatus) { joining=false; status.textContent='Aanvraag niet geaccepteerd. Wacht tot de scan klaar is en controleer de invoer.'; controls(); }
      else status.textContent='Tijdelijk geen antwoord. Blijf verbonden met de setup-wifi; de verbindingscontrole gaat automatisch verder.';
    } finally { posting=false; }
  };
  function target(s) {
    if(typeof s.station_ip!=='string'||!/^\d{1,3}(\.\d{1,3}){3}$/.test(s.station_ip)||s.station_ip==='0.0.0.0'||s.station_ip.split('.').some(n=>Number(n)>255)) return '';
    const port=s.station_port===undefined?80:s.station_port;
    if(!Number.isInteger(port)||port<1||port>65535) return '';
    return 'http://'+s.station_ip+(port===80?'':':'+port)+'/';
  }
  function cancelHandoff() {
    clearInterval(handoffTimer); navigateAt=closeAt=0; handoffTarget='';
  }
  function armHandoff(ms,url) {
    if(!Number.isFinite(ms)||ms<0||ms>10000) return false;
    if(navigateAt&&handoffTarget===url) return true;
    cancelHandoff(); handoffTarget=url; closeAt=Date.now()+ms; navigateAt=closeAt+2000;
    const update=()=>{
      const left=Math.max(0,Math.ceil((closeAt-Date.now())/1000));
      $('transition').textContent=left?'Het setupnetwerk sluit over '+left+' seconden. Daarna openen we automatisch je thermostaat op het adres hieronder.':'Setupnetwerk wordt gesloten. Verbind met je thuiswifi; we openen het nieuwe adres…';
      if(Date.now()>=navigateAt) {
        finished=true; clearInterval(handoffTimer); controls(); window.location.assign(handoffTarget);
      }
    };
    update(); handoffTimer=setInterval(update,250); controls(); return true;
  }
  async function automaticFinish(url) {
    if(finishing||navigateAt||finished) return;
    finishing=true; controls();
    $('transition').textContent='Het nieuwe adres staat klaar. Automatisch afronden wordt bevestigd…';
    try {
      const result=await (await request('/setup/finish',{method:'POST'})).json();
      if(!armHandoff(result.close_after_ms,url)) throw Error('Ongeldige afrondbevestiging');
    } catch(e) {
      $('transition').textContent='Afronden nog niet bevestigd. Deze pagina probeert automatisch opnieuw; het nieuwe adres blijft hieronder staan.';
    } finally { finishing=false; controls(); }
  }
  function showNetworks(rows) {
    const strongest=new Map();
    for(const row of rows) if(typeof row.ssid==='string'&&row.ssid&&(!strongest.has(row.ssid)||row.rssi>strongest.get(row.ssid).rssi)) strongest.set(row.ssid,row);
    networks.replaceChildren(new Option('Kies een netwerk',''));
    for(const row of [...strongest.values()].sort((a,b)=>b.rssi-a.rssi)) networks.add(new Option(row.ssid+' ('+row.rssi+' dBm)',row.ssid));
    $('scan-status').textContent=strongest.size?strongest.size+' netwerk(en) gevonden.':'Geen 2,4 GHz-netwerken gevonden. Probeer opnieuw of vul een netwerknaam handmatig in.';
  }
  async function tick() {
    if(finished) return;
    try {
      const r=await request('/setup/status'), s=await r.json();
      $('remaining').textContent=s.setup_active?'Setupnetwerk nog ongeveer '+Math.ceil(s.remaining_seconds/60)+' minuten beschikbaar.':'Setupnetwerk gesloten.';
      const url=target(s);
      if(s.status==='connected_saved'&&s.connected&&url) {
        saved=true; joining=false; password.value='';
        if(handoffTarget&&handoffTarget!==url) cancelHandoff();
        $('home').href=url; $('home').textContent=url;
        $('handoff').hidden=false;
        status.textContent='Je thermostaat is verbonden. De wifi-instellingen zijn opgeslagen.';
        if(s.closing) armHandoff(s.close_after_ms,url);
        else { cancelHandoff(); await automaticFinish(url); }
      } else if(s.status==='connection_failed'||s.status==='storage_error') {
        cancelHandoff(); joining=false; saved=false; $('handoff').hidden=true;
        status.textContent=s.status==='connection_failed'?'Verbinding mislukt. Controleer wifi-naam en wachtwoord en probeer opnieuw. De setup-wifi blijft beschikbaar.':'Verbonden, maar opslaan niet bevestigd. Probeer opnieuw; de setup-wifi blijft beschikbaar.';
      } else if(s.status==='connected_saved') {
        cancelHandoff(); joining=false; saved=false; $('handoff').hidden=true;
        status.textContent='Instellingen opgeslagen, maar de thuisnetwerkverbinding is weggevallen. Controleer het bereik of probeer opnieuw.';
      } else if(s.status==='connecting') { cancelHandoff(); joining=true; saved=false; $('handoff').hidden=true; }
      else if(joining&&!posting&&s.status==='ready') { joining=false; status.textContent='Geen verbindingspoging ontvangen. Je kunt opnieuw op Verbinden klikken.'; }
      if(scanning) {
        const scanResponse=await request('/setup/scan'), result=await scanResponse.json();
        if(result.status==='done') { scanning=false; showNetworks(result.networks||[]); }
        else if(result.status==='failed'||Date.now()>scanDeadline) { scanning=false; $('scan-status').textContent='Scannen mislukt. Probeer opnieuw of vul het 2,4 GHz-netwerk handmatig in.'; }
      }
      controls();
    } catch(e) {
      if(scanning&&Date.now()>scanDeadline) { scanning=false; $('scan-status').textContent='Scan niet bereikbaar. Verbind opnieuw met de setup-wifi en probeer opnieuw.'; controls(); }
      if(!saved) status.textContent='Tijdelijk geen verbinding met het apparaat. Blijf op de OpenThermostat-setup-wifi; deze pagina probeert automatisch opnieuw.';
    } finally { if(!finished) setTimeout(tick,1000); }
  }
  tick(); scan();
})();
