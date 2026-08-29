/**
 * Общая основа выбора и заведения на ступенях сборки ОРД.
 *
 * Все три ступени устроены одинаково: список того, что уже есть, и форма завести
 * недостающее не уходя со сборки. Уход в справочник посреди сборки — это потерянный
 * контекст и брошенная на полпути цепочка; замеры 26.08.2026 говорят, что уходить
 * пришлось бы часто: 57 из 92 агентств без единого юрлица, 16 из 40 юрлиц без
 * договора с отметкой ОРД.
 *
 * Формы спрашивают ВСЁ, что нужно для ЕРИД (решение владельца 26.08.2026): без ИНН,
 * адреса и сроков оплаты маркер не выпустить, а выясняется это через месяц, на сдаче
 * отчётности, и чинится задним числом.
 *
 * Компоненты объявлены на модульном уровне: компонент, созданный внутри рендера,
 * пересоздаётся на каждом кадре, и поле ввода теряет фокус после первой буквы.
 */
import { useState } from 'react'
import { UI, MONO, btnSm } from '../salesTableKit'

export const INPUT = {
  width: '100%', boxSizing: 'border-box', border: '1px solid var(--border-card)',
  borderRadius: 10, padding: '9px 11px', fontSize: 13, fontFamily: UI,
  background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none',
}

export function Field({ label, value, onChange, placeholder, hint, type = 'text', width }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0, flex: width || '1 1 180px' }}>
      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em',
        textTransform: 'uppercase', color: 'var(--text-muted)' }}>{label}</span>
      <input type={type} value={value} placeholder={placeholder}
        onChange={e => onChange(e.target.value)} style={INPUT} />
      {!!hint && <span style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>{hint}</span>}
    </label>
  )
}

/**
 * Строка формы со своим заголовком: пара полей, которые читаются вместе.
 *
 * Без неё поля раскладывались по ширине панели, и «Рекламодатель — ИНН», «Рекламодатель —
 * название», «Исполнитель — ИНН» вставали в один ряд, а «Исполнитель — название» уезжал
 * на следующий: глаз собирал стороны договора заново на каждом открытии формы.
 */
export function FieldRow({ label, children }) {
  return (
    <div style={{ flex: '1 1 100%', display: 'flex', flexDirection: 'column', gap: 5 }}>
      {!!label && (
        <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '.08em', fontWeight: 700,
          textTransform: 'uppercase', color: 'var(--text-secondary)' }}>{label}</span>
      )}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>{children}</div>
    </div>
  )
}

/**
 * Выбор из перечисления МедиаСкаута. Списки приходят с бэкенда (`GET /ord/enums`),
 * а не повторяются здесь: подставленный не тот вид договора уезжает в ЕРИР молча,
 * и разошедшаяся копия списка — самый дешёвый способ это устроить.
 */
export function SelectField({ label, value, onChange, options, placeholder, hint, width }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0, flex: width || '1 1 180px' }}>
      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.08em',
        textTransform: 'uppercase', color: 'var(--text-muted)' }}>{label}</span>
      <select value={value} onChange={e => onChange(e.target.value)} style={INPUT}>
        <option value="">{placeholder || '— не выбрано —'}</option>
        {(options || []).map(o => <option key={o.code} value={o.code}>{o.label}</option>)}
      </select>
      {!!hint && <span style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>{hint}</span>}
    </label>
  )
}

/**
 * Панель «завести новое» — свёрнута до кнопки, пока не понадобится.
 *
 * Развёрнутая форма рядом со списком уводит от выбора: заводить новое надо реже, чем
 * выбирать из имеющегося, а глаз идёт к полям ввода раньше, чем к строкам.
 */
export function CreatePanel({ label, note, open, onToggle, error, busy, onSubmit, submitLabel, children }) {
  if (!open) {
    // Тон карточки документов: акцентная заливка и рамка, знак «+» в квадрате 22×22 —
    // это приглашение добавить, а не рядовая кнопка, и в сером окне его надо видеть.
    return (
      <button type="button" onClick={onToggle}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 9, width: '100%',
          background: 'var(--accent-tint)', border: '1px solid var(--accent-border)',
          borderRadius: 11, padding: '9px 10px', cursor: 'pointer', fontFamily: UI,
          color: 'var(--accent)', fontSize: 13, fontWeight: 600, textAlign: 'left' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 22, height: 22, flex: '0 0 22px', borderRadius: 7, background: 'var(--bg-card)',
          color: 'var(--accent)', fontSize: 15, lineHeight: 1 }}>+</span>
        {label}
      </button>
    )
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '14px 15px',
      border: '1px solid var(--border-card)', borderRadius: 12, background: 'var(--bg-subtle)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em',
          textTransform: 'uppercase', fontWeight: 700, color: 'var(--text-muted)' }}>{label}</span>
        <button type="button" onClick={onToggle}
          style={{ marginLeft: 'auto', background: 'none', border: 0, cursor: 'pointer',
            fontSize: 12, color: 'var(--text-muted)', fontFamily: UI }}>отмена</button>
      </div>
      {!!note && <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', lineHeight: 1.45 }}>{note}</span>}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>{children}</div>
      {/* Подвал: ошибка слева, действие в правом нижнем углу — там, где его ищут
          после заполнения формы, и там же, где кнопки во всех окнах проекта. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        {!!error && (
          <span style={{ flex: '1 1 200px', fontSize: 12, color: 'var(--danger)' }}>{error}</span>
        )}
        <button type="button" onClick={onSubmit} disabled={busy}
          style={{ ...btnSm(true), marginLeft: 'auto' }}>
          {busy ? 'Сохраняю…' : submitLabel}
        </button>
      </div>
    </div>
  )
}

/** Состояние формы заведения: открыта/занята/ошибка — одинаково у всех трёх ступеней. */
export function useCreateForm(initial) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState(initial)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (v) => setData(d => ({ ...d, [k]: v }))
  const submit = async (fn) => {
    setBusy(true); setErr('')
    try {
      await fn(data)
      setOpen(false); setData(initial)
    } catch (e) {
      setErr(e.response?.data?.detail || 'Не удалось сохранить')
    } finally { setBusy(false) }
  }
  return { open, toggle: () => { setOpen(o => !o); setErr('') }, data, set, err, busy, submit }
}

/** Строка списка: то, что выбирают. Подпись справа говорит, поедет ли цепочка дальше. */
export function PickRow({ title, meta, right, chosen, onPick }) {
  return (
    <div onClick={onPick} style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', cursor: 'pointer',
      border: `1px solid ${chosen ? 'var(--accent)' : 'var(--border-card)'}`,
      background: chosen ? 'var(--accent-tint)' : 'var(--bg-card)',
      borderRadius: 11, fontFamily: UI,
    }}>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0, flex: 1 }}>
        <span style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</span>
        {!!meta && <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{meta}</span>}
      </span>
      {right}
    </div>
  )
}

/** Плашка состояния строки: «готово к ЕРИД» / «чего-то не хватает». */
export function Tag({ ok, children, title }) {
  return (
    <span title={title} style={{
      flex: '0 0 auto', fontFamily: MONO, fontSize: 9, fontWeight: 700, whiteSpace: 'nowrap',
      borderRadius: 6, padding: '2px 7px',
      background: ok ? 'var(--income-tint)' : 'var(--warning-tint)',
      color: ok ? 'var(--income)' : 'var(--warning-text)',
      border: `1px solid ${ok ? 'var(--income-border)' : 'var(--warning-border)'}`,
    }}>{children}</span>
  )
}
