// PDF-сайдкар: headless Chromium (Playwright) рендерит нашу же страницу медиаплана
// в НАТИВНЫЙ (текстовый) PDF — выделяемый текст, встроенные шрифты, кириллица, вёрстка 1:1.
// Данные плана инжектируются в страницу (window.__MP_PLAN__), поэтому браузеру не нужен ни
// /api, ни токен: доступ уже проверил бэкенд, который единственный ходит в этот сервис.
const express = require('express');
const { chromium } = require('playwright');

const FRONTEND = process.env.FRONTEND_URL || 'http://frontend:3000';
const PORT = process.env.PORT || 3001;

const app = express();
app.use(express.json({ limit: '8mb' }));

let browser = null;
async function getBrowser() {
  if (browser && browser.isConnected()) return browser;
  browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  return browser;
}

app.get('/health', (_req, res) => res.json({ ok: true }));

app.post('/render', async (req, res) => {
  const plan = req.body && req.body.plan;
  if (!plan) return res.status(400).json({ error: 'plan required' });
  let ctx;
  try {
    const b = await getBrowser();
    ctx = await b.newContext();
    const page = await ctx.newPage();
    // инжектим данные ДО скриптов страницы — страница в /deals/mp/pdf/render читает их вместо API
    await page.addInitScript((p) => { window.__MP_PLAN__ = p; }, plan);
    await page.goto(`${FRONTEND}/deals/mp/pdf/render`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForFunction(() => window.__MP_RENDERED__ === true, { timeout: 15000 }).catch(() => {});
    await page.evaluate(() => (document.fonts ? document.fonts.ready : true));
    await page.waitForTimeout(400); // добить авто-подгонку zoom'ом
    const pdf = await page.pdf({
      format: 'A4', printBackground: true, preferCSSPageSize: true,
      margin: { top: '0', bottom: '0', left: '0', right: '0' },
    });
    res.set('Content-Type', 'application/pdf').send(pdf);
  } catch (e) {
    console.error('render error:', e);
    res.status(500).json({ error: String(e && e.message || e) });
  } finally {
    if (ctx) await ctx.close().catch(() => {});
  }
});

app.listen(PORT, () => console.log(`pdf-service listening on ${PORT}, frontend=${FRONTEND}`));
