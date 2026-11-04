// Screenshots of the generated OpenThermostat dashboard in the demo Home Assistant (tools/dev/ha-demo).
//   node shoot.cjs <job.json>
// job: {base, tokens: {access_token, refresh_token, expires_in}, dashboard, views: [{path, title}], language,
//       widths: [390, 1280], themes: ["light", "dark"], out, closeups: true}
// Every view full length (the viewport grows to the view's height), and close-ups of the house card, the
// Boiler view's "Now" section and the heating-curve card. Writes <out>/shots-<language>.json with what it took.
'use strict';
const {chromium} = require('playwright-core');
const fs = require('node:fs'), path = require('node:path');

const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const taken = [], problems = [];

// In the page: every element matching sel, through all open shadow roots.
const DEEP = `window.__deep = (sel, root = document, out = []) => {
  for (const e of root.querySelectorAll(sel)) out.push(e);
  for (const e of root.querySelectorAll('*')) if (e.shadowRoot) window.__deep(sel, e.shadowRoot, out);
  return out;
};`;

async function settle(page, view) {
  // The view's cards exist, the custom cards have drawn, the charts have their data (or gave up).
  const t0 = Date.now();
  try {
    await page.waitForFunction(() => window.__deep && window.__deep('hui-sections-view, hui-panel-view, hui-masonry-view').length > 0,
      null, {timeout: 60000});
  } catch (e) {
    await page.screenshot({path: path.join(job.out, `debug-${job.language}-${view}.png`)});
    const tags = await page.evaluate(() => [location.href, document.title,
      [...new Set((window.__deep ? window.__deep('*') : []).map(e => e.localName))].filter(n => n.includes('-')).slice(0, 80).join(' ')]);
    throw new Error(`no view at ${tags[0]} (${tags[1]}): ${tags[2]}\n${problems.slice(-15).join('\n')}`);
  }
  for (;;) {
    const busy = await page.evaluate(() => {
      const loading = window.__deep('ha-spinner, ha-circular-progress, mwc-circular-progress')
        .filter(e => e.offsetParent !== null || e.getClientRects().length > 0);
      const custom = window.__deep('openthermostat-house, openthermostat-room-status, openthermostat-heating-curve, openthermostat-knowledge, openthermostat-e32-week')
        .filter(e => !e.shadowRoot || !e.shadowRoot.querySelector('ha-card'));
      return loading.length + custom.length;
    });
    if (!busy || Date.now() - t0 > 25000) break;
    await sleep(500);
  }
  await sleep(view === 'week-program' ? 2500 : 1800);
}

async function grow(page, width) {
  // Home Assistant scrolls inside its layout, not the document: make the viewport as tall as the content.
  let height = 900;
  for (let round = 0; round < 4; round++) {
    const extra = await page.evaluate(() => {
      let hidden = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
      for (const e of window.__deep('*')) {
        const style = getComputedStyle(e);
        if (/(auto|scroll)/.test(style.overflowY) && e.scrollHeight > e.clientHeight + 2)
          hidden = Math.max(hidden, e.scrollHeight - e.clientHeight);
      }
      return hidden;
    });
    if (extra <= 2) break;
    height = Math.min(16000, height + extra);
    await page.setViewportSize({width, height});
    await sleep(900);
  }
  return height;
}

async function closeup(page, kind, file) {
  const handle = await page.evaluateHandle(kind => {
    if (kind === 'house') return window.__deep('openthermostat-house')[0] || null;
    if (kind === 'curve') return window.__deep('openthermostat-heating-curve')[0] || null;
    if (kind === 'boiler-now') {
      // The section whose heading is the first of the Boiler view ("Now"/"Nu").
      const section = window.__deep('hui-section, hui-grid-section')[0];
      return section || null;
    }
    return null;
  }, kind);
  const element = handle.asElement();
  if (!element) return false;
  await element.scrollIntoViewIfNeeded();
  await sleep(400);
  await element.screenshot({path: file});
  return true;
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: job.chrome,
    args: ['--no-sandbox', '--disable-gpu', '--font-render-hinting=none']});
  const tokens = {access_token: job.tokens.access_token, token_type: 'Bearer', expires_in: job.tokens.expires_in,
    hassUrl: job.base, clientId: job.base + '/', expires: Date.now() + job.tokens.expires_in * 1000,
    refresh_token: job.tokens.refresh_token};
  try {
    for (const theme of job.themes) for (const width of job.widths) {
      const context = await browser.newContext({viewport: {width, height: 900}, deviceScaleFactor: width < 600 ? 2 : 1,
        colorScheme: theme, locale: job.language === 'nl' ? 'nl-NL' : 'en-GB', timezoneId: 'Europe/Amsterdam'});
      await context.addInitScript(([tokens, language]) => {
        localStorage.setItem('hassTokens', JSON.stringify(tokens));
        localStorage.setItem('selectedLanguage', JSON.stringify(language));
      }, [tokens, job.language]);
      await context.addInitScript(DEEP);
      const page = await context.newPage();
      page.on('requestfailed', r => problems.push(`${job.language} ${width} ${theme}: request failed ${r.url().slice(0, 200)} ${r.failure()?.errorText}`));
      page.on('console', async m => {
        if (m.type() !== 'error' && m.type() !== 'warning') return;
        let text = m.text();
        try {
          const parts = await Promise.all(m.args().map(a => a.evaluate(o => o && typeof o === 'object'
            ? (o.stack || o.message || JSON.stringify(o)) : String(o))));
          text = parts.join(' ');
        } catch (e) { /* the page went on */ }
        problems.push(`${job.language} ${width} ${theme}: ${text.slice(0, 500)}`);
      });
      page.on('websocket', ws => {
        ws.on('close', () => problems.push(`${job.language} ${width} ${theme}: websocket closed ${ws.url()}`));
        ws.on('framereceived', f => { if (String(f.payload).includes('auth_invalid')) problems.push(`auth_invalid: ${f.payload}`); });
      });
      page.on('pageerror', e => problems.push(`${job.language} ${width} ${theme}: ${String(e).slice(0, 300)}`));
      for (const [n, view] of job.views.entries()) {
        await page.setViewportSize({width, height: 900});
        await page.goto(`${job.base}/${job.dashboard}/${view.path}`, {waitUntil: 'domcontentloaded'});
        await settle(page, view.path);
        const height = await grow(page, width);
        await settle(page, view.path);
        const file = path.join(job.out, `${job.language}-${width}-${theme}-${n + 1}-${view.slug}.png`);
        await page.screenshot({path: file});
        taken.push({file: path.basename(file), view: view.path, title: view.title, width, theme, height});
        if (job.closeups && view.path === 'heating' && await closeup(page, 'house', file.replace(/-\d+-[^-]+\.png$/, '-closeup-house-card.png')))
          taken.push({file: path.basename(file).replace(/-\d+-[^-]+\.png$/, '-closeup-house-card.png'), width, theme});
        if (job.closeups && view.path === 'boiler' && await closeup(page, 'boiler-now', file.replace(/-\d+-[^-]+\.png$/, '-closeup-boiler-now.png')))
          taken.push({file: path.basename(file).replace(/-\d+-[^-]+\.png$/, '-closeup-boiler-now.png'), width, theme});
        if (job.closeups && view.path === job.learningPath && await closeup(page, 'curve', file.replace(/-\d+-[^-]+\.png$/, '-closeup-heating-curve.png')))
          taken.push({file: path.basename(file).replace(/-\d+-[^-]+\.png$/, '-closeup-heating-curve.png'), width, theme});
      }
      await context.close();
    }
  } finally {
    await browser.close();
  }
  fs.writeFileSync(path.join(job.out, `shots-${job.language}.json`), JSON.stringify({taken, problems}, null, 1));
  console.log(`${taken.length} screenshots (${job.language}), ${problems.length} console errors`);
})().catch(e => { console.error(e); process.exit(1); });
