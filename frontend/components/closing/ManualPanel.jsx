/**
 * Ручная сумма ДС («Вручную»): исходный факт, ввод суммы и причины.
 * Часть блока «Итоговая сверка» (`ClosingBlock.jsx`), вынесено при аудите 20.10.2026.
 */
import { useState } from 'react'
import { btn, inp, MONO } from '@/components/salesTableKit'
import { grp, rub2 } from '@/lib/salesFormat'
import { CAP, num } from '@/components/closing/closingKit'

export default function ManualPanel({ s, busy, onCancel, onSave }) {
  const base = s.lines.find(l => l.kind === 'base' && l.unit_price)
  const per = base ? (/cpm/i.test(base.model || '') ? base.unit_price / 1000 : base.unit_price) : null
  const [units, setUnits] = useState(grp(s.manual_volume ?? s.ds_volume))
  const [sum, setSum] = useState(rub2(s.amounts.manual ?? s.amounts.fact ?? s.base_plan_net))
  const [reason, setReason] = useState('')
  const v = num(sum)
  const over = v > s.base_plan_net + 0.005
  const ok = v > 0 && !over && reason.trim()
  const field = { ...inp, fontFamily: MONO, textAlign: 'right', width: '100%' }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '12px', borderRadius: 12, border: '1px solid var(--accent-border)', background: 'var(--bg-tint)', marginTop: 8 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 8 }}>
        <label><span style={CAP}>Показы</span>
          <input value={units} style={field} onChange={e => { setUnits(e.target.value); const n = num(e.target.value); if (n > 0 && per) setSum(rub2(n * per)) }} /></label>
        <label><span style={CAP}>Без НДС</span>
          <input value={sum} autoFocus style={{ ...field, borderColor: over ? 'var(--danger-border)' : undefined }}
            onChange={e => { setSum(e.target.value); const n = num(e.target.value); if (n > 0 && per) setUnits(grp(n / per)) }} /></label>
        <label><span style={CAP}>С НДС {s.vat_rate ?? ''} %</span>
          <input readOnly value={v > 0 ? rub2(v * (1 + (s.vat_rate || 0) / 100)) : ''} style={{ ...field, background: 'var(--bg-subtle)', color: 'var(--text-secondary)' }} /></label>
      </div>
      <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>
        Исходный факт{s.fact_source === 'entered' ? ' (введён аккаунтом)' : ' DSP/Adfox'}: {s.fact_shows != null ? `${grp(s.fact_shows)} показов` : 'нет данных'}{s.amounts.fact != null ? ` · ${rub2(s.amounts.fact)}` : ''}</span>
      {over && <span style={{ fontSize: 11.5, color: 'var(--danger-fg)' }}>Больше суммы МП ({rub2(s.base_plan_net)})</span>}
      <label><span style={CAP}>Причина</span>
        <input value={reason} onChange={e => setReason(e.target.value)} placeholder="почему сумма не по факту и не под МП" style={{ ...inp, width: '100%' }} /></label>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button type="button" style={btn(false)} onClick={onCancel}>Отмена</button>
        <button type="button" disabled={busy || !ok} style={{ ...btn(true), opacity: busy || !ok ? 0.5 : 1, cursor: ok ? 'pointer' : 'not-allowed' }}
          onClick={() => onSave(v, num(units) > 0 ? num(units) : null, reason.trim())}>Сохранить</button>
      </div>
    </div>
  )
}

// Ввод факта аккаунтом — контур аккаунта (владелец 19.10.2026; схема — макет «Закрытие по услугам» 14.10). Что вводится,
// решает МОДЕЛЬ строки МП (сервер отдаёт `kind`): cpm — показы + клики; video — показы + досмотры + клики, VTR считается;
// cpc — клики; fix — пакеты + показы справочно (на сумму не влияют). Факт сделки — когда заполнен основной факт всех строк.
// Модульный уровень: внутри поля ввода (ловушка фокуса).
