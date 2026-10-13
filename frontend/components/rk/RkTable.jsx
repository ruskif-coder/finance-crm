// Таблица «Разбора РК» в выбранном разрезе: одна сетка на шапку, строки и итог; сортировка по клику на
// заголовок; клик по строке — проваливание. Колонка выбранной метрики подсвечена.
import { MONO, UI } from '@/components/salesTableKit'
import { nf, rub, pf, sg, dm, box, title14, pctTone, WR_TONE } from './rkUi'

const WIDTH = { date: '78px', text: 'minmax(130px,1.4fr)', num: 'minmax(70px,1fr)', pct: '66px', pct1: '56px', wrd: '72px', ctr: '62px', rub: 'minmax(78px,1fr)' }
const METRIC_KEY = { shows: 'fact', clicks: 'clk', ctr: 'ctr', offered: 'off', plan: 'pct', spend: 'spend', cpm: 'cpm' }

export function cellText(c, v) {
  if (v == null) return '—'
  switch (c.kind) {
    case 'date': return /^\d{4}-\d\d-\d\d$/.test(v) ? dm(v) : v
    case 'num': return nf(v)
    case 'pct': return pf(v, 0)
    case 'pct1': return pf(v, 1)
    case 'ctr': return pf(v, 2)
    case 'wrd': return sg(v)
    case 'rub': return rub(v)
    default: return String(v)
  }
}

// Подсказки к колонкам плана: план дня считается по недокруту прошлых дней, а не плоско (владелец 13.10.2026).
const COL_HINT = {
  plan: 'План дня = (план − факт до этого дня) ÷ дни до конца флайта, считая этот. Недокрут прошлых дней поднимает план следующих, перекрут (в том числе после «темпа размещения») — снижает. В дни «темпа размещения» (строки подкрашены зелёным) план поднят на процент буста.',
  pct: 'Факт дня ÷ план дня (с учётом недокрута прошлых дней).',
}

export default function RkTable({ model, metric, sort, setSort, onDrill, drill, crumb, onUndrill, drillView, setDrillView, focus, weekLabel }) {
  const { cols, rows, tot, view } = model
  const hot = METRIC_KEY[metric]
  const def = view === 'day' || view === 'week' ? { key: 'label', dir: 1 } : { key: 'fact', dir: -1 }
  const so = sort || def
  const sorted = rows.slice().sort((a, b) => {
    const x = a[so.key], y = b[so.key]
    if (x == null) return 1
    if (y == null) return -1
    return (x > y ? 1 : x < y ? -1 : 0) * so.dir
  })
  const grid = cols.map(c => WIDTH[c.kind] || '1fr').join(' ')
  const minW = Math.max(720, cols.length * 80)
  const label = (r, c) => (c.key === 'label' && view === 'week' ? weekLabel(r) : cellText(c, r[c.key]))
  const toneOf = (c, r) => (c.key === 'pct' ? pctTone(r.pct) : c.key === 'wrd' ? WR_TONE[r.wrLevel] || 'var(--text-faint)'
    : c.key === hot ? 'var(--text-primary)' : c.kind === 'text' || c.kind === 'date' ? 'var(--text-primary)' : 'var(--text-secondary)')
  const footVal = (c, i) => {
    if (i === 0) return `Итого · ${rows.length}`
    if (['dsp', 'adf', 'fact', 'plan', 'wr', 'clk', 'off', 'uni'].includes(c.key)) return nf(tot[c.key])
    if (c.key === 'spend') return rub(tot.spend)
    if (c.key === 'pct') return pf(tot.pct, 0)
    if (c.key === 'wrd') return sg(tot.wrd)
    if (c.key === 'ctr') return pf(tot.ctr, 2)
    if (c.key === 'cpm') return rub(tot.cpm)
    return ''
  }
  return (
    <div style={{ ...box, flex: '1 1 640px', minWidth: 0, alignSelf: 'stretch', boxSizing: 'border-box', padding: '12px 16px 10px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={title14}>Таблица</span>
        <button type="button" onClick={onUndrill} style={{ height: 24, padding: '0 9px', borderRadius: 7, fontSize: 11.5, fontWeight: 600, fontFamily: UI, cursor: drill ? 'pointer' : 'default',
          background: drill ? 'var(--bg-card)' : 'var(--bg-subtle)', border: `1px solid ${drill ? 'var(--border-card)' : 'transparent'}`, color: drill ? 'var(--accent)' : 'var(--text-muted)' }}>
          {drill ? '← ' : ''}{crumb.base}</button>
        {!!drill && (
          <button type="button" onClick={onUndrill} style={{ height: 24, padding: '0 9px', borderRadius: 7, fontSize: 11.5, fontWeight: 600, fontFamily: UI, cursor: 'pointer',
            background: 'var(--accent-tint)', border: '1px solid var(--accent-border)', color: 'var(--accent-fg)' }}>{crumb.drill} ×</button>
        )}
        {drill?.type === 'placement' && (
          <span style={{ display: 'inline-flex', padding: 2, gap: 2, background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 8 }}>
            {[['day', 'дни'], ['creative', 'креативы']].map(([v, l]) => (
              <button key={v} type="button" onClick={() => setDrillView(v)} style={{ height: 20, padding: '0 8px', borderRadius: 6, border: 'none', fontSize: 11, fontFamily: UI, cursor: 'pointer',
                background: drillView === v ? 'var(--bg-card)' : 'transparent', color: drillView === v ? 'var(--accent)' : 'var(--text-secondary)', fontWeight: drillView === v ? 700 : 600 }}>{l}</button>
            ))}
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{drill ? 'провал · срез сохранён · Esc — назад' : 'клик по строке — провалиться'}</span>
      </div>
      <div style={{ flex: '1 1 0', minHeight: 280, maxHeight: 640, overflowX: 'auto', display: 'flex', flexDirection: 'column' }}>
        <div style={{ flex: '1 1 0', minHeight: 0, minWidth: minW, display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'grid', gridTemplateColumns: grid, gap: 10, padding: '0 8px 7px', borderBottom: '1px solid var(--border-card)' }}>
            {cols.map(c => {
              const on = so.key === c.key
              const right = !['text', 'date'].includes(c.kind)
              return (
                <span key={c.key} onClick={() => setSort({ key: c.key, dir: on ? -so.dir : right ? -1 : 1 })} title={COL_HINT[c.key] || 'сортировать'}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4, justifyContent: right ? 'flex-end' : 'flex-start', fontFamily: MONO, fontSize: 9, letterSpacing: '.06em',
                    textTransform: 'uppercase', color: c.key === hot ? 'var(--accent)' : on ? 'var(--text-primary)' : 'var(--text-cap)', fontWeight: c.key === hot ? 700 : 400,
                    cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}>{c.label}<span style={{ fontSize: 8 }}>{on ? (so.dir > 0 ? '▲' : '▼') : ''}</span></span>
              )
            })}
          </div>
          <div style={{ flex: '1 1 0', minHeight: 0, overflowY: 'auto' }}>
            {sorted.map(r => (
              <div key={r.id} onClick={() => r.drill && onDrill(r.drill)} title={r.boost ? `Темп размещения +${r.boost} %: план дня поднят на этот процент` + (r.drill ? ' · клик — провалиться' : '') : (r.drill ? 'провалиться' : '')}
                style={{ display: 'grid', gridTemplateColumns: grid, gap: 10, alignItems: 'center', padding: '6px 8px', borderBottom: '1px solid var(--border-row)', borderRadius: 7,
                  background: focus != null && (focus === r.id) ? 'var(--accent-tint)' : r.boost ? 'var(--income-tint)' : 'transparent', cursor: r.drill ? 'pointer' : 'default' }}>
                {cols.map(c => {
                  const right = !['text', 'date'].includes(c.kind)
                  return (
                    <span key={c.key} style={{ fontFamily: right ? MONO : UI, fontSize: right ? 11.5 : 12, fontWeight: c.key === hot || c.key === 'label' ? 700 : 400, color: toneOf(c, r),
                      textAlign: right ? 'right' : 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label(r, c)}</span>
                  )
                })}
              </div>
            ))}
            {!sorted.length && <div style={{ padding: 20, fontSize: 12, color: 'var(--text-muted)' }}>В этом срезе нет данных.</div>}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: grid, gap: 10, padding: '8px 8px 2px', borderTop: '1px solid var(--border-card)' }}>
            {cols.map((c, i) => (
              <span key={c.key} style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, textAlign: i === 0 || ['text', 'date'].includes(c.kind) ? 'left' : 'right',
                color: c.key === 'pct' ? pctTone(tot.pct) : c.key === 'wrd' ? WR_TONE[tot.wrLevel] || 'var(--text-primary)' : 'var(--text-primary)',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{footVal(c, i)}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
