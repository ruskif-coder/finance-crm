/**
 * «Бизнес» → светофор по месяцам — по хендоффу design_handoff_money_navy (20.11.2026, «Финансы - бизнес NAVY»), разметка
 * дословно: столбик 240 px на месяц флайта, слои снизу вверх, пунктир — выручка того же месяца прошлого года.
 * Клик по слою — выделение (остальное приглушено) и строка «месяц · слой · сумма» с переходом в реестр сделок;
 * клик по легенде — оставить один слой во всех месяцах. Данные — `GET /money/business` → months.
 */
import { useState } from 'react'
import Link from 'next/link'
import { CARD, H, MONO } from '../kit'
import { LAYERS, layerOf, likely, m1, pc, sure, vs } from './calc'

const BAR_H = 240

function Column({ m, k, scale, lay, sel, onPick }) {
  const px = (v) => Math.round((v || 0) / scale * BAR_H)
  const cur = m.role === 'now', past = m.role === 'past'
  const chip = cur ? 'сейчас' : past ? 'прошлый' : ''
  const toLy = vs(likely(m), m.ly)
  const stats = [
    ['надёжно', m1(sure(m)), 800, 'var(--text-primary)'],
    ['с вероятными', m1(likely(m)), 800, 'var(--text-primary)'],
    ['к пр. году', pc(toLy), 700, toLy == null ? 'var(--text-muted)' : toLy < 0 ? 'var(--bad-fg)' : 'var(--money-fg)'],
    ['к плану', m.plan ? pc(vs(likely(m), m.plan)) : 'нет цели', 500, 'var(--text-muted)'],
    ['низкая вероятность', m1(m.low), 500, 'var(--text-secondary)'],
    ['не случились', m.lost ? m1(m.lost) : '—', 500, 'var(--text-secondary)'],
  ]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
      <div style={{ position: 'relative', height: BAR_H }}>
        {m.ly > 0 && <>
          <div style={{ position: 'absolute', left: 0, right: 0, top: BAR_H - px(m.ly), zIndex: 1, borderTop: '1.5px dashed var(--text-muted)' }} />
          <span style={{ position: 'absolute', right: 0, top: BAR_H - px(m.ly), transform: 'translateY(-130%)', zIndex: 2, padding: '0 4px', borderRadius: 4,
            background: 'var(--bg-card)', fontFamily: MONO, fontSize: 10, color: 'var(--text-muted)' }}>пр. год {m1(m.ly)}</span>
        </>}
        {m.plan > 0 && <div title={`цель «Плана продаж»: ${m1(m.plan)} млн`} style={{ position: 'absolute', left: 0, right: 0, top: BAR_H - px(m.plan), zIndex: 1, borderTop: '1.5px solid var(--accent)' }} />}
        <div style={{ position: 'absolute', left: '14%', right: '14%', bottom: 0, display: 'flex', flexDirection: 'column-reverse', gap: 2 }}>
          {LAYERS.map(([key, name, c, bd]) => {
            const v = m[key]
            if (!(v > 0)) return null
            const isSel = sel && sel[0] === k && sel[1] === key
            const on = (!lay || lay === key) && (!sel || isSel)
            return <div key={key} role="button" tabIndex={0} title={`${m.name} · ${name}: ${m1(v)} млн`} onClick={() => onPick(k, key)}
              onKeyDown={e => e.key === 'Enter' && onPick(k, key)}
              style={{ height: px(v), background: c, border: `1px solid ${bd}`, borderRadius: 5, opacity: on ? 1 : 0.3, cursor: 'pointer', boxSizing: 'border-box',
                outline: isSel ? '2px solid var(--text-primary)' : 'none', outlineOffset: 2 }} />
          })}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, paddingTop: 4, borderTop: `2px solid ${cur ? 'var(--hot)' : 'var(--border-inner)'}` }}>
        <span style={{ fontSize: 14, fontWeight: 800 }}>{m.name}</span>
        {!!chip && <span style={{ display: 'inline-flex', alignItems: 'center', height: 18, padding: '0 6px', borderRadius: 5, background: cur ? 'var(--accent-tint)' : 'var(--bg-subtle)',
          border: `1px solid ${cur ? 'var(--accent-border)' : 'var(--border-inner)'}`, fontFamily: MONO, fontSize: 9.5, fontWeight: 700, letterSpacing: '0.06em',
          textTransform: 'uppercase', color: cur ? 'var(--accent-fg)' : 'var(--text-muted)' }}>{chip}</span>}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {stats.map(([key, v, w, fg]) => (
          <div key={key} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '3px 0', fontSize: 12, borderBottom: '1px solid var(--border-row)' }}>
            <span style={{ color: 'var(--text-secondary)' }}>{key}</span><span style={{ fontFamily: MONO, fontWeight: w, color: fg }}>{v}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Lights({ months }) {
  const [lay, setLay] = useState('')
  const [sel, setSel] = useState(null)
  const scale = Math.max(1, ...months.map(m => Math.max(m.docs + m.work + m.mid + m.low, m.ly || 0, m.plan || 0))) * 1.08
  const pick = (k, key) => setSel(s => (s && s[0] === k && s[1] === key ? null : [k, key]))
  const sm = sel && months[sel[0]], sl = sel && layerOf(sel[1])
  const href = sel && `/sales/deals?money_layer=${encodeURIComponent(sl[4])}&month=${sm.key}`
  return (
    <div style={{ ...CARD, gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <span style={H}>Светофор по месяцам</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>сделки по месяцу флайта · пунктир — выручка того же месяца прошлого года · нажмите на слой</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12, color: 'var(--text-secondary)' }}>
          {LAYERS.map(([key, name, c, bd]) => (
            <span key={key} role="button" tabIndex={0} title="Оставить один слой во всех месяцах" onClick={() => { setLay(l => (l === key ? '' : key)); setSel(null) }}
              onKeyDown={e => e.key === 'Enter' && setLay(l => (l === key ? '' : key))}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer', opacity: !lay || lay === key ? 1 : 0.45 }}>
              <span style={{ width: 10, height: 10, borderRadius: 3, background: c, border: `1px solid ${bd}` }} />{name}</span>
          ))}
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${months.length}, minmax(0,1fr))`, gap: 22 }}>
        {months.map((m, k) => <Column key={m.key} m={m} k={k} scale={scale} lay={lay} sel={sel} onPick={pick} />)}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', borderRadius: 12, background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', fontSize: 12.5, color: 'var(--text-secondary)' }}>
        <span style={{ width: 10, height: 10, borderRadius: 3, background: sel ? sl[2] : 'transparent' }} />
        <span>{sel ? `${sm.name} · ${sl[1]} · ${m1(sm[sel[1]])} млн · ${sm.deals[sel[1]].length} сделок` : 'Нажмите на слой столбика — покажем, из каких сделок он сложен'}</span>
        {sel && <span style={{ display: 'flex', marginLeft: 'auto', gap: 14, alignItems: 'center' }}>
          <Link href={href} title={sel[1] === 'mid' || sel[1] === 'low' ? 'В реестре — все планы месяца: средняя и низкая вероятность вместе' : undefined}
            style={{ fontWeight: 700, color: 'var(--text-primary)' }}>Открыть в «Сделках» →</Link>
          <span role="button" tabIndex={0} onClick={() => setSel(null)} onKeyDown={e => e.key === 'Enter' && setSel(null)} style={{ cursor: 'pointer', color: 'var(--text-muted)' }}>сбросить</span>
        </span>}
      </div>
    </div>
  )
}
