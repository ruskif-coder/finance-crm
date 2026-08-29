/** @type {import('next').NextConfig} */
module.exports = {
  // Не даём Next редиректить трейлинг-слэш: иначе /api/foo/ → 308 → /api/foo,
  // а FastAPI 307 возвращает слэш обратно — получается петля. Та же причина,
  // что и в финмодуле.
  skipTrailingSlashRedirect: true,
  // Локальная разработка без Caddy: браузер бьёт в /api того же origin, Next проксирует
  // на бэкенд кабинета. На проде /api перехватывает Caddy ДО Next.
  async rewrites() {
    return [
      { source: '/api/:path*/', destination: 'http://cabinet_backend:8001/api/:path*/' },
      { source: '/api/:path*', destination: 'http://cabinet_backend:8001/api/:path*' },
    ]
  },
}
