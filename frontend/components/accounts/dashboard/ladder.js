// Лестница стадий дашборда аккаунта (макет «акки 3», решения владельца 28.09.2026).
//
// Слот строки (`row.slot`) считает сервер — app/sales/stage_slots.py сопоставляет стадии
// по имени в одном месте. Здесь только то, как слоты складываются на экране:
//   * «В работе» и быстрые пины — ОДИН фильтр (`stage`): клик там и тут — одно состояние;
//   * ЭДО в лестнице не выделен — входит в «Закрытие» (владелец 28.09.2026);
//   * «Без стадии» в лестнице нет: такие строки видны только в таблице.

// fill — сколько клеток 2\2\2 закрашено (серый ×2 · жёлтый ×2 · зелёный ×2).
export const LADDER = [
  { key: 'mp_prep', label: 'МП Подготовка', slots: ['mp_prep'], fill: 1 },
  { key: 'mp_sent', label: 'МП Отправлено', slots: ['mp_sent'], fill: 1 },
  { key: 'booking', label: 'Бронь', slots: ['booking'], fill: 2 },
  { key: 'prep', label: 'Готовятся к старту', slots: ['prep'], fill: 3 },
  { key: 'live', label: 'В размещении', slots: ['live'], fill: 4 },
  { key: 'recon', label: 'Итоговая сверка', slots: ['recon'], fill: 5 },
  { key: 'closing', label: 'Закрытие', slots: ['ds_prep', 'ds_agree', 'closing', 'edo'], fill: 5 },
  { key: 'ord', label: 'Отчёты в ОРД', slots: ['ord'], fill: 5 },
  { key: 'pay', label: 'Оплата', slots: ['pay'], fill: 6 },
]
export const LADDER_BY_KEY = Object.fromEntries(LADDER.map(s => [s.key, s]))

// Быстрые пины в шапке таблицы — пять участков работы аккаунта (макет) плюс два особых:
// «Без срочности» (владелец 28.09.2026) и «⏱ Отложено».
export const QUICK = [
  ['Нужен МП', 'mp_prep'], ['Брони', 'booking'], ['Сборка', 'prep'],
  ['Сверка', 'recon'], ['Закрытие', 'closing'],
]

// Порядок слотов для сортировки по колонке «Стадия» — ход сделки по конвейеру.
export const SLOT_ORDER = ['unmapped', 'mp_prep', 'mp_sent', 'booking', 'prep', 'live', 'recon',
  'ds_prep', 'ds_agree', 'closing', 'edo', 'ord', 'pay']

export const inStage = (row, stageKey) =>
  !stageKey || (LADDER_BY_KEY[stageKey]?.slots || []).includes(row.slot)

// Цвет слоя денег — точка у названия стадии. Нет слоя — стадия не разобрана: красный.
export const LAYER_DOT = {
  'планируемые': 'var(--text-faint)',
  'реализуемые': 'var(--dot-current-dz)',
  'фактические': 'var(--income)',
}

// Тон срочности — точка в колонке «Что сделать» (горит / сегодня / скоро / в норме).
export const URGENCY_DOT = {
  overdue: 'var(--danger)', today: 'var(--dot-current-dz)',
  soon: 'var(--warning)', normal: 'var(--border-hover)',
}
export const URGENCY_RANK = { overdue: 0, today: 1, soon: 2, normal: 3 }

// Порядок по умолчанию (владелец 27–28.09.2026): рабочие строки по срочности и сроку →
// ЭДО и Оплата → «Без срочности» в самом конце. Внутри групп — порядок сервера
// (срочность, ближайший срок), поэтому сортировка стабильная.
export const defaultRank = (r) => (r.calm ? 2 : (r.tail ? 1 : 0))

export const mln = (n) => {
  if (!n) return '—'
  if (n >= 1e6) return `${(n / 1e6).toFixed(2).replace('.', ',')} млн ₽`
  return `${Math.round(n / 1e3)} тыс ₽`
}

// Значение для сортировки по колонке. Пустое — всегда в конце (null), см. compareRows.
export const sortVal = (r, key) => {
  switch (key) {
    case 'code': return r.code || null
    case 'advertiser': return (r.advertiser || r.title || '').toLowerCase() || null
    case 'agency': return (r.agency || '').toLowerCase() || null
    case 'product': return (r.product || '').toLowerCase() || null
    case 'amount': return r.amount || null
    case 'stage': return SLOT_ORDER.indexOf(r.slot) >= 0 ? SLOT_ORDER.indexOf(r.slot) : null
    case 'period': return r.period_from || null
    case 'todo': return URGENCY_RANK[r.urgency] ?? null
    default: return null
  }
}

export const compareRows = (key, dir) => (a, b) => {
  const va = sortVal(a, key), vb = sortVal(b, key)
  if (va == null || vb == null) return (va == null) - (vb == null)
  const k = dir === 'desc' ? -1 : 1
  if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * k
  return String(va).localeCompare(String(vb), 'ru', { numeric: true }) * k
}
