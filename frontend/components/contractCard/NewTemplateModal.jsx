/**
 * «Новый шаблон ДС» из карточки договора (хендофф «договорZ»): название, основа — базовый формата, основной договора или другой шаблон
 * договора («пустого» нет: «Предмет» и «Стоимость» обязательны — владелец 28.10.2026: «взять базовый»), отметка «основной ★».
 * Создаёт шаблон договора (`POST /annex-templates/custom`) и открывает его в конструкторе.
 */
import { useState } from 'react'
import { Modal, inp } from '@/components/salesTableKit'
import { annexTemplatesApi as API, errorOf } from '@/lib/annexTemplatesApi'
import { cap, btnGhost, btnPrimary, Notice } from '@/components/contractCard/ui'

export default function NewTemplateModal({ contractId, templates, sourceId, onClose, onCreated }) {
  const base = templates.find(t => t.scope === 'base')
  const [name, setName] = useState('')
  const [src, setSrc] = useState(sourceId ?? (templates.find(t => t.is_main) || base || templates[0] || {}).id)
  const [main, setMain] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const taken = templates.some(t => t.scope === 'custom' && t.title.toLowerCase() === name.trim().toLowerCase())
  const ok = !!name.trim() && !taken && src != null
  const fromBase = base && src === base.id
  const create = async () => {
    setBusy(true); setErr('')
    try {
      const t = await API.fork(contractId, { title: name.trim(), sourceId: src, main })
      onCreated(t.id)
    } catch (e) { setErr(errorOf(e, 'Не удалось создать шаблон').message) }
    finally { setBusy(false) }
  }
  return (
    <Modal title="Новый шаблон ДС" width={560} onClose={onClose}
           footer={<span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>
             <button type="button" onClick={onClose} style={btnGhost}>Отмена</button>
             <button type="button" onClick={create} disabled={!ok || busy} style={{ ...btnPrimary, opacity: ok ? 1 : 0.5, cursor: ok ? 'pointer' : 'not-allowed' }}>
               {busy ? 'Создаю…' : 'Создать и открыть конструктор →'}
             </button>
           </span>}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '6px 0' }}>
        {fromBase && <Notice>Базовый шаблон общий для формата договора — создаётся копия, базовый не меняется</Notice>}
        {err && <Notice tone="danger">{err}</Notice>}
        <span style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span style={cap}>Название</span>
          <input autoFocus value={name} onChange={e => setName(e.target.value)} placeholder="например «Фарма»" style={{ ...inp, height: 36 }} />
          {taken && <span style={{ fontSize: 11.5, color: 'var(--danger-fg)' }}>Шаблон с таким названием у договора уже есть</span>}
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span style={cap}>Основа</span>
          <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {templates.map(t => {
              const on = src === t.id
              return (
                <span key={t.id} onClick={() => setSrc(t.id)}
                      style={{ display: 'inline-flex', alignItems: 'center', height: 28, padding: '0 10px', borderRadius: 8, border: `1px solid ${on ? 'var(--accent-border)' : 'var(--border-card)'}`,
                               background: on ? 'var(--accent-tint)' : 'var(--bg-card)', color: on ? 'var(--accent-fg)' : 'var(--text-secondary)', fontSize: 12, fontWeight: on ? 700 : 600, cursor: 'pointer' }}>
                  {t.scope === 'base' ? `базовый «${t.title}»` : `${t.is_main ? '★ ' : ''}${t.title}`}
                </span>
              )
            })}
          </span>
        </span>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--text-secondary)', cursor: 'pointer' }}>
          <input type="checkbox" checked={main} onChange={e => setMain(e.target.checked)} />сделать основным ★ — новые ДС собираются по нему
        </label>
        <span style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.45 }}>Текст шаблона, пункты и подстановки правятся в конструкторе. Уже выпущенные ДС остаются на своей версии.</span>
      </div>
    </Modal>
  )
}
