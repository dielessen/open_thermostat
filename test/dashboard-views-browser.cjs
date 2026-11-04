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
 'custom:openthermostat-room-status':150,'custom:openthermostat-e32-week':400,'custom:openthermostat-house':260};
const label=card=>card.heading||card.name||card.title||card.entity||(card.content||'').replace(/<[^>]+>|\{[%{#][^}]*[%}#]\}/g,' ').replace(/\s+/g,' ').trim().slice(0,70)||card.type;
// Half-width by default (6 of 12 columns), as in Home Assistant's sections view; grid_options override both.
const HALF=['tile','button','statistic','gauge'];
// A grid row is 56 px with an 8 px gap. A figure (statistic) and a gauge are two rows (120 px), and so is the tile
// beside one (its grid_options say so).
const ROWS={statistic:2,gauge:2};
const height=card=>{const rows=(card.grid_options&&card.grid_options.rows)||ROWS[card.type];
 return rows?rows*56+(rows-1)*8:(HEIGHT[card.type]||90);};
const html=(view,hidden,width)=>{
 // Home Assistant fits as many section columns as the width allows (about 320 px each), up to max_columns.
 const columns=Math.max(1,Math.min(view.max_columns||1,Math.floor((width-32)/320)));
 const sections=(view.sections||[]).map(section=>`<section>${section.cards.filter(c=>!(hidden&&c.visibility)).map(card=>{
  const span=(card.grid_options&&card.grid_options.columns)||(HALF.includes(card.type)?6:12);
  return `<div class="card ${card.type.replace(/[^a-z-]/g,'')}" data-span="${span}" style="grid-column:span ${span};min-height:${height(card)}px">`+
   `<small>${card.type.replace('custom:openthermostat-','')}</small><b>${String(label(card)).replace(/</g,'&lt;')}</b>${card.visibility&&!hidden?'<i>conditional</i>':''}</div>`;}).join('')}</section>`).join('');
 return `<style>:root{--bg:#fafafa;--fg:#212121;--card:#fff;--muted:#727272;--tile:#eef5ff;--note:#fffbe8;--chart:#f1f8f1;--tag:#b26a00}
  @media (prefers-color-scheme:dark){:root{--bg:#111111;--fg:#e1e1e1;--card:#1c1c1c;--muted:#9b9b9b;--tile:#1d2a3a;--note:#2e2a1b;--chart:#1c2b1f;--tag:#e0a040}}
  body{margin:0;padding:16px;font:13px Roboto,Arial;background:var(--bg);color:var(--fg)}h1{font-size:16px;margin:0 0 12px}
  .view{display:grid;grid-template-columns:repeat(${columns},minmax(0,1fr));gap:8px 12px;align-items:start}
  section{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:8px;box-sizing:border-box}
  .card{background:var(--card);border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.25);padding:8px 10px;overflow:hidden;box-sizing:border-box}
  .card b{display:block;overflow-wrap:anywhere}.card small{color:var(--muted)}.card i{float:right;color:var(--tag);font-size:11px}
  .heading{background:none;box-shadow:none;padding:4px 0;font-size:15px}.tile,.statistic,.gauge{background:var(--tile)}.markdown{background:var(--note)}
  .thermostat,.history-graph,.statistics-graph{background:var(--chart)}</style><h1>${view.title}</h1><div class="view">${sections}</div>`;
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
  if(!hidden){
   await page.screenshot({path:path.join(out,file),fullPage:true});
   // The same layout in the dark scheme (only the colours change), for a look by eye.
   await page.emulateMedia({colorScheme:'dark'});
   await page.screenshot({path:path.join(out,file.replace('.png','-dark.png')),fullPage:true});
  }
  results.push({lang,view:view.path,width,hidden,problems:found});
  for(const message of found)problems.push(`${lang} ${view.path} ${width}${hidden?' (conditional cards hidden)':''}: ${message}`);
  await page.close();}
 }finally{await browser.close();}
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(results,null,1));
 assert.deepEqual(problems,[],problems.join('\n'));
 console.log(JSON.stringify({views:results.length,problems:0,screenshots:out}));
})().catch(e=>{console.error(e);process.exit(1);});
