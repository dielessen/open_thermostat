// Execute shipped room pages in Chromium. API fixture is explicit, not ESP32 proof.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../../data/html');
const room=(id,name)=>({id,name,sensor:'',valves:[]});
const program=id=>({room_id:id,base_temp:2000,temp_margin_up:5,temp_margin_down:15,enabled:false,temperatures:[]});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});let passed=0;
 const pass=name=>{passed++;console.log('PASS '+name);};
 let page, state, dialogs, errors;
 async function start(catalog=[],programs={default:[]},mode='catalog',failure=null) {
  if(page){assert.deepEqual(errors,[]);await page.close();}
  page=await browser.newPage();state={catalog:structuredClone(catalog),programs:structuredClone(programs),writes:[],fail:failure,corrupt:null,readHook:null,confirm:true,reads:[]};dialogs=[];errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',async d=>{dialogs.push(d.message());if(d.type()==='confirm'&&!state.confirm)await d.dismiss();else await d.accept();});
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),url=new URL(req.url()),p=decodeURIComponent(url.pathname),method=req.method();
   const json=(v,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(v)});
   if(method==='GET')state.reads.push(p);
   if(state.readHook&&method==='GET')state.readHook(p);
   if(state.fail&&state.fail.p===p&&state.fail.method===method){if(state.fail.hang)return;return route.fulfill({status:500,body:'injected storage failure'});}
   if(p==='/config/hardware')return json({valve_pins:[]});
   if(p==='/status/devices')return json([]);
   if(p==='/status/programs')return json(Object.keys(state.programs));
   if(p==='/config/program/current')return json({program:'default'});
   if(p==='/config/rooms'){
    if(method==='GET')return json(state.corrupt==='catalog'?[room('ffffffff','unexpected')]:state.catalog);
    const next=req.postDataJSON(),ids=new Set(next.map(r=>r.id));
    if(Object.values(state.programs).some(prog=>prog.some(entry=>!ids.has(entry.room_id))))return route.fulfill({status:409,body:'Room catalog conflicts with program default'});
    state.catalog=next;state.writes.push({p,next});return route.fulfill({status:205,body:''});
   }
   if(p.startsWith('/config/programs/')){
    const name=p.slice('/config/programs/'.length);
    if(method==='GET')return json(state.corrupt===name?[]:state.programs[name]);
    const next=req.postDataJSON(),ids=new Set(state.catalog.map(r=>r.id));
    if(next.some(entry=>!ids.has(entry.room_id)))return route.fulfill({status:400,body:'Invalid program or unknown room ID'});
    state.programs[name]=next;state.writes.push({p,next});return route.fulfill({status:204,body:''});
   }
   if(p==='/') {
    const content=fs.readFileSync(path.join(assets,mode==='catalog'?'room_setup.html':mode==='management'?'room_management.html':'rooms.html'),'utf8');
    return route.fulfill({contentType:'text/html',body:`<link rel="stylesheet" href="/deps/bs.min.css.gz"><link rel="stylesheet" href="/deps/bms.min.css.gz"><script src="/deps/jquery.min.js.gz"></script><script src="/deps/bs.bundle.min.js.gz"></script><script src="/deps/bms.min.js.gz"></script><script>const hostName='';function validateResponse(r){if(!r.ok)throw Error(r.statusText);return r;}function validateForm(s){return document.querySelector(s).checkValidity();}</script><div id="${mode==='management'?'maincontainer':'roomProgramsPane'}">${content}</div>`});
   }
   if(p==='/room_setup.html'||p==='/rooms.html')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(assets,p),'utf8')});
   if(p.startsWith('/deps/'))return route.fulfill({contentType:p.endsWith('.css.gz')?'text/css':'application/javascript',body:zlib.gunzipSync(fs.readFileSync(path.join(assets,p)))});
   return route.fulfill({status:404,body:'not found'});
  });
  await page.goto('http://opth.test/');
  if(failure)await page.waitForFunction(()=>{const retry=document.querySelector('#retryPhysicalRooms')||document.querySelector('#programLoadingError');return retry&&!retry.classList.contains('d-none');});
  else if(mode==='catalog'||mode==='management')await page.waitForFunction(()=>!document.querySelector('#physicalRoomCard').classList.contains('d-none'));
  else await page.waitForFunction(()=>Array.isArray(window.loadedProgram));
 }
 async function clickAlert(selector,text){await page.click(selector);await until(()=>dialogs.some(d=>d.includes(text)));}
 async function until(fn){for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,20));}throw Error('condition timeout: '+dialogs.join('\n'));}
 async function noErrors(){assert.deepEqual(errors,[]);}
 try{
  await start();assert.equal(await page.locator('#physicalRoomLoading').isVisible(),false,'loaded room editor must not retain a spinning loading indicator with shipped Bootstrap CSS');pass('successful room load hides spinner with actual bundled styles');
  assert.equal(await page.locator('#physicalRoomEmpty').isVisible(),true);assert.equal(await page.isDisabled('#deletePhysicalRoom'),true);pass('empty installation displays no phantom rooms and disables delete');
  await page.click('#addPhysicalRoom');await page.fill('#physicalRoomName','Bathroom');await clickAlert('#savePhysicalRooms','Rooms saved');
  assert.equal(state.catalog.length,1);const id=state.catalog[0].id;assert.match(id,/^[a-f0-9]{8}$/);
  const saved=structuredClone(state.catalog);await start(saved);assert.equal(await page.inputValue('#physicalRoomName'),'Bathroom');pass('add/save/readback/reload retains a stable room ID');
  await page.fill('#physicalRoomName','Bath');await clickAlert('#savePhysicalRooms','Rooms saved');assert.equal(state.catalog[0].id,id);pass('rename preserves room identity');
  await clickAlert('#deletePhysicalRoom','Room deleted and saved');assert.deepEqual(state.catalog,[]);assert.equal(await page.isVisible('#physicalRoomEmpty'),true);pass('delete last unreferenced room persists empty catalog');
  await start();await page.click('#addPhysicalRoom');await page.fill('#physicalRoomName','');await page.click('#deletePhysicalRoom');await page.waitForFunction(()=>document.querySelector('#physicalRoomSelect').options.length===0);assert.equal(state.writes.length,0);pass('invalid unsaved new room can be discarded without persisting or deleting other rooms');
  await start();await page.click('#addPhysicalRoom');await page.click('#choosePhysicalRoomSensor');await until(()=>dialogs.some(d=>d.includes('No temperature sensors scanned')));assert.equal(await page.locator('#physicalRoomSelect option').count(),1);pass('sensor chooser for an unsaved room never discards it');
  const a=room('aaaaaaaa','Bath'),b=room('bbbbbbbb','Office');
  await start([a,b],{default:[program(a.id),program(b.id)],holiday:[program(a.id)]});
  await clickAlert('#deletePhysicalRoom','Room deleted and saved');assert.deepEqual(state.catalog,[b]);assert.deepEqual(state.programs.default,[program(b.id)]);assert.deepEqual(state.programs.holiday,[]);
  assert.match(dialogs[0],/default, holiday/);assert.deepEqual(state.writes.map(w=>w.p),['/config/programs/default','/config/programs/holiday','/config/rooms']);pass('referenced deletion confirms scope and clears all programs first, preserving other room');
  await start([a],{default:[program(a.id)]});state.confirm=false;await page.click('#deletePhysicalRoom');await until(()=>dialogs.length>0);assert.equal(state.writes.length,0);pass('cancel deletion performs no writes');
  await start([a]);await page.fill('#physicalRoomName','Uncommitted');await clickAlert('#deletePhysicalRoom','Save room changes');assert.equal(state.writes.length,0);pass('delete cannot silently save unrelated unsaved edits');
  await start([a],{default:[program(a.id)]});state.fail={p:'/config/programs/default',method:'POST'};await clickAlert('#deletePhysicalRoom','Deletion not confirmed');assert.deepEqual(state.catalog,[a]);assert.equal(state.writes.length,0);pass('program write failure preserves room and reports failure');
  await start([a],{default:[program(a.id)],holiday:[program(a.id)]});state.fail={p:'/config/programs/holiday',method:'POST'};await clickAlert('#deletePhysicalRoom','Deletion not confirmed');assert.deepEqual(state.catalog,[a]);assert.deepEqual(state.programs.default,[]);assert.match(dialogs.at(-1),/already removed from: default/);pass('partial program failure preserves room and names completed changes');
  await start([a]);state.fail={p:'/config/rooms',method:'POST'};await clickAlert('#deletePhysicalRoom','Deletion not confirmed');assert.deepEqual(state.catalog,[a]);assert.equal(await page.locator('#physicalRoomSelect option').count(),1);pass('catalog failure never shows successful deletion');
  await start([a]);await page.fill('#physicalRoomName','new');state.corrupt='catalog';await clickAlert('#savePhysicalRooms','Cannot save rooms');assert.equal(state.writes.length,0);pass('concurrent catalog edit stops overwrite');
  await start([a],{default:[program(a.id)]});let reads=0;state.readHook=p=>{if(p==='/config/programs/default'&&++reads===2)state.programs.default=[];};await clickAlert('#deletePhysicalRoom','Program changed');assert.deepEqual(state.catalog,[a]);assert.equal(state.writes.length,0);pass('concurrent program edit stops deletion');
  await start([a],{default:[program(a.id)]});state.readHook=p=>{if(p==='/config/rooms'&&state.writes.length)state.corrupt='catalog';};await clickAlert('#deletePhysicalRoom','Deletion not confirmed');assert.ok(!dialogs.includes('Room deleted and saved.'));pass('readback mismatch cannot claim successful deletion');
  await start([b],{default:[program(a.id),program(b.id)]},'program');assert.equal(dialogs.length,0);assert.equal(await page.isVisible('#missingProgramRooms'),true);assert.match(await page.locator('#roomSelectorSelect').textContent(),/Missing room \(aaaaaaaa\)/);
  await page.click('#missingProgramRooms button');await page.waitForFunction(()=>window.loadedProgram.length===1);await clickAlert('#saveprogram','Program saved and verified');assert.deepEqual(state.programs.default,[program(b.id)]);pass('old orphan program entries can be removed and saved without modal error loop');
  await start([],{default:JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../data/programs/default.json'),'utf8'))},'program');await page.click('#missingProgramRooms button');await page.waitForFunction(()=>window.loadedProgram.length===0);await clickAlert('#saveprogram','Program saved and verified');assert.deepEqual(state.programs.default,[]);pass('legacy empty catalog plus shipped seven-room orphan program can be repaired to empty');
  await start([a],{default:[program(a.id)]},'program');state.fail={p:'/config/programs/default',method:'POST'};await clickAlert('#saveprogram','Cannot save program');assert.deepEqual(state.programs.default,[program(a.id)]);pass('program editor exposes backend save error without false success');
  await start([a]);state.fail={p:'/status/programs',method:'GET'};await clickAlert('#deletePhysicalRoom','Deletion not confirmed');assert.equal(state.writes.length,0);pass('program inventory read failure blocks deletion');
  await start([a],{default:[program(a.id)]});state.fail={p:'/config/programs/default',method:'GET'};await clickAlert('#deletePhysicalRoom','Deletion not confirmed');assert.equal(state.writes.length,0);pass('program read failure cannot skip dependency inspection');
  await start([a]);await page.fill('#physicalRoomName','changed');state.fail={p:'/config/rooms',method:'POST'};await clickAlert('#savePhysicalRooms','Cannot save rooms');assert.deepEqual(state.catalog,[a]);pass('ordinary catalog save failure preserves editor and reports error');
  await start([a]);await page.fill('#physicalRoomName','changed');state.readHook=p=>{if(p==='/config/rooms'&&state.writes.length)state.corrupt='catalog';};await clickAlert('#savePhysicalRooms','Cannot save rooms');assert.ok(!dialogs.includes('Rooms saved'));pass('catalog save readback mismatch rejects success');
  await start([a]);state.confirm=false;await page.click('#deletePhysicalRoom');await until(()=>dialogs.length>0);state.confirm=true;await clickAlert('#deletePhysicalRoom','Room deleted and saved');assert.deepEqual(state.catalog,[]);pass('cancelled deletion unlocks controls and permits retry');
  await start([a],{default:[program(a.id)]},'program');state.readHook=p=>{if(p==='/config/programs/default'&&state.writes.length)state.corrupt='default';};await clickAlert('#saveprogram','Cannot save program');assert.ok(!dialogs.includes('Program saved and verified.'));pass('program readback mismatch rejects success');
  await start([], {default:[]}, 'management');
  assert.equal(await page.locator('#physicalRoomLoading').isVisible(),false);
  await page.click('#roomProgramsTab');await page.waitForFunction(()=>Array.isArray(window.loadedProgram));
  await page.locator('#programeditform').waitFor({state:'visible'});
  assert.equal(await page.locator('#loadingprogress').isVisible(),false);
  await page.click('#physicalRoomsTab');assert.equal(await page.locator('#physicalRoomLoading').isVisible(),false);
  pass('actual combined Rooms and Programs tabs load both shipped fragments and hide both spinners');
  for(const p of ['/config/rooms','/config/hardware']) {
   await start([], {default:[]}, 'catalog',{p,method:'GET'});
   assert.equal(await page.locator('#physicalRoomLoading').isVisible(),false);
   assert.match(await page.locator('#physicalRoomLoadingMessage').textContent(),/Cannot load/);
   await page.waitForTimeout(2200);assert.equal(state.reads.filter(x=>x===p).length,1);
   assert.equal(state.writes.length,0);state.fail=null;
   await page.click('#retryPhysicalRooms');await page.locator('#physicalRoomCard').waitFor({state:'visible'});
   assert.equal(await page.locator('#physicalRoomLoading').isVisible(),false);
   assert.equal(await page.locator('#retryPhysicalRooms').isVisible(),false);
   assert.equal(state.writes.length,0);pass('room initial read failure stops spinner and explicit retry recovers: '+p);
  }
  for(const p of ['/config/rooms','/status/programs','/config/program/current','/config/programs/default']) {
   await start([], {default:[]}, 'program',{p,method:'GET'});
   assert.equal(await page.locator('#loadingprogress').isVisible(),false);
   assert.match(await page.locator('#programLoadingError').textContent(),/Cannot load programs/);
   await page.waitForTimeout(100);assert.equal(state.reads.filter(x=>x===p).length,1);
   assert.equal(state.writes.length,0);state.fail=null;
   await page.click('#programLoadingError button');await page.locator('#programeditform').waitFor({state:'visible'});
   assert.equal(await page.locator('#loadingprogress').isVisible(),false);
   assert.equal(await page.locator('#programLoadingError').isVisible(),false);
   assert.equal(await page.locator('#selectprogram option').count(),1);
   assert.equal(state.writes.length,0);pass('program initial read failure stops spinner, no recursion, explicit retry recovers: '+p);
  }
  for(const mode of ['catalog','program']) {
   await start([], {default:[]},mode,{p:'/config/rooms',method:'GET',hang:true});
   assert.equal(await page.locator(mode==='catalog'?'#physicalRoomLoading':'#loadingprogress').isVisible(),false);
   assert.equal(state.reads.filter(p=>p==='/config/rooms').length,1);
   assert.equal(state.writes.length,0);pass('nonresponding '+mode+' request times out and stops spinner');
  }
  await noErrors();console.log(`${passed} shipped-browser scenarios passed (simulated API, not board proof)`);
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
