/**
 * Сворачиваемая секция карточки сделки.
 *
 * Свёрнутая секция обязана нести ДАННЫЕ, а не подпись. Одной строки в заголовке мало:
 * карточка выглядит пустой, и разворачивать приходится всё подряд — сворачивание тогда
 * теряет смысл. Поэтому свёрнутый вид показывает короткий ряд ключевых значений (`facts`),
 * а строка `summary` справа отвечает на главный вопрос: сошлось или нужна работа.
 *
 * Содержимое передаётся ФУНКЦИЕЙ, а не элементом: пока секция свёрнута, оно не
 * создаётся и не ходит в бэкенд. Тот же приём уже применён на этой карточке для брифа.
 *
 * Состояние запоминается на пару «секция × сделка» — иначе человек разворачивает
 * нужное заново при каждом открытии карточки.
 */
import { useEffect, useState } from 'react'
import { UI, MONO } from '../salesTableKit'

const KEY = 'deal_sections_open'

const Chevron = ({ open }) => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
    style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .15s',
      flex: '0 0 auto' }}>
    <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

/* Свёрнутый вид бывает двух родов, и разница не косметическая.
   Цифры (медиаплан: суммы, показы, период) — колонки: у них нет состояния, и рамка
   вокруг каждой только добавила бы шума.
   Состояния (обвязка ОРД: сошлось / ждёт / закрыто) — плашки с маркером: тон и
   значок читаются раньше текста, и «выбрать из 7» видно, не вчитываясь. */
const FACT_TONE = {
  ok:   { bg: 'var(--income-tint)',  bd: 'var(--income-border)',  fg: 'var(--income)',       mark: '✓' },
  warn: { bg: 'var(--warning-tint)', bd: 'var(--warning-border)', fg: 'var(--warning-text)', mark: '!' },
  off:  { bg: 'var(--bg-subtle)',    bd: 'var(--border-card)',    fg: 'var(--text-muted)',   mark: '·' },
}

function FactChip({ label, value, tone }) {
  const t = FACT_TONE[tone] || FACT_TONE.off
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 9, padding: '8px 12px',
      background: t.bg, border: `1px solid ${t.bd}`, borderRadius: 11, minWidth: 0 }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 20, height: 20, flex: '0 0 20px', borderRadius: 6, background: 'var(--bg-card)',
        color: t.fg, fontSize: 11, fontWeight: 700 }}>{t.mark}</span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
        <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '.06em',
          textTransform: 'uppercase', color: 'var(--text-muted)' }}>{label}</span>
        <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: t.fg,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{value}</span>
      </span>
    </span>
  )
}

export default function Section({ id, dealId, title, subtitle, summary, tone, facts,
                                  factsAs = 'plain', right, collapsed, defaultOpen = false,
                                  children }) {
  const [open, setOpen] = useState(defaultOpen)
  const [ready, setReady] = useState(false)

  // localStorage читается только после монтирования: на сервере его не существует.
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) || '{}')
      const v = saved[`${dealId}:${id}`]
      if (typeof v === 'boolean') setOpen(v)
    } catch { /* повреждённое значение не должно ронять карточку */ }
    setReady(true)
  }, [dealId, id])

  const toggle = () => {
    const next = !open
    setOpen(next)
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) || '{}')
      saved[`${dealId}:${id}`] = next
      localStorage.setItem(KEY, JSON.stringify(saved))
    } catch { /* приватный режим — просто не запоминаем */ }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <button type="button" onClick={toggle}
        style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'none',
          border: 0, padding: 0, cursor: 'pointer', textAlign: 'left',
          flex: 1, minWidth: 0, color: 'var(--text-muted)', fontFamily: UI }}>
        <Chevron open={open} />
        <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 700,
          letterSpacing: '0.1em', textTransform: 'uppercase' }}>{title}</span>
        {/* Подпись рядом с заголовком — «цепочка договоров и ЕРИД» в блоке ОРД. */}
        {!!subtitle && (
          <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em',
            textTransform: 'uppercase', color: 'var(--text-faint)' }}>{subtitle}</span>
        )}
        {!!summary && (
          <span style={{ marginLeft: 'auto', fontSize: 12,
            color: tone === 'warn' ? 'var(--dot-current-dz)'
              : tone === 'ok' ? 'var(--income)' : 'var(--text-faint)' }}>
            {summary}
          </span>
        )}
      </button>
      {/* Узел справа от заголовка — сосед кнопки, а не её содержимое: внутри клик по
          нему сворачивал бы секцию, а абсолютным позиционированием он лёг бы поверх
          summary, который прижат к тому же правому краю. */}
      {!!right && <div style={{ flex: '0 0 auto' }}>{right}</div>}
      </div>
      {/* Свёрнутая секция несёт не подпись, а данные: заголовок с одной короткой
          строкой оставляет карточку пустой, и разворачивать приходится всё подряд.
          Раскрытая их не дублирует — там те же значения в полном виде. */}
      {/* Свой свёрнутый вид: когда строк несколько и у каждой своё состояние, ряд
          значений их не выражает — нужен список. Отдаётся УЗЛОМ, а не функцией: он
          обязан рисоваться именно в свёрнутом виде, ради него сворачивание и делают. */}
      {!!(ready && !open && collapsed) && collapsed}
      {!!(ready && !open && !collapsed && facts && facts.length) && (
        factsAs === 'chips' ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, paddingLeft: 21 }}>
            {facts.map((f, i) => <FactChip key={i} {...f} />)}
          </div>
        ) : (
          /* Цифры: лейбл MONO капсом, значение MONO крупно. Крупно потому, что ради
             этих значений блок и не разворачивают — они здесь конечная точка, а не
             намёк на содержимое. Цвет задаёт вызывающий: он один знает, что «с НДС»
             акцентное, а прогноз показов — доходный. */
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px 30px', paddingLeft: 21 }}>
            {facts.map((f, i) => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
                <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em',
                  textTransform: 'uppercase', color: 'var(--text-muted)' }}>{f.label}</span>
                <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 8 }}>
                  <span style={{ fontFamily: MONO, fontSize: 17, fontWeight: 700,
                    letterSpacing: '-0.02em', whiteSpace: 'nowrap',
                    color: f.color || (f.tone === 'warn' ? 'var(--warning-text)'
                      : f.tone === 'ok' ? 'var(--income)'
                        : f.tone === 'off' ? 'var(--text-faint)' : 'var(--text-primary)') }}>
                    {f.value}
                  </span>
                  {!!f.pill && (
                    <span style={{ background: 'var(--warning-tint)', color: 'var(--warning-text)',
                      border: '1px solid var(--warning-border)', borderRadius: 6, padding: '1px 7px',
                      fontSize: 10, fontWeight: 700, whiteSpace: 'nowrap' }}>{f.pill}</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        )
      )}
      {/* Содержимое создаётся только когда секция открыта — иначе свёрнутая секция
          сходила бы в бэкенд за данными, которых никто не видит. */}
      {!!(ready && open) && children()}
    </div>
  )
}
