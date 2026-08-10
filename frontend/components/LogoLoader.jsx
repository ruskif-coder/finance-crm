// Анимированный фирменный кубик SIMB-AD (из docs/Анимация кубика логотипа).
// Два режима: 'wave' (1a — импульс от синего модуля, загрузчик страниц) и
// 'spinner' (1c — модули гаснут по кругу, индикатор скачивания). Чистый inline-SVG
// + CSS @keyframes (mp-cube-pulse / mp-cube-trail в styles/globals.css), без зависимостей.

// 8 модулей знака: 7 чёрных + синий слева (blue). Порядок = порядок задержек ниже.
const TILES = [
  { d: 'M22.12 0.77C24.52 0.77 26.47 2.71 26.47 5.11V22.1C26.47 24.49 24.53 26.43 22.12 26.44H5.1C2.7 26.44 0.75 24.5 0.75 22.1V12.19H0.76C0.76 5.89 5.88 0.78 12.18 0.78H22.12V0.77Z' },
  { d: 'M55.24 0C57.99 0 60.21 2.22 60.21 4.97V22.27C60.21 25.01 57.99 27.24 55.24 27.24H37.94C35.19 27.24 32.97 25.01 32.97 22.27V4.97C32.97 2.22 35.19 0 37.94 0H55.24Z' },
  { d: 'M81.33 0.77C87.64 0.77 92.75 5.88 92.75 12.18V22.09C92.75 24.48 90.81 26.42 88.4 26.42H71.38C68.98 26.42 67.03 24.48 67.03 22.09V5.11H67.04C67.04 2.72 68.98 0.77 71.39 0.77H81.33Z' },
  { d: 'M88.19 32.96C90.94 32.96 93.16 35.19 93.16 37.93V55.23C93.16 57.97 90.94 60.2 88.19 60.2H70.9C68.16 60.2 65.93 57.97 65.93 55.23V37.93C65.93 35.19 68.16 32.96 70.9 32.96H88.19Z' },
  { d: 'M88.41 67.04C90.81 67.04 92.76 68.98 92.76 71.38V81.3C92.76 87.6 87.64 92.7 81.34 92.7H71.4C69 92.7 67.05 90.76 67.05 88.36V71.38H67.04C67.04 68.99 68.98 67.04 71.39 67.04H88.41Z' },
  { d: 'M55.24 65.92C57.99 65.92 60.21 68.15 60.21 70.89V88.19C60.21 90.94 57.99 93.16 55.24 93.16H37.94C35.19 93.16 32.97 90.94 32.97 88.19V70.89C32.97 68.15 35.19 65.92 37.94 65.92H55.24Z' },
  { d: 'M22.14 67.04C24.54 67.04 26.49 68.98 26.49 71.38V88.37C26.49 90.76 24.55 92.71 22.14 92.71H12.2C5.89 92.71 0.78 87.6 0.78 81.31V71.39H0.77C0.77 69 2.71 67.05 5.12 67.05H22.14V67.04Z' },
  { d: 'M0 37.93C0 35.19 2.23 32.96 4.97 32.96H22.27C25.02 32.96 27.24 35.19 27.24 37.93V55.23C27.24 57.97 25.02 60.2 22.27 60.2H4.97C2.23 60.19 0 57.96 0 55.22V37.93Z', blue: true },
]

// Задержки под каждый модуль (в секундах) — 1:1 из исходника анимаций.
const DELAYS = {
  wave: [0.28, 0.42, 0.56, 0.42, 0.56, 0.42, 0.28, 0],
  spinner: [0, -1.4, -1.2, -1, -0.8, -0.6, -0.4, -0.2],
}
const ANIM = {
  wave: 'mp-cube-pulse 2.4s ease-in-out infinite',
  spinner: 'mp-cube-trail 1.6s linear infinite',
}

export function Cube({ variant = 'wave', size = 96, accent = '#7096FC' }) {
  const delays = DELAYS[variant] || DELAYS.wave
  const anim = ANIM[variant] || ANIM.wave
  return (
    <svg width={size} height={size} viewBox="0 0 93.16 93.16" fill="none" aria-hidden="true">
      {TILES.map((t, i) => (
        <path key={i} data-tile="" d={t.d} fill={t.blue ? accent : '#111'}
          style={{ animation: anim, animationDelay: `${delays[i]}s` }} />
      ))}
    </svg>
  )
}

// Полноэкранный загрузчик страницы (1a «Волна»).
export function PageLoader() {
  return (
    <div style={overlay} role="status" aria-label="Загрузка">
      <Cube variant="wave" size={104} />
    </div>
  )
}

// Оверлей на время задачи (1c спиннер) + подпись + опциональный прогресс-бар {done,total}.
export function DownloadOverlay({ label = 'Готовим файл…', progress = null }) {
  const pct = progress && progress.total ? Math.round((progress.done / progress.total) * 100) : null
  return (
    <div style={{ ...overlay, background: 'rgba(20,22,28,.42)', backdropFilter: 'blur(3px)' }} role="status" aria-label={label}>
      <div style={card}>
        <Cube variant="spinner" size={72} />
        <span style={{ fontSize: 13, fontWeight: 600, color: '#3a3f4a', letterSpacing: '.01em' }}>
          {label}{progress ? ` — ${progress.done} из ${progress.total}` : ''}
        </span>
        {pct != null && (
          <div style={{ width: 220, height: 6, borderRadius: 3, background: '#e6e8ee', overflow: 'hidden' }}>
            <div style={{ width: pct + '%', height: '100%', background: '#4F6CE6', transition: 'width .25s ease' }} />
          </div>
        )}
      </div>
    </div>
  )
}

const overlay = {
  position: 'fixed', inset: 0, zIndex: 9999,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  background: 'rgba(247,248,250,.9)', backdropFilter: 'blur(2px)',
}
const card = {
  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14,
  padding: '26px 34px', background: '#fff', borderRadius: 16,
  boxShadow: '0 12px 40px rgba(20,22,28,.22)',
}

export default Cube
