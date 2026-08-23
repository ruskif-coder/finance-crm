/** @type {import('next').NextConfig} */
module.exports = {
  // ESLint подключён (npm run lint), но НЕ блокирует сборку. Next запускает линтер
  // внутри `next build` сам, как только видит .eslintrc.json — и падение линтера
  // становится падением сборки. Гейт из линтера заводится осознанно и после разбора
  // того, что он показывает, а не побочным эффектом установки зависимости.
  // Сейчас он показывает 5 мест с <a href> вместо <Link> на внутренние адреса.
  eslint: { ignoreDuringBuilds: true },
  // Версия приложения (из package.json) → в клиент, показывается в меню профиля.
  env: { NEXT_PUBLIC_APP_VERSION: require('./package.json').version },
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
  // Старые адреса живут за счёт этого слоя: по ним ходят закладки сотрудников и ссылки
  // внутри уже разосланных уведомлений (они лежат в notifications.link строками, задним
  // числом их не переписать). Временные (307), а не постоянные: постоянный редирект
  // браузер кэширует навсегда, и ошибка в адресе не лечится сбросом кэша у пользователя.
  async redirects() {
    const nav = require('./lib/nav.data.json')
    return nav.redirects.map(r => ({ source: r.from, destination: r.to, permanent: false }))
  },
}
