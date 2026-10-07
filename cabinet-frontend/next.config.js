/** @type {import('next').NextConfig} */
module.exports = {
  // Оптимизатор картинок Next (`/_next/image`) выключен: `next/image` в кабинете не используется, а эндпоинт
  // при `next start` по умолчанию живой и отвечает снаружи (проверено 07.10.2026: 200 на lk.simb-ad.com).
  // Это внешний сайт площадок; на оптимизатор приходятся самые тяжёлые записи аудита next 14.
  images: { unoptimized: true },
  // Не даём Next редиректить трейлинг-слэш: иначе /api/foo/ → 308 → /api/foo,
  // а FastAPI 307 возвращает слэш обратно — получается петля. Та же причина,
  // что и в финмодуле.
  skipTrailingSlashRedirect: true,
  // Версия кабинета инлайнится при СБОРКЕ — тем же способом, что в финмодуле. Отсюда
  // следствие, которое стоит помнить: старая версия в подвале означает, что фронт не
  // пересобрали, а не что правка не доехала.
  env: { NEXT_PUBLIC_CABINET_VERSION: require('./package.json').version },
  // Локальная разработка без Caddy: браузер бьёт в /api того же origin, Next проксирует
  // на бэкенд кабинета. На проде /api перехватывает Caddy ДО Next.
  async rewrites() {
    return [
      { source: '/api/:path*/', destination: 'http://cabinet_backend:8001/api/:path*/' },
      { source: '/api/:path*', destination: 'http://cabinet_backend:8001/api/:path*' },
    ]
  },
}
