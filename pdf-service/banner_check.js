// Проверка баннера из DSP настоящим браузером (владелец 15.11.2026). Бэкенд присылает разметку креатива, как её отдаёт
// DSP, и ЕРИД; здесь — только замер, решение «прошёл / нет» и слова проблем живут в бэкенде (app/dsp/banner_check.py).
//
// Каждый показ — в своём контексте, то есть в чистом окне, как фрейм на площадке. Проверять баннеры по очереди в одной
// странице нельзя: окно переживает смену документа, скрипт DSP видит свои переменные от прошлого баннера и не оформляет
// плашку — замер 15.11 записал «плашка не видна» десяткам исправных баннеров.
const { bannerRequestVerdict, privateIp } = require('./guards');
const dns = require('dns').promises;

const LANDING = 'https://landing.invalid/x';
const BTN = '[class*="_infoBannerTetraf_btn"]';

async function hostPrivate(host, cache) {
  if (cache.has(host)) return cache.get(host);
  let bad = true;
  try {
    const all = await dns.lookup(host, { all: true });
    bad = !all.length || all.some((a) => privateIp(a.address));
  } catch (e) { bad = true; }
  cache.set(host, bad);
  return bad;
}

const PROBE = `(() => {
  const btns = [...document.querySelectorAll('${BTN}')];
  const r = { plaque: btns.length > 0, n_btns: btns.length, styled: 0, plaque_on_top: false };
  for (const btn of btns) {
    const cs = getComputedStyle(btn); if (cs.position !== 'static') r.styled++;
    const b = btn.getBoundingClientRect(); const x = b.left + b.width / 2, y = b.top + b.height / 2;
    const vis = b.width > 0 && b.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'
      && x >= 0 && y >= 0 && x < innerWidth && y < innerHeight;
    const top = vis ? document.elementFromPoint(x, y) : null;
    if (top && top.closest('[class*="_infoBannerTetraf"]')) { r.plaque_on_top = true; r.xy = [x, y]; break; }
    r.cover = top ? (top.tagName + '.' + String(top.className).slice(0, 30)) : 'вне окна';
  }
  const c = document.elementFromPoint(innerWidth / 2, innerHeight / 2);
  const a = c && c.closest('a');
  r.center_href = a ? a.href : null;
  return r;
})()`;

async function oneImpression(browser, html, erid, w, h, opts) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, locale: 'ru-RU' });
  const hosts = new Map();
  let toLanding = 0;
  try {
    const page = await ctx.newPage();
    page.on('popup', (p) => p.close().catch(() => {}));      // target=_blank не уводит проверку
    await page.route('**/*', async (route) => {
      const rq = route.request();
      const url = rq.url();
      if (url.startsWith(LANDING)) { toLanding += 1; return route.abort('blockedbyclient'); }
      if (bannerRequestVerdict(url, rq.resourceType(), opts) === 'abort') return route.abort('blockedbyclient');
      let host = '';
      try { host = new URL(url).hostname; } catch (e) { return route.abort(); }
      if (host && await hostPrivate(host, hosts)) return route.abort('blockedbyclient');
      return route.continue();
    });
    await page.setContent(html.split('{LINK_UNESC}').join(LANDING), { waitUntil: 'load', timeout: 45000 });
    // Стили плашки приходят позже кнопки: ждём оформления, а не таймера (под нагрузкой таймер врал).
    await page.waitForFunction((sel) => [...document.querySelectorAll(sel)]
      .some((b) => getComputedStyle(b).position !== 'static'), BTN, { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(3000);                       // анимация входа баннера
    const r = await page.evaluate(PROBE);
    if (r.plaque_on_top) {
      const before = toLanding;
      await page.mouse.click(r.xy[0], r.xy[1]);
      await page.waitForTimeout(700);
      const txt = await page.evaluate(() => document.body ? document.body.innerText : '');
      r.erid_shown = !!erid && txt.includes(erid);
      r.plaque_click_navigates = toLanding > before;
    }
    r.center_ok = (r.center_href || '').startsWith(LANDING);
    delete r.xy;
    return r;
  } catch (e) {
    return { error: String(e && e.message || e).slice(0, 200) };
  } finally {
    await ctx.close().catch(() => {});
  }
}

function mount(app, getBrowser) {
  app.post('/banner-check', async (req, res) => {
    const b = req.body || {};
    if (typeof b.html !== 'string' || !b.html.trim()) return res.status(400).json({ error: 'html required' });
    if (b.html.length > 3 * 1024 * 1024) return res.status(400).json({ error: 'html too large' });
    const sizes = Array.isArray(b.sizes) && b.sizes.length ? b.sizes.slice(0, 4) : [[300, 600], [970, 250]];
    const opts = {
      landing_host: 'landing.invalid',
      block_hosts: Array.isArray(b.block_hosts) ? b.block_hosts.slice(0, 20) : [],
      block_domain: typeof b.block_domain === 'string' ? b.block_domain : '',
      allow_urls: Array.isArray(b.allow_urls) ? b.allow_urls.slice(0, 5) : [],
    };
    try {
      const browser = await getBrowser();
      const out = {};
      for (const s of sizes) {
        const w = Math.max(50, Math.min(Number(s[0]) || 300, 2000));
        const h = Math.max(50, Math.min(Number(s[1]) || 600, 2000));
        out[`${w}x${h}`] = await oneImpression(browser, b.html, typeof b.erid === 'string' ? b.erid : '', w, h, opts);
      }
      res.json({ sizes: out });
    } catch (e) {
      console.error('banner-check error:', e);
      res.status(500).json({ error: String(e && e.message || e).slice(0, 300) });
    }
  });
}

module.exports = { mount };
