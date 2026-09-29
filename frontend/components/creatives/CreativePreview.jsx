/* Предпросмотр креатива — ОДИН компонент на все места финмодуля: сборка у аккаунта,
   свёрнутые креативы сделки, очередь трафика, демо-стенд DSP. Вынесен из
   AssemblyCreatives.jsx 29.09.2026; там оставлен реэкспорт.

   Окно — 80 % браузера (владелец 29.09.2026). Размеры: первым «Во весь экран» (баннер на
   всю сцену, открывается по умолчанию), дальше типовые/объявленный, последним — «открыть
   в отдельной вкладке». Та же раскладка в кабинете площадки: `cabinet-frontend/lib/preview.js`.

   Пять типовых пропорций — те же, что на демо-стенде. Адаптивный баннер (а таких
   большинство: `ad.size` у них «0,0») смотрят именно так — прикладывая к местам, куда он
   поедет. Баннер с ОБЪЯВЛЕННЫМ размером показывается только в своём: класть фикс в чужую
   рамку — значит смотреть на то, чего в размещении не будет.

   ВТОРАЯ КОПИЯ СПИСКА РАЗМЕРОВ — `cabinet-frontend/lib/preview.js`, и она обязана
   совпадать. Кабинет отдельный пакет и отдельный контейнер, общего сборщика с нами у него
   нет по построению внешнего контура. Правя список — правь оба файла одним заходом. */
import { useEffect, useRef, useState } from 'react'
import api, { auth } from '@/lib/api'
import { MONO, btn } from '@/components/salesTableKit'
import { overlayClose } from '@/lib/overlay'

export const STOCK_SIZES = [[240, 400], [300, 600], [640, 100], [970, 250],
  [1000, 150], [1200, 150]]
// Порядок (владелец 25.09.2026): сначала вертикальные, потом горизонтальные, в каждой
// группе по возрастанию ширины; 320×50 убран. Правя список — правь оба файла.
export const FULL = 'full'

const RATIO_PX = (ratio) => {
  const m = /^(\d{2,4})\s*[x×]\s*(\d{2,4})$/i.exec((ratio || '').trim())
  return m ? [Number(m[1]), Number(m[2])] : null
}
const CAP = { fontFamily: MONO, fontSize: 10, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }
const OVERLAY = { position: 'fixed', inset: 0, background: 'rgba(16,20,30,.45)', zIndex: 60, display: 'flex', alignItems: 'center', justifyContent: 'center' }
const PILL = (on) => ({ cursor: 'pointer', fontFamily: MONO, fontSize: 11.5, fontWeight: 700,
  padding: '5px 12px', borderRadius: 100, textDecoration: 'none',
  border: `1px solid ${on ? 'var(--accent)' : 'var(--border-card)'}`,
  background: on ? 'var(--accent)' : 'var(--bg-subtle)',
  color: on ? 'var(--bg-card)' : 'var(--text-secondary)' })

/** Рамка баннера: во весь экран — по размеру сцены; фикс — вписан в сцену по обеим сторонам. */
function Frame({ wh, box, children }) {
  if (!wh) return <div style={{ width: '100%', height: '100%' }}>{children(null, 1)}</div>
  const k = Math.min(1, box.w / wh[0], box.h / wh[1])
  return (
    <div style={{ width: Math.round(wh[0] * k), height: Math.round(wh[1] * k), overflow: 'hidden', flex: '0 0 auto' }}>
      {children(wh, k)}
    </div>
  )
}

/** `htmlSource` — готовая разметка вместо файла из хранилища (демо-стенд DSP, 06.09.2026):
 *  баннер ещё не файл в нашей базе, а строка от загрузчика DSP. Отличается только
 *  источник разметки — не показ. */
export function CreativePreview({ files, startId, set, canApprove, onReviewed, onClose,
                                  htmlSource = null, sandboxUrl = null,
                                  title = 'Предпросмотр креатива' }) {
  const [curId, setCurId] = useState(startId)
  /* СВЕЖИЙ ДОКУМЕНТ НА КАЖДЫЙ ПОКАЗ. Баннер играет свою анимацию ОДИН раз и застывает на
     последнем кадре; пока адрес рамки не менялся, браузер переиспользовал отработавший
     документ, и со второго открытия человек видел застывшую картинку. */
  const [nonce] = useState(() => Date.now())
  const fresh = (u) => (u ? u + (u.includes('?') ? '&' : '?') + 'v=' + nonce + '-' + curId : u)
  const [blob, setBlob] = useState(null)
  const [html, setHtml] = useState(null)
  const [err, setErr] = useState('')
  const stageRef = useRef(null)
  const [box, setBox] = useState({ w: 720, h: 420 })
  const [size, setSize] = useState(FULL)
  const [reviewBusy, setReviewBusy] = useState(false)
  const [reviewErr, setReviewErr] = useState('')

  const review = async (verdict) => {
    if (verdict === 'на доработку') { onReviewed(verdict); return }   // причина обязательна — спросим в форме
    setReviewBusy(true); setReviewErr('')
    try {
      await api.post(`/launch-prep/set/${set.id}/primary-review`, { verdict, reason: '' }, auth())
      onReviewed(verdict)
    } catch (e) { setReviewErr(e.response?.data?.detail || 'Не удалось сохранить'); setReviewBusy(false) }
  }

  const list = files || []
  const cur = list.find(f => f.id === curId) || list[0]
  const ext = (cur?.name || '').toLowerCase().split('.').pop()
  const isImg = !htmlSource && ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)
  const isHtml = !!htmlSource || ext === 'html'
  const tabUrl = cur?.sandbox_url || sandboxUrl

  useEffect(() => {
    let alive = true
    let url = null
    setBlob(null); setHtml(null); setErr('')
    if (htmlSource) { setHtml(htmlSource); return }
    if (!cur || (!isImg && !isHtml)) return
    api.get(`/launch-prep/file/${cur.id}`, { ...auth(), responseType: 'blob' })
      .then(async r => {
        if (!alive) return
        if (isHtml) setHtml(await r.data.text())
        else { url = URL.createObjectURL(r.data); setBlob(url) }
      })
      .catch(() => { if (alive) setErr('Не удалось загрузить файл') })
    return () => { alive = false; if (url) URL.revokeObjectURL(url) }
  }, [cur, isImg, isHtml, htmlSource])

  // Размер сцены — от окна (80 % браузера); меняется вместе с окном браузера.
  useEffect(() => {
    const el = stageRef.current
    if (!el) return undefined
    const measure = () => setBox({ w: Math.max(240, el.clientWidth - 28), h: Math.max(160, el.clientHeight - 28) })
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const own = RATIO_PX(cur?.ratio)
  const sizes = own ? [own] : STOCK_SIZES
  const wh = size === FULL ? null : (sizes.find(([w, h]) => `${w}x${h}` === size) || null)
  const k = wh ? Math.min(1, box.w / wh[0], box.h / wh[1]) : 1
  const frame = (src) => {
    function renderFrame(w, kk) {
      return (
        <iframe key={`${curId}-${size}`} {...src} sandbox="allow-scripts" title={'Креатив ' + (cur?.ratio || '')}
          style={{ border: 0, display: 'block', background: 'var(--bg-card)',
            width: w ? w[0] : '100%', height: w ? w[1] : '100%',
            transform: w ? `scale(${kk})` : 'none', transformOrigin: 'top left' }} />
      )
    }
    return renderFrame
  }

  return (
    <div style={OVERLAY} {...overlayClose(onClose)}>
      <div style={{ background: 'var(--bg-card)', borderRadius: 'var(--radius-card)', boxShadow: 'var(--shadow-card)',
        width: '80vw', height: '80vh', padding: '18px 22px', boxSizing: 'border-box',
        display: 'flex', flexDirection: 'column', minWidth: 320 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 17, fontWeight: 700 }}>{title}</span>
          <button style={{ ...btn(false), marginLeft: 'auto' }} onClick={onClose}>Закрыть</button>
        </div>

        {/* Размеры: «во весь экран» → типовые (или объявленный) → «в отдельной вкладке». */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 12, alignItems: 'center' }}>
          <span onClick={() => setSize(FULL)} style={PILL(size === FULL)}>во весь экран</span>
          {sizes.map(([w, h]) => (
            <span key={`${w}x${h}`} onClick={() => setSize(`${w}x${h}`)} style={PILL(size === `${w}x${h}`)}>{w}×{h}</span>
          ))}
          {!err && !!tabUrl && (
            <a href={fresh(tabUrl)} target="_blank" rel="noreferrer" style={PILL(false)}
              title="Рисуется там, а здесь пусто — дело в рамке, а не в баннере">в отдельной вкладке ↗</a>
          )}
          <span style={{ ...CAP, marginLeft: 6 }}>{own ? 'размер объявлен в баннере' : 'баннер адаптивный'}</span>
          {list.length > 1 && (
            <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
              {list.map(f => (
                <span key={f.id} onClick={() => setCurId(f.id)} title={f.name}
                  style={{ cursor: 'pointer', fontSize: 10.5, padding: '4px 9px', borderRadius: 8, border: '1px solid var(--border-card)',
                    background: f.id === cur?.id ? 'var(--bg-subtle)' : 'transparent',
                    color: f.id === cur?.id ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                  {f.name.length > 18 ? f.name.slice(0, 17) + '…' : f.name}
                </span>
              ))}
            </span>
          )}
        </div>

        <div ref={stageRef} style={{ marginTop: 14, padding: 14, borderRadius: 12, flex: '1 1 auto', minHeight: 0,
          background: 'var(--bg-subtle)', border: '1px solid var(--border-card)',
          display: 'flex', justifyContent: 'center', alignItems: 'center', overflow: 'hidden', boxSizing: 'border-box' }}>
          {!!err && <span style={{ fontSize: 12.5, color: 'var(--dot-overdue)' }}>{err}</span>}
          {!err && isImg && !blob && <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>загрузка…</span>}
          {!err && isImg && !!blob && (
            <img src={blob} alt={cur?.name || 'креатив'} style={{ maxWidth: '100%', maxHeight: '100%', display: 'block', background: 'var(--bg-card)' }} />
          )}
          {!err && isHtml && html === null && <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>загрузка…</span>}
          {/* Чужой код — только в изолированной рамке без allow-same-origin. Песочница, если
              есть, а не srcdoc: srcdoc наследует НАШ CSP, и баннер после загрузчика DSP
              показал бы пустую рамку. */}
          {!err && isHtml && html !== null && (
            <Frame wh={wh} box={box}>{frame(sandboxUrl ? { src: fresh(sandboxUrl) } : { srcDoc: html })}</Frame>
          )}
          {/* Архив крутится ИЗ ПЕСОЧНИЦЫ — с отдельного домена, без нашей сессии и API. */}
          {!err && !isImg && !isHtml && !!cur?.sandbox_url && (
            <Frame wh={wh} box={box}>{frame({ src: fresh(cur.sandbox_url) })}</Frame>
          )}
          {!err && !isImg && !isHtml && !cur?.sandbox_url && (
            <span style={{ fontSize: 12.5, color: 'var(--text-muted)', maxWidth: 520, textAlign: 'center', lineHeight: 1.55 }}>
              {ext === 'zip'
                ? 'Архив не распакован в песочницу. Так бывает у файлов, загруженных до её появления: перезалейте архив — распаковка идёт при загрузке, и негодный архив отклоняется сразу.'
                : 'Для этого типа файла предпросмотра пока нет — скачайте его, чтобы посмотреть.'}
            </span>
          )}
        </div>

        <div style={{ marginTop: 10, fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.5 }}>
          {isHtml || cur?.sandbox_url
            ? 'Баннер крутится в изолированной рамке без доступа к странице.'
              + (wh && k < 1 ? ` Масштаб ${Math.round(k * 100)} % — размер ${wh[0]}×${wh[1]} не помещается в окно.` : '')
              + ' Если баннер не отображается, проверьте блокировщики рекламы или VPN.'
            : 'Файл тянется с авторизацией и живёт только в этой вкладке.'}
        </div>

        {/* Первичная проверка — здесь, где на креатив только что посмотрели (27.08.2026). */}
        {!!(canApprove && set && !set.primary_review) && (
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border-card)' }}>
            {!!reviewErr && <span style={{ marginRight: 'auto', fontSize: 12, color: 'var(--dot-overdue)' }}>{reviewErr}</span>}
            <button style={{ ...btn(false), color: 'var(--dot-overdue)', borderColor: 'var(--dot-overdue)' }}
              disabled={reviewBusy} onClick={() => review('на доработку')}>На доработку</button>
            <button style={btn(true)} disabled={reviewBusy} onClick={() => review('ок')}>Всё работает</button>
          </div>
        )}
      </div>
    </div>
  )
}
