// Shipped HA room status card (1.1; rc.5 in the form of the owner's sketch) with the integration's real translations and
// a fixture hass; no HA or device. Per room: a round disc in the colour of what the room does, its name, why in one muted
// line, the temperature now large on the right (spoken with its target), and the chips: the reason in a word in the
// disc's colour, "Smart warm-up on" while the switch is on, the house (its mode, else who is home; never "Away" twice)
// and the radiator valves. HA 1.0.0rc7 (the sketch): after the sentence the week program's step from the Reason sensor's
// "program" attribute ("Comfort until 22:30, then Night 18.0 °C"; a point with its own temperature by its temperature),
// nothing without a next step or without the attribute. English, Dutch and Polish; light and dark; desktop, phone and a
// narrow phone, no sideways scroll; every chip and line readable (contrast at least 4.5:1). Screenshots go to the
// evidence directory.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),component=path.join(root,'ha/config/custom_components/open_thermostat');
const source=fs.readFileSync(path.join(component,'frontend/room-status-card.js'));
const out=path.resolve(process.env.OPENTHERMOSTAT_ROOM_STATUS_CARD_EVIDENCE||path.join(root,'out/ha-room-status-card-20261104'));
const translations=lang=>JSON.parse(fs.readFileSync(path.join(component,'translations',lang+'.json')));
// What Home Assistant's frontend loads for the "entity" category: flattened component.<domain>.entity... keys.
function resources(lang){
 const flat={},walk=(value,prefix)=>{for(const [k,v] of Object.entries(value))typeof v==='object'?walk(v,prefix+k+'.'):flat[prefix+k]=v;};
 walk(translations(lang).entity,'component.open_thermostat.entity.');
 return flat;
}
const since=new Date(Date.now()-25*60000).toISOString(),until=new Date(Date.now()+3*86400000).toISOString();
// The week program's next step: in two hours (today, or with its weekday after midnight), in three days.
const soon=new Date(Date.now()+2*3600000).toISOString(),later=new Date(Date.now()+3*86400000).toISOString();
const reason=(state,line,values,extra)=>({state,attributes:{room_id:'living',line,values,temperature:20.6,setpoint:22.5,presence:null,window:null,
 valve_position:null,valve_problem:null,friendly_name:'Living Reason',...extra}});
const STATES={
 'sensor.living_reason':reason('heating','heating',{temperature:20.6,target:22.5},{presence:'room_home',valve_position:40,valve_problem:false,
  program:{level:'comfort',target:22.5,next_at:soon,next_level:'night',next_target:18}}),
 'sensor.kitchen_reason':reason('window_open','window_open_contact',{contact:'Back door',since},{setpoint:8,presence:'house_home',window:'open'}),
 'sensor.bedroom_reason':reason('room_away','room_away',{target:18},{presence:'room_away',program:null}),
 'sensor.study_reason':reason('off','off',{},{temperature:null,setpoint:null}),
 'sensor.hall_reason':reason('holiday','holiday',{until,target:15}),
 'sensor.warm_reason':reason('warm_enough','warm_enough',{temperature:21.2,target:21},{temperature:21.2,setpoint:21,presence:'house_away',
  valve_position:5,valve_problem:true,program:{level:null,target:21.5,next_at:later,next_level:'eco',next_target:19}}),
 // A program that changes nothing in the coming week: the level now, no step on the card.
 'sensor.even_reason':reason('warm_enough','warm_enough',{temperature:20.1,target:20},{temperature:20.1,setpoint:20,
  program:{level:'comfort',target:20,next_at:null,next_level:null,next_target:null}}),
 'sensor.attic_reason':{state:'unavailable',attributes:{friendly_name:'Attic Reason'}},
 'switch.smart_warm_up':{state:'on',attributes:{}},'select.house_mode':{state:'auto',attributes:{}},
};
const ROOMS=['living','kitchen','bedroom','study','hall','warm','even','attic','gone'];
// A figure and its unit stay together: a no-break space before °C and % (the regular expressions' \s takes it too).
const NB=s=>s.replace(/ (°C|%)/g,'\u00a0$1');
const WORDS={
 en:{living:NB('Heating: 20.6 → 22.5 °C'),kitchen:/^Paused: Back door open since (\S+ )?\d{1,2}:\d\d( [AP]M)?$/,bedroom:NB('Away: nobody of this room is home (18 °C)'),
  study:'Frost protection only (room off)',hall:/^Holiday until \S+ \d{1,2}:\d\d( [AP]M)? \(15\s°C\)$/,now:'20.6',spoken:'Now 20.6 °C, Target 22.5 °C',
  valves:NB('Radiator valves open: 40 %'),home:'Someone of this room is home',
  step:/^Comfort until (\S+\s)?\d{1,2}:\d\d(\s[AP]M)?, then Night 18\.0\u00a0°C$/,own:/^21\.5\u00a0°C until \S+\s\d{1,2}:\d\d(\s[AP]M)?, then Eco 19\.0\u00a0°C$/},
 nl:{living:NB('Verwarmt: 20,6 → 22,5 °C'),kitchen:/^Gepauzeerd: Back door open sinds (\S+ )?\d\d:\d\d$/,bedroom:NB('Afwezig: niemand van deze ruimte is thuis (18 °C)'),
  study:'Alleen vorstbeveiliging (ruimte uit)',hall:/^Vakantie tot \S+ \d\d:\d\d \(15\s°C\)$/,now:'20,6',spoken:'Nu 20,6 °C, Gewenst 22,5 °C',
  valves:NB('Radiatorkranen open: 40 %'),home:'Iemand van deze ruimte is thuis',
  step:/^Comfort tot (\S+\s)?\d\d:\d\d, daarna Nacht 18,0\u00a0°C$/,own:/^21,5\u00a0°C tot \S+\s\d\d:\d\d, daarna Eco 19,0\u00a0°C$/},
 pl:{living:NB('Grzeje: 20,6 → 22,5 °C'),kitchen:/^Wstrzymane: Back door otwarte od (\S+ )?\d\d:\d\d$/,bedroom:NB('Nieobecność: nikogo z tego pomieszczenia nie ma w domu (18 °C)'),
  study:'Tylko ochrona przed mrozem (pomieszczenie wyłączone)',hall:/^Urlop do \S+ \d\d:\d\d \(15\s°C\)$/,now:'20,6',spoken:'Teraz 20,6 °C, Cel 22,5 °C',
  valves:NB('Otwarcie zaworów grzejnikowych: 40 %'),home:'Ktoś z tego pomieszczenia jest w domu',
  step:/^Komfort do (\S+\s)?\d\d:\d\d, potem Noc 18,0\u00a0°C$/,own:/^21,5\u00a0°C do \S+\s\d\d:\d\d, potem Eko 19,0\u00a0°C$/},
};
// Home Assistant's default theme colours (light and dark) and its state colours.
const THEMES={light:'--primary-text-color:#212121;--secondary-text-color:#727272;--card-background-color:#fff;--secondary-background-color:#f5f5f5;'+
  '--state-climate-heat-color:#ff8100;--info-color:#039be5;--error-color:#db4437;--warning-color:#ffa600;--success-color:#43a047;'+
  '--state-climate-cool-color:#2b9af9;--disabled-text-color:#bdbdbd;--primary-color:#03a9f4;background:#fafafa',
 dark:'--primary-text-color:#e1e1e1;--secondary-text-color:#9b9b9b;--card-background-color:#1c1c1c;--secondary-background-color:#282828;'+
  '--state-climate-heat-color:#ff8100;--info-color:#039be5;--error-color:#db4437;--warning-color:#ffa600;--success-color:#43a047;'+
  '--state-climate-cool-color:#2b9af9;--disabled-text-color:#6f6f6f;--primary-color:#03a9f4;background:#111'};
// WCAG contrast of two "rgb(…)"/"color(srgb …)" colours (the second opaque).
const channels=c=>{const m=c.match(/rgba?\(([^)]+)\)/);if(m)return m[1].split(',').map(Number);
 const s=c.match(/color\(srgb ([^)]+)\)/);if(s)return s[1].split(/\s+/).map((v,i)=>i<3?Number(v)*255:Number(v));throw new Error('colour '+c);};
const luminance=([r,g,b])=>{const f=v=>{v/=255;return v<=0.03928?v/12.92:((v+0.055)/1.055)**2.4;};return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b);};
const contrast=(fg,bg)=>{const [a,b]=[luminance(channels(fg)),luminance(channels(bg))].sort((x,y)=>y-x);return (a+0.05)/(b+0.05);};
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const [lang,width,theme] of [['en',1280,'light'],['en',1280,'dark'],['en',390,'light'],['en',390,'dark'],['nl',1280,'light'],['nl',1280,'dark'],
  ['nl',390,'light'],['nl',390,'dark'],['pl',390,'dark'],['pl',320,'light']]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent(`<style>body{margin:0;padding:${width<500?8:16}px;font:14px Roboto,Arial,sans-serif;${THEMES[theme]}}
   main{display:grid;gap:12px;max-width:420px}</style><main></main>`);
  // ha-card is Home Assistant's own element (a surface with rounded corners); a plain block stands in for it here.
  await page.evaluate(()=>customElements.define('ha-card',class extends HTMLElement{connectedCallback(){
   Object.assign(this.style,{background:'var(--card-background-color)',borderRadius:'12px',boxShadow:'0 1px 3px rgba(0,0,0,.2)'});}}));
  // ha-icon is Home Assistant's own element too (it draws the mdi glyph); this stand-in shows a visible
  // marker per icon, so the screenshots show where each glyph goes and which one it is.
  await page.evaluate(()=>customElements.define('ha-icon',class extends HTMLElement{connectedCallback(){
   const name=(this.getAttribute('icon')||'').replace('mdi:','');this.title=name;
   this.textContent=name.split('-').map(w=>w[0]).join('').slice(0,2).toUpperCase();
   this.style.cssText='display:inline-flex;align-items:center;justify-content:center;width:var(--mdc-icon-size,24px);height:var(--mdc-icon-size,24px);font:700 9px Arial;border:1.5px solid currentColor;border-radius:4px;box-sizing:border-box';}}));
  await page.evaluate(async text=>{await import('data:text/javascript;base64,'+text)},source.toString('base64'));
  await page.evaluate(({states,lang,dict,dark,rooms})=>{
   // localize as Home Assistant's: the resource with its {placeholders} filled, '' for an unknown key.
   const localize=(key,values={})=>(dict[key]||'').replace(/\{(\w+)\}/g,(all,k)=>k in values?values[k]:all);
   window.events=[];window.hass={language:lang,locale:{language:lang,time_zone:'local'},themes:{darkMode:dark},states,localize,
    formatEntityState:st=>st.state==='unavailable'?({en:'Unavailable',nl:'Niet beschikbaar',pl:'Niedostępny'})[lang]:dict['component.open_thermostat.entity.sensor.room_reason.state.'+st.state]||st.state};
   for(const room of rooms){
    const card=document.createElement('openthermostat-room-status');card.dataset.room=room;
    card.setConfig({entity:`sensor.${room}_reason`,name:room[0].toUpperCase()+room.slice(1),smart:'switch.smart_warm_up',mode:'select.house_mode'});
    card.addEventListener('hass-more-info',e=>events.push(e.detail.entityId));
    document.querySelector('main').append(card);card.hass=hass;
   }
  },{states:STATES,lang,dict:resources(lang),dark:theme==='dark',rooms:ROOMS});
  const words=WORDS[lang],texts=translations(lang).entity.sensor.room_reason.state_attributes,chipWord=r=>texts.chip.state[r],card=texts.card.state;
  const room=name=>page.locator(`openthermostat-room-status[data-room="${name}"]`),why=name=>room(name).locator('.why').evaluate(p=>p.firstChild.textContent);
  const chips=name=>room(name).locator('.chip').evaluateAll(n=>n.map(c=>[c.dataset.chip,c.querySelector(':scope>span').textContent]));
  // The reason sentence, as before, in one muted line under the name.
  assert.equal(await why('living'),words.living);assert.match(await why('kitchen'),words.kitchen);
  assert.equal(await why('bedroom'),words.bedroom);assert.equal(await why('study'),words.study);assert.match(await why('hall'),words.hall);
  assert.deepEqual(await page.locator('.why').evaluateAll(n=>n.map(x=>x.dataset.reason)),
   ['heating','window_open','room_away','off','holiday','warm_enough','warm_enough']);
  assert.deepEqual(await page.locator('.name').allInnerTexts(),['Living','Kitchen','Bedroom','Study','Hall','Warm','Even','Attic','Gone']);
  // The week program's step after the sentence and a middle dot, in the same muted line (the sketch); a point with its
  // own temperature by that temperature; nothing without a next step or without the attribute.
  assert.match(await room('living').locator('[data-step]').innerText(),words.step);
  assert.equal(await room('living').locator('.why').innerText(),words.living+' · '+await room('living').locator('[data-step]').innerText());
  assert.match(await room('warm').locator('[data-step]').innerText(),words.own);
  for(const name of ['kitchen','bedroom','study','hall','even'])assert.equal(await room(name).locator('[data-step]').count(),0,name);
  const stepLook=await room('living').evaluate(c=>{const s=c.shadowRoot,g=q=>getComputedStyle(s.querySelector(q));
   return [g('.step').color,g('.why').color,g('.step').fontSize];});
  assert.deepEqual(stepLook,[stepLook[1],stepLook[1],'13px'],'the step in the sentence\'s muted 13 px');
  // Now, large, with a small degree sign; spoken with its label and the target. An off room without a reading: a dash.
  assert.equal(await room('living').locator('.now').innerText(),words.now+'°');
  assert.equal(await room('living').locator('.now').getAttribute('aria-label'),words.spoken);
  assert.equal(await room('study').locator('.now').innerText(),'–');assert.equal(await room('study').locator('.now').getAttribute('aria-label'),null);
  // The chips: the reason in a word, Smart warm-up while its switch is on (not for a room that is off), the house (who is
  // home while the house mode is automatic; not when the reason says "away" already) and the valves.
  const smart=['smart',card.smart_on];
  assert.deepEqual(await chips('living'),[['state',chipWord('heating')],smart,['house',card.home],['valves',words.valves]]);
  assert.deepEqual(await chips('kitchen'),[['state',chipWord('window_open')],smart,['house',card.home]]);
  assert.deepEqual(await chips('bedroom'),[['state',chipWord('room_away')],smart]);
  assert.deepEqual(await chips('study'),[['state',chipWord('off')]]);
  assert.deepEqual(await chips('hall'),[['state',chipWord('holiday')],smart]);
  assert.deepEqual((await chips('warm')).map(c=>c[0]),['state','smart','house','valves']);
  assert.equal((await chips('warm'))[2][1],card.away);
  if(lang==='nl')assert.deepEqual((await chips('living')).slice(0,3).map(c=>c[1]),['Verwarmt','Slim opwarmen aan','Thuis']);  // the sketch's words
  if(lang==='nl')assert.equal(chipWord('warm_enough'),'Op temperatuur');
  // Who is home and an open contact are in the chips' tooltips; the valves with their glyph.
  assert.equal(await room('living').locator('[data-chip=house]').getAttribute('title'),words.home);
  assert.match(await room('kitchen').locator('[data-chip=state]').getAttribute('title'),/^Back door: /);
  assert.equal(await room('kitchen').locator('[data-window]').getAttribute('data-window'),'open');
  assert.deepEqual(await page.locator('[data-valves] ha-icon').evaluateAll(n=>n.map(x=>x.getAttribute('icon'))),['mdi:valve','mdi:valve-closed']);
  // The disc: round, 44 px, the house glyph in the colour of what the room does, on a tint of it.
  const look=await page.evaluate(()=>{const get=r=>document.querySelector(`[data-room=${r}]`).shadowRoot;
   const disc=r=>getComputedStyle(get(r).querySelector('.disc')),state=r=>getComputedStyle(get(r).querySelector('[data-chip=state]'));
   const box=get('living').querySelector('.disc').getBoundingClientRect();
   return {size:[box.width,box.height],radius:disc('living').borderRadius,heat:disc('living').color,ok:disc('warm').color,
    away:disc('bedroom').color,warn:disc('kitchen').color,icon:get('living').querySelector('.disc ha-icon').getAttribute('icon'),
    heatText:state('living').color,smart:getComputedStyle(get('living').querySelector('[data-chip=smart]')).color};});
  assert.deepEqual(look.size,[44,44]);assert.equal(look.radius,'50%');assert.equal(look.icon,'mdi:home-outline');
  assert.deepEqual([look.heat,look.ok,look.away,look.warn],['rgb(255, 129, 0)','rgb(67, 160, 71)','rgb(43, 154, 249)','rgb(255, 166, 0)']);
  assert.notEqual(look.heatText,look.smart);
  // Every chip and line readable in this theme (WCAG AA, 4.5:1): a chip's words on its tint, the lines on the card.
  const pairs=await page.evaluate(()=>[...document.querySelectorAll('openthermostat-room-status')].flatMap(c=>{
   const s=c.shadowRoot,surface=getComputedStyle(s.querySelector('ha-card')).backgroundColor;
   return [...[...s.querySelectorAll('.chip')].map(x=>[c.dataset.room+' '+x.dataset.chip,getComputedStyle(x).color,getComputedStyle(x).backgroundColor]),
    ...[...s.querySelectorAll('.why,.name,.now,.missing')].map(x=>[c.dataset.room+' '+x.className,getComputedStyle(x).color,surface])];}));
  assert.equal(pairs.length,18+25,'the chips and lines of every card');
  for(const [name,fg,bg] of pairs)assert(contrast(fg,bg)>=4.5,`${lang} ${theme} ${name}: ${fg} on ${bg}: ${contrast(fg,bg).toFixed(2)}`);
  // The layout: the disc, the words and the temperature in one row; the chips under them; nothing wider than the screen.
  const row=await room('living').evaluate(c=>{const s=c.shadowRoot,r=q=>s.querySelector(q).getBoundingClientRect();
   return {disc:r('.disc'),text:r('.text'),now:r('.now'),chips:r('.chips'),card:r('ha-card')};});
  assert(row.disc.right<=row.text.left&&row.text.right<=row.now.left,'disc, words and temperature side by side');
  assert(row.chips.top>=row.disc.bottom&&row.chips.left>=row.card.left&&row.chips.right<=row.card.right+0.5,'the chips under them');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  // Unavailable says so in Home Assistant's words; a missing entity names itself, never a blank card.
  assert.match(await room('attic').locator('.missing').innerText(),/Unavailable|Niet beschikbaar|Niedostępny/);
  assert.match(await room('gone').locator('.missing').innerText(),/sensor\.gone_reason/);
  assert.equal(await room('attic').locator('.chip').count(),0);
  // Every card in the viewer's language: no English chip, tooltip or label in a Dutch or Polish dashboard.
  const shown=await page.locator('openthermostat-room-status').evaluateAll(cards=>cards.map(c=>[...c.shadowRoot.querySelectorAll('.chip,[aria-label],[title]')]
   .map(n=>n.getAttribute('aria-label')||n.getAttribute('title')||n.textContent)).flat());
  if(lang!=='en')for(const english of ['Now ','Target','Radiator valves open','Someone of this room is home','Nobody of this room is home','Smart warm-up',
   'Heating','At temperature','At home','Away','Holiday','Paused','Off'])
   assert(!shown.some(t=>t.startsWith(english)),lang+': '+english);
  await page.screenshot({path:path.join(out,`ROOM-STATUS-CARD-${lang}-${width}-${theme}.png`),fullPage:true});
  // Tapping or Enter opens the room's history; an unrelated change in the house does not redraw the card.
  await room('kitchen').locator('ha-card').click();await room('hall').locator('ha-card').press('Enter');
  assert.deepEqual(await page.evaluate(()=>events),['sensor.kitchen_reason','sensor.hall_reason']);
  await page.evaluate(()=>{window.kept=document.querySelector('[data-room=living]').shadowRoot.querySelector('.why');
   const next={...hass,states:{...hass.states,'light.x':{state:'on',attributes:{}}}};document.querySelectorAll('openthermostat-room-status').forEach(c=>c.hass=next);});
  assert.equal(await page.evaluate(()=>kept.isConnected),true);
  // Its own other entities do: Smart warm-up switched off, the house set to away or on holiday.
  const redraw=async(entity,state)=>page.evaluate(([entity,state])=>{window.hass={...hass,states:{...hass.states,[entity]:{state,attributes:{}}}};
   document.querySelectorAll('openthermostat-room-status').forEach(c=>c.hass=hass);},[entity,state]);
  await redraw('switch.smart_warm_up','off');
  assert.equal(await page.evaluate(()=>kept.isConnected),false);
  assert.deepEqual(await chips('living'),[['state',chipWord('heating')],['house',card.home],['valves',words.valves]]);
  await redraw('select.house_mode','away');assert.equal((await chips('living'))[1][1],card.away);
  await redraw('select.house_mode','holiday');assert.equal((await chips('living'))[1][1],card.holiday);
  assert.deepEqual((await chips('hall')).map(c=>c[0]),['state']);  // on holiday it says so once
  // Without the integration's words (an older Home Assistant cache): English last resorts, no placeholders.
  await page.evaluate(()=>{const c=document.querySelector('[data-room=bedroom]');c.hass={...hass,localize:()=>'',themes:{darkMode:!hass.themes.darkMode}};});
  assert.doesNotMatch(await why('bedroom'),/\{|undefined/);
  assert.deepEqual(await chips('bedroom'),[['state','Away'],['house','Holiday']]);  // the house is still on holiday
  await page.evaluate(()=>{const c=document.querySelector('[data-room=living]');c.hass={...hass,localize:()=>'',themes:{darkMode:!hass.themes.darkMode}};});
  assert.match(await room('living').locator('[data-step]').innerText(),/^Comfort until (\S+\s)?\d{1,2}:\d\d(\s[AP]M)?, then Night 18[.,]0\u00a0°C$/);
  assert.deepEqual(errors,[]);results.push({language:lang,width,theme,status:'PASS'});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({scope:'shipped_card_fixture_hass_no_ha',results},null,2)+'\n');
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
