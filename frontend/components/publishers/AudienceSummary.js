import { MONO, UI } from '@/components/salesTableKit'
import { shortNum, pct } from '@/lib/salesFormat'
import { dataOf, gapBar, gapTone, GAP_RED, GAP_YELLOW } from '@/components/publishers/audienceKit'

// Сводная по всем площадкам — правый блок, пока ни одна площадка не выбрана (владелец 09.10.2026).
// Считает по тому же набору, что таблица и карта («Активные / Все»), и ничего не придумывает:
// уники есть не у всех, поэтому сравнение «заявлено ↔ подтверждено» берёт только площадки, у которых
// есть И заявленный MAU, И уники, — иначе сумма MAU без уников выглядела бы огромным «разрывом».

const mono = (extra) => ({ fontFamily: MONO, ...extra })
const capS = (color = 'var(--text-cap)') => mono({ fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color })
const tiny = mono({ fontSize: 8.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' })
const box = (bg, extra) => ({ display: 'flex', flexDirection: 'column', gap: 8, padding: '12px 14px', background: bg, borderRadius: 12, ...extra })
const sum = (arr, f) => arr.reduce((a, p) => a + (f(p) || 0), 0)

const Stat = ({ k, v, n, fg }) => (
  <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
    <span style={tiny}>{k}</span>
    <span style={mono({ fontSize: 13, fontWeight: 700, color: fg })}>{v}</span>
    {!!n && <span style={{ fontSize: 9.5, color: 'var(--text-faint)' }}>{n}</span>}
  </span>
)

// полоса из долей: [{n, color, label}]
const Stack = ({ parts }) => {
  const total = parts.reduce((a, x) => a + x.n, 0) || 1
  return (
    <span style={{ display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden', gap: 2 }}>
      {parts.filter(x => x.n).map(x => <span key={x.label} title={`${x.label}: ${x.n}`} style={{ width: `${(x.n / total) * 100}%`, background: x.color }} />)}
    </span>
  )
}
const Legend = ({ parts }) => (
  <span style={{ display: 'flex', flexWrap: 'wrap', gap: '3px 12px' }}>
    {parts.map(x => (
      <span key={x.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
        <span style={{ width: 8, height: 8, borderRadius: 2, background: x.color }} />{x.label} <b style={mono({ color: 'var(--text-primary)' })}>{x.n}</b>
      </span>
    ))}
  </span>
)

export default function AudienceSummary({ publishers, days, onSelect }) {
  const withBoth = publishers.filter(p => p.declared.mau && p.measured.uniques != null)
  const mauB = sum(withBoth, p => p.declared.mau.value), uqB = sum(withBoth, p => p.measured.uniques)
  const gap = mauB ? (uqB / mauB) * 100 : null
  const gFg = gapTone(gap)[1]
  const maxBar = Math.max(mauB, uqB, 1)

  const shows = sum(publishers, p => p.measured.shows), ver = sum(publishers, p => p.measured.verifier_shows)
  const clicks = sum(publishers, p => p.measured.clicks)
  const withShows = publishers.filter(p => p.measured.shows)

  const gapParts = [
    { label: `< ${GAP_RED} %`, color: 'var(--danger)', n: publishers.filter(p => p.gap_pct != null && p.gap_pct < GAP_RED).length },
    { label: `${GAP_RED}–${GAP_YELLOW} %`, color: 'var(--warning)', n: publishers.filter(p => p.gap_pct != null && p.gap_pct >= GAP_RED && p.gap_pct < GAP_YELLOW).length },
    { label: `≥ ${GAP_YELLOW} %`, color: 'var(--income)', n: publishers.filter(p => p.gap_pct != null && p.gap_pct >= GAP_YELLOW).length },
    { label: 'нет разрыва', color: 'var(--violet-fg)', n: publishers.filter(p => p.gap_pct == null).length },
  ]
  const states = ['полные', 'только наши', 'без РК за окно', 'медиакит > 6 мес.', 'нет данных']
  const stateColor = { 'полные': 'var(--income)', 'только наши': 'var(--accent)', 'без РК за окно': 'var(--warning)', 'медиакит > 6 мес.': 'var(--accent-soft)', 'нет данных': 'var(--text-disabled)' }
  const dataParts = states.map(label => ({ label, color: stateColor[label], n: publishers.filter(p => dataOf(p)[0] === label).length }))

  const kinds = [...new Set(publishers.map(p => p.kind || '—'))].sort().map(k => {
    const ps = publishers.filter(p => (p.kind || '—') === k)
    return { k, n: ps.length, mau: sum(ps, p => p.declared.mau?.value) || null, uq: sum(ps, p => p.measured.uniques) || null, shows: sum(ps, p => p.measured.shows) || null }
  })
  const worst = [...withBoth].sort((a, b) => a.gap_pct - b.gap_pct).slice(0, 5)
  const biggest = [...withShows].sort((a, b) => b.measured.shows - a.measured.shows).slice(0, 5)
  const maxShows = biggest[0]?.measured.shows || 1

  const list = (title, rows, right) => (
    <div style={box('var(--bg-subtle)', { gap: 6 })}>
      <span style={capS()}>{title}</span>
      {rows.length ? rows.map(p => (
        <span key={p.id} onClick={() => onSelect(p.id)} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 70px', gap: 8, alignItems: 'center', cursor: 'pointer', fontSize: 12 }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 600 }}>{p.name}</span>
          {right(p)}
        </span>
      )) : <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>пока нет данных</span>}
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, fontFamily: UI }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: '-.02em' }}>Сводная по всем площадкам</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{publishers.length} площадок · окно {days} дн.</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-faint)' }}>выберите площадку на карте или в таблице</span>
      </div>

      <div style={box('var(--bg-tint)', { border: '1px solid var(--accent-border)', gap: 9 })}>
        <span style={capS('var(--accent-fg)')}>Заявлено ↔ подтверждено · по площадкам с обоими числами ({withBoth.length})</span>
        {[{ label: 'Σ MAU заявлен', v: mauB, bg: 'var(--accent-soft)', fg: 'var(--text-primary)' }, { label: 'Σ уники под рекламой', v: uqB, bg: gapBar(gap), fg: gFg }].map(c => (
          <span key={c.label} style={{ display: 'grid', gridTemplateColumns: '130px minmax(0, 1fr) 92px', gap: 10, alignItems: 'center' }}>
            <span style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>{c.label}</span>
            <span style={{ height: 12, background: 'var(--border-inner)', borderRadius: 4, overflow: 'hidden' }}>
              <span style={{ display: 'block', height: '100%', width: `${(c.v / maxBar) * 100}%`, background: c.bg, borderRadius: 4 }} />
            </span>
            <span style={mono({ fontSize: 12.5, fontWeight: 700, color: c.fg, textAlign: 'right' })}>{withBoth.length ? shortNum(c.v) : '—'}</span>
          </span>
        ))}
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, paddingTop: 4, borderTop: '1px solid var(--accent-border)' }}>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>разрыв в целом</span>
          <span style={mono({ fontSize: 15, fontWeight: 700, color: gap == null ? 'var(--text-disabled)' : gFg })}>{gap == null ? '—' : `${Math.round(gap)} %`}</span>
          <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-faint)' }}>уники ÷ заявленный MAU · верхняя оценка</span>
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 12 }}>
        <div style={box('var(--bg-subtle)')}>
          <span style={capS()}>Разрыв по площадкам</span>
          <Stack parts={gapParts} />
          <Legend parts={gapParts} />
          <span style={{ ...capS(), marginTop: 4 }}>Полнота данных</span>
          <Stack parts={dataParts} />
          <Legend parts={dataParts} />
        </div>
        <div style={box('var(--income-bg)', { border: '1px solid var(--income-border)' })}>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={capS('var(--income-fg)')}>Подтверждено нами</span>
            <span style={mono({ marginLeft: 'auto', fontSize: 9, color: 'var(--text-faint)' })}>{days} дн. · наш счётчик</span>
          </span>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
            <span style={mono({ fontSize: 24, fontWeight: 700, letterSpacing: '-.03em', lineHeight: 1 })}>{shortNum(shows || null)}</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>показов</span>
          </span>
          <span style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8 }}>
            <Stat k="верификатор" v={shortNum(ver || null)} n="Weborama, отдельно" fg="var(--text-secondary)" />
            <Stat k="CTR" v={shows ? pct((clicks / shows) * 100) : '—'} n={`${clicks} кликов`} fg="var(--text-secondary)" />
            <Stat k="площадок с показами" v={`${withShows.length} / ${publishers.length}`} />
            <Stat k="уники" v={shortNum(sum(publishers, p => p.measured.uniques) || null)} n="верхняя оценка" />
          </span>
        </div>
      </div>

      <div style={box('var(--bg-subtle)', { gap: 4, padding: '10px 14px' })}>
        <span style={capS()}>По видам площадок</span>
        <span style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) 56px 1fr 1fr 1fr', gap: 8, ...tiny }}>
          <span>вид</span><span style={{ textAlign: 'right' }}>площ.</span><span style={{ textAlign: 'right' }}>MAU</span><span style={{ textAlign: 'right' }}>уники</span><span style={{ textAlign: 'right' }}>показы</span>
        </span>
        {kinds.map(r => (
          <span key={r.k} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) 56px 1fr 1fr 1fr', gap: 8, fontSize: 12, alignItems: 'center' }}>
            <span style={{ fontWeight: 600 }}>{r.k}</span>
            <span style={mono({ textAlign: 'right' })}>{r.n}</span>
            <span style={mono({ textAlign: 'right' })}>{shortNum(r.mau)}</span>
            <span style={mono({ textAlign: 'right' })}>{shortNum(r.uq)}</span>
            <span style={mono({ textAlign: 'right' })}>{shortNum(r.shows)}</span>
          </span>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 12 }}>
        {list('Наименьший разрыв (заявлено завышено)', worst, p => <span style={mono({ textAlign: 'right', fontWeight: 700, color: gapTone(p.gap_pct)[1] })}>{Math.round(p.gap_pct)} %</span>)}
        {list('Крупнейшие по показам', biggest, p => (
          <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
            <span style={mono({ fontSize: 11, fontWeight: 700 })}>{shortNum(p.measured.shows)}</span>
            <span style={{ width: 60, height: 3, background: 'var(--border-inner)', borderRadius: 2, overflow: 'hidden' }}>
              <span style={{ display: 'block', height: '100%', width: `${(p.measured.shows / maxShows) * 100}%`, background: 'var(--accent-soft)' }} />
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}
