// Real shipped page, fixture transport only. No physical commissioning claim.
const {chromium} = require('playwright-core');
const fs = require('node:fs'), path = require('node:path'), zlib = require('node:zlib'), assert = require('node:assert/strict');
const assets = path.resolve(__dirname, '../data/html');
const out = path.resolve(process.env.OPENTHERMOSTAT_BOILER_TEST_EVIDENCE || 'out/boiler-test-browser');
const fixture = () => ({reception: {state:'classic_reports_received', report_count:3, last_report_age_ms:100},
  transport:{enabled:true, transmit_compiled:false, transmitted_frames:0, receive_queue_dropped:0, invalid_telegrams:0, uart_errors:0, uart_resets:0},
  fields:{measured_flow_temperature:{value:37.2,unit:'degC',state:'valid',quality:'reported',age_ms:100},
    raw_burner_bit:{value:1,unit:'bool',state:'valid',quality:'unreliable',age_ms:100},
    heating_active:{value:0,unit:'bool',state:'valid',quality:'inferred',age_ms:100},
    measured_return_temperature:{value:35,unit:'degC',state:'stale',quality:'reported',age_ms:31000},
    '<img src=x onerror=alert(1)>':{value:'<script>alert(1)</script>',unit:'text',state:'valid',quality:'unknown',age_ms:0}}});
(async () => {
  fs.mkdirSync(out, {recursive:true});
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_PATH});
  const results = [];
  try { for (const width of [1280,390,320]) {
    const page = await browser.newPage({viewport:{width,height:900},acceptDownloads:true});
    let data = fixture(), fail = false; const requests = [], errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('http://boiler.test/**', route => {
      const request = route.request(); requests.push({path:new URL(request.url()).pathname,method:request.method()});
      const pathname = new URL(request.url()).pathname;
      if (pathname === '/status/ems/telemetry') return route.fulfill({status:fail?503:200,contentType:'application/json',body:JSON.stringify(data)});
      if (pathname === '/status') return route.fulfill({contentType:'application/json',body:JSON.stringify({controlMode:'shadow',ems:{},control:{fresh:false,reason:'missing'}})});
      if (pathname === '/auth/session') return route.fulfill({contentType:'application/json',body:JSON.stringify({authenticated:true,csrf:'a'.repeat(64)})});
      const file = path.join(assets, pathname === '/' ? 'index.html' : pathname);
      if (!file.startsWith(assets + '/') || !fs.existsSync(file)) return route.fulfill({status:404,body:''});
      let body = fs.readFileSync(file); if (pathname.endsWith('.gz')) body = zlib.gunzipSync(body);
      return route.fulfill({contentType:pathname.endsWith('.css.gz')?'text/css':pathname.endsWith('.js')||pathname.endsWith('.js.gz')?'application/javascript':'text/html',body});
    });
    await page.goto('http://boiler.test/');
    await page.waitForFunction(() => typeof loadNativePage === 'function');
    await page.evaluate(() => loadNativePage('boiler_test'));
    await page.locator('[data-reception]').filter({hasText:'Verse EMS Classic'}).waitFor();
    assert.match(await page.locator('[data-fields] tr').nth(0).innerText(),/37.2/);
    assert.match(await page.locator('[data-fields] tr').nth(1).innerText(),/Geen bruikbare waarde/);
    assert.match(await page.locator('[data-fields] tr').nth(2).innerText(),/0 bool/);
    assert.match(await page.locator('[data-fields] tr').nth(3).innerText(),/Geen bruikbare waarde/);
    assert.match(await page.locator('[data-fields] tr').nth(4).innerText(),/Geen bruikbare waarde/);
    assert.equal(await page.locator('#boiler-test img').count(),0);
    const waiting = page.waitForEvent('download'); await page.locator('[data-download]').click();
    const download = await waiting; const saved = JSON.parse(fs.readFileSync(await download.path(),'utf8'));
    assert.equal(saved.physical_validation,false); assert.equal(saved.telemetry.transport.transmitted_frames,0);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true);
    await page.screenshot({path:path.join(out,`RECEPTION-${width}.png`),fullPage:true});
    const names = [...fs.readFileSync(path.resolve(__dirname,'../src/EMS/ClassicBoilerMonitor.h'),'utf8').matchAll(/\{"([^"]+)",/g)].map(match => match[1]);
    assert.equal(names.length,69);
    data.fields = Object.fromEntries(names.map(name => [name,{value:2.7,unit:'uA',state:'valid',quality:'reported',age_ms:120}]));
    data.telegram_inventory = {capacity:24,untracked_frames:2,types:[
      {type:24,frames:9,decoder:'classic_fields',age_ms:120},
      {type:1911,frames:1,decoder:'unmapped',age_ms:300}]};
    await page.waitForFunction(() => document.querySelectorAll('[data-fields] tr').length === 69);
    assert.match(await page.locator('[data-fields] tr').nth(32).innerText(),/Ionisatiestroom.*2.7 uA/s);
    assert.match(await page.locator('[data-fields] tr').last().innerText(),/warmwateractiefsignaal/);
    assert.match(await page.locator('[data-telegrams]').innerText(),/0x777.*Nog geen velddecoder/s);
    assert.match(await page.locator('[data-inventory-status]').innerText(),/volle lijst: 2/);
    const expandedWait = page.waitForEvent('download'); await page.locator('[data-download]').click();
    const expandedDownload = await expandedWait;
    const expandedSaved = JSON.parse(fs.readFileSync(await expandedDownload.path(),'utf8'));
    assert.equal(Object.keys(expandedSaved.telemetry.fields).length,69);
    assert.equal(expandedSaved.telemetry.telegram_inventory.types.length,2);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true);
    await page.screenshot({path:path.join(out,`EXPANDED-${width}.png`),fullPage:true});
    data.reception.state = 'conflicting_families';
    await page.locator('[data-reception]').filter({hasText:'Tegenstrijdige'}).waitFor();
    assert.match(await page.locator('[data-fields] tr').first().innerText(),/Geen bruikbare waarde/);
    data.reception.state = 'classic_reports_received';
    data.fields.overflow = {}; // 70 fits; explicitly reject over-budget responses
    for(let i=0;i<27;i++) data.fields['extra_'+i] = {};
    await page.locator('[data-reception]').filter({hasText:'niet beschikbaar'}).waitFor();
    assert.equal(await page.locator('[data-fields] tr').count(),0);
    data.fields = fixture().fields;
    await page.locator('[data-reception]').filter({hasText:'Verse EMS Classic'}).waitFor();
    fail = true;
    await page.locator('[data-reception]').filter({hasText:'niet beschikbaar'}).waitFor();
    assert.equal(await page.locator('[data-fields] tr').count(),0);
    assert.equal(await page.locator('[data-download]').isDisabled(),true);
    await page.evaluate(() => document.getElementById('boiler-test').remove());
    const before = requests.length; await page.waitForTimeout(5200); assert.equal(requests.length,before);
    assert.equal(requests.some(request => request.method !== 'GET'),false); assert.deepEqual(errors,[]);
    results.push({width,result:'PASS',readOnly:true,staleAndUnknownSuppressed:true,conflictSuppressed:true,navigationStopsPolling:true});
    await page.close();
  }} finally { await browser.close(); }
  fs.writeFileSync(path.join(out,'BROWSER.json'),JSON.stringify({result:'PASS',physicalProof:false,cases:results},null,2)+'\n');
  console.log(JSON.stringify({result:'PASS',viewports:results.length}));
})().catch(error => { console.error(error); process.exitCode=1; });
