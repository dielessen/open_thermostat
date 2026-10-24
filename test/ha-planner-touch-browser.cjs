// Actual shipped editor and Chromium touch events; synthetic HA, no live writes.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const {chromium}=require('playwright-core');
const root=path.resolve(__dirname,'..');
const fixtureScript=fs.readFileSync(path.join(__dirname,'ha-room-program-browser.cjs'),'utf8');
const {initial,source}=vm.runInNewContext(fixtureScript.split('(async()=>{')[0]+';({initial,source});',{require,__dirname,process});
const tag='openthermostat-room-editor-v35';
const output=path.resolve(process.env.OPENTHERMOSTAT_TOUCH_EVIDENCE||path.join(root,'out/ha-planner-touch-browser'));
(async()=>{
fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
try{for(const width of [390,320,1440])for(const language of ['nl','en']){
 const page=await browser.newPage({viewport:{width,height:900},isMobile:width<720,hasTouch:true});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.setContent('<meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:0;font:14px Arial}</style><main></main>');
 await page.evaluate(()=>customElements.define('home-assistant',class extends HTMLElement{}));
 await page.evaluate(async s=>{await import('data:text/javascript;base64,'+s)},source.toString('base64'));
 await page.evaluate(({initial,tag,language})=>{window.calls=[];window.card=document.createElement(tag);document.querySelector('main').append(card);card.setConfig({entry_id:'fixture',room_id:'room'});card.hass={language,user:{is_admin:true},callWS:async r=>{calls.push(r.type);if(r.type!=='open_thermostat/room/get')throw Error('Unexpected write');return structuredClone(initial);}};},{initial,tag,language});
 const card=page.locator(tag);await card.locator('.track').first().waitFor();const client=await page.context().newCDPSession(page);
 const set=async blocks=>{await page.evaluate(blocks=>{card._settings.week.tuesday=blocks;card._selected=null;card.renderTimeline();card.renderInline();card.refreshStatus();},blocks);await card.locator('.track').nth(1).scrollIntoViewIfNeeded();};
 const read=()=>page.evaluate(()=>structuredClone(card._settings.week.tuesday));
 const drag=async({fraction=.5,hours=2,mouse=false,cancel=false})=>{const track=await card.locator('.track').nth(1).boundingBox(),block=await card.locator('.track').nth(1).locator('.block').first().boundingBox(),x=block.x+block.width*fraction,y=block.y+block.height/2,dx=track.width*hours/24;
  if(mouse){await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+dx,y,{steps:8});if(cancel){await page.evaluate(()=>card.shadowRoot.querySelectorAll('.track')[1].dispatchEvent(new PointerEvent('pointercancel',{pointerId:1})));await page.mouse.up();}else await page.mouse.up();}
  else{await client.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});for(let i=1;i<=8;i++)await client.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x+dx*i/8,y}]});await client.send('Input.dispatchTouchEvent',{type:cancel?'touchCancel':'touchEnd',touchPoints:[]});}return block.width;};
 const checks=[];
 for(const duration of [900,3600])for(const fraction of [.15,.5,.85]){const before={start:25200,end:25200+duration,target_centi_c:2250};await set([before]);const blockWidth=await drag({fraction});const actual=await read();assert.deepEqual(actual,[{...before,start:32400,end:32400+duration}],JSON.stringify({width,duration,fraction,blockWidth,actual}));checks.push({duration,fraction,blockWidth,move_preserves_duration:true});}
 const short={start:25200,end:28800,target_centi_c:2250};await set([short]);await drag({mouse:true});assert.deepEqual(await read(),[{...short,start:32400,end:36000}]);
 await set([short]);await drag({cancel:true});assert.deepEqual(await read(),[short]);assert.equal(await card.locator('.ghost').count(),0);
 await set([short,{start:32400,end:36000,target_centi_c:2100}]);await drag({});assert.deepEqual(await read(),[short,{start:32400,end:36000,target_centi_c:2100}]);
 await set([{start:0,end:3600,target_centi_c:2250}]);await drag({hours:-2});assert.deepEqual(await read(),[{start:0,end:3600,target_centi_c:2250}]);
 await set([{start:82800,end:86400,target_centi_c:2250}]);await drag({hours:2});assert.deepEqual(await read(),[{start:82800,end:86400,target_centi_c:2250}]);
 if(width===1440){const wide={start:25200,end:54000,target_centi_c:2250};await set([wide]);await drag({mouse:true,fraction:.01,hours:1});assert.deepEqual(await read(),[{...wide,start:28800}]);await set([wide]);await drag({mouse:true,fraction:.99,hours:1});assert.deepEqual(await read(),[{...wide,end:57600}]);}
 await set([short]);await card.locator('.track').nth(1).locator('.block').click();await card.locator('#block-start').fill('07:15');await card.locator('#block-end').fill('08:15');assert.deepEqual(await read(),[{...short,start:26100,end:29700}]);
 // A selected short block remains editable through the precise time fields.
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(await page.evaluate(()=>calls),['open_thermostat/room/get']);assert.deepEqual(errors,[]);
 results.push({width,language,checks,cancel_preserved:true,overlap_rejected:true,day_boundaries_preserve_duration:true,mouse_resize_checked:width===1440,no_autosave:true,errors});await client.detach();await page.close();
}}finally{await browser.close();}
fs.writeFileSync(path.join(output,'RESULT.json'),JSON.stringify({status:'PASS',results},null,2)+'\n');console.log(JSON.stringify({status:'PASS',cases:results.length}));
})().catch(e=>{console.error(e);process.exitCode=1;});
