/**
 * СК юрлица закрытия: «скидка в счёт / постоплата / не задан», правка % по сделке при «скидке в счёт».
 * Часть блока «Итоговая сверка» (`ClosingBlock.jsx`), вынесено при аудите 20.10.2026.
 */
import { useState } from 'react'
import Link from 'next/link'
import { btn, inp, MONO } from '@/components/salesTableKit'
import { rub2 } from '@/lib/salesFormat'
import { CAP, num } from '@/components/closing/closingKit'

export default function SkRow({ sk, canEdit, busy, onSave }) {
  const [pct, setPct] = useState(sk.percent != null ? String(sk.percent).replace('.', ',') : '')
  const inBill = sk.mode === 'скидка в счёт'
  const post = sk.mode === 'постоплата'
  const own = sk.source === 'deal'
  const legal = sk.payer_percent != null ? `${String(sk.payer_percent).replace('.', ',')} %` : 'не задан'
  const changed = String(pct).trim() !== '' && num(pct) !== (sk.percent ?? null)
  const tone = inBill ? ['var(--accent-tint)', 'var(--accent-border)', 'var(--accent-fg)']
    : post ? ['var(--violet-tint)', 'var(--violet-border)', 'var(--violet-fg)']
      : ['var(--warning-tint)', 'var(--warning-border)', 'var(--warning-text)']
  return (
    <div style={{ padding: '12px 0', borderTop: '1px solid var(--border-row)', borderBottom: '1px solid var(--border-row)', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={CAP}>СК юрлица закрытия</span>
        <span style={{ padding: '4px 10px', borderRadius: 8, fontSize: 12, fontWeight: 700, background: tone[0], border: `1px solid ${tone[1]}`, color: tone[2] }}>
          {inBill ? 'Скидка в счёт' : post ? 'Постоплата СК' : 'Способ СК не задан'}{sk.mode ? ` · ${String(sk.percent ?? 0).replace('.', ',')} %` : ''}</span>
        <span style={{ ...CAP, fontWeight: 600 }}>{sk.payer_name || 'юрлицо не определено'}</span>
      </div>
      {inBill && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
            уменьшает сумму ДС{sk.amount_net ? `: −${rub2(sk.amount_net)}` : ''} · у юрлица {legal}{own ? ' · поправлено по сделке' : ''}</span>
          {canEdit && (
            <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center', marginLeft: 'auto' }}>
              <span style={CAP}>по этой сделке</span>
              <input value={pct} onChange={e => setPct(e.target.value)} style={{ ...inp, width: 72, fontFamily: MONO, textAlign: 'right', padding: '5px 8px' }} />
              <span style={{ fontSize: 12 }}>%</span>
              <button type="button" disabled={busy || !changed || !(num(pct) >= 0 && num(pct) <= 100)} style={{ ...btn(true), padding: '5px 12px', fontSize: 12, opacity: busy || !changed ? 0.5 : 1 }}
                onClick={() => onSave('скидка в счёт', num(pct))}>Сохранить</button>
              {own && <button type="button" disabled={busy} style={{ ...btn(false), padding: '5px 12px', fontSize: 12 }}
                onClick={() => onSave(null, null)}>Как у юрлица</button>}
            </span>
          )}
        </div>
      )}
      {post && <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>Счёт на полную сумму; СК {legal} выплачивается агентству отдельно — сумму ДС не меняет.</span>}
      {!sk.mode && (
        <span style={{ fontSize: 12.5, color: 'var(--warning-text)' }}>
          Задайте способ СК в карточке контрагента{sk.payer_id ? '' : ' (выберите плательщика или доходный договор)'} → «Условия по умолчанию».
          {!!sk.payer_id && <> <Link href={`/directory/counterparties/${sk.payer_id}`} target="_blank" style={{ color: 'var(--accent)' }}>Открыть карточку</Link></>}</span>
      )}
    </div>
  )
}

// Ручной режим: показы ↔ сумма связаны ценой МП; не больше суммы МП; причина обязательна.
