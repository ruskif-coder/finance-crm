/**
 * Проверка креатива — для аккаунтов (07.10.2026): загрузить баннер без сделки, посмотреть замечания по коду
 * и получить нацеливание — тот же демо-ЕРИД и демо-контур, что у первичной проверки трафиков.
 *
 * Вёрстка — по хендоффу «проверка крео.zip» (кода `code/` в нём нет, только референс .dc.html и README):
 * размеры, подписи капсом, тона плашек и порядок блоков взяты из макета; цвета — только `var(--*)`.
 * Где макет расходится с решением владельца в чате, взято решение владельца:
 *  · площадки по умолчанию — БЕЗ галочек (в макете чипы снимаются);
 *  · доступ у аккаунтов (в README макета — «инструмент трафика»).
 *
 * Истории нет: проверка живёт 48 часов, потом нацеливание останавливается, файлы удаляются. Видна только
 * автору. Выпущенная ссылка НЕ подтверждает, что баннер крутится: сообщение красится по ответу сервера.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import Head from 'next/head'
import Navbar from '@/components/Navbar'
import { UI, MONO, card, Modal, btn } from '@/components/salesTableKit'
import { CreativePreview } from '@/components/creatives/CreativePreview'
import { Cube } from '@/components/LogoLoader'
import api, { auth } from '@/lib/api'
import { can, canDelete, getPermissions } from '@/lib/auth'
import { serverDate } from '@/lib/dates'
import { errText } from '@/lib/loadError'
import safeHref from '@/lib/safeHref'
import useRefreshOnReturn from '@/lib/useRefreshOnReturn'
import { issueAimAt } from '@/lib/aimTab'

const ACCEPT = '.png,.jpg,.jpeg,.gif,.webp,.svg,.zip,.html,.htm'
const KIND = { image: 'Картинка', html5: 'HTML5' }
const WARN_BELOW_MIN = 6 * 60          // меньше шести часов до удаления — жёлтым

const CAP9 = { fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const CAP10 = { fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-cap)' }
const FIELD = { height: 38, boxSizing: 'border-box', padding: '0 12px', background: 'var(--bg-card)',
  border: '1px solid var(--border-card)', borderRadius: 12, fontSize: 13, outline: 'none',
  color: 'var(--text-primary)', fontFamily: UI, width: '100%' }
const ACT = { display: 'inline-flex', alignItems: 'center', gap: 8, height: 34, padding: '0 14px', borderRadius: 12,
  fontSize: 12.5, whiteSpace: 'nowrap', cursor: 'pointer', fontFamily: UI }

// Тон плашки замечания → [фон, рамка, маркер, подпись-цвет, подпись]; подписи капсом — как в макете.
const TONE = {
  warn: ['var(--warning-tint)', 'var(--warning-border)', 'var(--warning)', 'var(--warning-fg)', 'Замечание'],
  fix: ['var(--accent-tint)', 'var(--accent-border)', 'var(--accent)', 'var(--accent-fg)', 'Поправлено автоматически'],
  bad: ['var(--danger-tint)', 'var(--danger-border)', 'var(--danger)', 'var(--danger-fg)', 'Ошибка'],
}

/** Сколько минут осталось проверке; 0 — срок вышел. Момент с сервера — UTC без суффикса (`serverDate`). */
const minutesLeft = (iso) => {
  const end = serverDate(iso)
  return end ? Math.max(0, Math.floor((end.getTime() - Date.now()) / 60000)) : 0
}
const ttlText = (m) => `осталось ${Math.floor(m / 60)} ч ${String(m % 60).padStart(2, '0')} мин`

const Icon = ({ children, size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round">{children}</svg>
)

function Note({ tone, text }) {
  const [bg, border, dot, fg, label] = TONE[tone]
  return (
    <span style={{ display: 'flex', alignItems: 'flex-start', gap: 9, padding: '8px 12px', background: bg,
      border: `1px solid ${border}`, borderRadius: 10 }}>
      <span style={{ width: 7, height: 7, borderRadius: 2, background: dot, flex: '0 0 7px', marginTop: 5 }} />
      <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
        <span style={{ ...CAP9, color: fg }}>{label}</span>
        <span style={{ fontSize: 12.5, color: 'var(--text-primary)', lineHeight: 1.45 }}>{text}</span>
      </span>
    </span>
  )
}

function SiteLink({ p }) {
  const href = safeHref(p.domain)
  const style = { display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 8px',
    background: 'var(--bg-subtle)', borderRadius: 7, fontFamily: MONO, fontSize: 11, color: 'var(--accent-fg)',
    textDecoration: 'none' }
  return href
    ? <a href={href} target="_blank" rel="noopener noreferrer" title={p.name} style={style}>{p.domain}</a>
    : <span style={style}>{p.domain || p.name}</span>
}

function CheckCard({ c, mayEdit, mayDelete, onPreview, onDelete }) {
  const [aim, setAim] = useState(null)          // ответ последнего нажатия «Нацеливание»
  const [busy, setBusy] = useState(false)
  const left = minutesLeft(c.expires_at)
  const go = async () => {
    setBusy(true)
    setAim(await issueAimAt(api, auth, `/creative-check/${c.id}/targeting-link`))
    setBusy(false)
  }
  const notes = [
    ...(c.warnings || []).map(text => ({ tone: 'warn', text })),
    ...((c.prepared || []).length ? [{ tone: 'fix', text: c.prepared.join('. ') + '.' }] : []),
  ]
  const domain = c.advertiser_url
  const aimText = aim && (aim.message || (aim.active ? 'Нацеливание выпущено — баннер появится на сайте площадки' : ''))
  const aimColor = aim && (aim.failed ? 'var(--danger-fg)' : aim.active ? 'var(--income-fg)' : 'var(--warning-fg)')
  return (
    <div style={{ ...card, padding: '18px 24px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-.02em' }}>{c.title}</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 8px',
          background: 'var(--accent-tint)', border: '1px solid var(--accent-border)', borderRadius: 7,
          fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '.06em', color: 'var(--accent-fg)' }}>
          {KIND[c.kind] || c.kind}
        </span>
        <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
          {c.info?.size}
        </span>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 7, height: 26,
          padding: '0 10px', background: 'var(--bg-subtle)', borderRadius: 8, fontFamily: MONO, fontSize: 11,
          fontWeight: 700, whiteSpace: 'nowrap',
          color: left < WARN_BELOW_MIN ? 'var(--warning-fg)' : 'var(--text-secondary)' }}>
          <Icon size={12}><circle cx="12" cy="12" r="8" /><path d="M12 8v4l2.5 1.5" /></Icon>
          {ttlText(left)}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))', gap: '6px 24px' }}>
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 10, minWidth: 0 }}>
          <span style={{ ...CAP9, whiteSpace: 'nowrap' }}>Домен</span>
          {domain && safeHref(domain)
            ? <a href={safeHref(domain)} target="_blank" rel="noopener noreferrer"
                style={{ fontFamily: MONO, fontSize: 12, color: 'var(--accent)', textDecoration: 'none',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{domain}</a>
            : <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--text-faint)' }}>—</span>}
        </span>
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 10, minWidth: 0 }}>
          <span style={{ ...CAP9, whiteSpace: 'nowrap' }}>Файл</span>
          <span title={c.original_name} style={{ fontSize: 12, color: 'var(--text-secondary)', overflow: 'hidden',
            textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.original_name}</span>
        </span>
      </div>

      {notes.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {notes.map((n, i) => <Note key={i} tone={n.tone} text={n.text} />)}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 7, paddingTop: 12, borderTop: '1px solid var(--border-inner)' }}>
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span style={{ ...CAP9, fontWeight: 700, letterSpacing: '.1em' }}>Площадки</span>
          <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
            наш код · веб · {(c.publishers || []).length}
          </span>
        </span>
        <span style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
          {(c.publishers || []).map(p => <SiteLink key={p.id} p={p} />)}
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingTop: 12,
        borderTop: '1px solid var(--border-inner)' }}>
        <button type="button" disabled={!c.sandbox_url} onClick={() => onPreview(c)}
          title={c.sandbox_url ? 'Посмотреть баннер в песочнице' : 'Песочница не настроена'}
          style={{ ...ACT, border: 'none', background: 'var(--accent)', color: '#fff', fontWeight: 700,
            opacity: c.sandbox_url ? 1 : 0.5 }}>
          <Icon><circle cx="12" cy="12" r="3" /><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z" /></Icon>
          Посмотреть
        </button>
        {mayEdit && (
          <button type="button" disabled={busy} onClick={go}
            title="Ссылка с демо-ЕРИД: баннер появится на сайте площадки у вас в браузере"
            style={{ ...ACT, background: 'var(--bg-card)', border: '1px solid var(--border-card)',
              color: 'var(--text-secondary)', fontWeight: 600 }}>
            <Icon><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></Icon>
            {busy ? 'Готовим…' : 'Нацеливание'}
          </button>
        )}
        {aimText && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 12, color: aimColor }}>
            <span style={{ width: 7, height: 7, borderRadius: 2, background: 'currentColor' }} />{aimText}
          </span>
        )}
        {mayDelete && (
          <button type="button" onClick={() => onDelete(c)}
            style={{ ...ACT, marginLeft: 'auto', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
              color: 'var(--text-secondary)', fontWeight: 600 }}>Удалить</button>
        )}
      </div>
    </div>
  )
}

export default function CreativeCheck() {
  const [perms, setPerms] = useState({})
  const [rows, setRows] = useState(null)
  const [pubs, setPubs] = useState([])
  const [err, setErr] = useState('')
  const [title, setTitle] = useState('')
  const [url, setUrl] = useState('')
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [formErr, setFormErr] = useState('')
  const [sitesOpen, setSitesOpen] = useState(false)
  const [preview, setPreview] = useState(null)
  const [drop, setDrop] = useState(null)
  const [, setTick] = useState(0)
  const fileRef = useRef(null)

  useEffect(() => { setPerms(getPermissions()) }, [])
  const mayEdit = can(perms, 'creative_check', 'edit')
  const mayDelete = canDelete(perms, 'creative_check')

  const load = useCallback(() => {
    api.get('/creative-check', auth()).then(r => { setRows(r.data); setErr('') })
      .catch(e => { setErr(errText(e)); setRows(r => r || []) })
    api.get('/creative-check/publishers', auth()).then(r => setPubs(r.data)).catch(() => {})
  }, [])
  useEffect(() => { load() }, [load])
  useRefreshOnReturn(load)
  // Таймер тикает раз в минуту; по нулю проверка исчезает (сервер её уже не отдаёт).
  useEffect(() => {
    const t = setInterval(() => {
      setTick(n => n + 1)
      setRows(list => {
        if (list && list.some(c => minutesLeft(c.expires_at) === 0)) load()
        return list
      })
    }, 60000)
    return () => clearInterval(t)
  }, [load])

  const pick = (f) => { setFile(f || null); setFormErr('') }
  const submit = async () => {
    if (!file || !title.trim() || busy) return
    setFormErr('')
    const form = new FormData()
    form.append('title', title.trim())
    form.append('url', url.trim())
    form.append('file', file)
    setBusy(true)
    try {
      await api.post('/creative-check', form, auth())
      setTitle(''); setFile(null)
      if (fileRef.current) fileRef.current.value = ''
      load()
    } catch (er) { setFormErr(errText(er)) } finally { setBusy(false) }
  }

  const remove = async () => {
    const c = drop
    setDrop(null)
    try { await api.delete(`/creative-check/${c.id}`, auth()); load() } catch (er) { setErr(errText(er)) }
  }

  // Название обязательно (владелец 07.10.2026, поверх макета): иначе проверки не различить.
  const canSubmit = !!file && !!title.trim() && !busy
  return (
    <>
      <Head><title>Проверка креатива · Аккаунты | SIMB-AD ERP</title></Head>
      <Navbar />
      <div style={{ padding: '22px 28px 40px', display: 'flex', justifyContent: 'center', fontFamily: UI }}>
        <div style={{ width: '100%', maxWidth: 1240, display: 'flex', flexDirection: 'column', gap: 14 }}>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-.025em' }}>Проверка креатива</span>
              <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-cap)' }}>
                проверка живёт 48 часов
              </span>
            </div>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5, maxWidth: 880 }}>
              Загрузите баннер — проверим код и дадим нацеливание: баннер появится на сайтах площадок с нашим кодом у вас
              в браузере, с демо-маркером вместо ЕРИД. Через 48 часов проверка удаляется вместе с нацеливанием.
            </span>
          </div>

          {mayEdit && (
            <div style={{ ...card, padding: '18px 24px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
              <span style={CAP10}>Новая проверка</span>
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr) minmax(0,1.2fr)', gap: 12 }}>
                <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  <span style={CAP9}>Название <span style={{ color: 'var(--danger)' }}>*</span></span>
                  <input style={FIELD} value={title} onChange={e => setTitle(e.target.value)} maxLength={200}
                    placeholder="чтобы различать проверки" />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  <span style={CAP9}>Домен рекламодателя</span>
                  <input style={{ ...FIELD, fontFamily: MONO, fontSize: 12.5 }} value={url}
                    onChange={e => setUrl(e.target.value)} placeholder="example.ru" />
                </label>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 }}>
                  <span style={CAP9}>Файл</span>
                  <span role="button" tabIndex={0} onClick={() => fileRef.current && fileRef.current.click()}
                    onKeyDown={e => { if (e.key === 'Enter') fileRef.current && fileRef.current.click() }}
                    onDragOver={e => e.preventDefault()}
                    onDrop={e => { e.preventDefault(); pick(e.dataTransfer.files && e.dataTransfer.files[0]) }}
                    style={{ display: 'flex', alignItems: 'center', gap: 10, height: 38, boxSizing: 'border-box',
                      padding: '0 6px 0 12px', borderRadius: 12, cursor: 'pointer', minWidth: 0,
                      background: file ? 'var(--bg-tint)' : 'var(--bg-subtle)',
                      border: `1px dashed ${file ? 'var(--accent-border)' : 'var(--border-hover)'}` }}>
                    <span style={{ color: file ? 'var(--accent)' : 'var(--text-faint)', display: 'inline-flex', flex: '0 0 15px' }}>
                      <Icon size={15}><path d="M12 16V4" /><path d="M8 8l4-4 4 4" /><path d="M5 20h14" /></Icon>
                    </span>
                    <span title={file ? file.name : ''} style={{ flex: 1, minWidth: 0, fontSize: 12.5, overflow: 'hidden',
                      textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      color: file ? 'var(--text-primary)' : 'var(--text-faint)' }}>
                      {file ? file.name : 'Перетащите файл или выберите'}
                    </span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 10px',
                      background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 8,
                      fontSize: 11.5, fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                      {file ? 'Заменить' : 'Выбрать'}
                    </span>
                  </span>
                  <input ref={fileRef} type="file" accept={ACCEPT} style={{ display: 'none' }}
                    onChange={e => pick(e.target.files && e.target.files[0])} />
                </span>
              </div>
              <span style={{ fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.45 }}>
                Картинка (png, jpg, gif, webp, svg), HTML5-архив (zip) или html. Блокируем только битые архивы и
                несовместимые файлы — остальное покажем замечаниями.
              </span>

              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', paddingTop: 12,
                borderTop: '1px solid var(--border-inner)' }}>
                <button type="button" onClick={() => setSitesOpen(v => !v)}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5, fontWeight: 600,
                    color: 'var(--text-secondary)', cursor: 'pointer', background: 'none', border: 'none',
                    padding: 0, fontFamily: UI }}>
                  <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>{sitesOpen ? '▾' : '▸'}</span>
                  Площадки по умолчанию
                  <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>
                    наш код · веб · {pubs.length}
                  </span>
                </button>
                {formErr && <span style={{ fontSize: 12.5, color: 'var(--danger-fg)' }}>{formErr}</span>}
                <button type="button" onClick={submit} disabled={!canSubmit}
                  title={!file ? 'Выберите файл' : !title.trim() ? 'Укажите название' : undefined}
                  style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8, height: 38,
                    padding: '0 18px', border: 'none', borderRadius: 12, fontSize: 13, fontWeight: 700,
                    color: '#fff', fontFamily: UI, whiteSpace: 'nowrap',
                    background: canSubmit ? 'var(--accent)' : 'var(--text-disabled)',
                    cursor: canSubmit ? 'pointer' : 'not-allowed' }}>
                  {busy && <Cube variant="spinner" size={18} />}
                  {busy ? 'Проверяем…' : 'Проверить'}
                </button>
              </div>

              {sitesOpen && (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', padding: '10px 12px',
                  background: 'var(--bg-subtle)', borderRadius: 12 }}>
                  {pubs.map(p => (
                    <span key={p.id} title={p.name} style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
                      height: 26, padding: '0 9px', background: 'var(--bg-card)', border: '1px solid var(--border-card)',
                      borderRadius: 8, fontFamily: MONO, fontSize: 11, color: 'var(--text-primary)' }}>
                      <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--accent)' }} />{p.domain || p.name}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {err && <div style={{ ...card, padding: '12px 16px', color: 'var(--danger-fg)', fontSize: 13 }}>{err}</div>}
          {rows === null && <div style={{ padding: 30, textAlign: 'center' }}><Cube variant="wave" size={72} /></div>}
          {(rows || []).map(c => (
            <CheckCard key={c.id} c={c} mayEdit={mayEdit} mayDelete={mayDelete} onPreview={setPreview} onDelete={setDrop} />
          ))}
          {rows && rows.length === 0 && !err && (
            <div style={{ background: 'var(--bg-card)', border: '1px dashed var(--border-card)', borderRadius: 18,
              padding: 36, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)' }}>Проверок пока нет</span>
              <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>
                {mayEdit ? 'загрузите баннер в форме выше' : 'проверки появятся здесь после загрузки'}
              </span>
            </div>
          )}
        </div>
      </div>

      {preview && (
        <CreativePreview title={`Предпросмотр · ${preview.title}`} set={null} canApprove={false}
          onReviewed={() => {}} onClose={() => setPreview(null)}
          files={[{ id: preview.id, name: 'banner.zip', /* хранится архив: имя .png заставило бы тянуть картинку с авторизацией */
                    ratio: preview.info?.size, sandbox_url: preview.sandbox_url }]}
          startId={preview.id} />
      )}

      {drop && (
        <Modal title={`Удалить проверку «${drop.title}»?`} width={420} onClose={() => setDrop(null)}
          footer={
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', width: '100%' }}>
              <button type="button" style={btn(false)} onClick={() => setDrop(null)}>Отмена</button>
              <button type="button" onClick={remove}
                style={{ ...btn(true), background: 'var(--danger)' }}>Удалить</button>
            </div>
          }>
          <span style={{ display: 'flex', alignItems: 'flex-start', gap: 9, padding: '9px 12px', margin: '6px 0',
            background: 'var(--danger-tint)', border: '1px solid var(--danger-border)', borderRadius: 10,
            fontSize: 12.5, color: 'var(--danger-fg)', lineHeight: 1.45 }}>
            <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--danger)', flex: '0 0 7px', marginTop: 5 }} />
            Действие необратимо: нацеливание снимется, баннер пропадёт с площадок у вас в браузере.
          </span>
        </Modal>
      )}
    </>
  )
}
