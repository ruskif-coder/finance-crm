/**
 * Правая колонка компактной «Итоговой сверки» (хендофф design_handoff_final_recon, 14.11.2026): база ДС списком, СК по сделке,
 * «К закрытию» и кнопка. Правила — сервера и блока карточки: «Вручную» только мастер/админ, подтверждение — когда сумма
 * посчиталась, после «Отправить в ДО» сумму меняют мастер и админ, пока пакет не ушёл в 1С (`sum_open`).
 */
import { useState } from 'react'
import Link from 'next/link'
import { btn, inp, MONO, UI } from '@/components/salesTableKit'
import { rub2 } from '@/lib/salesFormat'
import { CLOSE_MODE } from '@/lib/masterStatus'
import { CAP, num, unitOf } from '@/components/closing/closingKit'
import ManualPanel from '@/components/closing/ManualPanel'

const BOX = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12 }
const cap1 = (t) => (t ? t[0].toUpperCase() + t.slice(1) : t)
const pctTxt = (v) => String(v ?? 0).replace('.', ',')

function PinList({ s, keys, on, canPick, onPick }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', background: 'var(--bg-subtle)', borderRadius: 10, padding: 3 }}>
      {keys.map(k => {
        const sel = on === k
        const off = !canPick || (k === 'manual' && !s.may_manual)
        return (
          <button key={k} type="button" disabled={off} onClick={() => onPick(k)} title={off && k === 'manual' ? 'Ручная сумма — только мастер или админ' : undefined}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', border: 0, borderRadius: 8, fontFamily: UI, fontSize: 12.5, textAlign: 'left',
              background: sel ? 'var(--bg-card)' : 'transparent', boxShadow: sel ? 'var(--shadow-card)' : 'none',
              color: off ? 'var(--text-faint)' : sel ? 'var(--accent-fg)' : 'var(--text-primary)', fontWeight: sel ? 700 : 500, cursor: off ? 'not-allowed' : 'pointer' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', border: `2px solid ${sel ? 'var(--accent)' : 'var(--border-hover)'}`, background: sel ? 'var(--accent)' : 'transparent' }} />
            {cap1(CLOSE_MODE[k])}
            {s.mode_default === k && <span style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 500 }}>по умолч.</span>}
            {k === 'manual' && s.manual_by && <span style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 500 }}>{s.manual_by}</span>}
            <span style={{ marginLeft: 'auto', fontFamily: MONO, fontWeight: 700 }}>{s.amounts[k] == null ? '—' : rub2(s.amounts[k])}</span>
          </button>
        )
      })}
    </div>
  )
}

function Sk({ sk, canEdit, busy, onSave }) {
  const [pct, setPct] = useState(sk.percent != null ? pctTxt(sk.percent) : '')
  const inBill = sk.mode === 'скидка в счёт'
  const own = sk.source === 'deal'
  const legal = sk.payer_percent != null ? `${pctTxt(sk.payer_percent)} %` : 'не задано'
  const changed = String(pct).trim() !== '' && num(pct) !== (sk.percent ?? null)
  const okPct = num(pct) >= 0 && num(pct) <= 100
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 10, borderTop: '1px solid var(--border-row)' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ ...CAP, fontSize: 9, letterSpacing: '.05em', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{inBill ? 'СК · скидка в счёт' : 'СК по агентским условиям'}</span>
        {inBill && canEdit && <>
          <input value={pct} onChange={e => setPct(e.target.value)} style={{ ...inp, width: 42, fontFamily: MONO, textAlign: 'right', padding: '4px 5px', fontSize: 12 }} />
          <span style={{ fontSize: 12 }}>%</span>
          <button type="button" disabled={busy || !changed || !okPct} onClick={() => onSave('скидка в счёт', num(pct))}
            style={{ ...btn(false), padding: '4px 7px', fontSize: 11, opacity: busy || !changed ? 0.5 : 1 }}>Сохранить</button>
        </>}
      </span>
      {inBill && <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
        Скидка в счёт · {pctTxt(sk.percent)} % {own ? `по этой сделке (по условиям ${legal})` : 'по условиям'}:
        {sk.amount_net ? ` −${rub2(sk.amount_net)}` : ''} с базовой услуги, допы без СК.
        {own && canEdit && <button type="button" disabled={busy} onClick={() => onSave(null, null)}
          style={{ marginLeft: 6, background: 'none', border: 0, padding: 0, color: 'var(--accent)', cursor: 'pointer', fontSize: 11.5 }}>как в условиях</button>}</span>}
      {sk.mode === 'постоплата' && <span style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>
        Постоплата СК {legal}: счёт на полную сумму, СК выплачивается агентству отдельно.</span>}
      {!sk.mode && <>
        <span style={{ alignSelf: 'flex-end', padding: '3px 9px', borderRadius: 7, fontSize: 11.5, fontWeight: 700, background: 'var(--warning-tint)', border: '1px solid var(--warning-border)', color: 'var(--warning-text)' }}>
          Способ СК не задан</span>
        <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
          Правило по договору закрытия и агентству сделки задаётся в «Агентских условиях»{sk.payer_id ? '' : ' (сначала выберите доходный договор)'}.{' '}
          <Link href="/sales/agency-terms" target="_blank" style={{ color: 'var(--accent)', fontWeight: 700 }}>Открыть →</Link></span>
      </>}
      {inBill && sk.mp_discount?.length > 0 && (
        <span style={{ fontSize: 11.5, fontWeight: 600, padding: '6px 8px', borderRadius: 8, lineHeight: 1.4,
          background: sk.double ? 'var(--danger-tint)' : 'var(--warning-tint)', color: sk.double ? 'var(--danger-fg)' : 'var(--warning-text)' }}>
          В строках МП уже скидка {sk.mp_discount.map(pctTxt).join(', ')} %{sk.double ? ' — вычтется дважды: уберите её из МП или поправьте СК. Пока так — сверку не подтвердить.' : ' — проверьте, что это не одна и та же скидка.'}
        </span>
      )}
    </div>
  )
}

export default function ReconDecision({ s, canEdit, busy, err, setMode, saveSk, confirm, closeNoDocs, onCollect, onReload }) {
  const [manualOpen, setManualOpen] = useState(false)
  const pinsOpen = !s.frozen || (!!s.may_manual && !!s.sum_open)
  const keys = s.may_manual || s.mode === 'manual' ? ['fact', 'plan', 'manual'] : ['fact', 'plan']
  const base = s.lines.find(l => l.kind === 'base')
  const unit = unitOf(base?.model)
  const calcError = s.base_ds_net == null
  const blocked = calcError || manualOpen || busy
  const fe = s.fact_entry
  const missing = (fe?.can_enter || fe?.open) ? [!fe.complete && 'факт', !fe.report && 'отчёт платформы', s.cost_net == null && 'себестоимость'].filter(Boolean) : []
  const waitFact = !fe?.can_enter && s.fact_shows == null && s.mode === 'fact'
  const pick = (k) => {
    if (busy || !canEdit || !pinsOpen) return
    if (k === 'manual') { setManualOpen(true); return }
    setManualOpen(false)
    if (k !== s.mode) setMode(k)
  }
  const hint = s.mode === 'fact' && s.fact_shows == null ? 'Факта нет — сумма по факту не считается.'
    : s.mode === 'fact' ? `В ДС уходит сумма по факту ${unit.gen}${base ? ` × ${rub2(base.unit_price)} за ${unit.price}` : ''}.`
      : s.mode === 'plan' ? (s.fact_shows != null && s.fact_shows < s.plan_shows ? 'В ДС уходит сумма МП, факт ниже — нужна договорённость с клиентом.' : 'В ДС уходит сумма МП.')
        : 'Ручная сумма — кто, когда и почему, в журнале.'
  const big = { height: 38, borderRadius: 10, border: 0, fontFamily: UI, fontSize: 13, fontWeight: 700, color: 'var(--on-accent)' }
  return (
    <div style={{ ...BOX, padding: '12px 12px', display: 'flex', flexDirection: 'column', gap: 8, opacity: s.frozen && !pinsOpen ? 0.75 : 1 }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ ...CAP, flex: 1 }}>Базовая услуга в ДС</span>
        {(s.frozen && !pinsOpen) ? <span style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>заморожено</span>
          : (!!s.master && !s.may_manual) && <span style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>правки у мастера</span>}
      </span>
      <PinList s={s} keys={keys} on={manualOpen ? 'manual' : s.mode} canPick={canEdit && pinsOpen && !busy} onPick={pick} />
      <span style={{ fontSize: 11.5, color: 'var(--text-faint)', lineHeight: 1.4 }}>{hint}</span>
      {s.mode === 'manual' && !s.may_manual && <span style={{ fontSize: 11.5, color: 'var(--text-muted)', padding: '6px 8px', borderRadius: 8, border: '1px dashed var(--border-card)' }}>
        Сумму поставил {s.manual_by ? `мастер ${s.manual_by}` : 'мастер'} — изменить может только он. Причина — в журнале действий.</span>}
      {calcError && !fe?.can_enter && s.mode !== 'fact' && (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 10, background: 'var(--danger-tint)', color: 'var(--danger-fg)', fontSize: 11.5 }}>
          Сверка не посчиталась: нет факта по РК — выберите «Под МП» или дождитесь статистики.
          {!!onReload && <button type="button" onClick={onReload} style={{ ...btn(false), marginLeft: 'auto', padding: '4px 10px', fontSize: 11.5 }}>Пересчитать</button>}
        </span>)}
      {manualOpen && <ManualPanel s={s} busy={busy} onCancel={() => setManualOpen(false)}
        onSave={async (v, vol, reason) => { if (await setMode('manual', v, vol, reason)) setManualOpen(false) }} />}
      <Sk key={`${s.sk.mode}${s.sk.percent}`} sk={s.sk} canEdit={canEdit && !s.frozen} busy={busy} onSave={saveSk} />
      <div style={{ marginTop: 'auto', padding: '10px 12px', borderRadius: 10, background: 'var(--bg-tint)', border: '1px solid var(--accent-border)' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <b style={{ fontSize: 13, color: 'var(--accent-fg)', flex: 1 }}>К закрытию</b>
          <span style={{ ...CAP, fontSize: 9 }}>до НДС</span><b style={{ fontFamily: MONO, fontSize: 12.5 }}>{calcError ? '—' : rub2(s.total_net)}</b>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'flex-end', gap: 8 }}>
          <span style={{ ...CAP, fontSize: 9 }}>с НДС</span>
          <b style={{ fontFamily: MONO, fontSize: 20, color: 'var(--accent-fg)' }}>{calcError ? '—' : rub2(s.total_gross)}</b>
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-faint)', lineHeight: 1.4 }}>
          {calcError ? `посчитается после ${fe?.can_enter ? 'ввода факта' : 'сбора факта'}`
            : `базовая ${rub2(s.base_ds_net)} + допы ${rub2(s.paid_extras_net)}${s.sk.mode === 'скидка в счёт' && s.sk.amount_net ? ` − скидка ${rub2(s.sk.amount_net)}` : ''}`}</div>
      </div>
      {!!err && <span style={{ fontSize: 11.5, color: 'var(--danger-fg)' }}>{err}</span>}
      {!!s.no_docs?.eligible && <span style={{ fontSize: 11.5, color: 'var(--violet-fg)' }}>Бонусное размещение: сумма МП 0 ₽ — документы не нужны.</span>}
      {canEdit && !s.frozen && (
        s.no_docs?.eligible ? <button type="button" disabled={busy} onClick={closeNoDocs} style={{ ...big, background: 'var(--accent)', cursor: 'pointer' }}>Закрыть без документов</button>
          : waitFact ? <span style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>Ждём факт — выберите «Под МП» или дождитесь статистики</span>
            : s.confirmed ? <button type="button" disabled={blocked} onClick={onCollect} style={{ ...big, background: blocked ? 'var(--accent-soft)' : 'var(--accent)', cursor: blocked ? 'not-allowed' : 'pointer' }}>Собрать ДС</button>
              : <>
                {missing.length > 0 && <span style={{ fontSize: 11.5, color: 'var(--warning-text)', lineHeight: 1.4 }}>Внесите: {missing.join(', ')}.</span>}
                {s.contract_missing
                  // Основная воронка: без доходного договора сервер не подтвердит (кроме прямого рекламодателя) — владелец 14.11.2026
                  ? <span style={{ fontSize: 11.5, color: 'var(--warning-text)', lineHeight: 1.4 }}>Чтобы подтвердить, нужно: доходный договор — блок ОРД карточки (или отметка «Прямой рекламодатель»).</span>
                  : !s.closing_to && <span style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.4 }}>Доходный договор не выбран — ДС соберётся без договора закрытия.</span>}
                <button type="button" disabled={blocked || !!s.contract_missing} onClick={() => confirm(true)}
                  style={{ ...big, background: blocked || s.contract_missing ? 'var(--accent-soft)' : 'var(--accent)', cursor: blocked || s.contract_missing ? 'not-allowed' : 'pointer' }}>Подтвердить сверку</button>
              </>
      )}
      {s.frozen && <span style={{ fontSize: 11.5, color: 'var(--text-muted)', textAlign: 'center' }}>
        {s.no_docs?.closed_at ? 'Закрыто без документов.' : 'Сверка зафиксирована.'}{pinsOpen ? ' Сумму ещё меняют мастер и админ, пока пакет не ушёл в 1С.' : ' Правка — только через юриста.'}</span>}
      {!s.frozen && !!s.master && !s.may_manual && <span style={{ fontSize: 11.5, color: 'var(--text-muted)', textAlign: 'center' }}>Сделка в мастер-сделке {s.master.code} — правки у мастера.</span>}
    </div>
  )
}
