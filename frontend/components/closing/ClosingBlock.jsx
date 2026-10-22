/**
 * Блок «Итоговая сверка» карточки сделки — по дизайну docs/IS.zip (design_handoff_final_recon, 15.10.2026).
 * Расчёт — один на сервере (`GET /final-recon/deal/{id}/closing`, app/final_recon/closing.py). Здесь только вид:
 * шапка (мета, пин «Сверка подтверждена», вердикт, «к закрытию»), три KPI, строки МП, расчёт справа и кнопка в два шага
 * «Подтвердить сверку» → «Собрать ДС» (модалка `CollectDsModal`). «Вручную» — только мастер и админ, причина обязательна.
 */
import { CLOSE_MODE } from '@/lib/masterStatus'
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import api, { auth } from '@/lib/api'
import { btn, MONO, UI } from '@/components/salesTableKit'
import { fmtDateTimeShort } from '@/lib/dates'
import { fmtDateFull, grp, grpDash, rub2 } from '@/lib/salesFormat'
import CollectDsModal from '@/components/closing/CollectDsModal'
import { CAP, Dot, GRID, Kpi, Pill, Pin, unitOf } from '@/components/closing/closingKit'
import SkRow from '@/components/closing/SkRow'
import ManualPanel from '@/components/closing/ManualPanel'
import FactEntryPanel from '@/components/closing/FactEntryPanel'

// Колонки строк МП резиновые — без горизонтальной прокрутки (владелец 19.10.2026; в макете она была — не копируем).
// Единицы по модели строки МП (макет 19.10.2026): CPC — клики, фикс — пакеты, иначе показы.



export default function ClosingBlock({ dealId, canEdit, cardStyle, reloadKey }) {
  const [s, setS] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(true)
  const [manualOpen, setManualOpen] = useState(false)
  const [modal, setModal] = useState(false)

  const load = useCallback(() => {
    api.get(`/final-recon/deal/${dealId}/closing`, auth())
      .then(r => { setS(r.data); setErr('') })
      .catch(e => setErr(e?.response?.data?.detail || 'Сверка не посчиталась'))
  }, [dealId])
  useEffect(() => { load() }, [load, reloadKey])

  const call = async (fn) => {
    setBusy(true); setErr('')
    try { await fn(); return true } catch (e) { setErr(e?.response?.data?.detail || 'Не удалось сохранить'); return false } finally { setBusy(false) }
  }
  const setMode = (mode, manualNet, vol, reason) => call(async () => {
    setS((await api.put(`/final-recon/deal/${dealId}/closing`, { mode, manual_net: manualNet ?? null, manual_volume: vol ?? null, reason: reason || null }, auth())).data)
  })
  const saveSk = (mode, percent) => call(async () => {
    await api.put(`/final-recon/deal/${dealId}/sk`, { mode, percent }, auth())
    setS((await api.get(`/final-recon/deal/${dealId}/closing`, auth())).data)
  })
  const saveCost = (cost) => call(async () => {
    setS((await api.put(`/final-recon/deal/${dealId}/cost`, { cost_net: cost }, auth())).data)
  })
  const saveFact = (rows, note) => call(async () => {
    setS((await api.put(`/final-recon/deal/${dealId}/fact`, { rows, note: note || null }, auth())).data)
  })
  const closeNoDocs = () => call(async () => {
    if (!window.confirm('Закрыть без документов? Бонусное размещение: сверка замораживается, сделка уходит в «Архив успешных сделок». ДС и закрывающих не будет.')) return
    setS((await api.post(`/final-recon/deal/${dealId}/close-no-docs`, {}, auth())).data)
  })
  const confirm = (on) => call(async () => { setS((await api.put(`/final-recon/deal/${dealId}/closing/confirm`, { on }, auth())).data) })
  const pick = (k) => {
    if (busy || !canEdit || s.frozen) return
    if (k === 'manual') { setManualOpen(true); return }
    setManualOpen(false)
    if (k !== s.mode) setMode(k)
  }

  if (!s) return err ? <div style={{ ...cardStyle, fontSize: 12.5, color: 'var(--danger-fg)' }}>{err}</div> : null
  const bonus = s.bonus.shows
  const factLow = s.fact_pct != null && s.fact_pct < s.thresholds.under
  const base = s.lines.find(l => l.kind === 'base')
  const unit = unitOf(base?.model)
  const account = !!s.fact_entry && (s.fact_entry.can_enter || s.fact_source === 'entered')
  const calcError = s.base_ds_net == null
  const blocked = calcError || manualOpen || busy
  // «Вручную» — только мастер и админ (владелец 16.10): штатному аккаунту пин не показываем вовсе;
  // уже выставленную мастером ручную сумму он видит как итог, без правки.
  const pins = s && (s.may_manual || s.mode === 'manual') ? ['fact', 'plan', 'manual'] : ['fact', 'plan']
  const head = (
    <div onClick={() => setOpen(o => !o)} style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', cursor: 'pointer' }}>
      <span style={{ fontSize: 10, color: 'var(--text-faint)', transform: open ? 'none' : 'rotate(-90deg)', transition: 'transform .15s' }}>▾</span>
      <span style={{ ...CAP, fontSize: 11, color: 'var(--text-secondary)' }}>Итоговая сверка</span>
      <span style={{ ...CAP, fontWeight: 600 }}>{s.period || '—'} · расчёт {fmtDateTimeShort(s.calculated_at)}</span>
      {/* На кого закрываем — контрагент доходного договора (у контура аккаунта это посредник; владелец 19.10.2026) */}
      <span style={{ fontSize: 12, color: s.closing_to ? 'var(--text-secondary)' : 'var(--warning-text)' }}
        title={s.closing_to ? `ИНН ${s.closing_to.inn || '—'} · договор ${s.closing_to.contract || '—'}` : 'Выберите доходный договор в блоке ОРД — по нему собираются ДС и закрывающие'}>
        закрытие на: {s.closing_to ? s.closing_to.name : 'доходный договор не выбран'}</span>
      <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }} onClick={e => e.stopPropagation()}>
        {/* В мастер-сделке — ссылка на её раскладку (п. 40 плана) */}
        {!!s.master && (
          <Link href={`/accounts/master/${s.master.code}`} title={`Мастер-сделка ${s.master.code} · ${s.master.status}`}
            style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent)', textDecoration: 'none',
              padding: '4px 10px', borderRadius: 8, border: '1px solid var(--accent-border)', background: 'var(--bg-tint)' }}>
            в {s.master.code}</Link>
        )}
        {!!s.master?.foreign && <span style={{ ...CAP, fontWeight: 600, color: 'var(--warning-text)' }}>собирает {s.master.by}</span>}
        {/* Сверка этой сделки готова, пакет ждёт остальных (владелец 21.10.2026) */}
        {!!s.master?.package_wait?.length && (
          <span style={{ ...CAP, fontWeight: 600, color: 'var(--text-secondary)' }}
            title={`Мастер-сделка соберётся, когда в ДО отправят: ${s.master.package_wait.join(', ')}`}>
            сверка готова · ждём пакет: {s.master.package_wait.join(', ')}</span>
        )}
        {s.no_docs?.closed_at ? <Pill tone="ok" title={`${s.no_docs.closed_by || ''} · ${fmtDateTimeShort(s.no_docs.closed_at)}`}>Закрыто без документов</Pill>
          : s.frozen ? <Pill tone="ok">Отправлено в ДО</Pill>
          : s.confirmed && <Pill tone="ok" title={canEdit ? 'Снять подтверждение' : undefined} onClick={canEdit ? () => confirm(false) : undefined}>Сверка подтверждена</Pill>}
        <Pill tone={s.verdict.tone}>{s.verdict.text}</Pill>
        {!!s.adfox_stale && (
          <Pill tone="warn" title={`Adfox грузится вручную и отстаёт: данные по ${fmtDateFull(s.adfox_stale.adfox_as_of)}, DSP/конец РК — ${fmtDateFull(s.adfox_stale.reference)}`}>
            данные Adfox на {fmtDateFull(s.adfox_stale.adfox_as_of)} — уточни у трафика</Pill>
        )}
        <span style={{ ...CAP, fontWeight: 600 }}>к закрытию · {CLOSE_MODE[s.mode]}</span>
        <b style={{ fontFamily: MONO, fontSize: 16 }}>{rub2(s.total_gross)}</b>
      </span>
    </div>
  )

  return (
    <div style={cardStyle}>
      {head}
      {open && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', margin: '16px 0', padding: '14px 0', borderTop: '1px solid var(--border-row)', borderBottom: '1px solid var(--border-row)' }}>
            <Kpi label={`План · ${unit.plural}`} value={grp(s.plan_shows)}
              tag={<span style={{ padding: '3px 8px', borderRadius: 7, fontFamily: MONO, fontSize: 10.5, fontWeight: 700,
                background: bonus ? 'var(--violet-tint)' : 'var(--bg-subtle)', color: bonus ? 'var(--violet-fg)' : 'var(--text-muted)' }}>
                {bonus ? `+ бонус ${grp(bonus)}` : 'бонус не заказан'}</span>}
              hint={bonus ? `перекрут до ${grp(s.plan_shows + bonus)} — бонусный` : 'всё сверх плана — перекрут'} />
            <div style={{ borderLeft: '1px solid var(--border-row)' }}>
              <Kpi label={`Факт · ${unit.plural}`} value={grpDash(s.fact_shows)} tone={s.fact_shows == null ? undefined : factLow ? 'var(--danger-fg)' : 'var(--income-fg)'}
                hint={s.fact_source === 'entered' ? 'введено аккаунтом' : s.fact_entry?.can_enter ? 'РК нет — введите факт ниже' : 'DSP + Adfox'} />
            </div>
            <div style={{ borderLeft: '1px solid var(--border-row)' }}>
              <Kpi label="Выполнение плана" value={s.fact_pct == null ? '—' : <>{String(s.fact_pct).replace('.', ',')}<span style={{ fontSize: 14 }}> %</span></>}
                tone={s.fact_pct == null ? undefined : factLow ? 'var(--danger-fg)' : 'var(--income-fg)'}
                hint={s.fact_shows != null && s.fact_shows < s.plan_shows ? `недокрут ${grp(s.plan_shows - s.fact_shows)}` : ''} />
            </div>
          </div>

          <div style={{ display: 'flex', gap: 20, alignItems: 'stretch', flexWrap: 'wrap', opacity: s.frozen ? 0.6 : 1 }}>
            <div style={{ flex: '1 1 520px', minWidth: 0 }}>
              {!!s.fact_entry?.can_enter && (
                <FactEntryPanel key={`${s.fact_entry.at || ''}${s.cost_net ?? ''}${s.fact_entry.report?.filename || ''}`} fe={s.fact_entry} dealId={dealId} cost={s.cost_net}
                  busy={busy} canEdit={canEdit} onSave={saveFact} onCost={saveCost} onUploaded={load} />
              )}
              <div style={{ ...CAP, marginBottom: 8 }}>Строки МП <span style={{ fontWeight: 600 }}>только чтение</span></div>
              <div style={{ display: 'grid', gridTemplateColumns: GRID, ...CAP, fontWeight: 600, padding: '0 4px 8px', borderBottom: '1px solid var(--border-card)', gap: 8 }}>
                <span>Строка</span><span>Режим</span><span style={{ textAlign: 'right' }}>План</span><span style={{ textAlign: 'right' }}>Факт</span>
                <span style={{ textAlign: 'right' }}>Цена · {unit.price}</span><span style={{ textAlign: 'right' }}>В ДС, до НДС</span>
              </div>
              {s.lines.map((l, i) => {
                const video = l.kind === 'base' && s.fact_entry?.rows?.some(r => r.kind === 'video' && l.name && l.name.startsWith(r.name))
                const mode = l.kind === 'base' ? `${l.model || 'CPM'}${video ? ' · видео' : ''}` : l.bonus ? 'Бонус' : 'Полная цена'
                const dot = l.kind === 'base' ? 'var(--accent)' : l.bonus ? 'var(--violet-fg)' : 'var(--text-faint)'
                const sub = l.kind === 'base' ? 'базовая услуга' : l.bonus ? 'доп · бонус' : 'доп · платный'
                const lineNet = l.kind === 'base' ? (s.lines.filter(x => x.kind === 'base').length === 1 ? s.base_ds_net : l.plan_net) : l.net
                const R = { fontFamily: MONO, fontSize: 12.5, textAlign: 'right', overflowWrap: 'anywhere', minWidth: 0 }
                return (
                  <div key={i} style={{ display: 'grid', gridTemplateColumns: GRID, gap: 8, alignItems: 'center', padding: '12px 4px', borderBottom: '1px solid var(--border-row)' }}>
                    <span style={{ minWidth: 0 }}><span style={{ display: 'block', fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.name}</span>
                      <span style={{ ...CAP, fontWeight: 600 }}>{sub}</span></span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', fontSize: 12.5 }}><Dot c={dot} />{mode}</span>
                    <span style={{ ...R, color: 'var(--text-secondary)' }}>{l.kind === 'base' ? grpDash(l.volume) : '—'}</span>
                    <span style={{ ...R, color: l.kind === 'base' && l.fact != null ? (l.fact / (l.volume || 1) * 100 < s.thresholds.under ? 'var(--danger-fg)' : 'var(--income-fg)') : 'var(--text-faint)' }}>
                      {l.kind === 'base' ? grpDash(l.fact) : '—'}</span>
                    <span style={{ ...R, color: 'var(--text-secondary)' }}>{l.unit_price ? rub2(l.unit_price) : '—'}</span>
                    <span style={{ ...R, fontWeight: 700, color: l.bonus ? 'var(--text-faint)' : 'var(--text-primary)' }}>{rub2(lineNet)}</span>
                  </div>
                )
              })}
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 4px', ...CAP }}>
                <span>Итого</span><b style={{ fontFamily: MONO, fontSize: 14, color: 'var(--text-primary)' }}>{rub2((s.base_ds_net || 0) + s.paid_extras_net)}</b></div>
              <div style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>
                {account ? 'Строки — из МП: базовая услуга и допы, платные и бонусные. Факт — из отчёта платформы.'
                  : <>Строки — из МП: базовая услуга и допы, платные и бонусные. Факт — DSP + Adfox. Разбор по площадкам — в{' '}
                    <Link href={`/traffic/campaign/${encodeURIComponent(s.deal_code || '')}`} target="_blank" style={{ color: 'var(--accent)' }}>«Отчёте по РК»</Link>.</>}</div>
            </div>

            <div style={{ flex: '0 1 440px', minWidth: 360, display: 'flex', flexDirection: 'column', gap: 10, borderLeft: '1px solid var(--border-row)', paddingLeft: 20 }}>
              <span style={CAP}>Базовая услуга в ДС</span>
              <div style={{ display: 'grid', gridTemplateColumns: `repeat(${pins.length}, minmax(0,1fr))`, gap: 8 }}>
                {pins.map(k => (
                  <Pin key={k} k={k} on={manualOpen ? k === 'manual' : s.mode === k} isDefault={s.mode_default === k}
                    value={s.amounts[k]} by={k === 'manual' ? s.manual_by : null} disabled={!canEdit || s.frozen || (k === 'manual' && !s.may_manual)} onPick={pick} />
                ))}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>
                {s.mode === 'fact' && s.fact_shows == null ? 'Факта нет — сумма по факту не считается.'
                  : s.mode === 'fact' && base ? `В ДС уходит откручённый факт: ${grp(Math.min(s.fact_shows ?? 0, s.plan_shows))} ${unit.gen} × ${rub2(base.unit_price)} за ${unit.price}.`
                  : s.mode === 'plan' ? 'В ДС уходит сумма МП — нужна договорённость с клиентом.'
                    : 'Ручная сумма — кто, когда и почему, в журнале.'}</div>
              {manualOpen && (
                <ManualPanel s={s} busy={busy} onCancel={() => setManualOpen(false)}
                  onSave={async (v, vol, reason) => { if (await setMode('manual', v, vol, reason)) setManualOpen(false) }} />
              )}
              <SkRow key={`${s.sk.mode}${s.sk.percent}`} sk={s.sk} canEdit={canEdit && !s.frozen} busy={busy} onSave={saveSk} />
              {calcError && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 12, background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', color: 'var(--danger-fg)', fontSize: 12.5 }}>
                  Сверка не посчиталась: нет факта{account ? '' : ' по РК'} — выберите «Под МП» или {account ? 'внесите факт выше' : 'дождитесь статистики'}.
                  <button type="button" style={{ ...btn(false), marginLeft: 'auto' }} onClick={load}>Пересчитать</button>
                </div>
              )}
              {!!err && <div style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</div>}
              <div style={{ padding: '14px 16px', borderRadius: 12, background: 'var(--bg-tint)', border: '1px solid var(--accent-border)', marginTop: 'auto' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10 }}>
                  <b style={{ fontSize: 15, color: 'var(--accent-fg)' }}>К закрытию</b>
                  <span><span style={{ ...CAP, fontWeight: 600 }}>до НДС </span><b style={{ fontFamily: MONO, fontSize: 13 }}>{rub2(s.total_net)}</b></span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10, marginTop: 4 }}>
                  <span style={{ fontSize: 11.5, color: 'var(--text-faint)', lineHeight: 1.45 }}>
                    базовая {rub2(s.base_ds_net)} + платные допы {rub2(s.paid_extras_net)}
                    {s.sk.mode === 'скидка в счёт' && !!s.sk.amount_net ? ` − скидка ${rub2(s.sk.amount_net)}` : ''}</span>
                  <span style={{ whiteSpace: 'nowrap' }}><span style={{ ...CAP, fontWeight: 600 }}>с НДС </span>
                    <b style={{ fontFamily: MONO, fontSize: 26, color: 'var(--accent-fg)' }}>{rub2(s.total_gross)}</b></span>
                </div>
              </div>
              {!!s.no_docs?.eligible && (
                <div style={{ padding: '10px 12px', borderRadius: 12, background: 'var(--violet-tint)', border: '1px solid var(--violet-border)', color: 'var(--violet-fg)', fontSize: 12.5 }}>
                  Бонусное размещение: сумма медиаплана 0 ₽ — документы не нужны. Сделка закрывается без ДС и уходит в «Архив успешных сделок».</div>
              )}
              {canEdit && !s.frozen && s.no_docs?.eligible && (
                <button type="button" disabled={busy} onClick={closeNoDocs}
                  style={{ height: 44, borderRadius: 12, border: 0, fontFamily: UI, fontSize: 14, fontWeight: 700, color: 'var(--on-accent)',
                    background: busy ? 'var(--accent-soft)' : 'var(--accent)', cursor: busy ? 'not-allowed' : 'pointer' }}>
                  Закрыть без документов</button>
              )}
              {canEdit && !s.frozen && !s.no_docs?.eligible && (
                s.confirmed ? (
                  <button key="collect" type="button" disabled={blocked} onClick={() => setModal(true)}
                    style={{ height: 44, borderRadius: 12, border: 0, fontFamily: UI, fontSize: 14, fontWeight: 700, color: 'var(--on-accent)',
                      background: blocked ? 'var(--accent-soft)' : 'var(--accent)', cursor: blocked ? 'not-allowed' : 'pointer', animation: 'popIn .2s ease both' }}>
                    Собрать ДС</button>
                ) : (
                  <button key="confirm" type="button" disabled={blocked} onClick={() => confirm(true)}
                    style={{ height: 44, borderRadius: 12, border: 0, fontFamily: UI, fontSize: 14, fontWeight: 700, color: 'var(--on-accent)',
                      background: blocked ? 'var(--accent-soft)' : 'var(--accent)', cursor: blocked ? 'not-allowed' : 'pointer' }}>
                    Подтвердить сверку</button>
                )
              )}
              {s.frozen && <span style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>
                {s.no_docs?.closed_at ? `Закрыто без документов${s.no_docs.closed_by ? ` · ${s.no_docs.closed_by}` : ''} · ${fmtDateTimeShort(s.no_docs.closed_at)}` : 'Отправлено в ДО'} — правки закрыты, цифры на момент закрытия.</span>}
              {!s.frozen && !!s.master && !s.may_manual && <span style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>Сделка в мастер-сделке — правки у мастера.</span>}
              {s.frozen && !s.no_docs?.closed_at && <CollectDsModal.OpenLink dealId={dealId} />}
              <style>{'@keyframes popIn{from{opacity:0;transform:scale(.97)}to{opacity:1;transform:none}}'}</style>
            </div>
          </div>
        </>
      )}
      {modal && <CollectDsModal dealId={dealId} gross={s.total_gross} onClose={() => setModal(false)} onDone={load} />}
    </div>
  )
}
