// The Boiler profile card on the real shipped boiler page (fixture transport only):
// three groups with friendly Dutch names, other-family fields left out, and the
// owner's "show anyway" for a not-fitted value.
const {chromium} = require('playwright-core');
const fs = require('node:fs'), path = require('node:path'), zlib = require('node:zlib'), assert = require('node:assert/strict');
const assets = path.resolve(__dirname, '../data/html');
const out = path.resolve(process.env.OPENTHERMOSTAT_BOILER_PROFILE_EVIDENCE || 'out/boiler-profile-browser');
const telemetry = {reception:{state:'classic_reports_received',report_count:3,last_report_age_ms:100},
  transport:{enabled:true,transmit_compiled:false,transmitted_frames:0,receive_queue_dropped:0,invalid_telegrams:0,uart_errors:0,uart_resets:0},
  fields:{measured_flow_temperature:{value:59,unit:'degC',state:'valid',quality:'reported',age_ms:100}}};
// The shape of EMS/BoilerProfileReport.h writeBoilerProfileJSON, for the owner's Classic boiler.
function profile(shown) {
  const fields = [
    {index:1,name:'measured_flow_temperature',state:'supported',last_valid_age_s:2},
    {index:2,name:'measured_return_temperature',state:'supported',last_valid_age_s:2},
    {index:6,name:'pressure',state:'not_fitted',last_valid_age_s:null,...(shown?{shown_anyway:true}:{})},
    {index:30,name:'storage_temperature_1',state:'not_fitted',last_valid_age_s:null},
    {index:3,name:'outdoor_temperature',state:'not_reported',last_valid_age_s:null},
    {index:7,name:'raw_burner_bit',state:'unknown',last_valid_age_s:null},
    {index:78,name:'plus_flow_temperature',state:'not_reported',last_valid_age_s:null},
    {index:104,name:'boiler_uptime',state:'not_reported',last_valid_age_s:null},
    {index:200,name:'<img src=x onerror=alert(1)>',state:'supported',last_valid_age_s:null}];
  return {schema:1,identity:{address:8,family:'classic',product_id:null,version:null},rules:{not_fitted_frames:10,not_fitted_span_s:600},
    counts:{supported:3,not_fitted:2,not_reported:3,unknown:1},settled:true,resets:0,restored:true,writes:1,write_failures:0,fields};
}
(async () => {
  fs.mkdirSync(out, {recursive:true});
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_PATH});
  try { for (const width of [1280, 390, 320]) {
    const page = await browser.newPage({viewport:{width,height:900}});
    let shown = false, available = true; const posts = [], errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('http://boiler.test/**', route => {
      const request = route.request(), pathname = new URL(request.url()).pathname;
      if (pathname === '/status/ems/telemetry') return route.fulfill({contentType:'application/json',body:JSON.stringify(telemetry)});
      if (pathname === '/status/boiler/profile') return route.fulfill(available ? {contentType:'application/json',body:JSON.stringify(profile(shown))} : {status:404,body:''});
      if (pathname === '/config/boiler-profile') {
        assert.equal(request.method(), 'POST');
        assert.equal(request.headers()['x-openthermostat-csrf'], 'a'.repeat(64));
        const body = request.postDataJSON(); posts.push(body);
        assert.deepEqual(Object.keys(body).sort(), ['index','show']);
        shown = body.show;
        return route.fulfill({contentType:'application/json',body:'{"saved":true}'});
      }
      if (pathname === '/status') return route.fulfill({contentType:'application/json',body:JSON.stringify({controlMode:'shadow',ems:{},control:{fresh:false,reason:'missing'}})});
      if (pathname === '/auth/session') return route.fulfill({contentType:'application/json',body:JSON.stringify({authenticated:true,csrf:'a'.repeat(64)})});
      const file = path.join(assets, pathname === '/' ? 'index.html' : pathname);
      if (!file.startsWith(assets + '/') || !fs.existsSync(file)) return route.fulfill({status:404,body:''});
      let body = fs.readFileSync(file); if (pathname.endsWith('.gz')) body = zlib.gunzipSync(body);
      return route.fulfill({contentType:pathname.endsWith('.css.gz')?'text/css':pathname.endsWith('.js')||pathname.endsWith('.js.gz')?'application/javascript':'text/html',body});
    });
    await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://boiler.test'}]);
    await page.goto('http://boiler.test/');
    await page.waitForFunction(() => typeof loadNativePage === 'function');
    await page.evaluate(() => loadNativePage('boiler_test'));
    const box = page.locator('[data-boiler-profile]');
    await box.waitFor();
    assert.equal(await box.evaluate(node => node.open), false, 'collapsed by default');
    await page.locator('[data-profile-summary]').filter({hasText:'3 beschikbaar, 2 niet aanwezig'}).waitFor();
    await box.locator('summary').click();
    assert.match(await box.locator('summary').innerText(), /Ketelprofiel/);
    const group = key => box.locator(`[data-profile-group="${key}"]`).innerText();
    const supported = await group('supported'), notFitted = await group('not_fitted'), pending = await group('pending');
    assert.match(supported, /Aanvoertemperatuur/); assert.match(supported, /Retourtemperatuur/);
    assert.match(supported, /<img src=x onerror=alert\(1\)>/);  // text, never markup
    assert.equal(await box.locator('img').count(), 0);
    assert.match(notFitted, /Waterdruk/); assert.match(notFitted, /Opslagtemperatuur 1/);
    assert.match(pending, /Buitentemperatuur/); assert.match(pending, /gezien, nog te weinig berichten/);
    assert.doesNotMatch(pending, /EMS\+/, 'a Classic boiler lists no EMS+ fields');
    assert.equal(await box.locator('[data-profile-family]').isVisible(), true);
    // Show anyway: one POST, then the button reads "hide again".
    await box.getByRole('button', {name:'Toch tonen'}).first().click();
    await box.getByRole('button', {name:'Weer verbergen'}).waitFor();
    assert.deepEqual(posts, [{index:6, show:true}]);
    assert.equal(await box.getByRole('button', {name:'Weer verbergen'}).getAttribute('aria-pressed'), 'true');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'no horizontal scroll at ' + width);
    await page.screenshot({path:path.join(out, `boiler-profile-${width}.png`), fullPage:true});
    // Older firmware without the route: no card, nothing else breaks.
    available = false;
    await page.evaluate(() => loadNativePage('boiler_test'));
    await page.locator('[data-boiler-profile]').waitFor({state:'hidden'});
    await page.locator('[data-essentials]').filter({hasText:'Aanvoertemperatuur'}).waitFor();
    assert.deepEqual(errors, []);
    await page.close();
  } } finally { await browser.close(); }
  console.log('boiler profile browser: ok');
})().catch(error => { console.error(error); process.exit(1); });
