// The generated OpenThermostat dashboard laid out like Home Assistant's sections view (12-column sections, tiles 6 wide),
// at phone and desktop width: every row of every section is full, nothing scrolls sideways, each section starts with its
// heading. Cards are wireframes (their type and name), the structure and the words are the generated config
// (test/fixtures/ha-dashboard-views.json, kept current by ha/tests_native/test_dashboard_layout.py). No HA, no device.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const config=JSON.parse(fs.readFileSync(path.join(root,'test/fixtures/ha-dashboard-views.json'),'utf8'));
const out=path.resolve(process.env.OPENTHERMOSTAT_DASHBOARD_VIEWS_EVIDENCE||path.join(root,'out/ha-dashboard-views-20261103'));
const HEIGHT={heading:40,tile:64,thermostat:300,'history-graph':200,'statistics-graph':200,markdown:90,entities:150,glance:90,button:56,
 'custom:openthermostat-room-status':150,'custom:openthermostat-e32-week':400};
const label=card=>card.heading||card.name||card.title||card.entity||(card.content||'').replace(/<[^>]+>|\{[%{#][^}]*[%}#]\}/g,' ').replace(/\s+/g,' ').trim().slice(0,70)||card.type;
const html=(view,hidden,width)=>{
 // Home Assistant fits as many section columns as the width allows (about 320 px each), up to max_columns.
 const columns=Math.max(1,Math.min(view.max_columns||1,Math.floor((width-32)/320)));
 const sections=(view.sections||[]).map(section=>`<section>${section.cards.filter(c=>!(hidden&&c.visibility)).map(card=>{
  const span=(card.grid_options&&card.grid_options.columns)||(['tile','button'].includes(card.type)?6:12);
  return `<div class="card ${card.type.replace(/[^a-z-]/g,'')}" data-span="${span}" style="grid-column:span ${span};min-height:${HEIGHT[card.type]||90}px">`+
   `<small>${card.type.replace('custom:openthermostat-','')}</small><b>${String(label(card)).replace(/</g,'&lt;')}</b>${card.visibility&&!hidden?'<i>conditional</i>':''}</div>`;}).join('')}</section>`).join('');
 return `<style>body{margin:0;padding:16px;font:13px Roboto,Arial;background:#fafafa;color:#212121}h1{font-size:16px;margin:0 0 12px}
  .view{display:grid;grid-template-columns:repeat(${columns},minmax(0,1fr));gap:8px 12px;align-items:start}
  section{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:8px;box-sizing:border-box}
  .card{background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.25);padding:8px 10px;overflow:hidden;box-sizing:border-box}
  .card b{display:block;overflow-wrap:anywhere}.card small{color:#727272}.card i{float:right;color:#b26a00;font-size:11px}
  .heading{background:none;box-shadow:none;padding:4px 0;font-size:15px}.tile{background:#eef5ff}.markdown{background:#fffbe8}
  .thermostat,.history-graph,.statistics-graph{background:#f1f8f1}</style><h1>${view.title}</h1><div class="view">${sections}</div>`;
};
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[],problems=[];
 try{for(const lang of Object.keys(config))for(const view of config[lang].views)if(view.sections)for(const width of [390,1280])for(const hidden of [false,true]){
  const page=await browser.newPage({viewport:{width,height:900}});
  await page.setContent(html(view,hidden,width));
  const found=await page.evaluate(()=>{
   const bad=[],tolerance=2;
   document.querySelectorAll('section').forEach(section=>{
    const cards=[...section.children],box=section.getBoundingClientRect(),rows=new Map();
    if(cards.length&&!cards[0].classList.contains('heading'))bad.push('section does not start with a heading');
    for(const card of cards){const r=card.getBoundingClientRect(),key=Math.round(r.top);
     // cards of one row share a top (the tallest sets the row), so group by the row they start in
     const row=[...rows.keys()].find(k=>Math.abs(k-key)<=tolerance)??key;rows.set(row,[...(rows.get(row)||[]),r]);}
    for(const [,items] of rows){const used=items.reduce((sum,r)=>sum+r.width,0);
     if(used<box.width-24-tolerance*items.length&&items.length)bad.push('half-empty row: '+items.length+' card(s), '+Math.round(used)+' of '+Math.round(box.width)+' px');}
   });
   if(document.documentElement.scrollWidth>innerWidth)bad.push('sideways scroll');
   return bad;});
  const file=`${lang}-${view.path}-${width}${hidden?'-conditional-hidden':''}.png`;
  if(!hidden)await page.screenshot({path:path.join(out,file),fullPage:true});
  results.push({lang,view:view.path,width,hidden,problems:found});
  for(const message of found)problems.push(`${lang} ${view.path} ${width}${hidden?' (conditional cards hidden)':''}: ${message}`);
  await page.close();}
 }finally{await browser.close();}
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(results,null,1));
 assert.deepEqual(problems,[],problems.join('\n'));
 console.log(JSON.stringify({views:results.length,problems:0,screenshots:out}));
})().catch(e=>{console.error(e);process.exit(1);});
