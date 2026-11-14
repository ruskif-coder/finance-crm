/**
 * «Сборка» в расхлопе «Моих сделок» — в виде свёрнутого блока ОРД карточки (владелец 13.11.2026): шапка с итогом и полосками
 * «N из M», четыре плашки `FactChip` (те же, что у ОРД): ОРД · креативы · пиксель · ДС — каждая ведёт в свой блок карточки.
 *
 * Данные — `now.chips` и `now.head` с сервера (`app/sales/account_now.assembly_chips`).
 */
import { useState } from 'react'
import api, { auth } from '@/lib/api'
import { detailText } from '@/lib/loadError'
import { MONO } from '@/components/salesTableKit'
import { StatePips } from '@/components/ord/AssemblyOrd'
import { FactChip } from '@/components/deal/Section'

const CAP = { fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }
const PIP = { ok: 'done', warn: 'todo', off: 'skip' }

/** Контур аккаунта (OLV, Альфарм-Таргет, Polza): запуск во внешней системе, аккаунт подтверждает его — сделка «В размещении».
 *  Та же ручка, что кнопка «Запустить» в карточке (`/final-recon/deal/{id}/launch`, AccountFlowButton). */
function ExternalLaunch({ dealId, canEdit, onDone }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const run = async () => {
    if (!window.confirm('Подтвердить запуск? Сделка перейдёт в «В размещении».')) return
    setBusy(true); setErr('')
    try { await api.post(`/final-recon/deal/${dealId}/launch`, {}, auth()); onDone() }
    catch (e) { setErr(detailText(e, 'Не удалось подтвердить запуск')) }
    finally { setBusy(false) }
  }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', marginBottom: 8, borderRadius: 10, background: 'var(--accent-tint)', border: '1px solid var(--accent-border)' }}>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1, minWidth: 0 }}>
        <b style={{ fontSize: 13, color: 'var(--accent-fg)' }}>Запуск во внешней системе</b>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>РК в нашей DSP нет — когда размещение запущено, подтвердите: сделка перейдёт в «В размещении».</span>
        {!!err && <span style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</span>}
      </span>
      {canEdit && <button type="button" disabled={busy} onClick={run}
        style={{ height: 34, padding: '0 16px', borderRadius: 9, border: 0, background: 'var(--accent)', color: 'var(--on-accent)', fontSize: 12.5, fontWeight: 700,
          cursor: busy ? 'wait' : 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap', opacity: busy ? 0.6 : 1 }}>Подтвердить запуск</button>}
    </div>
  )
}

export default function AssemblyNow({ now, code, hot, cols = 4, dealId, canEdit, onDone }) {
  const chips = now.chips || []
  const done = chips.every(c => c.tone !== 'warn')
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12, padding: '12px 16px 8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingBottom: 4 }}>
          <span style={CAP}>Сборка</span>
          {!!now.period_from && <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{now.period_from} — {now.period_to}</span>}
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 10 }}>
            {!!chips.length && <StatePips all={chips.map(c => PIP[c.tone] || 'skip')} />}
            {hot && <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: 'var(--danger-fg)', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--danger)' }} />горит</span>}
          </span>
        </div>
        {!!now.external_launch && <ExternalLaunch dealId={dealId} canEdit={canEdit} onDone={onDone} />}
        {!!now.head?.text && !now.external_launch && <div style={{ fontSize: 12.5, fontWeight: 600, color: done ? 'var(--income-fg)' : 'var(--warning-text)', paddingBottom: 10 }}>{now.head.text}</div>}
        {/* Четыре плашки одной ширины: сеткой (в ряд — 4, в модалке — 2×2), а не переносом — иначе ширина пляшет от длины значения */}
        {!!chips.length && <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))`, gap: 8, paddingBottom: 8 }}>
          {chips.map(c => (
            <a key={c.key} href={`/sales/deals/${code}${c.href}`} target="_blank" rel="noreferrer" title="Открыть в карточке сделки"
              style={{ textDecoration: 'none', display: 'grid', minWidth: 0 }}><FactChip label={c.label} value={c.value} tone={c.tone} /></a>))}
        </div>}
      </div>
    </div>
  )
}
