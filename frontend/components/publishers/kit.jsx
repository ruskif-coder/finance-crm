import { MONO, UI } from '@/components/salesTableKit'
import { grp } from '@/lib/salesFormat'

/**
 * Общие детали экранов паблишеров: тона статусов, метки, иконки мессенджеров,
 * пересчёт времени площадки и форматы чисел.
 *
 * Появился после ревью: одни и те же тона и иконки лежали копиями в реестре, сводке и
 * карточке. Правка цвета в одном месте оставляла два других со старым — одна и та же
 * поверхность выглядела по-разному на соседних экранах.
 */

// Тон метки поверхности берётся из статуса интеграции, а не задаётся руками.
// Три значения: фон, текст, рамка.
export const INTEG_TONE = {
  'ПОДКЛЮЧЕНО':   ['var(--accent-tint)', 'var(--accent)', 'var(--accent-border)'],
  'СОГЛАСОВАНИЕ': ['var(--warning-tint)', 'var(--warning-text)', '#F2DFC0'],
  'ПОДГОТОВКА':   ['var(--warning-tint)', 'var(--warning-text)', '#F2DFC0'],
  'ПРАВКИ':       ['var(--danger-tint)', 'var(--danger)', '#F0C9CA'],
  'ОТЛОЖЕНО':     ['var(--bg-subtle)', 'var(--text-faint)', 'var(--border-card)'],
  'НЕТ':          ['var(--bg-subtle)', 'var(--text-faint)', 'var(--border-card)'],
}
// В строке реестра подключённая поверхность заливается целиком — её видно с расстояния.
export const INTEG_TONE_SOLID = { ...INTEG_TONE, 'ПОДКЛЮЧЕНО': ['var(--accent)', '#fff', 'var(--accent)'] }

export const STATUS_TONE = {
  'СОТРУДНИЧАЕМ': ['var(--income-tint)', 'var(--income)'],
  'ПЕРЕГОВОРЫ':   ['var(--accent-tint)', 'var(--accent)'],
  'НА ПАУЗЕ':     ['var(--warning-tint)', 'var(--warning-text)'],
  'ОТКАЗ':        ['var(--danger-tint)', 'var(--danger)'],
  'АРХИВ':        ['var(--bg-subtle)', 'var(--text-muted)'],
}
export const NEUTRAL_TONE = ['var(--bg-subtle)', 'var(--text-secondary)']
export const EMPTY_TONE = ['transparent', 'var(--text-faint)']

// Порядок переключения статуса кликом по пину — тот же, что список значений.
export const SURFACE_CYCLE = ['НЕТ', 'ОТЛОЖЕНО', 'ПОДГОТОВКА', 'СОГЛАСОВАНИЕ', 'ПРАВКИ', 'ПОДКЛЮЧЕНО']
export const nextStatus = (current) =>
  SURFACE_CYCLE[(SURFACE_CYCLE.indexOf(current) + 1) % SURFACE_CYCLE.length]

export const SURFACE_LABEL = { web: 'WEB', app: 'APP' }
export const PLATFORM_LABEL = { android: 'Android', ios: 'iOS' }

// Четыре строки таблицы трафика; у запросов рекламного кода глубины не существует.
export const TRAFFIC_ROWS = [
  ['web', 'Трафик WEB', true],
  ['app_android', 'APP · Android', true],
  ['app_ios', 'APP · iOS', true],
  ['ad_requests', 'Запросы рекл. кода', false],
]

// Смещение хранится от МСК: «МСК+4» читается быстрее, чем UTC+7.
export const tzLabel = (off) => (!off ? 'МСК' : `МСК${off > 0 ? '+' : '−'}${Math.abs(off)}`)
export const localTime = (off) => {
  const now = new Date()
  const msk = new Date(now.getTime() + (now.getTimezoneOffset() + 180) * 60000)
  const t = new Date(msk.getTime() + (off || 0) * 3600000)
  return `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`
}

// Деньги форматирует ОБЩИЙ `grp` из lib/salesFormat: своя копия `Intl.NumberFormat`
// была четырнадцатой в проекте, а копии расходятся в округлении и в том, что
// печатают для нуля. Имя оставлено — на него завязано два десятка мест карточки.
export const fmtMoney = grp
export const fmtCompact = (v) => {
  if (v == null) return '—'
  if (v >= 1e6) return (v / 1e6).toFixed(2).replace('.', ',')
  if (v >= 1e3) return Math.round(v / 1e3).toString()
  return Math.round(v).toString()
}
export const fmtUnit = (v) => (v == null ? '' : v >= 1e6 ? 'млн' : v >= 1e3 ? 'тыс' : '')

// Метка-пин: статус, сеть, вид, поверхность. dim — «есть, но не работаем».
export const Pin = ({ text, tone, title, onClick, dim, dot }) => (
  <span title={title} onClick={onClick}
    style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: dot ? '3px 10px' : '2px 8px',
      borderRadius: 8, background: tone[0], color: tone[1],
      border: `1px solid ${tone[2] || 'transparent'}`,
      fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '.06em',
      textTransform: 'uppercase', whiteSpace: 'nowrap', opacity: dim ? .5 : 1,
      cursor: onClick ? 'pointer' : 'default' }}>
    {dot && <span style={{ width: 6, height: 6, borderRadius: 2, background: tone[1] }} />}
    {text}
  </span>
)

export const TgIcon = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
    <path d="M21.8 4.2 18.9 19c-.2 1-.8 1.2-1.6.75l-4.5-3.3-2.2 2.1c-.24.24-.44.44-.9.44l.32-4.6L18.4 6.9c.36-.32-.08-.5-.56-.18L7.5 13.3l-4.5-1.4c-.98-.3-1-.98.2-1.45l17.6-6.8c.8-.3 1.5.2 1 1.55z" />
  </svg>
)
export const MaxIcon = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
    strokeLinecap="round" strokeLinejoin="round"><path d="M4 19V6l8 8 8-8v13" /></svg>
)

// Кнопка мессенджера: есть ссылка — контрастная, нет — бледная заглушка.
export const ChatBtn = ({ href, kind, title, size = 26 }) => {
  const icon = kind === 'max' ? <MaxIcon size={size - 12} /> : <TgIcon size={size - 12} />
  const base = { display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: size, height: size, borderRadius: 8, flex: '0 0 auto' }
  return href
    ? <a href={href} target="_blank" rel="noreferrer" title={title} onClick={e => e.stopPropagation()}
        style={{ ...base, border: '1px solid var(--accent-border)', background: 'var(--accent-tint)',
          color: 'var(--accent)', textDecoration: 'none' }}>{icon}</a>
    : <span title={`${title} — не заведён`}
        style={{ ...base, border: '1px solid var(--border-card)', background: 'transparent',
          color: 'var(--text-faint)', opacity: .5 }}>{icon}</span>
}

// Телеграм пишут и ником, и ссылкой — приводим к адресу.
export const tgHref = (value) => {
  if (!value) return null
  return value.startsWith('http') ? value : `https://t.me/${value.replace('@', '')}`
}

/**
 * Плашка услуги. parts — [{label, working}]: поверхность, с которой мы не работаем,
 * показывается перечёркнутой. Услуга там отмечена как поддерживаемая площадкой, но
 * продавать её нельзя, и плашка не должна обещать обратное.
 */
export const ServiceChip = ({ name, parts, sharesData, isTarget, size = 12 }) => {
  const live = parts.some(x => x.working)
  return (
    <span title={`${name} — ${parts.map(x => x.label + (x.working ? '' : ' (не работаем)')).join(', ')}` +
      (isTarget ? (sharesData ? ' · делится данными' : ' · данными не делится') : '')}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 9px', borderRadius: 8,
        fontSize: size, fontWeight: 700, whiteSpace: 'nowrap',
        background: live ? 'var(--accent-tint)' : 'var(--bg-subtle)',
        color: live ? 'var(--accent)' : 'var(--text-faint)',
        border: `1px solid ${live ? 'var(--accent-border)' : 'var(--border-card)'}` }}>
      {name}
      <span style={{ fontFamily: MONO, fontSize: size - 3.5, letterSpacing: '.06em',
        display: 'inline-flex', gap: 4 }}>
        {parts.map(x => (
          <span key={x.label} style={{ opacity: x.working ? .75 : .4,
            textDecoration: x.working ? 'none' : 'line-through' }}>{x.label}</span>
        ))}
      </span>
      {isTarget && (
        <span style={{ padding: '1px 5px', borderRadius: 5, fontFamily: MONO, fontSize: size - 4,
          fontWeight: 700, background: sharesData ? 'var(--income-tint)' : 'var(--warning-tint)',
          color: sharesData ? 'var(--income)' : 'var(--warning-text)' }}>
          {sharesData ? 'DATA' : 'NO DATA'}
        </span>
      )}
    </span>
  )
}

export { MONO, UI }
