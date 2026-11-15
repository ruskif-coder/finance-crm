// Проверки входа сайдкара (аудит 13.11.2026). Чистые функции — их проверяет `guards.test.js` (`node --test`).
//
// /render: адрес страницы склеивается как `${FRONTEND}${path}`. Путь вида «@169.254.169.254/…» превращал
// `http://frontend:3000` в userinfo, и Chromium шёл на чужой хост — отдавая его страницу как PDF. Путь бэкенд строит сам,
// но сайдкар доступен всем контейнерам общей сети, поэтому проверка здесь, а не в надежде на вызывающего.
//
// /probe: проверка сайта площадки браузером. Адрес приходит из справочника площадок, который правят люди, — поэтому
// внутренние адреса (сеть контейнеров, метаданные облака, localhost) запрещены и для исходного адреса, и для любого
// запроса страницы после переадресаций.
const net = require('net');

function safePath(p) {
  if (typeof p !== 'string' || !p.startsWith('/') || p.length > 300) return false;
  if (p.includes('//') || p.includes('..') || p.includes('@') || p.includes('\\')) return false;
  return /^\/[A-Za-z0-9/_\-.]*$/.test(p);
}

function privateIp(ip) {
  if (!net.isIP(ip)) return true;                       // не адрес — не пускаем
  if (net.isIPv4(ip)) {
    const [a, b] = ip.split('.').map(Number);
    return a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31)
      || (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127) || a >= 224;
  }
  const v = ip.toLowerCase();
  if (v.startsWith('::ffff:')) return privateIp(v.slice(7));
  return v === '::1' || v === '::' || v.startsWith('fc') || v.startsWith('fd') || v.startsWith('fe8') || v.startsWith('fe9')
    || v.startsWith('fea') || v.startsWith('feb');
}

// /banner-check (15.11.2026): баннер из DSP рендерится как на площадке, но счётчики не должны сработать — проверочный
// показ не показ. Пропускаем то, из чего баннер рисуется (скрипты, стили, картинки, шрифты, медиа), и скрипт видимости
// DSP (он рисует плашку ЕРИД). Режем: сетевые вызовы скриптов (xhr/fetch/beacon/сокеты) — так стучат маяки; любые
// адреса домена DSP, кроме самого скрипта видимости (маяки и синхронизация живут на его соседних поддоменах); хосты из
// `block_hosts` (наш счётчик — он открывает скрытые фреймы с чужими рекламными блоками); переход на посадочную.
// Имён поставщика здесь нет: домен и адреса приходят от бэкенда из настроек.
const DRAW_TYPES = new Set(['document', 'script', 'stylesheet', 'image', 'font', 'media']);

function bannerRequestVerdict(url, resourceType, opts) {
  const o = opts || {};
  let u;
  try { u = new URL(url); } catch (e) { return 'abort'; }
  if (u.protocol === 'data:' || u.protocol === 'blob:') return resourceType === 'document' ? 'abort' : 'continue';
  if (u.protocol !== 'https:' && u.protocol !== 'http:') return 'abort';
  const host = u.hostname.toLowerCase();
  if (o.landing_host && host === o.landing_host) return 'abort';
  if (!DRAW_TYPES.has(resourceType)) return 'abort';
  if ((o.block_hosts || []).map((h) => String(h).toLowerCase()).includes(host)) return 'abort';
  const dom = String(o.block_domain || '').toLowerCase();
  if (dom && (host === dom || host.endsWith('.' + dom)) && !(o.allow_urls || []).some((a) => url.split('?')[0] === String(a).split('?')[0])) {
    return 'abort';
  }
  return 'continue';
}

module.exports = { safePath, privateIp, bannerRequestVerdict };
