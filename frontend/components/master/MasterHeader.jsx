/**
 * Шапка мастер-сделки и сделки пакета (дизайн §1–2): мета договора, сумма пакета, таблица сделок, «+ сделка» (тот же договор
 * и месяц), × — убрать из пакета, предупреждение о несверенных. После выпуска ДС правки состава скрыты.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { MONO, UI, PortalPopover } from '@/components/salesTableKit'
import { StatusPill } from '@/components/closing/StatusPill'
import { fmtDateFull, rub2 } from '@/lib/salesFormat'
import { CARD, lineBtn, Note, NW } from '@/components/master/kit'
import { CLOSE_MODE, MasterStatusPill } from '@/lib/masterStatus'
import EfficiencyRow from '@/components/master/EfficiencyRow'
import StagePipeline from '@/components/master/StagePipeline'

// хендофф «реестр + карточка»: код·название · статус · сверка · режим · цена за ед.·модель · к закрытию до НДС · с НДС · ×
const GRID = 'minmax(0,2fr) 150px minmax(0,1.2fr) 100px 110px 150px 150px 26px'
const VERDICT = { ok: 'var(--income-fg)', warn: 'var(--warning-fg)', bad: 'var(--danger-fg)', off: 'var(--text-muted)' }

/** Ручные шаги статуса: вперёд — у кого есть редактирование (кнопки нет без права — сервер ответит 403), назад — мастер и админ. */
function StatusMoves({ m, busy, onStatus }) {
  const a = m.status_actions || {}
  if (!onStatus || (!a.next && !a.prev)) return null
  const noChannel = a.next === 'выставление' && !a.channel
  const btn = lineBtn({ tone: 'secondary', size: 'sm', busy })
  return (
    <span style={{ display: 'inline-flex', gap: 6, alignItems: 'baseline' }}>
      {a.prev && <button type="button" disabled={busy} style={btn} title="Вернуть статус на шаг назад — мастер или админ"
        onClick={() => window.confirm(`Вернуть пакет в «${a.prev}»?`) && onStatus(a.prev)}>← {a.prev}</button>}
      {a.next && <button type="button" disabled={busy || noChannel}
        style={{ ...btn, color: 'var(--accent-fg)', borderColor: 'var(--accent-fg)', opacity: noChannel ? 0.45 : 1 }}
        title={noChannel ? 'У договора не задано «Выставление» — ЭДО или бумага (реестр договоров)' : undefined}
        onClick={() => onStatus(a.next)}>{a.next === 'выставление' && a.channel ? `выставление · ${a.channel}` : a.next} →</button>}
      {noChannel && <span style={{ fontSize: 11, color: 'var(--danger-fg)' }}>у договора не задано ЭДО / бумага</span>}
    </span>
  )
}


export default function MasterHeader({ m, locked, busy, onAdd, onRemove, onStatus, canEdit, onApply, onScans }) {
  const [pop, setPop] = useState(false)
  useEffect(() => {
    if (!pop) return undefined
    const off = (e) => { if (!e.target.closest('[data-pop-root]')) setPop(false) }
    document.addEventListener('mousedown', off)
    return () => document.removeEventListener('mousedown', off)
  }, [pop])
  const nw = NW
  return (
    <div style={{ ...CARD, padding: '18px 22px 16px', marginBottom: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* хендофф «мастер и шапка» (19.10.2026): шапка, эффективность и сделки — одна карточка */}
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap', marginBottom: -6, fontSize: 12, color: 'var(--text-faint)' }}>
        <Link href="/finance/master-deals" style={{ fontWeight: 600, color: 'var(--text-muted)', textDecoration: 'none' }}>← Мастер-сделки</Link>
        {!!m.deals.length && <>
          <span aria-hidden>·</span>
          <span>{m.deals.length === 1 ? 'сделка' : 'сделки'}</span>
          {m.deals.map((d, i) => (
            <span key={d.id}><Link href={`/sales/deals/${d.code}`} style={{ fontFamily: MONO, fontWeight: 700, color: 'var(--accent)' }}>{d.code}</Link>{i < m.deals.length - 1 ? ',' : ''}</span>
          ))}
        </>}
      </span>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.025em', whiteSpace: 'nowrap' }}>Мастер-сделка {m.code}</span>
        <span style={{ alignSelf: 'center' }}><MasterStatusPill status={m.status} label={m.status} height={24} /></span>
        {!!m.docs && m.status !== 'черновик' && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{m.docs.paper ? 'бумага' : 'ЭДО'}</span>}
        <span style={{ fontSize: 12, color: 'var(--text-muted)', minWidth: 0 }}>
          договор <span style={{ fontFamily: MONO, color: 'var(--text-secondary)', ...nw }}>№ {m.contract?.number || '—'}</span> от <span style={nw}>{fmtDateFull(m.contract?.date)}</span>
          {' · '}{m.payer?.name || 'плательщик не задан'}{m.payer?.inn ? <>, ИНН <span style={{ fontFamily: MONO, ...nw }}>{m.payer.inn}</span></> : ''}
          {' · '}<span style={nw}>период <span style={{ fontFamily: MONO }}>{m.period}</span></span>
        </span>
        <StatusMoves m={{ ...m, status_actions: { ...(m.status_actions || {}), next: null } }} busy={busy} onStatus={onStatus} />
        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'baseline', gap: 6, whiteSpace: 'nowrap' }}>
          <span style={{ fontFamily: MONO, fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em' }}>{rub2(m.layout.total_gross)}</span>
          <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>с НДС</span>
        </span>
      </div>
      <StagePipeline m={m} canEdit={canEdit} onDone={onApply} onScans={onScans} />
      <EfficiencyRow eff={m.efficiency} />

      <div style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 14, padding: '0 4px 8px', borderBottom: '1px solid var(--border-card)', fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
        <span>Сделка</span><span>Статус</span><span>Итоговая сверка</span><span>Сумма ДС</span><span style={{ textAlign: 'right' }}>Цена за ед.</span><span style={{ textAlign: 'right' }}>К закрытию, до НДС</span><span style={{ textAlign: 'right' }}>С НДС</span><span />
      </div>
      {!m.deals.length && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, padding: '22px 0', borderBottom: '1px solid var(--border-row)' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)' }}>В пакете нет сделок</span>
          <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>Добавьте сделку этого договора за {m.period} — раскладка и ДС соберутся из её сверки.</span>
        </div>
      )}
      {m.deals.map(d => (
        <div key={d.id} style={{ display: 'grid', gridTemplateColumns: GRID, gap: 14, alignItems: 'center', padding: '9px 4px', borderBottom: '1px solid var(--border-row)' }}>
          <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 10, minWidth: 0 }}>
            <Link href={`/sales/deals/${d.code}`} style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, flex: '0 0 auto', color: 'var(--accent)' }}>{d.code}</Link>
            <span style={{ fontSize: 12.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.title}</span>
          </span>
          <span style={{ display: 'flex' }}><StatusPill state={d.state} text={d.status} /></span>
          <span title={d.verdict.text} style={{ fontFamily: MONO, fontSize: 11.5, color: VERDICT[d.verdict.tone], whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{d.verdict.text}</span>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{CLOSE_MODE[d.mode]}</span>
          <span title={d.price ? 'цена за единицу базовой строки медиаплана' : ''} style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)', textAlign: 'right', whiteSpace: 'nowrap' }}>
            {d.price ? `${rub2(d.price.price)} · ${d.price.model}` : '—'}</span>
          <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, textAlign: 'right', whiteSpace: 'nowrap' }}>{rub2(d.total_net)}</span>
          <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, textAlign: 'right', whiteSpace: 'nowrap' }}>{d.total_gross == null ? '—' : rub2(d.total_gross)}</span>
          <span>{!locked && <button type="button" disabled={busy} onClick={() => onRemove(d)} title="Убрать сделку из пакета"
            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, borderRadius: 6, border: 0, background: 'none', color: 'var(--text-faint)', cursor: 'pointer' }}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" aria-hidden><path d="M6 6l12 12M18 6L6 18" /></svg></button>}</span>
        </div>
      ))}
      {!locked && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 9 }}>
          <span data-pop-root style={{ position: 'relative', display: 'inline-flex' }}>
            <button type="button" disabled={busy} onClick={() => setPop(p => !p)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 30, padding: '0 12px', borderRadius: 9, border: '1px dashed var(--accent-border)', background: 'var(--bg-card)', color: 'var(--accent)', fontSize: 12, fontFamily: UI, fontWeight: 600, cursor: 'pointer' }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden><path d="M12 5v14M5 12h14" /></svg>сделка</button>
            <PortalPopover open={pop} minWidth={460}>
              <div data-pop-root style={{ padding: 8, fontFamily: UI }}>
                {!m.candidates.length && <div style={{ padding: 10, fontSize: 12.5, color: 'var(--text-muted)' }}>Других сделок по договору за {m.period} нет</div>}
                {m.candidates.map(c => (
                  <button key={c.id} type="button" onClick={() => { setPop(false); onAdd(c) }}
                    style={{ display: 'flex', width: '100%', gap: 8, alignItems: 'baseline', padding: '8px 10px', border: 0, borderRadius: 8, background: 'none', cursor: 'pointer', textAlign: 'left' }}>
                    <b style={{ fontFamily: MONO, color: 'var(--accent)' }}>{c.code}</b>
                    <span style={{ fontSize: 12.5, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title}</span>
                    <span style={{ marginLeft: 'auto', fontSize: 11.5, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{c.stage}</span>
                  </button>
                ))}
              </div>
            </PortalPopover>
          </span>
          <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>только этого договора и месяца</span>
        </div>
      )}
      </div>
      {!m.gate.ok && (
        <Note><b>Дальше конструктора документов пакет не уйдёт</b>, пока сверка не завершена у всех сделок:{' '}
          {m.gate.wait.map(w => `${w.code} — ${w.status}`).join('; ')}. Раскладку и ДС можно готовить уже сейчас.</Note>
      )}
    </div>
  )
}
