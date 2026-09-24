/**
 * «Сообщить о сбое» в кабинете площадки — кнопка перед переключателем темы.
 *
 * Тот же смысл, что во внутреннем контуре: обстановку (адрес страницы, заголовок,
 * версию кабинета, размер окна) снимаем САМИ, человек пишет только то, что видел.
 * Заявка уходит в ОБЩИЙ журнал с пометкой контура — отдельный список для площадок
 * означал бы, что половина заявок теряется из виду.
 *
 * Кабинет в базу не пишет: `POST /api/bug` идёт в свой бэкенд, тот — в шлюз ядра.
 */
import { useEffect, useRef, useState } from 'react'
import api, { auth } from '../lib/http'
import { C, btn } from '../lib/ui'

const MAX_FILES = 5
const MAX_MB = 10
const OK_EXT = ['.png', '.jpg', '.jpeg', '.webp']

const BugIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M8 6a4 4 0 0 1 8 0" /><rect x="8" y="6" width="8" height="12" rx="4" />
    <path d="M3 11h5M16 11h5M4 6l3 2M20 6l-3 2M4 17l3-2M20 17l-3-2" />
  </svg>
)

export default function BugReport({ btnStyle }) {
  const [open, setOpen] = useState(false)
  const [comment, setComment] = useState('')
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [done, setDone] = useState(null)
  const [where, setWhere] = useState(null)
  const pick = useRef(null)

  useEffect(() => {
    if (!open || typeof window === 'undefined') return
    setWhere({
      page_url: window.location.pathname + window.location.search,
      page_title: (document.title || '').split('·')[0].trim(),
      app_version: process.env.NEXT_PUBLIC_CABINET_VERSION || '',   // та же, что в подвале; APP_VERSION кабинет не задаёт
      viewport: `${window.innerWidth}x${window.innerHeight}`,
    })
  }, [open])

  const close = () => { setOpen(false); setComment(''); setFiles([]); setErr(''); setDone(null) }

  const addFiles = (list) => {
    const add = []
    for (const f of Array.from(list || [])) {
      const ext = '.' + (f.name.split('.').pop() || '').toLowerCase()
      if (!OK_EXT.includes(ext)) { setErr(`${f.name}: нужен снимок экрана`); continue }
      if (f.size > MAX_MB * 1024 * 1024) { setErr(`${f.name}: больше ${MAX_MB} МБ`); continue }
      add.push(f)
    }
    setFiles(prev => [...prev, ...add].slice(0, MAX_FILES))
  }

  const send = async () => {
    if (!comment.trim()) { setErr('Опишите, что случилось'); return }
    setBusy(true); setErr('')
    try {
      const r = await api.post('/bug', { comment, ...(where || {}) }, auth())
      const id = r.data.id
      const failed = []
      for (const f of files) {
        try {
          const form = new FormData(); form.append('file', f)
          await api.post(`/bug/${id}/file`, form,
            { ...auth(), headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' } })
        } catch { failed.push(f.name) }
      }
      // Уведомление — последним: снимки приезжают после создания заявки.
      await api.post(`/bug/${id}/sent`, {}, auth())
      setDone({ id, failed })
    } catch (e) {
      setErr(e.response?.data?.detail || 'Не удалось отправить заявку')
    } finally { setBusy(false) }
  }

  const box = {
    background: C.card, border: `1px solid ${C.border}`, borderRadius: 14,
    width: 520, maxWidth: '100%', padding: 20,
  }
  const field = {
    width: '100%', boxSizing: 'border-box', padding: 10, borderRadius: 10,
    border: `1px solid ${C.border}`, background: C.bg, color: C.primary,
    fontSize: 13.5, lineHeight: 1.5, fontFamily: 'inherit',
  }
  // Кнопки — общим китом кабинета, а не своей копией: `btn` уже знает и про цвет текста
  // на заливке (`C.onFill`), и про тёмную тему. Здесь стоял хекс белого, и прибор
  // `check-tokens` его поймал — ровно тот случай, ради которого он заведён: хекс не
  // переключается вместе с темой. (Он проверяет и комментарии, так что писать хекс
  // даже в объяснении нельзя — и это правильно, иначе список исключений растёт.)

  return (
    <>
      <button onClick={() => setOpen(true)} title="Сообщить о сбое" style={btnStyle}>
        <BugIcon />
      </button>

      {open && (
        <div onMouseDown={e => { if (e.target === e.currentTarget) close() }}
          style={{ position: 'fixed', inset: 0, background: 'rgba(20,26,38,.45)', zIndex: 300,
            display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '60px 16px' }}>
          <div style={box}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 6 }}>
              <span style={{ fontSize: 16, fontWeight: 700 }}>Сообщить о сбое</span>
              <span onClick={close} style={{ marginLeft: 'auto', cursor: 'pointer', fontSize: 22,
                lineHeight: 1, color: C.faint }}>×</span>
            </div>

            {done ? (
              <div style={{ fontSize: 13.5, lineHeight: 1.6, color: C.secondary }}>
                Заявка №{done.id} принята — спасибо, мы увидим её сразу.
                {done.failed?.length > 0 && (
                  <div style={{ marginTop: 8, color: C.danger }}>
                    Не приложились снимки: {done.failed.join(', ')}. Заявка при этом принята.
                  </div>
                )}
                <div style={{ marginTop: 14 }}>
                  <button style={btn(true)} onClick={close}>Закрыть</button>
                </div>
              </div>
            ) : (
              <>
                <div style={{ fontSize: 11.5, color: C.faint, marginBottom: 10, lineHeight: 1.6 }}>
                  приложится само: {where?.page_title || '—'} · {where?.page_url || '—'}
                  {where?.app_version ? ` · v${where.app_version}` : ''}
                </div>
                <textarea value={comment} onChange={e => setComment(e.target.value)} rows={5}
                  autoFocus placeholder="Что произошло и что вы делали перед этим"
                  style={field} />
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10,
                  flexWrap: 'wrap' }}>
                  <button style={btn(false)} onClick={() => pick.current?.click()}
                    disabled={files.length >= MAX_FILES}>📎 Снимок экрана</button>
                  <input ref={pick} type="file" accept={OK_EXT.join(',')} multiple
                    style={{ display: 'none' }}
                    onChange={e => { addFiles(e.target.files); e.target.value = '' }} />
                  <span style={{ fontSize: 11.5, color: C.faint }}>
                    до {MAX_FILES} штук, {MAX_MB} МБ каждый
                  </span>
                </div>
                {files.length > 0 && (
                  <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {files.map((f, i) => (
                      <div key={i} style={{ display: 'flex', gap: 8, fontSize: 12, color: C.secondary }}>
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap' }}>{f.name}</span>
                        <span style={{ marginLeft: 'auto', cursor: 'pointer', color: C.faint }}
                          onClick={() => setFiles(p => p.filter((_, k) => k !== i))}>убрать</span>
                      </div>
                    ))}
                  </div>
                )}
                {!!err && <div style={{ marginTop: 10, fontSize: 12.5, color: C.danger }}>{err}</div>}
                <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
                  <button style={btn(true)} disabled={busy} onClick={send}>
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
