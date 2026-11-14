/**
 * Левая колонка компактной «Итоговой сверки» (хендофф design_handoff_final_recon, 14.11.2026): три показателя с полосой
 * выполнения, у услуг без РК — «Факт вводит аккаунт» тремя строками (факт · отчёт · себестоимость), строки МП — чтение.
 * Данные и действия — те же, что у блока карточки (`useClosing`).
 */
import { useState } from 'react'
import Link from 'next/link'
import { btn, inp, MONO } from '@/components/salesTableKit'
import { grp, grpDash, rub2 } from '@/lib/salesFormat'
import { detailText } from '@/lib/loadError'
import { CAP, num, unitOf } from '@/components/closing/closingKit'
import { FACT_FIELDS, factBad, factFilled, factPayload, factVals, uploadReport } from '@/components/closing/FactEntryPanel'

const BOX = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 12 }
const R = { fontFamily: MONO, fontSize: 12, textAlign: 'right', whiteSpace: 'nowrap' }
const LINES = 'minmax(0,1.5fr) minmax(0,.9fr) minmax(0,.8fr) minmax(72px,.8fr) minmax(0,1fr)'

function Metric({ l, v, s, fg }) {
  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
      <span style={{ ...CAP, fontSize: 9 }}>{l}</span>
      <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700, color: fg || 'var(--text-primary)', whiteSpace: 'nowrap' }}>{v}</span>
      <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={s}>{s}</span>
    </span>
  )
}

function Mark({ ok }) {
  return <span style={{ width: 14, fontWeight: 700, color: ok ? 'var(--income-fg)' : 'var(--warning-text)' }}>{ok ? '✓' : '!'}</span>
}

function EntryRow({ ok, title, sub, children }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '14px 108px minmax(0,1fr)', gap: 8, alignItems: 'start', padding: '8px 0', borderTop: '1px solid var(--border-row)' }}>
      <Mark ok={ok} />
      <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}><b style={{ fontSize: 12.5, whiteSpace: 'nowrap' }}>{title}</b>
        <span style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>{sub}</span></span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>{children}</span>
    </div>
  )
}

const vtrOf = (v) => (v && num(v.fact) > 0 && String(v.completed || '').trim() !== '' ? `${(num(v.completed) / num(v.fact) * 100).toFixed(1).replace('.', ',')} %` : '—')

function FactEntry({ fe, cost, dealId, canEdit, busy, onSave, onCost, onUploaded }) {
  const [vals, setVals] = useState(() => factVals(fe.rows))
  const [note, setNote] = useState(fe.note || '')
  const [costVal, setCostVal] = useState(cost != null ? String(cost) : '')
  const [upErr, setUpErr] = useState('')
  const set = (rid, k, v) => setVals(x => ({ ...x, [rid]: { ...x[rid], [k]: v } }))
  const canSave = !busy && !factBad(fe.rows, vals) && factFilled(fe.rows, vals).length > 0 && note.trim() !== ''
  const field = { ...inp, fontFamily: MONO, textAlign: 'right', padding: '5px 8px', fontSize: 12, minWidth: 0 }
  const upload = async (file) => {
    if (!file) return
    setUpErr('')
    try { await uploadReport(dealId, file); onUploaded() } catch (e) { setUpErr(detailText(e, 'Отчёт не загрузился')) }
  }
  const small = { ...btn(false), padding: '5px 12px', fontSize: 12 }
  return (
    <div style={{ background: 'var(--bg-tint)', border: '1px solid var(--accent-border)', borderRadius: 10, padding: '8px 12px', margin: '10px 0' }}>
      <span style={{ ...CAP, color: 'var(--accent-fg)' }}>Факт вводит аккаунт</span>
      <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 4 }}>статистики в системе нет — цифры из отчёта платформы / подрядчика</div>
      {!fe.rows.length && (
        <EntryRow ok={false} title="Факт" sub="строк МП нет">
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>В медиаплане сделки нет строк — факт внести не к чему. Отчёт и себестоимость — ниже.</span>
        </EntryRow>)}
      {fe.rows.map(r => (
        <EntryRow key={r.row_id} ok={r.fact != null} title="Факт" sub={`${fe.rows.length > 1 ? `${r.name} · ` : ''}план ${grp(r.volume)}`}>
          {/* Поля — по модели строки МП (эталон по услугам). Два поля (CPM, CPC) — подпись внутри поля, «Сохранить» в той же строке, как
              в эталоне дашборда; видео (досмотры, VTR) и фикс (пакеты, показы справочно) — подписи над полями. */}
          {(() => {
            const fields = FACT_FIELDS[r.kind] || FACT_FIELDS.cpm
            const labeled = r.kind === 'video' || r.kind === 'fix'
            const save = canEdit && fe.rows.length === 1 && <button type="button" disabled={!canSave} onClick={() => onSave(factPayload(fe.rows, vals), note.trim())}
              style={{ ...small, opacity: canSave ? 1 : 0.5, alignSelf: 'flex-end' }}>Сохранить</button>
            if (!labeled) {
              return (
                <span style={{ display: 'flex', gap: 6 }}>
                  {fields.map(([k, label]) => (
                    <input key={k} value={vals[r.row_id]?.[k] ?? ''} disabled={!canEdit} placeholder={label.replace(' факт', '').toLowerCase()}
                      onChange={e => set(r.row_id, k, e.target.value)} style={{ ...field, flex: 1 }} />))}
                  {save}
                </span>)
            }
            return (
              <span style={{ display: 'flex', gap: 6, alignItems: 'flex-end' }}>
                <span style={{ flex: 1, display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: '4px 6px' }}>
                  {fields.map(([k, label]) => (
                    <label key={k} style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                      <span style={{ ...CAP, fontSize: 8.5, whiteSpace: 'nowrap' }}>{label.replace(' факт', '').toLowerCase()}</span>
                      <input value={vals[r.row_id]?.[k] ?? ''} disabled={!canEdit} onChange={e => set(r.row_id, k, e.target.value)} style={field} />
                    </label>))}
                  {r.kind === 'video' && (
                    <label style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                      <span style={{ ...CAP, fontSize: 8.5, whiteSpace: 'nowrap' }}>VTR · считается</span>
                      <input readOnly value={vtrOf(vals[r.row_id])} style={{ ...field, background: 'var(--bg-subtle)', color: 'var(--text-secondary)', borderStyle: 'dashed' }} />
                    </label>)}
                </span>
                {save}
              </span>)
          })()}
        </EntryRow>
      ))}
      {!!fe.rows.length && <div style={{ display: 'flex', gap: 6, padding: '0 0 8px 130px' }}>
        <input value={note} disabled={!canEdit} onChange={e => setNote(e.target.value)} placeholder="источник цифр: отчёт платформы за …"
          style={{ ...inp, padding: '5px 8px', fontSize: 12, flex: 1, minWidth: 0 }} />
        {canEdit && fe.rows.length > 1 && <button type="button" disabled={!canSave} onClick={() => onSave(factPayload(fe.rows, vals), note.trim())}
          style={{ ...small, opacity: canSave ? 1 : 0.5 }}>Сохранить</button>}
      </div>}
      <EntryRow ok={!!fe.report} title="Отчёт" sub="платформы">
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, flex: 1, color: fe.report ? 'var(--income-fg)' : 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {fe.report ? `приложен · ${fe.report.filename}` : 'не приложен'}</span>
          {canEdit && <label style={{ ...small, color: 'var(--accent-fg)', cursor: 'pointer' }}>{fe.report ? 'Заменить' : 'Приложить'}
            <input type="file" style={{ display: 'none' }} onChange={e => upload(e.target.files?.[0])} /></label>}
        </span>
        {!!upErr && <span style={{ fontSize: 11.5, color: 'var(--danger-fg)' }}>{upErr}</span>}
      </EntryRow>
      <EntryRow ok={cost != null} title="Себестоимость" sub="без НДС">
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input value={costVal} disabled={!canEdit} onChange={e => setCostVal(e.target.value)} placeholder="сумма" style={{ ...field, flex: 1 }} />
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>₽</span>
          {canEdit && <button type="button" disabled={busy || costVal.trim() === '' || !(num(costVal) >= 0)}
            onClick={() => onCost(num(costVal))} style={{ ...small, opacity: busy || costVal.trim() === '' ? 0.5 : 1 }}>Сохранить</button>}
        </span>
      </EntryRow>
    </div>
  )
}

export default function ReconFacts({ s, dealId, canEdit, busy, onSave, onCost, onUploaded }) {
  const base = s.lines.find(l => l.kind === 'base')
  const unit = unitOf(base?.model)
  const low = s.fact_pct != null && s.fact_pct < s.thresholds.under
  const entered = !!s.fact_entry && (s.fact_entry.can_enter || s.fact_source === 'entered')
  const factFg = s.fact_shows == null ? undefined : low ? 'var(--warning-fg)' : 'var(--income-fg)'
  const over = s.fact_shows != null && s.fact_shows > s.plan_shows
  const pctSub = s.fact_shows == null ? '' : over ? 'сверх плана — перекрут' : s.fact_shows < s.plan_shows ? `недокрут ${grp(s.plan_shows - s.fact_shows)}` : 'в плане'
  return (
    <div style={{ ...BOX, padding: '12px 14px', display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 12 }}>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
          <span style={{ ...CAP, fontSize: 9 }}>План · {unit.plural}</span>
          <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700, whiteSpace: 'nowrap' }}>{grp(s.plan_shows)}</span>
          <span style={{ alignSelf: 'flex-start', padding: '1px 6px', borderRadius: 6, fontFamily: MONO, fontSize: 9.5, fontWeight: 700,
            background: s.bonus.shows ? 'var(--violet-tint)' : 'var(--bg-subtle)', color: s.bonus.shows ? 'var(--violet-fg)' : 'var(--text-muted)' }}>
            {s.bonus.shows ? `+ бонус ${grp(s.bonus.shows)}` : 'бонус не заказан'}</span>
          <span style={{ fontSize: 10.5, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {s.bonus.shows ? `перекрут до ${grp(s.plan_shows + s.bonus.shows)} — бонусный` : 'всё сверх плана — перекрут'}</span>
        </span>
        <Metric l={`Факт · ${unit.plural}`} v={grpDash(s.fact_shows)} fg={factFg}
          s={s.fact_source === 'entered' ? 'из отчёта платформы' : s.fact_entry?.can_enter ? 'РК нет — введите факт ниже' : 'DSP + Adfox'} />
        <Metric l="Выполнение плана" v={s.fact_pct == null ? '—' : `${String(s.fact_pct).replace('.', ',')} %`} fg={factFg} s={pctSub} />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 }}>
        <span style={{ flex: 1, height: 4, borderRadius: 2, background: 'var(--bg-subtle)', overflow: 'hidden' }}>
          <span style={{ display: 'block', height: '100%', width: `${Math.min(100, s.fact_pct || 0)}%`, background: low ? 'var(--warning)' : 'var(--income)' }} /></span>
        {over && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>перекрут в ДС не идёт</span>}
      </div>
      {!!(s.fact_entry?.can_enter || s.fact_entry?.open) && (
        <FactEntry key={`${s.fact_entry.at || ''}${s.cost_net ?? ''}${s.fact_entry.report?.filename || ''}`} fe={s.fact_entry} cost={s.cost_net}
          dealId={dealId} canEdit={canEdit} busy={busy} onSave={onSave} onCost={onCost} onUploaded={onUploaded} />
      )}
      <div style={{ display: 'grid', gridTemplateColumns: LINES, gap: 8, ...CAP, fontSize: 9, padding: '10px 0 6px', borderBottom: '1px solid var(--border-card)', marginTop: 8 }}>
        <span>Строки МП · чтение</span><span style={{ textAlign: 'right' }}>План</span><span style={{ textAlign: 'right' }}>Факт</span>
        <span style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>Цена · {unit.price}</span><span style={{ textAlign: 'right' }}>В ДС, до НДС</span>
      </div>
      {s.lines.map((l, i) => {
        const isBase = l.kind === 'base'
        const sub = isBase ? `базовая услуга · ${l.model || 'CPM'}` : l.bonus ? 'доп · бонус' : 'доп · платный'
        const net = isBase ? (s.lines.filter(x => x.kind === 'base').length === 1 ? s.base_ds_net : l.plan_net) : l.net
        return (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: LINES, gap: 8, alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--border-row)' }}>
            <span style={{ minWidth: 0 }}><span style={{ display: 'block', fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={l.name}>{l.name}</span>
              <span style={{ display: 'block', ...CAP, fontSize: 8.5, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{sub}</span></span>
            <span style={{ ...R, color: 'var(--text-secondary)' }}>{isBase ? grpDash(l.volume) : '—'}</span>
            <span style={{ ...R, fontWeight: 700, color: isBase && l.fact != null ? factFg : 'var(--text-faint)' }}>{isBase ? grpDash(l.fact) : '—'}</span>
            <span style={{ ...R, color: 'var(--text-secondary)' }}>{l.unit_price ? rub2(l.unit_price) : '—'}</span>
            <span style={{ ...R, fontWeight: 700, color: l.bonus ? 'var(--text-faint)' : 'var(--text-primary)' }}>{rub2(net)}</span>
          </div>
        )
      })}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, marginTop: 'auto', paddingTop: 10 }}>
        <span style={{ fontSize: 11, color: 'var(--text-faint)', flex: 1 }}>
          {entered ? 'Факт — из отчёта платформы.' : <>Факт — DSP + Adfox. Разбор по площадкам — в{' '}
            <Link href={`/traffic/campaign/${encodeURIComponent(s.deal_code || '')}`} target="_blank" style={{ color: 'var(--accent)', fontWeight: 700 }}>отчёте по РК →</Link></>}</span>
        <span style={{ ...CAP, fontSize: 9 }}>итого</span>
        <b style={{ fontFamily: MONO, fontSize: 14 }}>{rub2((s.base_ds_net || 0) + s.paid_extras_net)}</b>
      </div>
    </div>
  )
}
