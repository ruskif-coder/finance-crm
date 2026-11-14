// Раскладка итога сверки по РК (владелец 14.11.2026): менеджер принимает цифру площадки и выбирает, куда идёт дельта —
// пропорционально нашему факту или целиком на одну РК. Цифры раскладки считает сервер (`/agree/preview`) — то же правило,
// что запишет «Согласовать итог»; от раскладки зависят разаллокация площадке и ОРД по ЕРИД.
import { useEffect, useState } from 'react'
import api, { auth } from '@/lib/http'
import { MONO, Modal } from '@/components/salesTableKit'
import { dm, grpDash } from '@/lib/salesFormat'
import { detailText } from '@/lib/loadError'
import useLatest from '@/lib/useLatest'
import { CAPS, actBtn } from './reconKit'

const GRID = '22px minmax(180px,1.6fr) 98px 110px 110px 104px'
const signed = (n) => (n === 0 ? '0' : `${n > 0 ? '+' : '−'}${grpDash(Math.abs(n))}`)

function Choice({ on, title, note, onPick }) {
  return (
    <span onClick={onPick} style={{ flex: '1 1 260px', display: 'flex', gap: 10, alignItems: 'flex-start', padding: '10px 12px', borderRadius: 12, cursor: 'pointer',
      background: on ? 'var(--bg-tint)' : 'var(--bg-card)', border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}` }}>
      <span style={{ width: 14, height: 14, borderRadius: 7, marginTop: 2, flex: '0 0 14px', boxSizing: 'border-box',
        border: on ? '4px solid var(--accent)' : '1.5px solid var(--border-hover)', background: 'var(--bg-card)' }} />
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <b style={{ fontSize: 13 }}>{title}</b>
        <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{note}</span>
      </span>
    </span>
  )
}

export default function DeltaModal({ rid, site, volume, ours, campaigns, onClose, onAgreed }) {
  const [mode, setMode] = useState('even')
  const [target, setTarget] = useState(() => [...campaigns].sort((a, b) => b.fact - a.fact)[0]?.placement_id ?? null)
  const [pv, setPv] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const latest = useLatest()
  const delta = volume - ours

  useEffect(() => {
    const fresh = latest()
    setErr('')
    api.post(`/publisher-recon/${rid}/agree/preview`, { volume, mode, target_id: mode === 'target' ? target : null }, auth())
      .then(r => { if (fresh()) setPv(r.data) })
      .catch(e => { if (fresh()) { setPv(null); setErr(detailText(e, 'Не удалось посчитать раскладку')) } })
  }, [rid, volume, mode, target, latest])

  const byId = Object.fromEntries((pv?.lines || []).map(l => [l.placement_id, l]))
  const confirm = async () => {
    if (busy || !pv) return
    setBusy(true)
    try {
      await api.post(`/publisher-recon/${rid}/agree`, { volume, mode, target_id: mode === 'target' ? target : null }, auth())
      onAgreed()
    } catch (e) { setErr(detailText(e, 'Не удалось зафиксировать итог')) } finally { setBusy(false) }
  }

  return (
    <Modal width={900} onClose={onClose}
      title={<span>Раскладка итога по РК <span style={{ fontFamily: MONO, fontSize: 14, color: 'var(--text-secondary)' }}>· {site}</span></span>}
      summary={<span style={{ fontFamily: MONO, fontSize: 12 }}>наши {grpDash(ours)} → итог {grpDash(volume)} ·{' '}
        <b style={{ color: delta < 0 ? 'var(--warning-fg)' : 'var(--income-fg)' }}>дельта {signed(delta)}</b></span>}
      footer={<>
        <span style={{ fontSize: 12, lineHeight: 1.45, flex: '1 1 300px', color: err ? 'var(--danger-fg)' : 'var(--text-muted)' }}>
          {err || 'Без возврата: по этой раскладке формируются разаллокация площадке и ОРД по ЕРИД.'}</span>
        <button type="button" onClick={onClose} style={actBtn('g', false)}>Отмена</button>
        <button type="button" disabled={!pv || busy} onClick={confirm} style={actBtn('ok', !pv || busy)}>Согласовать итог {grpDash(volume)}</button>
      </>}>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', padding: '6px 0 14px' }}>
        <Choice on={mode === 'even'} onPick={() => setMode('even')} title="Распределить дельту равномерно"
          note="пропорционально нашему факту: большая РК берёт больше" />
        <Choice on={mode === 'target'} onPick={() => setMode('target')} title="Применить дельту к одной РК"
          note="выберите РК в списке — остальные останутся с нашим фактом" />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, padding: '0 4px 6px', borderBottom: '1px solid var(--border-card)', ...CAPS, fontSize: 8.5, fontWeight: 400, letterSpacing: '0.08em' }}>
        <span /><span>Рекламодатель · бренд</span><span>Флайт</span><span style={{ textAlign: 'right' }}>Наши</span>
        <span style={{ textAlign: 'right' }}>Итог</span><span style={{ textAlign: 'right' }}>Изменение</span>
      </div>
      {campaigns.map(c => {
        const l = byId[c.placement_id]
        const pick = mode === 'target'
        const on = pick && target === c.placement_id
        const ch = l ? l.agreed - l.ours : null
        return (
          <div key={c.placement_id} onClick={pick ? () => setTarget(c.placement_id) : undefined}
            style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, alignItems: 'center', padding: '6px 4px', borderBottom: '1px solid var(--border-row)',
              cursor: pick ? 'pointer' : 'default', background: on ? 'var(--bg-tint)' : 'transparent' }}>
            <span style={{ width: 12, height: 12, borderRadius: 6, boxSizing: 'border-box', visibility: pick ? 'visible' : 'hidden',
              border: on ? '4px solid var(--accent)' : '1.5px solid var(--border-hover)' }} />
            <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: on ? 700 : 400 }}>{c.brand}</span>
            <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-secondary)' }}>{dm(c.date_from)} — {dm(c.date_to)}</span>
            <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right', color: 'var(--text-secondary)' }}>{grpDash(c.fact)}</span>
            <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right', fontWeight: 700 }}>{l ? grpDash(l.agreed) : '—'}</span>
            <span style={{ fontFamily: MONO, fontSize: 11.5, textAlign: 'right', color: !ch ? 'var(--text-faint)' : ch < 0 ? 'var(--warning-fg)' : 'var(--income-fg)' }}>
              {ch == null ? '—' : signed(ch)}</span>
          </div>)
      })}
      <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, padding: '8px 4px 0', fontWeight: 700 }}>
        <span /><span style={{ ...CAPS, fontSize: 9, letterSpacing: '0.08em' }}>Итого · {campaigns.length} РК</span><span />
        <span style={{ fontFamily: MONO, fontSize: 12, textAlign: 'right' }}>{grpDash(ours)}</span>
        <span style={{ fontFamily: MONO, fontSize: 12, textAlign: 'right' }}>{pv ? grpDash(pv.total) : '—'}</span>
        <span style={{ fontFamily: MONO, fontSize: 12, textAlign: 'right' }}>{signed(delta)}</span>
      </div>
    </Modal>
  )
}
