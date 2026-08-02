/** @type {import('next').NextConfig} */
module.exports = {
  // Не даём Next редиректить трейлинг-слэш: иначе /api/operations/ → 308 → /api/operations,
  // а FastAPI 307 возвращает слэш обратно → петля (эндпойнты со слэшем не грузятся на :3000).
  skipTrailingSlashRedirect: true,
  // Локальная разработка: браузер бьёт в /api того же origin (:3000), Next проксирует на backend.
  // Явный rewrite со слэшем идёт ПЕРВЫМ, чтобы /api/foo/ проксировался как /api/foo/ (без потери
  // слэша), иначе catch-all теряет его. На проде /api перехватывает Caddy ДО Next — здесь безопасно.
  async rewrites() {
    return [
      { source: '/api/:path*/', destination: 'http://backend:8000/api/:path*/' },
      { source: '/api/:path*', destination: 'http://backend:8000/api/:path*' },
    ]
  },
}
