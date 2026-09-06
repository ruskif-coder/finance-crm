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

// Сайдкар печатает ЛЮБУЮ нашу страницу, а не только медиаплан (05.09.2026): под
// приложения к договору понадобился второй документ, и второй сервис ради этого заводить
// незачем — отличаются только адрес страницы и имя окна, куда кладутся данные.
//
// Старый вызов `{ plan }` продолжает работать как раньше: у медиаплана свои умолчания.
app.post('/render', async (req, res) => {
  const body = req.body || {};
  const plan = body.plan;
  const data = body.data !== undefined ? body.data : plan;
  if (data === undefined || data === null) return res.status(400).json({ error: 'data required' });
  const path = body.path || '/deals/mp/pdf/render';
  const key = body.key || '__MP_PLAN__';
  const flag = body.flag || '__MP_RENDERED__';
  let ctx;
  try {
    const b = await getBrowser();
    ctx = await b.newContext();
    const page = await ctx.newPage();
    // инжектим данные ДО скриптов страницы — она читает их вместо API и токена
    await page.addInitScript(([k, d]) => { window[k] = d; }, [key, data]);
    await page.goto(`${FRONTEND}${path}`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForFunction((f) => window[f] === true, flag, { timeout: 15000 }).catch(() => {});
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
