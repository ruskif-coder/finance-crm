/**
 * Предпросмотр баннера в типовых размерах.
 *
 * Копия логики из `frontend/components/creatives/AssemblyCreatives.jsxx`, и это осознанная
 * копия, а не недосмотр: кабинет — отдельный пакет и отдельный контейнер, общего сборщика
 * с финмодулем у них нет. Тащить сюда весь кит ради одного компонента значило бы тянуть
 * во внешний контур зависимости, которые ему не нужны.
 *
 * Что обязано совпадать — СПИСОК РАЗМЕРОВ: площадка и аккаунт должны видеть баннер в
 * одних и тех же местах, иначе «у нас всё нормально» и «у вас поехало» становятся
 * неразрешимым спором. При правке списка правятся оба файла.
 */
import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { overlayClose } from './overlay'
import { C, MONO, UI, btn } from './ui'
import Sheet, { SHEET_BTN } from './sheet'
import useIsMobile from './useIsMobile'

export const STOCK_SIZES = [[240, 400], [300, 600], [640, 100], [970, 250],
  [1000, 150], [1200, 150]]
// Порядок (владелец 25.09.2026): сначала вертикальные, потом горизонтальные, в каждой
// группе по возрастанию ширины; 320×50 убран. Правя список — правь оба файла.

/** Размер, объявленный в самом баннере (`<meta name="ad.size">`). Имя файла врёт. */
export const RATIO_PX = (ratio) => {
  const m = /^(\d{2,4})\s*[x×]\s*(\d{2,4})$/i.exec((ratio || '').trim())
  return m ? [Number(m[1]), Number(m[2])] : null
}

export const FULL = 'full'

/* Размеры (владелец 29.09.2026): первым «во весь экран» — баннер на всю сцену, он же по
   умолчанию; дальше типовые (или объявленный); последним — «в отдельной вкладке».
   Та же раскладка в финмодуле: `frontend/components/creatives/CreativePreview.jsx`.

   `fill` — сцена занимает всё место окна (модалка 80 % браузера). Без него (нижний лист
   на телефоне) сцена своей высоты, и для фикс-размеров остаётся «по экрану / 1:1». */
export default function Preview({ file, fill = false }) {
  const stageRef = useRef(null)
  const [box, setBox] = useState({ w: 720, h: 420 })
  const own0 = RATIO_PX(file?.size)
  // Телефон (нижний лист) — прежний вид без «во весь экран»: у мобилки своя раскладка.
  const [size, setSize] = useState(fill ? FULL : `${(own0 || STOCK_SIZES[0])[0]}x${(own0 || STOCK_SIZES[0])[1]}`)
  /* «По экрану / 1:1» (владелец 26.09.2026). На телефоне поле ~330 px, и 1200×150
     вписывается в 28 % — полоска, на которой не прочитать текст. */
  const [real, setReal] = useState(false)

  const own = RATIO_PX(file?.size)
  const sizes = own ? [own] : STOCK_SIZES
  const wh = size === FULL ? null : (sizes.find(([w, h]) => `${w}x${h}` === size) || null)
  const fitK = wh ? Math.min(1, box.w / wh[0], fill ? box.h / wh[1] : Infinity) : 1
  const k = real && !fill ? 1 : fitK
  const canReal = !fill && !!wh && wh[0] > box.w
  /* Сцена телефона держит высоту САМОГО ВЫСОКОГО из размеров и не прыгает при
     переключении — как было до 29.09.2026. */
  const stageH = fill ? null : Math.max(160, ...sizes.map(([w, h]) =>
    Math.round((real ? 1 : Math.min(1, box.w / w)) * h))) + 28

  useEffect(() => {
    const el = stageRef.current
    if (!el) return undefined
    const measure = () => setBox({ w: Math.max(240, el.clientWidth - 28), h: Math.max(160, el.clientHeight - 28) })
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [file?.id])

  if (!file?.preview_url) {
    return (
      <div style={{ padding: '18px 0', fontSize: 12.5, color: C.faint }}>
        Предпросмотр недоступен — материал не разворачивается в тестовой среде.
      </div>
    )
  }

  const pill = (on) => ({ cursor: 'pointer', fontFamily: MONO, fontSize: 11.5, fontWeight: 700,
    padding: '5px 12px', borderRadius: 100, textDecoration: 'none',
    border: `1px solid ${on ? C.accent : C.border}`,
    background: on ? C.accent : C.subtle, color: on ? C.onFill : C.secondary })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, ...(fill ? { flex: '1 1 auto', minHeight: 0 } : {}) }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        {fill && <span onClick={() => setSize(FULL)} style={pill(size === FULL)}>во весь экран</span>}
        {sizes.map(([w, h]) => (
          <span key={`${w}x${h}`} onClick={() => setSize(`${w}x${h}`)} style={pill(size === `${w}x${h}`)}>{w}×{h}</span>
        ))}
        {fill && (
          <a href={file.preview_url} target="_blank" rel="noreferrer" style={pill(false)}
            title="Рисуется там, а здесь пусто — дело в рамке, а не в баннере">в отдельной вкладке ↗</a>
        )}
        <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.06em',
          textTransform: 'uppercase', color: C.faint, marginLeft: 4 }}>
          {own ? 'размер объявлен в баннере' : 'баннер адаптивный'}
        </span>
        {canReal && (
          <span style={{ marginLeft: 'auto', display: 'inline-flex', borderRadius: 9,
            border: `1px solid ${C.border}`, overflow: 'hidden' }}>
            {[[false, 'по экрану'], [true, '1:1']].map(([v, label]) => (
              <span key={label} onClick={() => setReal(v)}
                style={{ cursor: 'pointer', padding: '6px 12px', fontSize: 12, fontWeight: 700,
                  background: real === v ? C.accentTint : C.card,
                  color: real === v ? C.accent : C.secondary }}>{label}</span>
            ))}
          </span>
        )}
      </div>

      {/* Широкий баннер в 1:1 прижат к левому краю: при центрировании его левая часть
          уходила бы за край сцены, куда прокрутка не достаёт. */}
      <div ref={stageRef} style={{ padding: 14, borderRadius: 12, background: C.subtle,
        border: `1px solid ${C.border}`, display: 'flex',
        justifyContent: wh && wh[0] * k > box.w ? 'flex-start' : 'center',
        alignItems: 'center', overflowX: real ? 'auto' : 'hidden', boxSizing: 'border-box',
        ...(fill ? { flex: '1 1 auto', minHeight: 0 } : { height: stageH }) }}>
        {/* Баннер крутится С ЧУЖОГО ДОМЕНА — из песочницы: HTML5-баннер в архиве —
            исполняемый код, и на домене кабинета он получил бы доступ к сессии. */}
        <div style={wh ? { width: Math.round(wh[0] * k), height: Math.round(wh[1] * k), overflow: 'hidden', flex: '0 0 auto' }
          : { width: '100%', height: '100%' }}>
          <iframe key={size} src={file.preview_url} title={`Баннер ${wh ? wh.join('×') : 'во весь экран'}`}
            // Скрипты баннера — да, наше происхождение — нет (аудит 23.09.2026, 7.L2).
            sandbox="allow-scripts"
            /* Белый ЖЁСТКО, а не из темы: это полотно чужой страницы, а не наш
               интерфейс. Единственное исключение, разрешённое `scripts/check-tokens.mjs`. */
            style={{ border: 0, display: 'block', background: '#fff',
              width: wh ? wh[0] : '100%', height: wh ? wh[1] : '100%',
              transform: wh ? `scale(${k})` : 'none', transformOrigin: 'top left' }} />
        </div>
      </div>

      <div style={{ fontSize: 11.5, color: C.muted }}>
        Баннер запущен в тестовой среде.
        {wh && k < 1 && ` Масштаб ${Math.round(k * 100)} % — размер ${wh[0]}×${wh[1]} не помещается в окно.`}
        {real && wh && wh[0] > box.w && ' Настоящий размер — листайте баннер вбок.'}
        {/* Блокировщик принимает баннер типового размера за рекламу и режет его картинки
            (владелец 25.09.2026 — сам поймал это на своём браузере). */}
        <br />Если баннер не отображается, проверьте блокировщики рекламы или VPN.
      </div>
    </div>
  )
}


/* Баннер по умолчанию СВЁРНУТ и открывается модалкой — как у аккаунтов и трафиков.
   Причина не в экономии места: у площадки в списке несколько заданий, и три-четыре
   крутящихся баннера на одном экране мешают друг другу, тянут ресурсы и не дают
   сравнить ни одного — смотрят их по очереди, а не разом. */
const OVERLAY = {
  position: 'fixed', inset: 0, background: 'var(--overlay)', zIndex: 10000,
  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
}

export function PreviewModal({ file, title, onClose, onDownload }) {
  const mobile = useIsMobile()
  /* Рисуется ПОРТАЛОМ в `body`, а не там, где вызвана. `position: fixed` считает свои
     координаты от ближайшего предка с `transform`/`filter`/`will-change`, а `z-index`
     живёт внутри стека родителя: карточка запроса с анимацией `riseIn` создаёт такой
     стек, и окно уезжает под соседние блоки. Ровно эта ошибка и была видна.
     Портал выносит его наружу — тогда `z-index` сравнивается с корневым уровнем. */
  const [ready, setReady] = useState(false)
  useEffect(() => { setReady(true) }, [])   // на сервере `document` не существует
  if (!ready) return null

  // Телефон — нижний лист (хендофф «моб версия кп»): размеры, превью, «Скачать архив».
  if (mobile) {
    return (
      <Sheet title="Предпросмотр креатива" meta={title} onClose={onClose}
        footer={(
          <>
            {!!onDownload && (
              <button style={{ ...btn(false), ...SHEET_BTN, flex: 1 }} onClick={onDownload}>
                Скачать архив
              </button>
            )}
            <button style={{ ...btn(true), ...SHEET_BTN, flex: 1 }} onClick={onClose}>
              Закрыть
            </button>
          </>
        )}>
        <Preview file={file} />
      </Sheet>
    )
  }

  return createPortal(
    <div style={OVERLAY} {...overlayClose(onClose)}>
      {/* Ширина — под самый широкий типовой размер 1:1 (владелец 25.09.2026): 1200 баннера +
          74 полей окна и сцены + 16 на полосу прокрутки. Уже экрана — вписывается, как раньше. */}
      {/* Окно — 80 % браузера (владелец 29.09.2026), сцена занимает всё остальное. */}
      <div style={{ background: C.card, borderRadius: 16, padding: '20px 22px',
        width: '80vw', height: '80vh', boxSizing: 'border-box', display: 'flex', flexDirection: 'column',
        boxShadow: '0 20px 60px rgba(16,20,30,.25)', fontFamily: UI }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
          <span style={{ fontSize: 17, fontWeight: 700 }}>Предпросмотр креатива</span>
          {!!title && (
            <span style={{ fontSize: 12.5, color: C.muted }}>{title}</span>
          )}
          <span style={{ flex: 1 }} />
          {!!onDownload && <button style={btn(false)} onClick={onDownload}>Скачать</button>}
          <button style={btn(false)} onClick={onClose}>Закрыть</button>
        </div>
        <Preview file={file} fill />
      </div>
    </div>,
    document.body)
}
