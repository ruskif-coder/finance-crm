/** Шапка экрана «Деньги»: дата, неснижаемый остаток, режим расчёта (README хендоффа, каркас и п. 1). */
import { useState } from 'react'
import { Segmented } from '@/lib/motion'
import { BTN, CAPS, MONO, f } from './kit'
import { MONTHS_GEN, WD_FULL, parseDate } from './model'

/** Неснижаемый остаток — настройка собственника. Пока хранится в этом браузере: поля в системе нет (п. 2 учёта). */
function Threshold({ thr, setThr }) {
  const [edit, setEdit] = useState(false)
  const [v, setV] = useState('')
  const save = () => { const n = Number(String(v).replace(/[^\d]/g, '')); if (n >= 0 && n < 1e10) setThr(n); setEdit(false) }
  if (edit) {
    return (
      <span style={{ ...BTN, cursor: 'default' }}>Неснижаемый остаток
        <input autoFocus value={v} onChange={e => setV(e.target.value)} onBlur={save}
          onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEdit(false) }}
          style={{ width: 96, height: 22, border: '1px solid var(--border-hover)', borderRadius: 6, padding: '0 6px', fontFamily: MONO, fontSize: 12.5,
            background: 'var(--bg-subtle)', color: 'var(--text-primary)' }} /> ₽</span>
    )
  }
  return (
    <button type="button" style={BTN} title="Своя настройка собственника: от неё считаются «можно тратить» и коралловые дни. Пока хранится в этом браузере."
      onClick={() => { setV(String(thr)); setEdit(true) }}>Неснижаемый остаток <b style={{ fontFamily: MONO }}>{f(thr)} ₽</b></button>
  )
}

export default function Header({ today, thr, setThr, mode, setMode }) {
  const d = parseDate(today)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
        <span style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.02em' }}>Деньги</span>
        <span style={{ ...CAPS, fontSize: 11 }}>сегодня {d.getDate()} {MONTHS_GEN[d.getMonth()]}, {WD_FULL[d.getDay()].toLowerCase()} · выписок нет — по проведённым операциям</span>
      </div>
      <span style={{ ...BTN, marginLeft: 'auto', cursor: 'default' }} title="Разрез по одному счёту появится позже">Все счета</span>
      <Threshold thr={thr} setThr={setThr} />
      <Segmented tone="hot" value={mode} onChange={setMode} title="Как считать даты поступлений: по сроку (начало следующего периода + отсрочка из реестра) или как клиент обычно платит (+ его среднее время оплаты)"
        options={[['contract', 'По сроку'], ['real', 'Как платят на деле']]} />
    </div>
  )
}
