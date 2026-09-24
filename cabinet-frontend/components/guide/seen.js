/**
 * «Руководство уже показывали» — в браузере, без базы (решение владельца 24.09.2026).
 * Отдельный лёгкий модуль: импорт из `Guide.jsx` затянул бы слайды в основной чанк.
 * Приватный режим — считаем показанным: окно на каждом входе хуже, чем ни разу.
 */
export const GUIDE_SEEN_KEY = 'cabinet_guide_seen'

export function guideSeen() {
  try { return localStorage.getItem(GUIDE_SEEN_KEY) === '1' } catch { return true }
}

export function markGuideSeen() {
  try { localStorage.setItem(GUIDE_SEEN_KEY, '1') } catch { /* приватный режим */ }
}
