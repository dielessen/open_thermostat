'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const ssid=$('ssid'), password=$('password'), status=$('status'), networks=$('networks');
  let scanning=false, joining=false, posting=false, saved=false, finished=false, scanDeadline=0;
  let finishing=false, handoffTarget='', navigateAt=0, closeAt=0, handoffTimer;
  function controls() {
    $('network-fields').hidden=$('intro').hidden=$('remaining').hidden=saved;
    $('heading').textContent=saved?uiText("Connected to WiFi"):uiText("Connect to your WiFi");
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
        const error=Error(await r.text()||uiText("Request failed")); error.httpStatus=r.status; throw error;
      }
      return r;
    } finally { clearTimeout(timeout); }
  }
  async function scan() {
    if(scanning||joining||finished) return;
    scanning=true; scanDeadline=Date.now()+20000; controls();
    $('scan-status').textContent=uiText("Searching for 2.4 GHz networks…");
    try { await request('/setup/scan',{method:'POST'}); }
    catch(e) {
      if(e.httpStatus) { scanning=false; controls(); }
      $('scan-status').textContent=uiText("Scan not yet confirmed. Wait for connection or retry.");
    }
  }
  $('scan').onclick=scan;
  networks.onchange=()=>{if(networks.value) ssid.value=networks.value;};
  $('form').onsubmit=async e=>{
    e.preventDefault(); if(scanning||joining||finished) return;
    const name=ssid.value, secret=password.value;
    if(!name||new TextEncoder().encode(name).length>32||new TextEncoder().encode(secret).length>63||(secret&&new TextEncoder().encode(secret).length<8)) {
      status.textContent=uiText("Enter a WiFi name of up to 32 bytes and a password of 8–63 bytes (or leave empty for an open network)."); return;
    }
    joining=true; posting=true; saved=false; $('handoff').hidden=true; controls();
    status.textContent=uiText("Testing connection (up to 30 seconds). During a brief interruption, stay on the OpenThermostat setup network; this page will retry.");
    try {
      await request('/setup/network',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ssid:name,password:secret})});
    } catch(e) {
      // A lost POST response does not mean failure. Status resolves the result
      // without duplicate requests while the single radio changes channel.
      if(e.httpStatus) { joining=false; status.textContent=uiText("Request not accepted. Wait for the scan to finish and check your input."); controls(); }
      else status.textContent=uiText("Temporarily no response. Stay connected to the setup WiFi; the connection check continues automatically.");
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
      $('transition').textContent=left?uiText("The setup network closes in ")+left+uiText(" seconds. We will then open your thermostat automatically at the address below."):uiText("Closing setup network. Connect to your home WiFi; we will open the new address…");
      if(Date.now()>=navigateAt) {
        finished=true; clearInterval(handoffTimer); controls(); window.location.assign(handoffTarget);
      }
    };
    update(); handoffTimer=setInterval(update,250); controls(); return true;
  }
  async function automaticFinish(url) {
    if(finishing||navigateAt||finished) return;
    finishing=true; controls();
    $('transition').textContent=uiText("The new address is ready. Confirming automatic completion…");
    try {
      const result=await (await request('/setup/finish',{method:'POST'})).json();
      if(!armHandoff(result.close_after_ms,url)) throw Error(uiText("Invalid completion confirmation"));
    } catch(e) {
      $('transition').textContent=uiText("Completion not yet confirmed. This page retries automatically; the new address remains below.");
    } finally { finishing=false; controls(); }
  }
  function showNetworks(rows) {
    const strongest=new Map();
    for(const row of rows) if(typeof row.ssid==='string'&&row.ssid&&(!strongest.has(row.ssid)||row.rssi>strongest.get(row.ssid).rssi)) strongest.set(row.ssid,row);
    networks.replaceChildren(new Option(uiText("Choose a network"),''));
    for(const row of [...strongest.values()].sort((a,b)=>b.rssi-a.rssi)) networks.add(new Option(row.ssid+' ('+row.rssi+' dBm)',row.ssid));
    $('scan-status').textContent=strongest.size?strongest.size+uiText(" network(s) found."):uiText("No 2.4 GHz networks found. Retry or enter a network name manually.");
  }
  async function tick() {
    if(finished) return;
    try {
      const r=await request('/setup/status'), s=await r.json();
      $('remaining').textContent=s.setup_active?uiText("Setup network available for about ")+Math.ceil(s.remaining_seconds/60)+uiText(" minutes available."):uiText("Setup network closed.");
      const url=target(s);
      if(s.status==='connected_saved'&&s.connected&&url) {
        saved=true; joining=false; password.value='';
        if(handoffTarget&&handoffTarget!==url) cancelHandoff();
        $('home').href=url; $('home').textContent=url;
        $('handoff').hidden=false;
        status.textContent=uiText("Your thermostat is connected. WiFi settings have been saved.");
        if(s.closing) armHandoff(s.close_after_ms,url);
        else { cancelHandoff(); await automaticFinish(url); }
      } else if(s.status==='connection_failed'||s.status==='storage_error') {
        cancelHandoff(); joining=false; saved=false; $('handoff').hidden=true;
        status.textContent=s.status==='connection_failed'?uiText("Connection failed. Check the WiFi name and password and retry. Setup WiFi remains available."):uiText("Connected, but saving not confirmed. Retry; setup WiFi remains available.");
      } else if(s.status==='connected_saved') {
        cancelHandoff(); joining=false; saved=false; $('handoff').hidden=true;
        status.textContent=uiText("Settings saved, but the home network connection was lost. Check signal range or retry.");
      } else if(s.status==='connecting') { cancelHandoff(); joining=true; saved=false; $('handoff').hidden=true; }
      else if(joining&&!posting&&s.status==='ready') { joining=false; status.textContent=uiText("No connection attempt received. You can click Connect again."); }
      if(scanning) {
        const scanResponse=await request('/setup/scan'), result=await scanResponse.json();
        if(result.status==='done') { scanning=false; showNetworks(result.networks||[]); }
        else if(result.status==='failed'||Date.now()>scanDeadline) { scanning=false; $('scan-status').textContent=uiText("Scan failed. Retry or enter the 2.4 GHz network manually."); }
      }
      controls();
    } catch(e) {
      if(scanning&&Date.now()>scanDeadline) { scanning=false; $('scan-status').textContent=uiText("Scan unreachable. Reconnect to the setup WiFi and retry."); controls(); }
      if(!saved) status.textContent=uiText("Temporarily no connection to the device. Stay on the OpenThermostat setup WiFi; this page retries automatically.");
    } finally { if(!finished) setTimeout(tick,1000); }
  }
  tick(); scan();
})();
