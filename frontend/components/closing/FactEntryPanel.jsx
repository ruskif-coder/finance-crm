/**
 * Ввод факта для контура аккаунта: метрики по модели строки МП, отчёт платформы, себестоимость, чек-лист.
 * Часть блока «Итоговая сверка» (`ClosingBlock.jsx`), вынесено при аудите 20.10.2026.
 */
import { useState } from 'react'
import api, { auth } from '@/lib/api'
import { btn, inp, MONO } from '@/components/salesTableKit'
import { fmtDateTimeShort } from '@/lib/dates'
import { grp, rub2 } from '@/lib/salesFormat'
import { CAP, Check, asText, isNum, num } from '@/components/closing/closingKit'

export const FACT_FIELDS = {
  cpm: [['fact', 'Показы факт'], ['clicks', 'Клики факт']],
  video: [['fact', 'Показы факт'], ['completed', 'Досмотры 100 %'], ['clicks', 'Клики факт']],
  cpc: [['fact', 'Клики факт']],
  fix: [['fact', 'Пакетов факт'], ['reference_shows', 'Показы справочно']],
}
export const PLAN_UNIT = { cpm: 'показов', video: 'показов', cpc: 'кликов', fix: 'пак.' }
export default function FactEntryPanel({ fe, dealId, cost, busy, canEdit, onSave, onCost, onUploaded }) {
  const [vals, setVals] = useState(() => Object.fromEntries(fe.rows.map(r => [r.row_id,
    Object.fromEntries((FACT_FIELDS[r.kind] || FACT_FIELDS.cpm).map(([k]) => [k, asText(r[k])]))])))
  const [note, setNote] = useState(fe.note || '')
  const [costVal, setCostVal] = useState(cost != null ? rub2(cost) : '')
  const [upErr, setUpErr] = useState('')
  const set = (rid, k, v) => setVals(x => ({ ...x, [rid]: { ...x[rid], [k]: v } }))
  const filled = fe.rows.filter(r => isNum(vals[r.row_id]?.fact))
  const bad = fe.rows.some(r => Object.values(vals[r.row_id] || {}).some(v => String(v || '').trim() !== '' && !(num(v) >= 0)))
  const field = { ...inp, fontFamily: MONO, textAlign: 'right', width: '100%' }
  const vtr = (r) => {
    const v = vals[r.row_id] || {}
    return isNum(v.fact) && isNum(v.completed) && num(v.fact) > 0 ? `${(num(v.completed) / num(v.fact) * 100).toFixed(1).replace('.', ',')} %` : '—'
  }
  const upload = async (file) => {
    if (!file) return
    setUpErr('')
    const fd = new FormData()
    fd.append('file', file)
    try { await api.post(`/sales/deals/${dealId}/files/report`, fd, auth()); onUploaded() }
    catch (e) { setUpErr(e?.response?.data?.detail || 'Отчёт не загрузился') }
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 12, borderRadius: 12, border: '1px solid var(--accent-border)', background: 'var(--bg-tint)', marginBottom: 14 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ ...CAP, color: 'var(--accent-fg)' }}>План и факт · факт вводит аккаунт</span>
        <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>Статистики в системе нет — цифры из отчёта платформы / подрядчика.</span>
        {!!fe.by && <span style={{ marginLeft: 'auto', fontSize: 11.5, color: 'var(--text-muted)' }}>введено: {fe.by} · {fmtDateTimeShort(fe.at)}</span>}
      </div>
      {fe.rows.map(r => {
        const fields = FACT_FIELDS[r.kind] || FACT_FIELDS.cpm
        return (
          <div key={r.row_id} style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 8, borderTop: '1px solid var(--border-row)' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
              <b style={{ fontSize: 13 }}>{r.name || 'строка МП'}</b>
              <span style={{ ...CAP, fontWeight: 600 }}>{r.model}{r.kind === 'video' ? ' · видео' : ''}</span>
              <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 12.5, color: 'var(--text-muted)' }}>план {grp(r.volume)} {PLAN_UNIT[r.kind] || ''}</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 8 }}>
              {fields.map(([k, label]) => (
                <label key={k}><span style={CAP}>{label}</span>
                  <input value={vals[r.row_id]?.[k] ?? ''} disabled={!canEdit} style={field} onChange={e => set(r.row_id, k, e.target.value)} /></label>
              ))}
              {r.kind === 'video' && (
                <label><span style={CAP}>VTR</span>
                  <input readOnly value={vtr(r)} style={{ ...field, background: 'var(--bg-subtle)', color: 'var(--text-secondary)' }} /></label>
              )}
            </div>
            {r.kind === 'fix' && <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>Фикс: сумма в ДС по договорённости; показы — для отчёта клиенту, на деньги не влияют.</span>}
          </div>
        )
      })}
      <label><span style={CAP}>Источник цифр</span>
        <input value={note} disabled={!canEdit} onChange={e => setNote(e.target.value)} placeholder="например: отчёт платформы за октябрь" style={{ ...inp, width: '100%' }} /></label>
      {canEdit && (
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button type="button" disabled={busy || bad || !filled.length} style={{ ...btn(true), opacity: busy || bad || !filled.length ? 0.5 : 1 }}
            onClick={() => onSave(filled.map(r => {
              const v = vals[r.row_id]
              const n = (k) => (isNum(v[k]) ? num(v[k]) : null)
              return { row_id: r.row_id, fact: num(v.fact), clicks: n('clicks'), completed: n('completed'), reference_shows: n('reference_shows') }
            }), note.trim())}>Сохранить факт</button>
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 12, paddingTop: 10, borderTop: '1px solid var(--border-row)' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={CAP}>Отчёт платформы</span>
          {fe.report
            ? <span style={{ fontSize: 12.5 }}>{fe.report.filename}</span>
            : <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>не приложен</span>}
          {canEdit && <label style={{ ...btn(false), alignSelf: 'flex-start', padding: '4px 12px', fontSize: 12 }}>
            {fe.report ? 'Заменить файл' : 'Приложить отчёт'}
            <input type="file" style={{ display: 'none' }} onChange={e => upload(e.target.files?.[0])} /></label>}
          {!!upErr && <span style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{upErr}</span>}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={CAP}>Себестоимость, без НДС</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <input value={costVal} disabled={!canEdit} onChange={e => setCostVal(e.target.value)} placeholder="вносит аккаунт" style={field} />
            {canEdit && <button type="button" disabled={busy || (costVal.trim() !== '' && !(num(costVal) >= 0))} style={btn(false)}
              onClick={() => onCost(costVal.trim() === '' ? null : num(costVal))}>Сохранить</button>}
          </div>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>
        <Check ok={fe.complete}>Факт внесён по всем строкам МП</Check>
        <Check ok={!!fe.report} warn>Отчёт платформы приложен</Check>
        <Check ok={cost != null} warn>Себестоимость внесена</Check>
      </div>
    </div>
  )
}
