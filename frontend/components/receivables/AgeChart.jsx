/** «Возраст задолженности» в рублях (хендофф, п. 3): по договору — 7 корзин дней к сроку; на деле — 5 корзин «когда придут деньги»
 *  парой столбиков (пунктир — по договору, сплошной — на деле). Наведение — подсказка, клик — отбор в таблице. */
import { useState } from 'react'
import { CAPS, H, MONO, f } from '@/components/money/kit'
import { invL, cpL, pl } from './model'

const mln = (n) => (n / 1e6).toFixed(2).replace('.', ',') + ' млн'
const Lg = ({ c, dashed, children }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
    <span style={{ width: dashed ? 10 : 8, height: dashed ? 10 : 8, borderRadius: 2, ...(dashed ? { border: '1.5px dashed var(--border-hover)', boxSizing: 'border-box' } : { background: c }) }} />{children}</span>
)

function Tip({ b, right }) {
  return (
    <div style={{ position: 'absolute', zIndex: 20, top: 8, left: right ? 'auto' : '100%', right: right ? '100%' : 'auto', width: 290, padding: '12px 14px', borderRadius: 14,
      background: 'var(--bg-card)', border: '1px solid var(--border-hover)', boxShadow: 'var(--shadow-float, var(--shadow-card))', display: 'flex', flexDirection: 'column', gap: 4,
      pointerEvents: 'none', textAlign: 'left' }}>
      <span style={CAPS}>{b.head}</span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}><span style={{ width: 10, height: 10, borderRadius: 2, background: b.c }} />
        <span style={{ fontFamily: MONO, fontSize: 19, fontWeight: 700, color: b.fg }}>{f(b.sum)} ₽</span></span>
      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{invL(b.n)} · {cpL(b.top.length)} · {b.pct} % портфеля</span>
      <span style={{ ...CAPS, marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-inner)' }}>крупнейшие контрагенты</span>
      {b.top.slice(0, 5).map(a => (
        <span key={a.who} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto auto', gap: 10, alignItems: 'baseline', padding: '2px 0' }}>
          <span style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.who}</span>
          <span style={{ fontSize: 10.5, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{a.n} сч.</span>
          <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap', minWidth: 58, textAlign: 'right' }}>{mln(a.v)}</span>
        </span>
      ))}
      <span style={{ marginTop: 6, fontSize: 11, color: 'var(--text-muted)' }}>{b.top.length > 5 ? `и ещё ${b.top.length - 5} · ` : ''}клик — показать эти счета в таблице</span>
    </div>
  )
}

/** Корзины: [{ label, sum, n, c, fg, head, top, pct, sumC (по договору — только «на деле») }] */
export function ageBuckets(all, bk, real) {
  const tot = all.reduce((a, x) => a + x.sum, 0) || 1
  const out = bk.labels.map((label, k) => ({ label, k, sum: 0, n: 0, sumC: 0, by: {} }))
  all.forEach(x => x.its.forEach(it => {
    const k = bk.of(x, it)
    if (k < 0) return
    const q = out[k]; q.sum += it.v; q.n += 1
    const a = q.by[x.who] || (q.by[x.who] = { who: x.who, n: 0, v: 0 }); a.n += 1; a.v += it.v
    if (real && it.srok) out[bk.mIdx(it.srok)].sumC += it.v
  }))
  return out.map(q => {
    const c = real ? (q.k === 0 ? 'var(--bad)' : 'var(--ok)') : q.k < 3 ? 'var(--ok)' : q.k < 5 ? 'var(--attn)' : 'var(--bad)'
    const st = real ? (q.k === 0 ? 'уже должны были заплатить' : 'придут на деле') : q.k < 3 ? 'до срока' : q.k < 5 ? 'текущая' : 'просрочка'
    return { ...q, c, fg: (!real && q.k >= 5 && q.sum) || (real && q.k === 0 && q.sum) ? 'var(--bad-fg)' : 'var(--text-primary)', head: `${q.label} · ${st}`,
      top: Object.values(q.by).sort((a, b) => b.v - a.v), pct: Math.round(q.sum / tot * 100) }
  })
}

export default function AgeChart({ buckets, real, sel, onPick }) {
  const [hov, setHov] = useState(null)
  const max = Math.max(1, ...buckets.map(q => Math.max(q.sum, q.sumC)))
  const n = buckets.length
  const cols = `repeat(${n}, minmax(0,1fr))`
  const on = sel != null
  return (
    <div data-motion="rise" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 20, padding: '20px 22px',
      display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <span style={H}>Возраст задолженности</span>
        <span style={CAPS}>{real ? 'когда придут деньги: на деле (сплошной) и по договору (пунктир) · рубли' : 'дней к сроку оплаты · «−» до срока, «+» после · рубли'}</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 14, fontSize: 12, color: 'var(--text-secondary)' }}>
          {real ? <><Lg dashed>по договору</Lg><Lg c="var(--ok)">как платят на деле</Lg><Lg c="var(--bad)">уже должны были заплатить</Lg></>
            : <><Lg c="var(--ok)">до срока</Lg><Lg c="var(--attn)">текущая · до 30 дн после срока</Lg><Lg c="var(--bad)">просрочка</Lg></>}
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 14, alignItems: 'end', height: 210, paddingTop: 8, borderBottom: '1px solid var(--border-inner)' }}>
        {buckets.map(b => {
          const has = b.sum > 0, picked = sel === b.k
          return (
            <div key={b.k} onClick={() => has && onPick(picked ? null : b.k)} onMouseEnter={() => setHov(b.k)} onMouseLeave={() => setHov(h => (h === b.k ? null : h))}
              style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', gap: 6, height: '100%',
                opacity: on && !picked ? 0.4 : 1, cursor: has ? 'pointer' : 'default', borderRadius: 10, boxShadow: picked ? 'inset 0 0 0 1.5px var(--hot)' : 'none', padding: '0 4px',
                transition: 'opacity var(--dur-base) var(--ease-out)' }}>
              <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: b.fg, whiteSpace: 'nowrap' }}>{b.sum ? mln(b.sum) : '0'}</span>
                {real && <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>по договору {mln(b.sumC)}</span>}
              </span>
              <span style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'center', gap: 5, width: '100%' }}>
                {real && <span style={{ width: '30%', height: Math.round(b.sumC / max * 140), borderRadius: '6px 6px 2px 2px', border: '1.5px dashed var(--border-hover)', borderBottom: 'none', boxSizing: 'border-box' }} />}
                <span style={{ width: real ? '30%' : '72%', height: Math.round(b.sum / max * (real ? 140 : 150)), minHeight: 2, borderRadius: '6px 6px 2px 2px', background: b.c,
                  transition: 'height var(--dur-slow) var(--ease-out)' }} />
              </span>
              {hov === b.k && has && <Tip b={b} right={b.k >= n - 2} />}
            </div>
          )
        })}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 14 }}>
        {buckets.map(b => (
          <span key={b.k} onClick={() => b.sum > 0 && onPick(sel === b.k ? null : b.k)} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1,
            opacity: on && sel !== b.k ? 0.4 : 1, cursor: b.sum > 0 ? 'pointer' : 'default' }}>
            <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', fontWeight: sel === b.k ? 800 : 500 }}>{b.label}</span>
            <span style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>{b.n ? `${b.n} ${pl(b.n, 'счёт', 'счёта', 'счетов')}` : '—'}</span>
          </span>
        ))}
      </div>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        {real ? `На деле до конца месяца придёт ${mln(buckets[1]?.sum || 0)} вместо ${mln(buckets[1]?.sumC || 0)} по договору: остальное клиенты по привычке заплатят позже.`
          : 'Текущая — до 30 дн после срока, дальше — просрочка. Договорная отсрочка — из карточки контрагента.'}
      </span>
    </div>
  )
}
