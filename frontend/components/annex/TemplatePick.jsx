/**
 * Первый экран окна «Базовые шаблоны ДС»: именованные базовые шаблоны — варианты договоров, форматы сотрудничества, которые каждый
 * обслуживает, текущая версия. Данные — с сервера (спринт 2, 14.10.2026). Новый вариант заводится копией существующего.
 */
import { useState } from 'react'
import { MONO } from '@/components/salesTableKit'
import { fmtDate } from '@/lib/dates'

function BaseCard({ b, onPick }) {
  return (
    <div onClick={onPick}
         style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '16px 18px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 14, cursor: 'pointer' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-0.02em' }}>{b.title}</span>
        <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--accent)' }}>v{b.version}</span>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
        {b.formats.length
          ? b.formats.map(f => <span key={f} style={{ display: 'inline-flex', alignItems: 'center', height: 20, padding: '0 8px', borderRadius: 6, background: 'var(--accent-tint)', color: 'var(--accent-fg)', fontSize: 10.5, fontWeight: 700 }}>{f}</span>)
          : <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>форматы не назначены — ни один договор по этому шаблону не соберётся</span>}
      </div>
      <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)', paddingTop: 8, borderTop: '1px solid var(--border-row)' }}>
        правка {fmtDate(b.updated_at)} · {b.author || '—'}
      </span>
    </div>
  )
}

function NewBase({ bases, onAdd }) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [src, setSrc] = useState(bases[0] ? bases[0].id : null)
  const taken = bases.some(b => b.title.toLowerCase() === title.trim().toLowerCase())
  const ok = !!title.trim() && !taken && src != null
  if (!open) {
    return (
      <div onClick={() => setOpen(true)}
           style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 120, border: '1px dashed var(--accent-border)', borderRadius: 14, fontSize: 13, fontWeight: 600, color: 'var(--accent)', cursor: 'pointer' }}>
        + Новый вариант договора
      </div>
    )
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '14px 16px', border: '1px solid var(--accent-border)', borderRadius: 14, background: 'var(--bg-tint)' }}>
      <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Название, например «Агентский»"
             style={{ height: 34, boxSizing: 'border-box', padding: '0 10px', border: '1px solid var(--border-card)', borderRadius: 9, fontSize: 13, outline: 'none', background: 'var(--bg-card)', color: 'var(--text-primary)' }} />
      <select value={src == null ? '' : src} onChange={e => setSrc(Number(e.target.value))}
              style={{ height: 34, boxSizing: 'border-box', padding: '0 8px', border: '1px solid var(--border-card)', borderRadius: 9, fontSize: 12.5, background: 'var(--bg-card)', color: 'var(--text-primary)' }}>
        {bases.map(b => <option key={b.id} value={b.id}>копия: {b.title}</option>)}
      </select>
      {taken && <span style={{ fontSize: 11.5, color: 'var(--danger-fg)' }}>Шаблон с таким названием уже есть</span>}
      <div style={{ display: 'flex', gap: 8 }}>
        <span onClick={async () => { if (ok && await onAdd(title.trim(), src)) { setTitle(''); setOpen(false) } }}
              style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 14px', borderRadius: 9, background: ok ? 'var(--accent)' : 'var(--accent-soft)', color: 'var(--on-accent)', fontSize: 12, fontWeight: 700, cursor: ok ? 'pointer' : 'not-allowed' }}>Создать</span>
        <span onClick={() => setOpen(false)} style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 12px', border: '1px solid var(--border-card)', borderRadius: 9, fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer' }}>Отмена</span>
      </div>
    </div>
  )
}

export default function TemplatePick({ bases, canCreate, onPick, onAdd }) {
  return (
    <div style={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', padding: '22px 24px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>
        Базовые шаблоны · вариант договора и форматы, которые он обслуживает
      </span>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 14 }}>
        {bases.map(b => <BaseCard key={b.id} b={b} onPick={() => onPick(b.id)} />)}
        {canCreate && !!bases.length && <NewBase bases={bases} onAdd={onAdd} />}
      </div>
      {!bases.length && <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Базовых шаблонов ещё нет — их заводит скрипт сидирования или юрист.</span>}
      <span style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.5 }}>
        Шаблон ДС определяется «Форматом сотрудничества» договора: аккаунт шаблон руками не выбирает. Один формат обслуживает один шаблон.
        Договор без формата, а также формат без шаблона — ДС не собирается, пока формат не заполнен или не назначен шаблону.
      </span>
    </div>
  )
}
