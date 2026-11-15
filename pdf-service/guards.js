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

module.exports = { safePath, privateIp };
