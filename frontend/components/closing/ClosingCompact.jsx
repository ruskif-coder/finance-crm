/**
 * «Итоговая сверка» в расхлопе «Моих сделок» — компактно, около 400 px (хендофф design_handoff_final_recon, 14.11.2026).
 * Функции те же, что у блока карточки (`ClosingBlock`): одно состояние и одни действия (`useClosing`), один расчёт на сервере.
 * Шапка · слева факты (`ReconFacts`) · справа решение (`ReconDecision`) в две колонки `minmax(0,1fr) 280px`.
 */
import { useState } from 'react'
import Link from 'next/link'
import { MONO } from '@/components/salesTableKit'
import { fmtDateTimeShort } from '@/lib/dates'
import { CAP, Pill } from '@/components/closing/closingKit'
import CollectDsModal from '@/components/closing/CollectDsModal'
import useClosing from '@/components/closing/useClosing'
import ReconFacts from '@/components/closing/compact/ReconFacts'
import ReconDecision from '@/components/closing/compact/ReconDecision'

export default function ClosingCompact({ dealId, canEdit, hot, wide = true }) {
  const c = useClosing(dealId)
  const [modal, setModal] = useState(false)
  const { s } = c
  if (!s) return c.err ? <div style={{ fontSize: 12.5, color: 'var(--danger-fg)' }}>{c.err}</div> : <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Загрузка сверки…</span>
  const time = fmtDateTimeShort(s.calculated_at).split(' ').pop()
  return (
    <div style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border-inner)', borderRadius: 12, padding: '10px 12px 12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ ...CAP, color: 'var(--text-secondary)' }}>Итоговая сверка</span>
        <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>{s.period || '—'} · расчёт {time}</span>
        <span style={{ fontSize: 12, color: s.closing_to ? 'var(--text-secondary)' : 'var(--warning-text)' }}
          title={s.closing_to ? `ИНН ${s.closing_to.inn || '—'} · договор ${s.closing_to.contract || '—'}` : 'Выберите доходный договор в блоке ОРД карточки'}>
          закрытие на: <b>{s.closing_to ? s.closing_to.name : 'доходный договор не выбран'}</b></span>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {!!s.master && <Link href={`/accounts/master/${s.master.code}`} target="_blank" style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--accent)' }}>в {s.master.code}</Link>}
          {!!s.master?.foreign && <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-muted)' }}>собирает {s.master.by}</span>}
          {!!s.adfox_stale && <Pill tone="warn" title={`Adfox грузится вручную: данные по ${s.adfox_stale.adfox_as_of}`}>Adfox отстаёт</Pill>}
          {s.no_docs?.closed_at ? <Pill tone="ok">Закрыто без документов</Pill>
            : s.frozen ? <Pill tone="ok">Отправлено в ДО</Pill>
              : s.confirmed && <Pill tone="ok" title={canEdit ? 'Снять подтверждение' : undefined} onClick={canEdit ? () => c.confirm(false) : undefined}>Сверка подтверждена</Pill>}
          <Pill tone={s.verdict.tone}>{s.verdict.text}</Pill>
          {hot && <span style={{ fontFamily: MONO, fontSize: 10.5, fontWeight: 700, color: 'var(--danger-fg)', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--danger)' }} />горит</span>}
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: wide ? 'minmax(0,1fr) 280px' : 'minmax(0,1fr)', gap: 10, alignItems: 'stretch' }}>
        <ReconFacts s={s} dealId={dealId} canEdit={canEdit} busy={c.busy} onSave={c.saveFact} onCost={c.saveCost} onUploaded={c.load} />
        <ReconDecision s={s} canEdit={canEdit} busy={c.busy} err={c.err} setMode={c.setMode} saveSk={c.saveSk} confirm={c.confirm}
          closeNoDocs={c.closeNoDocs} onCollect={() => setModal(true)} onReload={c.load} />
      </div>
      {s.frozen && !s.no_docs?.closed_at && <CollectDsModal.OpenLink dealId={dealId} />}
      {modal && <CollectDsModal dealId={dealId} gross={s.total_gross} onClose={() => setModal(false)} onDone={c.load} />}
    </div>
  )
}
