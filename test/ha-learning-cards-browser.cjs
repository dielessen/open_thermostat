// The Learning view's two cards (E32 rc.5, frontend/heating-curve-card.js) with the integration's real translations and
// a fixture hass; no HA or device. The heating curve: the standard line dashed, the learned one solid with the gain
// between them, "Now" and the hard-frost point labelled, a crosshair by pointer and keyboard, the values as a table, one
// line of plain language; what the E32 knows: a ring with the percentage and what it still learns. English, Dutch and
// Polish; light and dark (each mode its own validated colours); desktop, phone and a narrow phone. Screenshots go to the
// evidence directory for the visual check.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),component=path.join(root,'ha/config/custom_components/open_thermostat');
const source=fs.readFileSync(path.join(component,'frontend/heating-curve-card.js'));
const out=path.resolve(process.env.OPENTHERMOSTAT_LEARNING_CARDS_EVIDENCE||path.join(root,'out/ha-learning-cards-20261104'));
function resources(lang){
 const flat={},walk=(value,prefix)=>{for(const [k,v] of Object.entries(value))typeof v==='object'?walk(v,prefix+k+'.'):flat[prefix+k]=v;};
 walk(JSON.parse(fs.readFileSync(path.join(component,'translations',lang+'.json'))).entity,'component.open_thermostat.entity.');
 return flat;
}
// A radiator house (standard slope 1.167 from 55 °C at −10 °C) that learned 0.9; 6.5 °C outside, the curve asks 35 °C.
const curve=(extra={},state='35')=>({state,attributes:{state:'applied',slope:0.9,slope_source:'learned',design_flow_c:55,standard_slope:1.167,
 room_c:21,outdoor_c:6.5,minimum_flow_c:28,maximum_flow_c:60,friendly_name:'Water temperature by weather compensation',...extra}});
const MISSING={en:['It still has to see how fast Slaapkamer warms up.','It still has to check whether Slaapkamer is warm on time.',
 'It is still listening to how your boiler holds its temperature.'],nl:['Hij moet nog zien hoe snel Slaapkamer opwarmt.',
 'Hij moet nog nagaan of Slaapkamer op tijd warm is.','Hij luistert nog hoe je ketel zijn temperatuur vasthoudt.'],
 pl:['Musi jeszcze zobaczyć, jak szybko nagrzewa się pomieszczenie Slaapkamer.','Musi jeszcze sprawdzić, czy pomieszczenie Slaapkamer jest ciepłe na czas.',
 'Wciąż wsłuchuje się, jak Twój kocioł utrzymuje swoją temperaturę.']};
const states=lang=>({'sensor.curve':curve(),'sensor.curve_standard':curve({slope_source:'design',slope:1.167}),'sensor.curve_off':curve({state:'advice'}),
 'sensor.curve_waiting':{state:'unknown',attributes:{}},'sensor.knowledge':{state:'70',attributes:{missing:MISSING[lang],more:2}},
 'sensor.knowledge_full':{state:'100',attributes:{missing:[],more:0}},'sensor.knowledge_unknown':{state:'unknown',attributes:{}}});
const WORDS={
 en:{title:'Water temperature by outdoor temperature',legend:['Standard','Learned for your house','Now'],now:'6.5 °C outside → 35 °C',
  frost:['At −10 °C: 49 °C','8 °C cooler than standard'],standardFrost:'At −10 °C: 57 °C',caption:/^The colder it is outside, the warmer the water\./,
  off:'Weather compensation is off; the lines show what it would ask.',waiting:'The E32 has not reported its weather compensation yet.',
  tip:['At 6.5 °C outside','34 °C','Learned for your house','38 °C','Standard'],next:'At 7.5 °C outside',values:'Show the values',
  ring:'The E32 knows your house: 70 %',knows:'The E32 knows your house',more:'And 2 more.',missing:'Still to learn',
  done:'It has learned everything it needs; it keeps checking as the seasons change.',unknown:'The E32 has not reported what it knows yet.'},
 nl:{title:'Watertemperatuur bij buitentemperatuur',legend:['Standaard','Geleerd voor je huis','Nu'],now:'6,5 °C buiten → 35 °C',
  frost:['Bij −10 °C: 49 °C','8 °C koeler dan standaard'],standardFrost:'Bij −10 °C: 57 °C',caption:/^Hoe kouder het buiten is, hoe warmer het water\./,
  off:'De weerafhankelijke regeling staat uit; de lijnen tonen wat hij zou vragen.',waiting:'De E32 heeft zijn weerafhankelijke regeling nog niet gemeld.',
  tip:['Bij 6,5 °C buiten','34 °C','Geleerd voor je huis','38 °C','Standaard'],next:'Bij 7,5 °C buiten',values:'Toon de waarden',
  ring:'De E32 kent je huis: 70 %',knows:'De E32 kent je huis',more:'En nog 2.',missing:'Nog te leren',
  done:'Hij heeft alles geleerd wat hij nodig heeft; hij blijft het controleren als de seizoenen wisselen.',unknown:'De E32 heeft nog niet gemeld wat hij weet.'},
 pl:{title:'Temperatura wody a temperatura zewnętrzna',legend:['Standardowa','Wyuczona dla Twojego domu','Teraz'],now:'6,5 °C na zewnątrz → 35 °C',
  frost:['Przy −10 °C: 49 °C','o 8 °C chłodniej niż standardowo'],standardFrost:'Przy −10 °C: 57 °C',caption:/^Im zimniej na zewnątrz, tym cieplejsza woda\./,
  off:'Kompensacja pogodowa jest wyłączona; linie pokazują, czego by żądała.',waiting:'E32 jeszcze nie przekazał danych kompensacji pogodowej.',
  tip:['Przy 6,5 °C na zewnątrz','34 °C','Wyuczona dla Twojego domu','38 °C','Standardowa'],next:'Przy 7,5 °C na zewnątrz',values:'Pokaż wartości',
  ring:'E32 zna Twój dom w 70 %',knows:'E32 zna Twój dom',more:'I jeszcze 2.',missing:'Jeszcze do nauczenia',
  done:'Nauczył się wszystkiego, czego potrzebuje; sprawdza to dalej wraz ze zmianą pór roku.',unknown:'E32 jeszcze nie przekazał, co wie.'}};
// The rows of the table view: outdoor every 5 °C, the standard and the learned line within the plan's 28..60 °C
// (the standard line would ask 63 °C at −15 °C: the plan's highest water temperature holds it at 60).
const TABLE=[[-15,60,53],[-10,57,49],[-5,51,44],[0,46,40],[5,40,35],[10,34,31],[15,28,28],[20,28,28]];
const THEMES={light:'--primary-text-color:#212121;--secondary-text-color:#6b6b6b;--card-background-color:#fff;--divider-color:rgba(0,0,0,.12);--primary-color:#03a9f4;background:#fafafa',
 dark:'--primary-text-color:#e1e1e1;--secondary-text-color:#9b9b9b;--card-background-color:#1c1c1c;--divider-color:rgba(225,225,225,.12);--primary-color:#03a9f4;background:#111'};
const LINE={light:'rgb(0, 135, 111)',dark:'rgb(35, 156, 138)'},NOW={light:'rgb(181, 96, 12)',dark:'rgb(201, 122, 44)'};
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const [lang,width,theme] of [['en',1280,'light'],['en',390,'dark'],['nl',390,'light'],['nl',1280,'dark'],['pl',320,'light'],['pl',390,'dark']]){
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const n=lang==='en'?String:v=>String(v).replace('.',','),words=WORDS[lang];
  await page.setContent(`<style>body{margin:0;padding:16px;font:14px Roboto,Arial;${THEMES[theme]}}main{display:grid;gap:12px;max-width:560px}
   ha-card{display:block;background:var(--card-background-color);border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.2)}</style><main></main>`);
  // ha-card is Home Assistant's own element: a stand-in with the card surface, so the screenshots look like a dashboard.
  await page.evaluate(()=>customElements.define('ha-card',class extends HTMLElement{constructor(){super();this.attachShadow({mode:'open'}).innerHTML=
   '<style>:host{display:block;background:var(--card-background-color);border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.2)}</style><slot></slot>';}}));
  await page.evaluate(async text=>{await import('data:text/javascript;base64,'+text)},source.toString('base64'));
  await page.evaluate(({states,lang,dict,dark})=>{
   const localize=(key,values={})=>(dict[key]||'').replace(/\{(\w+)\}/g,(all,k)=>k in values?values[k]:all);
   window.hass={language:lang,locale:{language:lang},themes:{darkMode:dark},states,localize};
   for(const [id,type] of [['sensor.knowledge','knowledge'],['sensor.knowledge_full','knowledge'],['sensor.knowledge_unknown','knowledge'],
    ['sensor.curve','heating-curve'],['sensor.curve_standard','heating-curve'],['sensor.curve_off','heating-curve'],['sensor.curve_waiting','heating-curve'],
    ['sensor.gone','heating-curve']]){
    const card=document.createElement('openthermostat-'+type);card.dataset.id=id.split('.')[1];card.setConfig({entity:id});
    document.querySelector('main').append(card);card.hass=hass;
   }
  },{states:states(lang),lang,dict:resources(lang),dark:theme==='dark'});
  const card=id=>page.locator(`[data-id="${id}"]`),svg=card('curve').locator('svg[role=img]');
  await svg.locator('[data-point=now]').waitFor();
  // The heating curve: title, legend (line keys), the two lines, the band between them, the points and their labels.
  assert.equal(await card('curve').locator('h2').innerText(),words.title);
  assert.deepEqual(await card('curve').locator('.legend li').allInnerTexts(),words.legend);
  assert.equal(await svg.locator('path[data-line=standard]').count(),1);assert.equal(await svg.locator('path[data-line=learned]').count(),1);
  assert.equal(await svg.locator('path.band').count(),1);
  assert.equal(await svg.locator('[data-label=now]').textContent(),words.now);
  assert.deepEqual(await svg.locator('[data-label=frost] tspan').allTextContents(),words.frost);
  assert.match(await card('curve').locator('.caption').innerText(),words.caption);
  // Marks 2 px, the standard dashed and the learned solid; markers ringed in the card colour; text in text colours.
  const style=await svg.evaluate(s=>{const g=(q,p)=>getComputedStyle(s.querySelector(q))[p];
   return {learned:g('path[data-line=learned]','stroke'),width:g('path[data-line=learned]','strokeWidth'),dash:g('path[data-line=standard]','strokeDasharray'),
    solid:g('path[data-line=learned]','strokeDasharray'),now:g('[data-point=now]','fill'),ring:g('[data-point=now]','strokeWidth'),
    label:g('[data-label=now]','fill'),r:s.querySelector('[data-point=now]').getAttribute('r')};});
  assert.equal(style.learned,LINE[theme]);assert.equal(style.now,NOW[theme]);assert.equal(style.width,'2px');assert.equal(style.ring,'2px');
  assert.notEqual(style.dash,'none');assert.equal(style.solid,'none');assert(Number(style.r)>=4,'markers at least 8 px');
  assert.equal(style.label,theme==='dark'?'rgb(225, 225, 225)':'rgb(33, 33, 33)','labels wear the text colour, not the series colour');
  // The table view: every 5 °C, both lines, within the plan's water temperature limits.
  await card('curve').locator('summary').click();
  const rows=await card('curve').locator('table tr').evaluateAll(r=>r.map(x=>[...x.children].map(c=>c.textContent)));
  assert.deepEqual(rows[0],[{en:'Outside',nl:'Buiten',pl:'Na zewnątrz'}[lang],...words.legend.slice(0,2)]);
  assert.deepEqual(rows.slice(1),TABLE.map(([o,s,l])=>[String(o).replace('-','−')+' °C',s+' °C',l+' °C']));
  assert.equal(await card('curve').locator('summary').innerText(),words.values);
  // The crosshair: focus shows "now", the arrow keys step a degree; a pointer anywhere along the x axis reads the curve.
  await svg.focus();
  const tip=card('curve').locator('.tip');await tip.waitFor();
  assert.deepEqual((await tip.innerText()).split('\n').map(s=>s.trim()).filter(Boolean),words.tip);
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction(([next])=>document.querySelector('[data-id=curve]').shadowRoot.querySelector('.tip-head').textContent===next,[words.next]);
  await svg.evaluate(s=>s.blur());await tip.waitFor({state:'hidden'});
  const box=await svg.boundingBox();
  await page.mouse.move(box.x+box.width*0.35,box.y+box.height*0.45);await tip.waitFor();
  assert.match(await tip.locator('.tip-head').innerText(),/−?\d/);
  await page.mouse.move(box.x+box.width/2,box.y+box.height+80);await tip.waitFor({state:'hidden'});
  // Only the standard line before the house is learned; weather compensation off says so; nothing reported yet says that.
  const standard=card('curve_standard').locator('svg[role=img]');await standard.locator('[data-point=frost]').waitFor();
  assert.equal(await standard.locator('path[data-line=learned]').count(),0);assert.equal(await standard.locator('path.band').count(),0);
  assert.deepEqual(await standard.locator('[data-label=frost] tspan').allTextContents(),[words.standardFrost]);
  assert.deepEqual(await card('curve_standard').locator('.legend li').allInnerTexts(),[words.legend[0],words.legend[2]]);
  assert.equal(await card('curve_off').locator('.note').innerText(),words.off);
  assert.equal(await card('curve_waiting').locator('p').innerText(),words.waiting);
  assert.match(await card('gone').locator('p').innerText(),/sensor\.gone/);
  // What the E32 knows: the ring with the percentage, what it still learns, and the last line counting the rest.
  const ring=card('knowledge').locator('svg.ring');
  assert.equal(await ring.getAttribute('aria-label'),words.ring);assert.equal(await ring.locator('text').textContent(),'70 %');
  assert.equal(await card('knowledge').locator('h2').innerText(),words.knows);assert.equal(await card('knowledge').locator('h3').innerText(),words.missing);
  assert.deepEqual(await card('knowledge').locator('li').allInnerTexts(),[...MISSING[lang],words.more]);
  const arc=await ring.locator('.fill').evaluate(c=>c.getAttribute('stroke-dasharray').split(' ').map(Number));
  assert(Math.abs(arc[0]/arc[1]-0.7)<0.001,'the ring is filled 70 %');
  assert.equal(await card('knowledge_full').locator('.done').innerText(),words.done);assert.equal(await card('knowledge_full').locator('li').count(),0);
  assert.equal(await card('knowledge_unknown').locator('p').innerText(),words.unknown);assert.equal(await card('knowledge_unknown').locator('svg').count(),0);
  // An unrelated change in the house does not redraw; a new state does.
  await page.evaluate(()=>{window.kept=document.querySelector('[data-id=curve]').shadowRoot.querySelector('svg');
   const next={...hass,states:{...hass.states,'light.x':{state:'on',attributes:{}}}};document.querySelectorAll('main > *').forEach(c=>c.hass=next);});
  assert.equal(await page.evaluate(()=>document.querySelector('[data-id=curve]').shadowRoot.querySelector('svg')===kept),true);
  // Phone width first: nothing scrolls sideways.
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  await page.screenshot({path:path.join(out,`${lang}-${width}-${theme}.png`),fullPage:true});
  assert.deepEqual(errors,[]);
  results.push({lang,width,theme,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify({results,screenshots:out}));
})().catch(error=>{console.error(error);process.exitCode=1;});
