/**
 * Готовность сделки к пакету закрытия (сверка завершена / РК не завершена / …) — общая плашка модалки «Собрать ДС» и карточки
 * мастер-сделки. Своим файлом, а не экспортом из модалки (аудит 20.10.2026). Цвета — таблица §6 хендоффа «мастер и шапка».
 */
const PILL = {
  rk: ['var(--danger-tint)', 'var(--danger-fg)'], recon: ['var(--warning-tint)', 'var(--warning-fg)'],
  ready: ['var(--income-tint)', 'var(--income-fg)'], done: ['var(--income-tint)', 'var(--income-fg)'],
}

export function StatusPill({ state, text }) {
  const [bg, fg] = PILL[state] || PILL.recon
  return <span style={{ padding: '3px 10px', borderRadius: 7, fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap', background: bg, color: fg }}>{text}</span>
}
