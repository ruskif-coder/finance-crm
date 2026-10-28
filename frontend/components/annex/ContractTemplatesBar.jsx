/**
 * Шаблоны договора в окне «Шаблон ДС» (владелец 27.10.2026): у договора несколько именованных шаблонов и базовый его формата. Здесь —
 * переключение между ними, отметка «основной» (подставляется в новый ДС, если для бренда шаблон ещё не выбирали), имя и новый шаблон
 * копией открытого. Только показ и ввод; запросы — в `useTemplateData`.
 */
import { useState } from 'react'
import { inpSm } from '@/components/salesTableKit'
import { capTxt, small, stripBox } from '@/components/annex/TemplateBars'

function Tab({ t, on, onPick }) {
  const base = t.scope === 'base'
  return (
    <span onClick={onPick} title={base ? 'Базовый шаблон формата договора — правится в реестре приложений' : t.is_main ? 'Основной шаблон договора' : ''}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 26, padding: '0 10px', borderRadius: 8, whiteSpace: 'nowrap', cursor: 'pointer', fontSize: 12, fontWeight: 700,
                   border: `1px solid ${on ? 'var(--violet-border)' : 'var(--border-card)'}`, background: on ? 'var(--violet-tint)' : 'var(--bg-card)', color: on ? 'var(--violet-fg)' : 'var(--text-secondary)' }}>
      {t.is_main && <span style={{ color: 'var(--warning)' }}>★</span>}
      {t.title}
      {base && <span style={{ fontWeight: 600, color: 'var(--text-faint)' }}>· базовый формата</span>}
    </span>
  )
}

/** Ввод имени: «Создать» / «Сохранить» доступно, когда имя не пустое и не занято другим шаблоном договора. */
export function NameForm({ initial, taken, okText, onOk, onCancel, children }) {
  const [v, setV] = useState(initial || '')
  const clash = taken.some(x => x.toLowerCase() === v.trim().toLowerCase())
  const ok = !!v.trim() && !clash
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <input autoFocus value={v} onChange={e => setV(e.target.value)} placeholder="Имя шаблона, например «Фарма»" style={inpSm(220)}
             onKeyDown={e => { if (e.key === 'Enter' && ok) onOk(v.trim()); if (e.key === 'Escape') onCancel() }} />
      {children}
      {clash && <span style={{ fontSize: 11.5, color: 'var(--danger-fg)' }}>такое имя у договора уже есть</span>}
      <span onClick={() => ok && onOk(v.trim())} style={{ ...small, background: ok ? 'var(--accent)' : 'var(--accent-soft)', color: 'var(--on-accent)', border: 'none', cursor: ok ? 'pointer' : 'not-allowed' }}>{okText}</span>
      <span onClick={onCancel} style={small}>Отмена</span>
    </span>
  )
}

export default function ContractTemplatesBar({ templates, selectedId, mayCreate, mayEdit, busy, onSelect, onCreate, onRename, onMain }) {
  const [mode, setMode] = useState(null)              // null | 'new' | 'rename'
  const [main, setMain] = useState(false)
  const sel = templates.find(t => t.id === selectedId)
  const own = templates.filter(t => t.scope === 'custom')
  const names = (skip) => own.filter(t => t.id !== skip).map(t => t.title)
  return (
    <div style={{ ...stripBox, flexWrap: 'wrap', gap: 8, overflow: 'visible' }}>
      <span style={capTxt}>шаблоны договора</span>
      {templates.map(t => <Tab key={t.id} t={t} on={t.id === selectedId} onPick={() => { setMode(null); onSelect(t.id) }} />)}
      {!own.length && <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>своих шаблонов нет — ДС собираются по базовому формата</span>}
      <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {mode === 'new' && (
          <NameForm taken={names(null)} okText={busy ? 'Создаю…' : 'Создать'} onCancel={() => setMode(null)}
                    onOk={async (title) => { if (await onCreate(title, sel ? sel.id : null, main)) { setMode(null); setMain(false) } }}>
            <span style={{ fontSize: 11.5, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>копия «{sel ? sel.title : 'базового'}»</span>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11.5, color: 'var(--text-secondary)', whiteSpace: 'nowrap', cursor: 'pointer' }}>
              <input type="checkbox" checked={main} onChange={e => setMain(e.target.checked)} />основной
            </label>
          </NameForm>
        )}
        {mode === 'rename' && sel && (
          <NameForm initial={sel.title} taken={names(sel.id)} okText="Сохранить" onCancel={() => setMode(null)}
                    onOk={async (title) => { if (await onRename(sel.id, title)) setMode(null) }} />
        )}
        {!mode && sel && sel.scope === 'custom' && mayEdit && (
          <>
            <span onClick={() => onMain(sel.id, !sel.is_main)} style={small}
                  title={sel.is_main ? 'Новые ДС будут собираться по базовому формата, если для бренда шаблон не выбирали' : 'Подставлять в новый ДС, если для бренда шаблон ещё не выбирали'}>
              {sel.is_main ? 'Снять «основной»' : '★ Сделать основным'}
            </span>
            <span onClick={() => setMode('rename')} style={small}>Переименовать</span>
          </>
        )}
        {!mode && mayCreate && (
          <span onClick={() => setMode('new')} style={{ ...small, borderColor: 'var(--violet-border)', color: 'var(--violet-fg)', background: 'var(--violet-tint)' }}>+ Новый шаблон</span>
        )}
      </span>
    </div>
  )
}
