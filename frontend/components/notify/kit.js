/**
 * Общий набор модуля «Уведомления и письма».
 *
 * Модуль один (владелец 16.09.2026): правила рассылки, журнал отправок, шаблоны писем и
 * настройки отправителя — части одного целого, и выглядеть они обязаны одинаково. До
 * сведения у каждого экрана были свои плашки, свои слова для статуса и свои цвета тона:
 * «доставлено» на одном экране было зелёным, на другом серым, и это читалось как разные
 * состояния.
 *
 * ЗДЕСЬ ТОЛЬКО ТО, ЧТО НУЖНО ДВУМ И БОЛЕЕ ЧАСТЯМ. Стиль, живущий в одном месте,
 * остаётся там же: вынос «про запас» превращает набор в свалку, из которой перестают
 * брать. Базовые кирпичи (card, inp, th, Modal) берутся из общего кита проекта
 * `components/salesTableKit.js` и здесь не переопределяются.
 */
import { UI } from '../salesTableKit'

export const msg = e => e?.response?.data?.detail || e?.message || 'Ошибка'

/** Тон события: четыре слова, одни и те же в реестре, в панели, в письме и здесь. */
export const TONE_UI = {
  bad: ['var(--danger-tint)', 'var(--danger-fg)', 'срочно'],
  warn: ['var(--warning-tint)', 'var(--warning-fg)', 'нужно решение'],
  ok: ['var(--income-tint)', 'var(--income-fg)', 'готово'],
  info: ['var(--accent-tint)', 'var(--accent-fg)', 'к сведению'],
}

/** Исход доставки. «Ждёт канала» — не ошибка: канал не настроен или письмо ждёт часа,
 *  и красным оно быть не должно. */
export const STATUS = {
  sent: ['var(--income-tint)', 'var(--income-fg)'],
  queued: ['var(--bg-subtle)', 'var(--text-muted)'],
  suppressed: ['var(--bg-subtle)', 'var(--text-muted)'],
  failed: ['var(--danger-tint)', 'var(--danger-fg)'],
}

export const CH_LABELS = { app: 'В приложении', tg: 'Telegram', mail: 'Почта', digest: 'Дайджест' }

export const topTab = on => ({
  padding: '8px 14px', borderRadius: 10, border: 'none', fontFamily: UI,
  cursor: on ? 'default' : 'pointer', fontWeight: on ? 700 : 600, fontSize: 13,
  background: on ? 'var(--accent-tint)' : 'var(--bg-card)',
  color: on ? 'var(--accent)' : 'var(--text-secondary)',
})

export const segBtn = on => ({
  border: 0, background: on ? 'var(--bg-card)' : 'transparent', padding: '7px 14px',
  borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: on ? 700 : 600, fontFamily: UI,
  color: on ? 'var(--text-primary)' : 'var(--text-secondary)',
})

export const linkBtn = {
  background: 'none', border: 0, padding: 0, fontSize: 12,
  color: 'var(--accent)', cursor: 'pointer', fontFamily: UI,
}

export const hint = { fontSize: 12, color: 'var(--text-muted)' }

export const td = {
  padding: '11px 10px', borderBottom: '1px solid var(--border-row)', verticalAlign: 'top',
}

export const badge = (bg, bd, fg) => ({
  fontSize: 10, borderRadius: 5, padding: '2px 6px', background: bg,
  border: `1px solid ${bd}`, color: fg, whiteSpace: 'nowrap',
})

/** Плашка тона или исхода: одна функция на оба словаря — рисуются они одинаково. */
export const Chip = ({ pair, text, style }) => {
  const [bg, fg] = pair || ['var(--bg-subtle)', 'var(--text-muted)']
  return (
    <span style={{ padding: '2px 8px', borderRadius: 7, background: bg, color: fg,
      fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap', ...style }}>{text}</span>
  )
}

/** Галочка правила: пунктир — унаследовано от профиля, сплошная — переопределено. */
export const checkbox = (on, inherited) => ({
  display: 'inline-block', width: 18, height: 18, borderRadius: 6, cursor: 'pointer',
  verticalAlign: 'middle',
  border: `1.5px ${inherited ? 'dashed' : 'solid'} ${on ? (inherited ? '#B9C5F2' : 'var(--accent)') : '#C9D1E4'}`,
  background: on ? (inherited ? '#DDE3FA' : 'var(--accent)') : 'var(--bg-card)',
  backgroundImage: on ? `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'><path d='M2 6.5l2.5 2.5L10 3.5' fill='none' stroke='${inherited ? '%237E90DF' : 'white'}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/></svg>")` : 'none',
  backgroundSize: '13px 13px', backgroundPosition: 'center', backgroundRepeat: 'no-repeat',
})

/** «1 письмо · 2 письма · 5 писем». Одиннадцать — ловушка: по последней цифре вышло бы
 *  «письмо». Та же функция, что на сервере (`app/mail/editor.py`), и по той же причине:
 *  тема письма с «2 событий» читается как машинная рассылка. */
export const plural = (n, one, few, many) => {
  const a = Math.abs(n)
  if (a % 100 >= 11 && a % 100 <= 14) return many
  const last = a % 10
  return last === 1 ? one : (last >= 2 && last <= 4 ? few : many)
}
