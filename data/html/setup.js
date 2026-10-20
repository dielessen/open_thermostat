'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const ssid=$('ssid'), password=$('password'), status=$('status'), networks=$('networks');
  let scanning=false, joining=false, posting=false, saved=false, finished=false, scanDeadline=0;
  function controls() {
    $('scan').disabled=scanning||joining||finished;
    $('connect').disabled=scanning||joining||finished;
    ssid.disabled=password.disabled=networks.disabled=joining||finished;
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
  $('finish').onclick=async()=>{
    if(!saved||finished) return;
    $('finish').disabled=true;
    try {
      await request('/setup/finish',{method:'POST'}); finished=true; controls();
      status.textContent='Opgeslagen. Verbind je telefoon of laptop nu met je thuisnetwerk en open de link hieronder.';
    } catch(e) {
      $('finish').disabled=false;
      status.textContent='Afronden niet bevestigd. Verbind opnieuw met de setup-wifi om de status te controleren, of open de thuisnetwerk-link nadat je bent overgeschakeld.';
    }
  };
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
      if(s.status==='connected_saved'&&s.connected&&/^\d{1,3}(\.\d{1,3}){3}$/.test(s.station_ip)&&s.station_ip!=='0.0.0.0') {
        saved=true; joining=false; password.value='';
        $('home').href='http://'+s.station_ip+'/'; $('home').textContent='Open http://'+s.station_ip+'/ op je thuisnetwerk';
        $('handoff').hidden=false;
        status.textContent='Verbonden en opgeslagen. Schakel naar je thuisnetwerk en open de link hieronder. Het setupnetwerk blijft tot afronden of het einde van het setupvenster beschikbaar.';
      } else if(s.status==='connection_failed'||s.status==='storage_error') {
        joining=false; saved=false; $('handoff').hidden=true;
        status.textContent=s.status==='connection_failed'?'Verbinding mislukt. Controleer wifi-naam en wachtwoord en probeer opnieuw. De setup-wifi blijft beschikbaar.':'Verbonden, maar opslaan niet bevestigd. Probeer opnieuw; de setup-wifi blijft beschikbaar.';
      } else if(s.status==='connected_saved'&&!s.connected) {
        joining=false; saved=false; $('handoff').hidden=true;
        status.textContent='Instellingen opgeslagen, maar de thuisnetwerkverbinding is weggevallen. Controleer het bereik of probeer opnieuw.';
      } else if(s.status==='connecting') { joining=true; saved=false; $('handoff').hidden=true; }
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
