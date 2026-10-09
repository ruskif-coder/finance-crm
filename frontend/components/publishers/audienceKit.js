// Общие правила экрана «Паблишеры → Аудитория»: цвет разрыва, состояние данных, поверхности.
// Живут в одном месте, потому что их читают и таблица, и карта, и карточка (макет Claude Design 09.10.2026):
// три копии порогов разошлись бы, а «красный» в одном месте и «жёлтый» в другом — тихо неверно.

export const GAP_RED = 10      // разрыв (уники ÷ заявленный MAU), % — ниже красный
export const GAP_YELLOW = 25   // ниже жёлтый, иначе зелёный
export const ACTIVE = 'СОТРУДНИЧАЕМ'   // статус площадки, с которой работаем

// [фон, текст] плашки разрыва; нет разрыва — фиолетовая (не измерено, а не «плохо»).
export const gapTone = (g) => (g == null
  ? ['var(--violet-tint)', 'var(--violet-fg)']
  : g < GAP_RED ? ['var(--danger-tint)', 'var(--danger-fg)']
    : g < GAP_YELLOW ? ['var(--warning-tint)', 'var(--warning-fg)']
      : ['var(--income-tint)', 'var(--income-fg)'])

// цвет полосы «уники» в сравнении
export const gapBar = (g) => (g == null ? 'var(--text-disabled)'
  : g < GAP_RED ? 'var(--danger)' : g < GAP_YELLOW ? 'var(--warning)' : 'var(--income)')

export const gapText = (p) => (p.gap_pct != null ? `${Math.round(p.gap_pct)} %`
  : (p.declared.mau ? 'нет уник.' : 'нет заявл.'))

// Состояние данных площадки — приоритет сверху вниз, как в макете: просроченный медиакит
// важнее прочего, дальше — чего не хватает. → [подпись, фон, текст, рамка, маркер]
export function dataOf(p) {
  const hasD = !!p.declared.mau, hasM = p.measured.shows != null && p.measured.shows > 0
  if (p.media_kit_stale) return ['медиакит > 6 мес.', 'var(--warning-tint)', 'var(--warning-fg)', 'var(--warning-border)', 'var(--warning)']
  if (!hasD && !hasM) return ['нет данных', 'var(--bg-subtle)', 'var(--text-faint)', 'var(--border-card)', 'var(--text-disabled)']
  if (!hasD) return ['только наши', 'var(--accent-tint)', 'var(--accent-fg)', 'var(--accent-border)', 'var(--accent)']
  if (!hasM) return ['без РК за окно', 'var(--warning-tint)', 'var(--warning-fg)', 'var(--warning-border)', 'var(--warning)']
  return ['полные', 'var(--income-tint)', 'var(--income-fg)', 'var(--income-border)', 'var(--income)']
}

export const surfacesOf = (p) => Object.keys(p.coverage || {}).sort().reverse().join(' + ')   // web + app

export const declVal = (p, key) => p.declared?.[key]?.value ?? null
