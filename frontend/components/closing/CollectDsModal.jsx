/**
 * Модалка «Собрать ДС» после подтверждения сверки — по дизайну docs/IS.zip (design_handoff_final_recon §5, 15.10.2026).
 * Куда: «Своё ДС» (новая мастер-сделка на одну сделку) или «В мастер-сделку» (одно ДС на сделки того же договора и месяца —
 * открытая мастер-сделка, если есть, иначе новая; список «Вместе с ними»). Несверенная сделка прикрепляется к пакету, но
 * пакет не уйдёт из конструктора документов, пока сверка не завершена у всех. Действие фиксирует сверку — необратимо.
 */
import { overlayClose } from '@/lib/overlay'
import { StatusPill } from '@/components/closing/StatusPill'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import api, { auth } from '@/lib/api'
import { btn, MONO, primaryBtn, UI, Z } from '@/components/salesTableKit'
import { rub2 } from '@/lib/salesFormat'


const Warn = ({ children }) => (
  <div style={{ display: 'flex', gap: 10, padding: '12px 14px', borderRadius: 12, background: 'var(--warning-bg)', border: '1px solid var(--warning-border)',
    color: 'var(--warning-text)', fontSize: 13, lineHeight: 1.5 }}>
    <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--warning)', marginTop: 7, flex: '0 0 7px' }} />
    <span>{children}</span>
  </div>
)

function Choice({ on, title, hint, onPick }) {
  return (
    <button type="button" onClick={onPick}
      style={{ flex: 1, minWidth: 0, display: 'flex', gap: 12, textAlign: 'left', padding: '14px 16px', borderRadius: 14, cursor: 'pointer', fontFamily: UI,
        border: `1px solid ${on ? 'var(--accent)' : 'var(--border-card)'}`, background: on ? 'var(--accent-tint)' : 'var(--bg-card)' }}>
      <span style={{ width: 18, height: 18, flex: '0 0 18px', borderRadius: 4, marginTop: 1, border: `1.5px solid ${on ? 'var(--accent)' : 'var(--border-hover)'}`,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
        {on && <span style={{ width: 9, height: 9, borderRadius: 2, background: 'var(--accent)' }} />}</span>
      <span><b style={{ fontSize: 14, color: on ? 'var(--accent-fg)' : 'var(--text-primary)' }}>{title}</b>
        <span style={{ display: 'block', fontSize: 12.5, color: 'var(--text-muted)', marginTop: 3, lineHeight: 1.45 }}>{hint}</span></span>
    </button>
  )
}

const CAP = { fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-faint)' }
const SIB_GRID = '24px 80px minmax(0,1fr) 150px 150px 110px'

export default function CollectDsModal({ dealId, gross, onClose, onDone }) {
  const router = useRouter()
  const [fork, setFork] = useState(null)
  const [mode, setMode] = useState('own')       // own | master
  const [withIds, setWithIds] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.get(`/master-deals/deal/${dealId}/fork`, auth())
      .then(r => { setFork(r.data); if (r.data.candidates?.length) setMode('master') })
      .catch(e => setErr(e?.response?.data?.detail || 'Не удалось открыть'))
  }, [dealId])

  const send = async () => {
    setBusy(true); setErr('')
    const master = fork.candidates?.[0]
    const body = fork.in_master ? { target: 'existing' }
      : mode === 'own' ? { target: 'new' }
        : master ? { target: 'join', master_id: master.id, with_deals: withIds } : { target: 'new', with_deals: withIds }
    try {
      const r = await api.put(`/master-deals/deal/${dealId}/send`, body, auth())
      onDone?.(); onClose()
      router.push(`/accounts/master/${r.data.master.code}`)
    } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось отправить') } finally { setBusy(false) }
  }

  const sibs = fork?.siblings || []
  const unready = sibs.filter(x => withIds.includes(x.id) && x.state !== 'ready' && x.state !== 'done')
  const label = fork?.in_master ? 'В конструктор закрытия'
    : mode === 'master' && withIds.length ? `Отправить ${withIds.length + 1} сделки и собрать закрытие` : 'Отправить и собрать ДС'

  return (
    <div {...overlayClose(() => !busy && onClose())}
      style={{ position: 'fixed', inset: 0, zIndex: Z.overlay, background: 'var(--scrim)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, fontFamily: UI }}>
      <div style={{ width: 860, maxWidth: '100%', maxHeight: '90vh', overflow: 'auto', background: 'var(--bg-card)', borderRadius: 18,
        boxShadow: 'var(--shadow-modal)', animation: 'popIn .2s ease both' }}>
        <style>{'@keyframes popIn{from{opacity:0;transform:scale(.97)}to{opacity:1;transform:none}}'}</style>
        <div style={{ display: 'flex', alignItems: 'center', padding: '20px 26px' }}>
          <b style={{ fontSize: 20 }}>{fork?.in_master ? `Мастер-сделка ${fork.in_master.code}` : 'Собрать ДС'}</b>
          <button type="button" onClick={onClose} aria-label="Закрыть" style={{ marginLeft: 'auto', border: 0, background: 'none', fontSize: 18, color: 'var(--text-faint)', cursor: 'pointer' }}>✕</button>
        </div>
        {fork && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 26px', background: 'var(--bg-subtle)', borderTop: '1px solid var(--border-row)', borderBottom: '1px solid var(--border-row)' }}>
              <b style={{ fontFamily: MONO, color: 'var(--accent)' }}>{fork.deal?.code}</b>
              <span style={{ fontSize: 14, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{fork.deal?.title}</span>
              <b style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 15 }}>{rub2(gross)}</b>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '18px 26px' }}>
              {fork.blocked ? <Warn>{fork.blocked}</Warn> : fork.in_master ? (
                <div style={{ fontSize: 13.5, color: 'var(--text-secondary)' }}>Сделка уже в пакете {fork.in_master.code} ({fork.in_master.status}). Откроется конструктор закрытия.</div>
              ) : (
                <>
                  <Warn>Цифры сверки зафиксируются, сделка перейдёт на следующую стадию — правка сверки после этого только через юриста.
                    Дальше — конструктор закрытия: ДС и закрывающие.</Warn>
                  <span style={CAP}>Куда</span>
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                    <Choice on={mode === 'own'} onPick={() => setMode('own')} title="Своё ДС"
                      hint="Отдельное ДС только на эту сделку. Объединить с другими сделками договора можно позже." />
                    <Choice on={mode === 'master'} onPick={() => setMode('master')}
                      title={fork.candidates?.length ? `В мастер-сделку ${fork.candidates[0].code}` : 'В мастер-сделку'}
                      hint="Одно ДС на несколько сделок того же договора и месяца — отметьте, какие собрать вместе." />
                  </div>
                  {mode === 'master' && (
                    <div>
                      <div style={{ ...CAP, marginBottom: 6 }}>Вместе с ними <span style={{ fontWeight: 600 }}>тот же договор · {fork.period}</span></div>
                      {!sibs.length && <div style={{ fontSize: 12.5, color: 'var(--text-faint)', padding: '8px 0' }}>Других сделок этого договора за {fork.period} нет.</div>}
                      {sibs.map(x => (
                        <label key={x.id} style={{ display: 'grid', gridTemplateColumns: SIB_GRID, gap: 10, alignItems: 'center', padding: '12px 0', borderTop: '1px solid var(--border-row)', cursor: 'pointer' }}>
                          <input type="checkbox" checked={withIds.includes(x.id)} style={{ width: 18, height: 18 }}
                            onChange={e => setWithIds(v => (e.target.checked ? [...v, x.id] : v.filter(i => i !== x.id)))} />
                          <b style={{ fontFamily: MONO, color: 'var(--accent)' }}>{x.code}</b>
                          <span style={{ fontSize: 13.5, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{x.title}</span>
                          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{x.stage}</span>
                          <span><StatusPill state={x.state} text={x.status} /></span>
                          <b style={{ fontFamily: MONO, textAlign: 'right' }}>{rub2(x.total_net)}</b>
                        </label>
                      ))}
                      {!!unready.length && (
                        <div style={{ marginTop: 8 }}><Warn>{unready.length === 1 ? `Сделка ${unready[0].code} ещё не сверена` : `Сделки ${unready.map(x => x.code).join(', ')} ещё не сверены`} —
                          прикрепится к пакету, но пакет не уйдёт из конструктора документов, пока сверка не завершится у всех.</Warn></div>
                      )}
                    </div>
                  )}
                </>
              )}
              {!!err && <div style={{ fontSize: 12.5, color: 'var(--danger-fg)' }}>{err}</div>}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '16px 26px', borderTop: '1px solid var(--border-row)' }}>
              {!fork.in_master && <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>Действие фиксирует сверку — отменить нельзя</span>}
              <button type="button" style={{ ...btn(false), marginLeft: 'auto' }} disabled={busy} onClick={onClose}>Отмена</button>
              <button type="button" style={primaryBtn} disabled={busy || !!fork.blocked} onClick={send}>{busy ? '…' : label}</button>
            </div>
          </>
        )}
        {!fork && !!err && <div style={{ padding: '0 26px 20px', color: 'var(--danger-fg)' }}>{err}</div>}
      </div>
    </div>
  )
}

// После отправки — ссылка в конструктор закрытия своего пакета.
CollectDsModal.OpenLink = function OpenLink({ dealId }) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  return (
    <button type="button" disabled={busy} style={{ ...btn(false), height: 44 }}
      onClick={async () => {
        setBusy(true)
        try {
          const r = await api.get(`/master-deals/deal/${dealId}/fork`, auth())
          if (r.data.in_master) router.push(`/accounts/master/${r.data.in_master.code}`)
        } finally { setBusy(false) }
      }}>Открыть закрытие</button>
  )
}
