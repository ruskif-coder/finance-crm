import Link from 'next/link'
import { UI, MONO } from '../salesTableKit'

// Список требований к переходу — ОДИН на все экраны: карточка сделки, диалог движения и
// модалка отказа после массовой правки. Три копии разошлись бы в формулировках, и человек
// увидел бы «не согласовано» в одном месте и «нет вердикта площадки» в другом про одно и
// то же.
//
// Четыре исхода приходят с бэкенда (app/sales/stage_checks.py) и означают РАЗНОЕ:
//   выполнено   — сошлось;
//   не сделано  — единственное, что запирает переход;
//   неизвестно  — проверить нечем (нет интеграции). Показываем, но не запираем;
//   неприменимо — до экрана не доходит вовсе, бэкенд отсеивает такие строки.
const TONE = {
  ok:      { mark: '✓', fg: 'var(--income)',    bg: 'var(--income-tint)',  bd: 'var(--income-border)' },
  not_yet: { mark: '!', fg: 'var(--danger)',    bg: 'var(--danger-tint)',  bd: 'var(--danger-border)' },
  unknown: { mark: '?', fg: 'var(--warning-text)', bg: 'var(--warning-tint)', bd: 'var(--warning-border)' },
}

const badge = (t) => ({
  width: 18, height: 18, borderRadius: 5, flex: '0 0 18px',
  display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 800,
  color: t.fg, background: t.bg, border: `1px solid ${t.bd}`,
})

// Куда ведёт место. «#секция» — блок на этой же карточке: прокручиваем, а не уходим со
// страницы. Абсолютный адрес — обычная ссылка. Пусто — место есть, а идти никуда не надо
// (например, воронка выбирается здесь же в диалоге).
function Where({ line, onCard }) {
  const text = line.where
  if (!text) return null
  const common = { fontSize: 11.5, color: 'var(--text-muted)' }
  // Якорь на блок карточки кликабелен ТОЛЬКО на самой карточке. В модалке реестра
  // слушателя `deal-section-open` нет, и ссылка делала бы preventDefault в пустоту —
  // место названо, а нажатие ничего не даёт. Там показываем то же место текстом.
  if (!line.link || (line.link.startsWith('#') && !onCard)) {
    return <span style={common}>{text}</span>
  }
  if (line.link.startsWith('#')) {
    // Блок на этой же карточке: разворачиваем и прокручиваем. Только прокрутить мало —
    // секции сворачиваемые, и человек упёрся бы в закрытый заголовок.
    const sec = line.link.slice(1)
    return (
      <a href={line.link} style={{ ...common, color: 'var(--accent)', textDecoration: 'none' }}
         onClick={(e) => {
           e.preventDefault()
           window.dispatchEvent(new CustomEvent('deal-section-open', { detail: sec }))
           // Разворачивание — состояние React, поэтому скроллим следующим кадром:
           // до перерисовки узел ещё имеет высоту свёрнутого.
           requestAnimationFrame(() => {
             const el = document.getElementById(`sec-${sec}`)
             if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
           })
         }}>{text}</a>
    )
  }
  return (
    <Link href={line.link} style={{ ...common, color: 'var(--accent)', textDecoration: 'none' }}>
      {text}
    </Link>
  )
}

export default function StageRequirements({ lines, title, empty = 'Требований нет',
                                            onCard = false }) {
  if (!lines) return null
  if (!lines.length) {
    return <div style={{ fontFamily: UI, fontSize: 12.5, color: 'var(--text-muted)' }}>{empty}</div>
  }
  return (
    <div style={{ fontFamily: UI, display: 'flex', flexDirection: 'column', gap: 7 }}>
      {title && (
        <div style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: '.04em',
                      textTransform: 'uppercase', color: 'var(--text-faint)' }}>{title}</div>
      )}
      {lines.map(ln => {
        const t = TONE[ln.state] || TONE.unknown
        return (
          <div key={ln.key} style={{ display: 'flex', gap: 9, alignItems: 'flex-start' }}>
            <span style={badge(t)}>{t.mark}</span>
            <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
              <div style={{ fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.35 }}>
                {ln.title}
                {ln.detail && (
                  <span style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-muted)',
                                 marginLeft: 7 }}>{ln.detail}</span>
                )}
                {/* Предупреждение отличаем словом, а не только цветом: цвет мимо
                    дальтоника, а «не запирает» — единственное, что человеку нужно знать
                    про жёлтую строку. */}
                {!ln.is_blocking && ln.state !== 'ok' && (
                  <span style={{ fontSize: 11, color: 'var(--text-faint)', marginLeft: 7 }}>
                    не запирает
                  </span>
                )}
              </div>
              {/* Имена мешающих у веерных проверок: «не согласовано» без ответа «у кого»
                  отправляет человека искать вручную. */}
              {!!(ln.blockers || []).length && (
                <div style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>
                  {ln.blockers.join(', ')}
                </div>
              )}
              {ln.state === 'not_yet' && ln.hint && (
                <div style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>{ln.hint}</div>
              )}
              {ln.state !== 'ok' && <Where line={ln} onCard={onCard} />}
            </div>
          </div>
        )
      })}
    </div>
  )
}
