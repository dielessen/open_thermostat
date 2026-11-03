// Shipped HA room status card (1.1) with the integration's real translations and a fixture hass; no HA or device.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),component=path.join(root,'ha/config/custom_components/open_thermostat');
const source=fs.readFileSync(path.join(component,'frontend/room-status-card.js'));
const out=path.resolve(process.env.OPENTHERMOSTAT_ROOM_STATUS_CARD_EVIDENCE||path.join(root,'out/ha-room-status-card-20261101'));
// What Home Assistant's frontend loads for the "entity" category: flattened component.<domain>.entity... keys.
function resources(lang){
 const flat={},walk=(value,prefix)=>{for(const [k,v] of Object.entries(value))typeof v==='object'?walk(v,prefix+k+'.'):flat[prefix+k]=v;};
 walk(JSON.parse(fs.readFileSync(path.join(component,'translations',lang+'.json'))).entity,'component.open_thermostat.entity.');
 return flat;
}
const since=new Date(Date.now()-25*60000).toISOString(),until=new Date(Date.now()+3*86400000).toISOString();
const reason=(state,line,values,extra)=>({state,attributes:{room_id:'living',line,values,temperature:20.6,setpoint:22.5,presence:null,window:null,
 valve_position:null,valve_problem:null,friendly_name:'Living Reason',...extra}});
const STATES={
 'sensor.living_reason':reason('heating','heating',{temperature:20.6,target:22.5},{presence:'room_home',valve_position:40,valve_problem:false}),
 'sensor.kitchen_reason':reason('window_open','window_open_contact',{contact:'Back door',since},{setpoint:8,presence:'house_home',window:'open'}),
 'sensor.bedroom_reason':reason('room_away','room_away',{target:18},{presence:'room_away'}),
 'sensor.study_reason':reason('off','off',{},{temperature:null,setpoint:null}),
 'sensor.hall_reason':reason('holiday','holiday',{until,target:15}),
 'sensor.attic_reason':{state:'unavailable',attributes:{friendly_name:'Attic Reason'}},
};
const WORDS={
 en:{living:'Heating: 20.6 → 22.5 °C',kitchen:/^Paused: Back door open since (\S+ )?\d{1,2}:\d\d( [AP]M)?$/,bedroom:'Away: nobody of this room is home (18 °C)',
  study:'Frost protection only (room off)',hall:/^Holiday until \S+ \d{1,2}:\d\d( [AP]M)? \(15 °C\)$/,valves:'Radiator valves open: 40 %',home:'Someone of this room is home'},
 nl:{living:'Verwarmt: 20,6 → 22,5 °C',kitchen:/^Gepauzeerd: Back door open sinds (\S+ )?\d\d:\d\d$/,bedroom:'Afwezig: niemand van deze ruimte is thuis (18 °C)',
  study:'Alleen vorstbeveiliging (ruimte uit)',hall:/^Vakantie tot \S+ \d\d:\d\d \(15 °C\)$/,valves:'Radiatorkranen open: 40 %',home:'Iemand van deze ruimte is thuis'},
 pl:{living:'Grzeje: 20,6 → 22,5 °C',kitchen:/^Wstrzymane: Back door otwarte od (\S+ )?\d\d:\d\d$/,bedroom:'Nieobecność: nikogo z tego pomieszczenia nie ma w domu (18 °C)',
  study:'Tylko ochrona przed mrozem (pomieszczenie wyłączone)',hall:/^Urlop do \S+ \d\d:\d\d \(15 °C\)$/,valves:'Otwarcie zaworów grzejnikowych: 40 %',home:'Ktoś z tego pomieszczenia jest w domu'},
};
const THEMES={light:'--primary-text-color:#212121;--secondary-text-color:#727272;--card-background-color:#fff;--secondary-background-color:#f5f5f5;background:#fafafa',
 dark:'--primary-text-color:#e1e1e1;--secondary-text-color:#9b9b9b;--card-background-color:#1c1c1c;--secondary-background-color:#282828;background:#111'};
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const lang of ['en','nl','pl'])for(const [width,theme] of [[1280,'light'],[390,'dark'],[320,'light']]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent(`<style>body{margin:0;padding:16px;font:14px Roboto,Arial;${THEMES[theme]}}main{display:grid;gap:12px;max-width:420px}
   ha-card{background:var(--card-background-color);border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.2)}</style><main></main>`);
  // ha-card is Home Assistant's own element; a plain block stands in for it here.
  await page.evaluate(()=>customElements.define('ha-card',class extends HTMLElement{}));
  // ha-icon is Home Assistant's own element too (it draws the mdi glyph); this stand-in shows a visible
  // marker per icon, so the screenshots show where each glyph goes and which one it is.
  await page.evaluate(()=>customElements.define('ha-icon',class extends HTMLElement{connectedCallback(){
   const name=(this.getAttribute('icon')||'').replace('mdi:','');this.title=name;
   this.textContent=name.split('-').map(w=>w[0]).join('').slice(0,2).toUpperCase();
   this.style.cssText='display:inline-flex;align-items:center;justify-content:center;width:var(--mdc-icon-size,24px);height:var(--mdc-icon-size,24px);font:700 10px Arial;border:1.5px solid currentColor;border-radius:4px';}}));
  await page.evaluate(async text=>{await import('data:text/javascript;base64,'+text)},source.toString('base64'));
  await page.evaluate(({states,lang,dict,dark})=>{
   // localize as Home Assistant's: the resource with its {placeholders} filled, '' for an unknown key.
   const localize=(key,values={})=>(dict[key]||'').replace(/\{(\w+)\}/g,(all,k)=>k in values?values[k]:all);
   window.events=[];window.hass={language:lang,locale:{language:lang,time_zone:'local'},themes:{darkMode:dark},states,localize,
    formatEntityState:st=>st.state==='unavailable'?({en:'Unavailable',nl:'Niet beschikbaar',pl:'Niedostępny'})[lang]:dict['component.open_thermostat.entity.sensor.room_reason.state.'+st.state]||st.state};
   for(const id of [...Object.keys(states),'sensor.gone_reason']){
    const card=document.createElement('openthermostat-room-status');card.dataset.room=id.split('.')[1].replace('_reason','');
    card.setConfig({entity:id,name:card.dataset.room[0].toUpperCase()+card.dataset.room.slice(1)});
    card.addEventListener('hass-more-info',e=>events.push(e.detail.entityId));
    document.querySelector('main').append(card);card.hass=hass;
   }
  },{states:STATES,lang,dict:resources(lang),dark:theme==='dark'});
  const words=WORDS[lang],card=room=>page.locator(`openthermostat-room-status[data-room="${room}"]`),why=room=>card(room).locator('.why span').innerText();
  assert.equal(await why('living'),words.living);assert.match(await why('kitchen'),words.kitchen);
  assert.equal(await why('bedroom'),words.bedroom);assert.equal(await why('study'),words.study);assert.match(await why('hall'),words.hall);
  assert.deepEqual(await page.locator('.why').evaluateAll(n=>n.map(x=>x.dataset.reason)),['heating','window_open','room_away','off','holiday']);
  // Temperature against target; an off room shows only what it measures (nothing here).
  assert.match(await card('living').locator('.temps').innerText(),lang==='en'?/Now\s+20\.6\s*°C\s+→\s+Target\s+22\.5\s*°C/:/20,6\s*°C[\s\S]*22,5\s*°C/);
  assert.equal(await card('study').locator('.target').count(),0);
  // Icons: presence (room or house) and the open contact by name; valves only for a room with valves.
  assert.equal(await card('living').locator('[data-presence]').getAttribute('aria-label'),words.home);
  assert.equal(await card('bedroom').locator('[data-presence]').getAttribute('data-presence'),'room_away');
  assert.match(await card('kitchen').locator('[data-window]').getAttribute('title'),/^Back door: /);
  assert.equal(await card('living').locator('[data-valves] > span').innerText(),words.valves);
  assert.equal(await page.locator('[data-valves]').count(),1);
  // Unavailable says so in Home Assistant's words; a missing entity names itself, never a blank card.
  assert.match(await card('attic').locator('.missing').innerText(),/Unavailable|Niet beschikbaar|Niedostępny/);
  assert.match(await card('gone').locator('.missing').innerText(),/sensor\.gone_reason/);
  // Tapping opens the room's history; an unrelated change in the house does not redraw the card.
  await card('kitchen').locator('ha-card').click();assert.deepEqual(await page.evaluate(()=>events),['sensor.kitchen_reason']);
  await page.evaluate(()=>{window.kept=document.querySelector('[data-room=living]').shadowRoot.querySelector('.why');
   const next={...hass,states:{...hass.states,'light.x':{state:'on',attributes:{}}}};document.querySelectorAll('openthermostat-room-status').forEach(c=>c.hass=next);});
  assert.equal(await page.evaluate(()=>kept.isConnected),true);
  // Every card in the viewer's language: no English label or icon text in a Dutch or Polish dashboard.
  const shown=await page.locator('openthermostat-room-status').evaluateAll(cards=>cards.map(c=>[...c.shadowRoot.querySelectorAll('.label,.valves span,[aria-label]')]
   .map(n=>n.getAttribute('aria-label')||n.textContent)).flat());
  assert.equal(shown.filter(t=>t===words.home).length,1);
  if(lang!=='en')for(const english of ['Now','Target','Radiator valves open','Someone of this room is home','Nobody of this room is home','Someone is home','Window or door open'])
   assert(!shown.some(t=>t.startsWith(english)),lang+': '+english);
  // The icons carry their glyph (Home Assistant's ha-icon): presence, the open contact and each reason.
  assert.deepEqual(await page.locator('.icons ha-icon').evaluateAll(n=>n.map(x=>x.getAttribute('icon'))),
   ['mdi:account-check','mdi:home-account','mdi:window-open-variant','mdi:account-off-outline']);
  assert.equal(await page.locator('.why ha-icon:not([icon=""])').count(),5);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(out,`ROOM-STATUS-CARD-${lang}-${width}-${theme}.png`),fullPage:true});
  // Without the integration's words (an older Home Assistant cache): the state's own translation, no placeholders.
  await page.evaluate(()=>{const c=document.querySelector('[data-room=bedroom]');c.hass={...hass,localize:()=>'',themes:{darkMode:!hass.themes.darkMode}};});
  assert.doesNotMatch(await why('bedroom'),/\{|undefined/);
  assert.deepEqual(errors,[]);results.push({language:lang,width,theme,status:'PASS'});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({scope:'shipped_card_fixture_hass_no_ha',results},null,2)+'\n');
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
