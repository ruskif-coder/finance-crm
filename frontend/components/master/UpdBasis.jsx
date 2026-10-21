/**
 * Основания для закрытия по каждой УПД пакета (одна УПД = одно основание, владелец 15.10.2026). Текст по умолчанию — по своему ДС
 * Механизм — тот же, что «основание для закрывающих» в конструкторе ДС (19.10.2026): шаблон с подстановками, наследование из прошлого ДС,
 * правка тем же редактором; бренд — свой у каждого УПД. Правится до отправки в 1С.
 */
import { useState } from 'react'
import api, { auth } from '@/lib/api'
import { MONO, btn } from '@/components/salesTableKit'
import AnnexQuickEdit from '@/components/annex/AnnexQuickEdit'
import { rub2 } from '@/lib/salesFormat'
import { CAP, CARD, groupLabel } from '@/components/master/kit'

// Одна строка — модульный уровень: внутри поле ввода, объявление в теле списка сбрасывало бы фокус на каждом символе.
export function BasisRow({ code, u, busy, onSaved, compact = false }) {
  const [edit, setEdit] = useState(false)
  const save = async (value) => {
    onSaved((await api.put(`/master-deals/${code}/upd/${u.upd_no}/basis`, { text: value }, auth())).data)
    setEdit(false)
  }
  const tag = u.basis_custom ? ['изменено', 'var(--accent-tint)', 'var(--accent-fg)']
    : u.basis_inherited_from ? [`взято: ${u.basis_inherited_from}`, 'var(--violet-tint)', 'var(--violet-fg)'] : ['по шаблону ДС', 'var(--bg-subtle)', 'var(--text-muted)']
  if (edit) {
    return (
      <div style={{ padding: compact ? 0 : '12px 0', borderTop: compact ? 0 : '1px solid var(--border-row)' }}>
        <AnnexQuickEdit title={`Основание к закрытию · УПД № ${u.upd_no}`} hint="попадёт в УПД и счёт; как в конструкторе ДС"
          source={u.basis_template} edited={u.basis_custom} inheritedFrom={u.basis_inherited_from} values={u.values} canEdit={!busy} copy
          onSave={save} aside={<button type="button" onClick={() => setEdit(false)} style={{ ...btn(false), marginLeft: 'auto', padding: '2px 10px', fontSize: 11.5 }}>Закрыть</button>} />
      </div>
    )
  }
  return (
    <div style={{ padding: compact ? 0 : '12px 0', borderTop: compact ? 0 : '1px solid var(--border-row)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ ...CAP, color: compact ? 'var(--text-cap)' : 'var(--accent-fg)' }}>{compact ? 'Основание к закрытию' : `УПД № ${u.upd_no}`}</span>
        {!compact && <b style={{ fontSize: 13 }}>{groupLabel(u)}</b>}
        {!compact && <span style={{ fontFamily: MONO, fontSize: 12.5 }}>{rub2(u.gross)}</span>}
        <span style={{ fontSize: 10.5, fontWeight: 700, background: tag[1], color: tag[2], borderRadius: 6, padding: '2px 8px' }}>{tag[0]}</span>
        <button type="button" disabled={busy} onClick={() => setEdit(true)} style={{ ...btn(false), marginLeft: 'auto', padding: compact ? '2px 10px' : '4px 12px', fontSize: compact ? 11.5 : 12 }}>Изменить</button>
      </div>
      <div style={{ fontSize: compact ? 12 : 12.5, color: 'var(--text-secondary)', lineHeight: 1.5, marginTop: compact ? 4 : 6 }}>{u.basis}</div>
    </div>
  )
}

export default function UpdBasis({ m, busy, onSaved }) {
  if (!m.upds?.length) return null
  return (
    <div style={{ ...CARD, padding: '14px 18px', marginBottom: 14 }}>
      <span style={CAP}>Основания для закрытия · по УПД</span>
      <div style={{ fontSize: 11.5, color: 'var(--text-faint)', margin: '4px 0 2px' }}>Формулировка для УПД и счёта; уходит в 1С. Правится до отправки.</div>
      {m.upds.map(u => <BasisRow key={`${u.upd_no}:${u.basis}`} code={m.code} u={u} busy={busy} onSaved={onSaved} />)}
    </div>
  )
}
