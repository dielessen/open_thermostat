// Real shipped rooms page with simulated HTTP: create the living room, save, show status.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const status={schema:1,mode:'shadow',request:{heat:true,flow_c:36,reason:'heating'},
  rooms:[{id:'woonkamer',status:'ok',source:'climate.woonkamer',temperature:20.4,setpoint:21,demand:true}]};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const width of [1280,320]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[],posts=[];
  let plan={schema:1,mode:'shadow',minimum_flow_c:30,maximum_flow_c:60,rooms:[]};
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>d.accept());
  await page.route('http://opth.test/**',async route=>{
   const request=route.request(),p=new URL(request.url()).pathname;
   const json=(body,code=200)=>route.fulfill({status:code,contentType:'application/json',body:JSON.stringify(body)});
   if(p==='/auth/session')return json({authenticated:true,csrf:'a'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/status/heating')return json(plan.rooms.length?status:{...status,rooms:[],request:{heat:false,flow_c:0,reason:'no_demand'}});
   if(p==='/config/heating'){
    if(request.method()==='POST'){
     assert.equal(request.headers()['x-openthermostat-csrf'],'a'.repeat(64));
     const body=request.postDataJSON();posts.push(body);plan=body;
    }
    return json(plan);
   }
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  await page.evaluate(()=>loadNativePage('heating'));
  const root=page.locator('#heating-plan');
  await root.getByText('Nog geen ruimtes. Voeg eerst de woonkamer toe.').waitFor();
  await root.locator('[data-heating-request]').getByText(/Berekende ketelvraag: uit/).waitFor();
  await root.locator('[data-heating-add]').click();
  const card=root.locator('[data-heating-room]').last();
  await card.getByLabel('Naam').fill('Woonkamer');
  await card.getByLabel('Status').selectOption('active');
  await card.getByLabel('Afgifte').selectOption('floor');
  const first=card.locator('[data-heating-source]').first();
  await first.locator('select').selectOption('ha');await first.locator('input').fill('climate.woonkamer');
  await card.getByRole('button',{name:'Bron toevoegen'}).click();
  await card.locator('[data-heating-source]').nth(1).locator('input').fill('A4:C1:38:A3:E8:DB');
  await card.getByLabel('Setpoint uit Home Assistant-entiteit (optioneel)').fill('climate.woonkamer');
  await root.locator('[data-heating-save]').click();
  await root.getByText('Ruimtes opgeslagen.').waitFor();
  assert.equal(posts.length,1);
  assert.deepEqual(posts[0],{schema:1,mode:'shadow',minimum_flow_c:30,maximum_flow_c:60,rooms:[{id:'woonkamer',name:'Woonkamer',
   state:'active',inactive_until:0,emitter:'floor',sources:[{type:'ha',id:'climate.woonkamer'},{type:'ble',id:'a4c138a3e8db'}],
   setpoint_entity:'climate.woonkamer',fallback_centi_c:2000,minimum_centi_c:500,maximum_centi_c:2500}]});
  await root.locator('[data-heating-room="woonkamer"] summary').getByText(/Gemeten · 20,4 °C \/ 21,0 °C · vraagt warmte/).waitFor();
  await root.locator('[data-heating-request]').getByText('Berekende ketelvraag: 36 °C · Verwarmen').waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  assert.deepEqual(errors,[]);
  results.push({width,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
