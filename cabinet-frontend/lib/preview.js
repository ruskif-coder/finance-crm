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

export const STOCK_SIZES = [[240, 400], [300, 600], [640, 100], [970, 250],
  [1000, 150], [1200, 150]]
// Порядок (владелец 25.09.2026): сначала вертикальные, потом горизонтальные, в каждой
// группе по возрастанию ширины; 320×50 убран. Правя список — правь оба файла.

/** Размер, объявленный в самом баннере (`<meta name="ad.size">`). Имя файла врёт. */
export const RATIO_PX = (ratio) => {
  const m = /^(\d{2,4})\s*[x×]\s*(\d{2,4})$/i.exec((ratio || '').trim())
  return m ? [Number(m[1]), Number(m[2])] : null
}

export default function Preview({ file }) {
  const stageRef = useRef(null)
  const [avail, setAvail] = useState(720)
  const [idx, setIdx] = useState(0)

  const own = RATIO_PX(file?.size)
  const sizes = own ? [own] : STOCK_SIZES
  const wh = sizes[Math.min(idx, sizes.length - 1)]
  const k = wh ? Math.min(1, avail / wh[0]) : 1

  /* Сцена держит высоту САМОГО ВЫСОКОГО из доступных размеров и не меняется при
     переключении: иначе окно прыгает на сотни пикселей между 300×600 и 1200×150, кнопки
     ответа уезжают из-под курсора, и сравнить два размера подряд невозможно. */
  const stageH = Math.max(160, ...sizes.map(([w, h]) => Math.round(Math.min(1, avail / w) * h)))

  useEffect(() => {
    const el = stageRef.current
    if (el) setAvail(Math.max(240, el.clientWidth - 28))
  }, [file?.id, idx])

  if (!file?.preview_url) {
    return (
      <div style={{ padding: '18px 0', fontSize: 12.5, color: C.faint }}>
        Предпросмотр недоступен — материал не разворачивается в тестовой среде.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        {sizes.map(([w, h], i) => {
          const on = i === Math.min(idx, sizes.length - 1)
          return (
            <span key={`${w}x${h}`} onClick={() => setIdx(i)}
              style={{ cursor: 'pointer', fontFamily: MONO, fontSize: 11.5, fontWeight: 700,
                padding: '5px 12px', borderRadius: 100,
                border: `1px solid ${on ? C.accent : C.border}`,
                background: on ? C.accent : C.subtle,
                color: on ? C.onFill : C.secondary }}>
              {w}×{h}
            </span>
          )
        })}
        <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '.06em',
          textTransform: 'uppercase', color: C.faint, marginLeft: 4 }}>
          {own ? 'размер объявлен в баннере' : 'баннер адаптивный'}
        </span>
      </div>

      <div ref={stageRef} style={{ padding: 14, borderRadius: 12, background: C.subtle,
        border: `1px solid ${C.border}`, display: 'flex', justifyContent: 'center',
        alignItems: 'center', overflowX: 'auto', height: stageH + 28,
        boxSizing: 'border-box' }}>
        {/* Баннер крутится С ЧУЖОГО ДОМЕНА — из песочницы. Это не деталь раздачи:
            HTML5-баннер в архиве — исполняемый код, и на домене кабинета он получил бы
            доступ к сессии смотрящего. */}
        <div style={{ width: wh ? Math.round(wh[0] * k) : '100%',
          height: wh ? Math.round(wh[1] * k) : 420, overflow: 'hidden' }}>
          <iframe src={file.preview_url} title={`Баннер ${wh ? wh.join('×') : ''}`}
            // Скрипты баннера — да, наше происхождение — нет (аудит 23.09.2026, 7.L2).
            sandbox="allow-scripts"
            /* Белый ЖЁСТКО, а не из темы: это полотно чужой страницы, а не наш
               интерфейс. Баннер рисуют для белого сайта, и тёмный фон под ним показал
               бы не то размещение, которое будет на самом деле. Единственное
               исключение, разрешённое `scripts/check-tokens.mjs` поимённо. */
            style={{ border: 0, display: 'block', background: '#fff',
              width: wh ? wh[0] : '100%', height: wh ? wh[1] : 420,
              transform: `scale(${k})`, transformOrigin: 'top left' }} />
        </div>
      </div>

      <div style={{ fontSize: 11.5, color: C.muted }}>
        Баннер запущен в тестовой среде.
        {k < 1 && ` Масштаб ${Math.round(k * 100)} % — размер ${wh[0]}×${wh[1]} не помещается в окно.`}
        {/* Блокировщик принимает баннер типового размера за рекламу и режет его
            картинки: остаётся пустой фон, и выглядит это как поломка у нас (владелец
            25.09.2026 — сам поймал это на своём браузере). */}
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

export function PreviewModal({ file, title, onClose }) {
  /* Рисуется ПОРТАЛОМ в `body`, а не там, где вызвана. `position: fixed` считает свои
     координаты от ближайшего предка с `transform`/`filter`/`will-change`, а `z-index`
     живёт внутри стека родителя: карточка запроса с анимацией `riseIn` создаёт такой
     стек, и окно уезжает под соседние блоки. Ровно эта ошибка и была видна.
     Портал выносит его наружу — тогда `z-index` сравнивается с корневым уровнем. */
  const [ready, setReady] = useState(false)
  useEffect(() => { setReady(true) }, [])   // на сервере `document` не существует
  if (!ready) return null

  return createPortal(
    <div style={OVERLAY} {...overlayClose(onClose)}>
      {/* Ширина — под самый широкий типовой размер 1:1 (владелец 25.09.2026): 1200 баннера +
          74 полей окна и сцены + 16 на полосу прокрутки. Уже экрана — вписывается, как раньше. */}
      <div style={{ background: C.card, borderRadius: 16, padding: '20px 22px',
        width: 'min(1290px, 96vw)', maxHeight: '86vh', overflowY: 'auto',
        boxShadow: '0 20px 60px rgba(16,20,30,.25)', fontFamily: UI }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
          <span style={{ fontSize: 17, fontWeight: 700 }}>Предпросмотр креатива</span>
          {!!title && (
            <span style={{ fontSize: 12.5, color: C.muted }}>{title}</span>
          )}
          <span style={{ flex: 1 }} />
          <button style={btn(false)} onClick={onClose}>Закрыть</button>
        </div>
        <Preview file={file} />
      </div>
    </div>,
    document.body)
}
