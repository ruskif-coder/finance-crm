/**
 * «Что требует учёта — по услугам» (владелец 14.10.2026): все требования стадий по смысловым блокам, столбцы — услуги.
 * Клетка — действует ли пункт для услуги; клик сохраняет сразу (журнал на сервере). Блокирует или предупреждает — у строки, одно для всех.
 * Условие цикла («полный цикл» / «контур аккаунта») показано у строки и здесь не правится: пункт работает, если услуга отмечена И цикл совпадает.
 * Новая услуга появляется столбцом сама; общие пункты сервер включает ей при создании.
 */
import { useCallback, useEffect, useState } from 'react'
import api, { auth } from '@/lib/api'
import { card, MONO } from '@/components/salesTableKit'

const CAP = { fontFamily: MONO, fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', fontWeight: 600, color: 'var(--text-faint)' }
const TD = { padding: '7px 10px', borderBottom: '1px solid var(--border-row)', verticalAlign: 'middle', fontSize: 13 }

/** Клетка — три состояния по клику (владелец 14.10.2026): серый — не требуется → зелёный — уведомляет → синий — требуется (запирает переход). */
const NEXT = { off: 'warn', warn: 'block', block: 'off' }
const LOOK = {
  off: { bg: 'var(--border-card)', left: 2, word: 'не требуется' },
  warn: { bg: 'var(--income)', left: 9, word: 'уведомляет' },
  block: { bg: 'var(--accent)', left: 16, word: 'требуется' },
}

function Cell({ state, busy, disabled, title, onClick }) {
  const l = LOOK[state]
  return (
    <span onClick={disabled || busy ? undefined : onClick} title={title} role="button"
      style={{ position: 'relative', display: 'inline-block', width: 32, height: 18, borderRadius: 9, verticalAlign: 'middle',
        background: l.bg, cursor: disabled ? 'not-allowed' : busy ? 'wait' : 'pointer',
        opacity: busy ? 0.5 : disabled ? 0.6 : 1, transition: 'background-color 150ms ease' }}>
      <span style={{ position: 'absolute', top: 2, left: l.left, width: 14, height: 14, borderRadius: '50%', background: '#fff',
        boxShadow: '0 1px 2px rgba(28,36,51,.25)', transition: 'left 150ms ease' }} />
    </span>
  )
}

export default function RequirementsMatrix({ services, canEdit }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')

  const load = useCallback(() => {
    api.get('/final-recon/assembly', auth()).then(r => setData(r.data)).catch(e => setErr(e?.response?.data?.detail || 'Не удалось загрузить матрицу'))
  }, [])
  useEffect(() => { load() }, [load])

  const cols = (services || []).filter(s => s.is_active)
  const stateOf = (it, s) => (it.state && it.state[s.id]) || 'off'
  const cycle = async (it, s) => {
    const state = NEXT[stateOf(it, s)]
    setBusy(`${it.key}:${s.id}`); setErr('')
    try {
      await api.put('/final-recon/assembly', { key: it.key, service_id: s.id, state }, auth())
      setData(d => ({ blocks: d.blocks.map(b => ({ ...b, items: b.items.map(x => {
        if (x.key !== it.key) return x
        const st = { ...(x.state || {}) }
        if (state === 'off') delete st[s.id]; else st[s.id] = state
        return { ...x, state: st }
      }) })) }))
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось сохранить') }
    finally { setBusy('') }
  }

  if (!data) return <div style={{ ...card, padding: 20, color: 'var(--text-muted)' }}>{err || 'Загрузка…'}</div>
  return (
    <div>
      <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', margin: '0 0 12px', lineHeight: 1.5 }}>
        У каждой услуги по пункту три состояния, клик переключает по кругу: серый — <b>не требуется</b> →
        <b style={{ color: 'var(--income)' }}> зелёный — уведомляет</b> (подсказка, переход не держит) →
        <b style={{ color: 'var(--accent)' }}> синий — требуется</b> (без него стадию не сменить). Сохраняется сразу.
        Наведите на название пункта — подсказка заполняющему.
      </div>
      {!!err && <div style={{ marginBottom: 10, fontSize: 12.5, color: 'var(--danger-fg)' }}>{err}</div>}
      {data.blocks.map(b => (
        <div key={b.title} style={{ ...card, marginBottom: 16, overflow: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '12px 16px 8px', flexWrap: 'wrap', borderBottom: '1px solid var(--border-card)' }}>
            <span title={b.desc} style={{ fontSize: 15, fontWeight: 800, cursor: 'help', borderBottom: '1px dashed var(--text-faint)' }}>{b.title}</span>
            <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', background: 'var(--bg-subtle)', borderRadius: 6, padding: '2px 8px' }}>заполняет: {b.who}</span>
            <span style={{ flexBasis: '100%', fontSize: 12, color: 'var(--text-faint)' }}>{b.desc}</span>
          </div>
          <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 300 + cols.length * 96 }}>
            <thead><tr>
              <th style={{ ...TD, ...CAP, textAlign: 'left', width: 300 }}>Пункт</th>
              <th style={{ ...TD, ...CAP, textAlign: 'left', width: 200 }}>Стадии</th>
              {cols.map(s => <th key={s.id} style={{ ...TD, ...CAP, textAlign: 'center' }}>{s.name}</th>)}
            </tr></thead>
            <tbody>
              {b.items.map(it => (
                <tr key={it.key}>
                  <td style={TD}>
                    <span title={`${it.hint || ''}${it.where ? ` Где: ${it.where}.` : ''}`} style={{ fontWeight: 600, cursor: 'help', borderBottom: '1px dashed var(--border-card)' }}>{it.title}</span>
                    <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 2 }}>
                      {it.flow ? `только «${it.flow}»` : ''}{it.flow && it.pixel ? ' · ' : ''}{it.pixel ? 'если пиксель заказан' : ''}
                    </div>
                  </td>
                  <td style={{ ...TD, fontSize: 11.5, color: 'var(--text-faint)' }}>{it.stages.join(' · ')}</td>
                  {cols.map(s => (
                    <td key={s.id} style={{ ...TD, textAlign: 'center' }}>
                      <Cell state={stateOf(it, s)} busy={busy === `${it.key}:${s.id}`} disabled={!canEdit}
                        title={`${s.name}: ${LOOK[stateOf(it, s)].word} — клик: ${LOOK[NEXT[stateOf(it, s)]].word}`}
                        onClick={() => cycle(it, s)} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}
