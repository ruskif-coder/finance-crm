/**
 * Глобальные диалоги (confirm / prompt / alert) вместо нативных window.confirm / window.prompt —
 * во встроенном браузере нативные диалоги не показываются (владелец 22.11.2026).
 *
 * Стили — из кита (styling-new-page): кнопки `btn`/`primaryBtn`, поле `inp`; цвета только var(--*).
 * Провайдер монтируется один раз в `pages/_app.js`; компонент берёт `useDialogs()`:
 *   const { confirm, prompt, alert } = useDialogs()
 *   if (await confirm('Удалить?')) { … }
 *   const text = await prompt('Что исправили?')     // null — отмена
 *   alert('Сохранено')                               // fire-and-forget, await не нужен
 */
import { createContext, useContext, useMemo, useRef, useState } from 'react'
import { Modal, btn, inp } from '@/components/salesTableKit'

const Ctx = createContext(null)

export function DialogsProvider({ children }) {
  const [d, setD] = useState(null)          // { kind, title, text, confirmLabel, danger, initial }
  const [value, setValue] = useState('')
  const resolveRef = useRef(null)

  const close = (result) => {
    const r = resolveRef.current
    resolveRef.current = null
    setD(null)
    if (r) r(result)
  }

  const api = useMemo(() => ({
    confirm: (text, opts = {}) => new Promise((resolve) => {
      resolveRef.current = resolve
      setD({ kind: 'confirm', text, ...opts })
    }),
    prompt: (text, opts = {}) => new Promise((resolve) => {
      resolveRef.current = resolve
      setValue(opts.initial || '')
      setD({ kind: 'prompt', text, ...opts })
    }),
    alert: (text, opts = {}) => new Promise((resolve) => {
      resolveRef.current = resolve
      setD({ kind: 'alert', text, ...opts })
    }),
  }), [])

  return (
    <Ctx.Provider value={api}>
      {children}
      {d?.kind === 'confirm' && (
        <Modal title={d.title || 'Подтвердите действие'} width={480} onClose={() => close(false)}
          footer={
            <>
              <button type="button" onClick={() => close(false)} style={{ ...btn(false), marginLeft: 'auto' }}>Отмена</button>
              <button type="button" onClick={() => close(true)}
                style={{ ...btn(true), ...(d.danger ? { background: 'var(--danger)' } : {}) }}>{d.confirmLabel || 'Подтвердить'}</button>
            </>
          }>
          <div style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--text-primary)', whiteSpace: 'pre-line' }}>{d.text}</div>
        </Modal>
      )}
      {d?.kind === 'prompt' && (
        <Modal title={d.title || 'Укажите'} width={480} onClose={() => close(null)}
          footer={
            <>
              <button type="button" onClick={() => close(null)} style={{ ...btn(false), marginLeft: 'auto' }}>Отмена</button>
              <button type="button" onClick={() => close(value)} style={btn(true)}>{d.confirmLabel || 'ОК'}</button>
            </>
          }>
          <div style={{ fontSize: 13, lineHeight: 1.5, color: 'var(--text-secondary)', marginBottom: 8 }}>{d.text}</div>
          <input autoFocus value={value} onChange={e => setValue(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') close(value) }}
            style={{ ...inp, width: '100%', height: 36 }} />
        </Modal>
      )}
      {d?.kind === 'alert' && (
        <Modal title={d.title || 'Внимание'} width={480} onClose={() => close(true)}
          footer={<button type="button" onClick={() => close(true)} style={{ ...btn(true), marginLeft: 'auto' }}>ОК</button>}>
          <div style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--text-primary)', whiteSpace: 'pre-line' }}>{d.text}</div>
        </Modal>
      )}
    </Ctx.Provider>
  )
}

export function useDialogs() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useDialogs вне DialogsProvider')
  return ctx
}
