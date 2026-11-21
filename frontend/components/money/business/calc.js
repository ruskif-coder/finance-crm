// «Бизнес» — общие мелочи вкладки (хендофф design_handoff_money_navy, 20.11.2026): слои светофора, цвета, ветви прогноза.
// Суммы с сервера — в рублях, экран — в млн.

// [ключ, подпись, заливка, рамка, слой в реестре сделок]. «В работе» — --tl-work: днём --hot, ночью --ok (styles/navy.css).
export const LAYERS = [
  ['docs', 'Подкреплено документами', 'var(--money)', 'var(--money)', 'фактические'],
  ['work', 'В работе', 'var(--tl-work)', 'var(--tl-work)', 'реализуемые'],
  ['mid', 'Планы · средняя вероятность', 'var(--attn)', 'var(--attn)', 'планируемые'],
  ['low', 'Планы · низкая', 'var(--bg-subtle)', 'var(--border-hover)', 'планируемые'],
]
export const layerOf = (k) => LAYERS.find(l => l[0] === k)

export const m1 = (v) => ((v || 0) / 1e6).toFixed(1).replace('.', ',')
/** «+12 %» / «−37 %» — к прошлому году и к плану */
export const pc = (v) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(Math.round(v))} %`)
export const vs = (a, b) => (b ? (a / b - 1) * 100 : null)
export const sure = (m) => m.docs + m.work                 // «надёжно» — документы и в работе
export const likely = (m) => sure(m) + m.mid               // «с вероятными» — плюс средняя вероятность из разметки продаж
