/**
 * Итог по площадкам — цикл «приоритезация», итоговая сверка (владелец 13.11.2026: «часть услуги идёт на основании движков
 * площадок, а не нашего кода»; «переключатель уже на итоговой сверке, у аккаунта решение подгружать или нет»).
 *
 * У каждой запущенной площадки факт — из статистики сервиса (ночной сбор) или из итогового файла. Файл — по шаблону Adfox
 * без номера креатива: «День · Название кампании (КОДСДЕЛКИ-КОДПЛОЩАДКИ) · Показы · Переходы · Уникальные показы». Загрузка
 * переключает площадки из файла на «файл»; «вернуть к сервису» — обратно. В ДО сделка уходит, когда факт есть по всем.
 */
import { useRef, useState } from 'react'
import api, { auth } from '@/lib/api'
import { downloadFile } from '@/lib/download'
import { MONO, btn, btnSm } from '@/components/salesTableKit'
import { grp } from '@/lib/salesFormat'

const RUNNING = ['идёт', 'остановлено']
const CAP = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }
const GRID = 'minmax(180px,1.4fr) 120px 140px 140px minmax(140px,1fr)'

function Source({ v }) {
  const file = v === 'файл'
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', height: 20, padding: '0 8px', borderRadius: 7, fontFamily: MONO, fontSize: 10,
      fontWeight: 700, background: file ? 'var(--violet-tint)' : 'var(--accent-tint)', color: file ? 'var(--violet-fg)' : 'var(--accent)' }}>
      {file ? 'файл площадки' : 'статистика сервиса'}</span>
  )
}

export default function PrioFactTotals({ s, base, canEdit, busy, call }) {
  const fileRef = useRef(null)
  const [res, setRes] = useState(null)
  const rows = (s.placements || []).filter(p => RUNNING.includes(p.status))
  if (s.flow !== 'приоритезация' || !rows.length) return null

  const upload = async (f) => {
    if (!f) return
    const fd = new FormData()
    fd.append('file', f)
    setRes(null)
    await call(async () => {
      const r = await api.post(`${base}/fact-file`, fd, auth())
      setRes(r.data.fact_file)
      return r
    })
    if (fileRef.current) fileRef.current.value = ''
  }

  return (
    <div style={{ borderTop: '1px solid var(--border-row)', marginTop: 16, paddingTop: 14 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', marginBottom: 8 }}>
        <span style={CAP}>Итог по площадкам</span>
        <span style={{ fontSize: 11.5, color: 'var(--text-faint)', flex: '1 1 320px' }}>
          Факт — из статистики сервиса. Площадка крутила своим движком — загрузите её итоговый файл: факт этих площадок будет из файла.</span>
        <span style={{ display: 'inline-flex', gap: 6 }}>
          <button type="button" onClick={() => downloadFile(`${base}/fact-template.xlsx`, `prio_${s.deal_code}_itog.xlsx`)} style={btn(false)}>↓ Шаблон</button>
          {canEdit && <>
            <button type="button" disabled={busy} onClick={() => fileRef.current?.click()} style={{ ...btn(true), opacity: busy ? 0.5 : 1 }}>↑ Загрузить итог</button>
            <input ref={fileRef} type="file" accept=".xlsx" onChange={e => upload(e.target.files?.[0])} style={{ display: 'none' }} />
          </>}
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, padding: '0 4px 8px', borderBottom: '1px solid var(--border-card)', ...CAP, fontWeight: 600 }}>
        <span>Площадка</span><span>Статус</span><span style={{ textAlign: 'right' }}>Факт сервиса · цель</span><span>Источник факта</span><span />
      </div>
      {rows.map(p => (
        <div key={p.id} style={{ display: 'grid', gridTemplateColumns: GRID, gap: 10, alignItems: 'center', padding: '8px 4px', borderBottom: '1px solid var(--border-row)' }}>
          <span style={{ fontWeight: 700, fontSize: 12.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={p.name}>{p.name}</span>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{p.status}</span>
          <span style={{ fontFamily: MONO, fontSize: 12, textAlign: 'right' }}>
            {p.fact_imp != null ? grp(p.fact_imp) : '—'} <span style={{ color: 'var(--text-faint)' }}>/ {grp(p.goal_imp)}</span></span>
          <span><Source v={p.fact_source} /></span>
          <span>
            {canEdit && p.fact_source === 'файл' && (
              <button type="button" disabled={busy} onClick={() => call(() => api.put(`${base}/placements/${p.id}/fact-source`, { source: 'сервис' }, auth()))}
                style={btnSm(false)} title="Факт этой площадки снова будет из статистики сервиса">Вернуть к сервису</button>)}
          </span>
        </div>
      ))}
      {!!res && (
        <div style={{ marginTop: 10, padding: '8px 12px', borderRadius: 10, fontSize: 12, background: 'var(--income-tint)', color: 'var(--income-fg)' }}>
          Записано {res.written} строк факта ({res.days[0]} — {res.days[1]}): {res.placements.join(', ')}.
          {res.unknown.length > 0 && <span style={{ color: 'var(--warning-text)' }}> Не распознаны названия: {res.unknown.join(', ')} — нужен формат «{s.deal_code}-КОДПЛОЩАДКИ».</span>}
        </div>
      )}
    </div>
  )
}
