/**
 * «Сообщить о сбое» — кнопка рядом с колокольчиком и форма заявки.
 *
 * ОБСТАНОВКУ СНИМАЕМ САМИ: адрес страницы, её заголовок, версию сборки и размер окна.
 * Человек пишет только то, что видел. Заявка без адреса и версии — это «у меня что-то
 * не работает», и разбирать её дороже, чем не получать; а требовать от человека
 * переписать адрес из строки браузера значит получать заявки с опечатками.
 *
 * ПОРЯДОК ОТПРАВКИ — три шага, и он не случаен: создать → доложить снимки → сообщить.
 * Уведомление отправляется ПОСЛЕДНИМ вызовом, потому что снимки приезжают после
 * создания: уведоми мы сразу, в нём стояло бы «скриншотов 0» на заявке со снимками.
 *
 * Правом подача НЕ закрыта: заявка — свидетельство, а не привилегия.
 */
import { useEffect, useRef, useState } from 'react'
import api, { auth } from '../lib/http'
import { overlayClose } from '../lib/overlay'
import { UI, MONO, card, inp, primaryBtn, btn } from './salesTableKit'

const MAX_FILES = 5
const MAX_MB = 10
const OK_EXT = ['.png', '.jpg', '.jpeg', '.webp']

const BugIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M8 6a4 4 0 0 1 8 0" /><rect x="8" y="6" width="8" height="12" rx="4" />
    <path d="M3 11h5M16 11h5M4 6l3 2M20 6l-3 2M4 17l3-2M20 17l-3-2" />
  </svg>
)

export default function BugReport({ size = 32 }) {
  const [open, setOpen] = useState(false)
  const [comment, setComment] = useState('')
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [done, setDone] = useState(null)
  const pick = useRef(null)

  // Обстановка читается в момент ОТКРЫТИЯ формы, а не отправки: человек может успеть
  // уйти на другую страницу, пока пишет, и тогда адрес указал бы не на тот экран.
  const [where, setWhere] = useState(null)
  useEffect(() => {
    if (!open || typeof window === 'undefined') return
    setWhere({
      page_url: window.location.pathname + window.location.search,
      page_title: (document.title || '').split('|')[0].trim(),
      app_version: process.env.NEXT_PUBLIC_APP_VERSION || '',
      viewport: `${window.innerWidth}x${window.innerHeight}`,
    })
  }, [open])

  const close = () => {
    setOpen(false); setComment(''); setFiles([]); setErr(''); setDone(null)
  }

  const addFiles = (list) => {
    const add = []
    for (const f of Array.from(list || [])) {
      const ext = '.' + (f.name.split('.').pop() || '').toLowerCase()
      if (!OK_EXT.includes(ext)) { setErr(`${f.name}: нужен снимок экрана (${OK_EXT.join(', ')})`); continue }
      if (f.size > MAX_MB * 1024 * 1024) { setErr(`${f.name}: больше ${MAX_MB} МБ`); continue }
      add.push(f)
    }
    setFiles(prev => {
      const next = [...prev, ...add].slice(0, MAX_FILES)
      if (prev.length + add.length > MAX_FILES) setErr(`Можно приложить ${MAX_FILES} снимков`)
      return next
    })
  }

  const send = async () => {
    if (!comment.trim()) { setErr('Опишите, что случилось'); return }
    setBusy(true); setErr('')
    try {
      const r = await api.post('/bugs', { comment, ...(where || {}) }, auth())
      const id = r.data.id
      // Снимки — по одному: отказ по одному файлу не должен терять заявку целиком.
      const failed = []
      for (const f of files) {
        try {
          const form = new FormData(); form.append('file', f)
          await api.post(`/bugs/${id}/file`, form,
            { ...auth(), headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' } })
        } catch (e) { failed.push(f.name) }
      }
      await api.post(`/bugs/${id}/sent`, {}, auth())
      setDone({ id, failed })
    } catch (e) {
      setErr(e.response?.data?.detail || 'Не удалось отправить заявку')
    } finally { setBusy(false) }
  }

  return (
    <>
      <button type="button" className="nav-icon" onClick={() => setOpen(true)}
        title="Сообщить о сбое" aria-label="Сообщить о сбое"
        style={{
          background: 'transparent', border: 'none', padding: 0, cursor: 'pointer',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: size, height: size, borderRadius: 10, color: 'var(--text-muted)',
          flex: `0 0 ${size}px`,
        }}>
        <BugIcon />
      </button>

      {open && (
        <div {...overlayClose(close)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(20,26,38,.45)', zIndex: 300,
            display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
            padding: '60px 16px', fontFamily: UI,
          }}>
          <div style={{ ...card, width: 560, maxWidth: '100%', padding: 20 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 4 }}>
              <span style={{ fontSize: 17, fontWeight: 700 }}>Сообщить о сбое</span>
              <span onClick={close} style={{ marginLeft: 'auto', cursor: 'pointer',
                fontSize: 22, lineHeight: 1, color: 'var(--text-muted)' }}>×</span>
            </div>

            {done ? (
              <div style={{ fontSize: 13.5, lineHeight: 1.6 }}>
                Заявка №{done.id} принята — спасибо. Мы увидим её сразу.
                {done.failed?.length > 0 && (
                  <div style={{ marginTop: 8, color: 'var(--dot-overdue)' }}>
                    Не приложились снимки: {done.failed.join(', ')}. Заявка при этом принята.
                  </div>
                )}
                <div style={{ marginTop: 14 }}>
                  <button style={primaryBtn} onClick={close}>Закрыть</button>
                </div>
              </div>
            ) : (
              <>
                {/* Что уйдёт вместе с заявкой — показываем, а не подразумеваем: человек
                    должен видеть, что именно мы о нём узнаем. */}
                <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginBottom: 12,
                  fontFamily: MONO, lineHeight: 1.6 }}>
                  приложится само: {where?.page_title || '—'} · {where?.page_url || '—'}
                  {where?.app_version ? ` · v${where.app_version}` : ''} · {where?.viewport || ''}
                </div>

                <textarea value={comment} onChange={e => setComment(e.target.value)}
                  autoFocus rows={5}
                  placeholder="Что произошло и что вы делали перед этим"
                  style={{ ...inp, width: '100%', boxSizing: 'border-box', height: 'auto',
                    padding: 10, fontFamily: UI, fontSize: 13.5, lineHeight: 1.5 }} />

                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10,
                  flexWrap: 'wrap' }}>
                  <button style={btn(false)} onClick={() => pick.current?.click()}
                    disabled={files.length >= MAX_FILES}>
                    📎 Снимок экрана
                  </button>
                  <input ref={pick} type="file" accept={OK_EXT.join(',')} multiple
                    style={{ display: 'none' }}
                    onChange={e => { addFiles(e.target.files); e.target.value = '' }} />
                  <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>
                    до {MAX_FILES} штук, {MAX_MB} МБ каждый
                  </span>
                </div>

                {files.length > 0 && (
                  <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {files.map((f, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8,
                        fontSize: 12, color: 'var(--text-secondary)' }}>
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap' }}>{f.name}</span>
                        <span style={{ marginLeft: 'auto', cursor: 'pointer', color: 'var(--text-faint)' }}
                          onClick={() => setFiles(p => p.filter((_, k) => k !== i))}>убрать</span>
                      </div>
                    ))}
                  </div>
                )}

                {!!err && (
                  <div style={{ marginTop: 10, fontSize: 12.5, color: 'var(--dot-overdue)' }}>{err}</div>
                )}

                <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
                  <button style={primaryBtn} disabled={busy} onClick={send}>
                    {busy ? 'Отправляю…' : 'Отправить'}
                  </button>
                  <button style={btn(false)} onClick={close}>Отмена</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
