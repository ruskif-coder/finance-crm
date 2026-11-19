/** Платёжный календарь на 14 дней + операции выбранного дня (README хендоффа, п. 5). Геометрия — из макета. */
import { CAPS, MONO, Flag, f, sg, short, tys } from './kit'
import { WD, WD_FULL, ddmm } from './model'

const H = 96            // половина высоты поля столбиков: 0 — посередине поля 200 px
const BH = 44           // высота полосы остатка

const Legend = ({ c, children }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{children}</span>
)

function flagOf(o) {
  if (o.flag === 'today') return <Flag tone="signal">срок сегодня</Flag>
  if (o.flag === 'late') return <Flag tone="signal">{o.note}</Flag>
  if (o.flag === 'scen') return <Flag tone="scen">{o.note}</Flag>
  if (o.flag === 'shift') return <Flag tone="attn">{o.note}</Flag>
  return null
}

export default function Calendar({ R, real, thr, day, setDay }) {
  const { days, mi } = R
  // Масштаб — по второму по величине дню: один день с крупным поступлением (конец месяца) иначе сплющивает остальные в нитку.
  // Столбик выше масштаба обрезается по краю поля и помечается, сумма — в подсказке и в списке дня.
  const vals = days.flatMap(x => [x.inS, x.outS]).sort((a, b) => b - a)
  const scale = Math.max(1, vals[1] > 0 ? Math.max(vals[1] * 1.15, vals[0] * 0.2) : vals[0])
  const bar = (v) => Math.min(H, Math.round(v / scale * H))
  const balMax = Math.max(thr * 2, ...days.map(x => x.bal))
  const sx = days[Math.min(day, days.length - 1)]
  const sel = sx.d
  return (
    <div data-motion="rise" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)',
      borderRadius: 20, display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 420px', '--i': 3 }}>
      <div style={{ padding: '20px 22px 18px', display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.01em' }}>Платёжный календарь</span>
          <span style={CAPS}>14 дней · {real ? 'поступления сдвинуты на привычную задержку клиентов' : 'план операций по срокам'}</span>
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 16, fontSize: 12, color: 'var(--text-secondary)' }}>
            <Legend c="var(--money)">поступления</Legend><Legend c="var(--ok)">оплаты</Legend>
            <Legend c="var(--signal)">срок сегодня</Legend><Legend c="var(--bad)">остаток ниже {tys(thr)}</Legend>
          </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '52px repeat(14, minmax(0,1fr))', gap: '0 4px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', height: 200, padding: '2px 0', fontFamily: MONO,
            fontSize: 9.5, color: 'var(--text-faint)', textAlign: 'right' }}>
            <span>+{short(scale)}</span><span>0</span><span>−{short(scale)}</span>
          </div>
          {days.map((x, k) => {
            const late = x.ops.some(o => o.v < 0 && (o.flag === 'today' || o.flag === 'late'))
            const on = k === day
            return (
              <div key={k} onClick={() => setDay(k)} title={`${WD[x.d.getDay()]} ${ddmm(x.d)} · +${f(x.inS)} / −${f(x.outS)} · остаток ${f(x.bal)} ₽`}
                style={{ position: 'relative', height: 200, borderRadius: 10, background: on ? 'var(--bg-subtle)' : 'transparent',
                  boxShadow: on ? 'inset 0 0 0 1.5px var(--hot)' : 'none', cursor: 'pointer' }}>
                <span style={{ position: 'absolute', left: 0, right: 0, top: 100, height: 1, background: 'var(--border-inner)' }} />
                <span style={{ position: 'absolute', left: '22%', right: '22%', bottom: 100, height: bar(x.inS), borderTop: x.inS > scale ? '2px dashed var(--bg-card)' : 'none',
                  borderRadius: '4px 4px 1px 1px', background: 'var(--money)' }} />
                <span style={{ position: 'absolute', left: '22%', right: '22%', top: 101, height: bar(x.outS), borderBottom: x.outS > scale ? '2px dashed var(--bg-card)' : 'none',
                  borderRadius: '1px 1px 4px 4px', background: late ? 'var(--signal)' : 'var(--ok)' }} />
              </div>
            )
          })}
          <span style={{ ...CAPS, alignSelf: 'center', textAlign: 'right', paddingTop: 8 }}>остаток</span>
          {days.map((x, k) => (
            <div key={k} style={{ position: 'relative', height: 46, marginTop: 8, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
              <span style={{ position: 'absolute', left: -2, right: -2, bottom: Math.round(thr / balMax * BH), borderTop: '1px dashed var(--bad-border)' }} />
              <span style={{ width: '56%', height: Math.max(3, Math.round(Math.max(0, x.bal) / balMax * BH)), borderRadius: '3px 3px 0 0',
                background: x.bal < thr ? 'var(--bad)' : 'var(--ok-border)' }} />
            </div>
          ))}
          <span />
          {days.map((x, k) => {
            const low = x.bal < thr
            const weekend = x.d.getDay() === 0 || x.d.getDay() === 6
            const tag = k === 0 ? 'сегодня' : low ? (k === mi ? 'минимум' : 'ниже') : ''
            return (
              <div key={k} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, paddingTop: 6 }}>
                <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: low ? 'var(--bad-fg)' : 'var(--text-primary)', whiteSpace: 'nowrap' }}>{short(x.bal)}</span>
                <span style={{ fontSize: 11.5, fontWeight: k === 0 ? 800 : 600, color: weekend ? 'var(--text-faint)' : 'var(--text-primary)', whiteSpace: 'nowrap' }}>
                  {WD[x.d.getDay()]} {ddmm(x.d)}</span>
                <span style={{ fontFamily: MONO, fontSize: 8.5, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', height: 11,
                  color: k === 0 ? 'var(--text-primary)' : 'var(--bad-fg)' }}>{tag}</span>
              </div>
            )
          })}
        </div>
      </div>
      <div style={{ borderLeft: '1px solid var(--border-inner)', background: 'var(--bg-subtle)', borderRadius: '0 20px 20px 0', padding: '20px 22px',
        display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.01em' }}>{WD_FULL[sel.getDay()]}, {ddmm(sel)}</span>
          {!!sx.ops.length && <span style={CAPS}>{sx.ops.length} операц{sx.ops.length === 1 ? 'ия' : sx.ops.length < 5 ? 'ии' : 'ий'}</span>}
        </div>
        <div style={{ overflowY: 'auto', maxHeight: 250, display: 'flex', flexDirection: 'column' }}>
          {sx.ops.map((o, i) => (
            <div key={`${o.id}-${i}`} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto', gap: '2px 12px', padding: '10px 0',
              borderBottom: '1px solid var(--border-row)' }}>
              <span style={{ fontSize: 13, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.who}</span>
              <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: o.v > 0 ? 'var(--money-fg)' : 'var(--text-primary)', textAlign: 'right',
                whiteSpace: 'nowrap' }}>{sg(o.v)}</span>
              <span style={{ fontSize: 11.5, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {o.v > 0 ? 'поступление' : 'оплата'} · {(o.article || o.cat || '').toLowerCase()}{o.invoice ? ` · счёт ${o.invoice}` : ''}</span>
              <span style={{ justifySelf: 'end' }}>{flagOf(o)}</span>
            </div>
          ))}
        </div>
        {!sx.ops.length && <span style={{ fontSize: 13, color: 'var(--text-muted)', padding: '10px 0' }}>
          {sel.getDay() === 0 || sel.getDay() === 6 ? 'Выходной — движений нет' : 'Плановых движений нет'}</span>}
        <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', paddingTop: 10 }}>
          <span style={CAPS}>остаток на конец дня</span>
          <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700, color: sx.bal < thr ? 'var(--bad-fg)' : 'var(--text-primary)' }}>{f(sx.bal)} ₽</span>
        </div>
      </div>
    </div>
  )
}

/** Полоса «что если · не сохранено» над календарём (README, п. 4). Сохранение в план ждёт переносов с причиной (п. 8 учёта). */
export function WhatIfBar({ text, from, to, thr, onReset }) {
  return (
    <div data-motion="drop" style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 18px', borderRadius: 16, background: 'var(--attn-tint)',
      border: '1px solid var(--attn-border)', flexWrap: 'wrap' }}>
      <span style={{ ...CAPS, color: 'var(--attn-fg)' }}>что если · не сохранено</span>
      <span style={{ fontSize: 13, color: 'var(--text-primary)' }}>{text}</span>
      <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>минимум <b style={{ fontFamily: MONO, color: 'var(--text-primary)' }}>{from}</b> →{' '}
        <b style={{ fontFamily: MONO, color: to.v < thr ? 'var(--bad-fg)' : 'var(--money-fg)' }}>{to.s}</b></span>
      <button type="button" onClick={onReset} style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 12px',
        background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 10, fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)',
        cursor: 'pointer', fontFamily: 'inherit' }}>Сбросить</button>
      <button type="button" disabled title="Появится вместе с переносом плановой операции с причиной (п. 8 «процессов и учёта»)"
        style={{ display: 'inline-flex', alignItems: 'center', height: 32, padding: '0 14px', borderRadius: 10, background: 'var(--hot)', color: 'var(--hot-fg)',
          fontSize: 12.5, fontWeight: 700, border: 0, opacity: 0.45, cursor: 'not-allowed', fontFamily: 'inherit' }}>Сохранить в план</button>
    </div>
  )
}
