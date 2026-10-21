/**
 * Статусы мастер-сделки (19.10.2026) — цвет и порядок одни для реестра «Финансы → Мастер-сделки» и шапки пакета.
 * Сами статусы и правила переходов живут на сервере (`backend/app/master_deal/status.py`); здесь — только вид.
 */
// [подложка, рамка, текст, маркер] — как в хендоффе «мастер и шапка» (19.10.2026)
import { MONO } from '@/components/salesTableKit'

export const MASTER_TONE = {
  'черновик': ['var(--accent-tint)', 'var(--accent-border)', 'var(--accent-fg)', 'var(--accent)'],      // §6: сборка и согласование — синие
  'согласование': ['var(--accent-tint)', 'var(--accent-border)', 'var(--accent-fg)', 'var(--accent)'],
  'ждём 1С': ['var(--violet-tint)', 'var(--violet-border)', 'var(--violet-fg)', 'var(--violet-fg)'],
  'выставление': ['var(--warning-tint)', 'var(--warning-border)', 'var(--warning-fg)', 'var(--warning)'],
  'ждём оплату': ['var(--warning-tint)', 'var(--warning-border)', 'var(--warning-fg)', 'var(--warning)'],
  'ждём сканы': ['var(--warning-tint)', 'var(--warning-border)', 'var(--warning-fg)', 'var(--warning)'],
  'архив': ['var(--income-tint)', 'var(--income-border)', 'var(--income-fg)', 'var(--income)'],
}
// Режим суммы ДС на итоговой сверке — одна подпись для карточки пакета и блока сверки (было объявлено дважды)
export const CLOSE_MODE = { fact: 'по факту', plan: 'под МП', manual: 'вручную' }
export const capFirst = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s)

export const statusDot = (s) => (MASTER_TONE[s] || MASTER_TONE['черновик'])[3]

export function MasterStatusPill({ status, label, height = 26 }) {
  const [bg, bd, fg, dot] = MASTER_TONE[status] || MASTER_TONE['черновик']
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height, padding: '0 10px', background: bg, border: `1px solid ${bd}`,
      borderRadius: 8, fontSize: 11.5, fontWeight: 700, color: fg, whiteSpace: 'nowrap', maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', boxSizing: 'border-box' }}>
      <span aria-hidden style={{ width: 6, height: 6, borderRadius: 2, background: dot, flex: '0 0 6px' }} />{label || status}
    </span>
  )
}

export const TODO_DOT = { info: 'var(--accent)', warn: 'var(--warning)', bad: 'var(--danger)' }

/** «Что нужно сейчас» в строку (шапка пакета): квадратная точка, действие жирным, «· очередь» капсом. Считает сервер. */
export function MasterTodo({ todo }) {
  if (!todo) return <span style={{ color: 'var(--text-faint)' }}>—</span>
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 12.5, whiteSpace: 'nowrap' }}>
      <span aria-hidden style={{ width: 7, height: 7, borderRadius: 2, background: TODO_DOT[todo.tone] || TODO_DOT.info }} />
      <b style={{ fontWeight: 700, color: todo.tone === 'bad' ? 'var(--danger-fg)' : 'var(--text-primary)' }}>{todo.text}</b>
      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>· {todo.who}</span>
    </span>
  )
}

/** Цвет услуги — квадрат-маркер в ДС, расхлопе реестра и карточке (хендофф §5). */
export const SVC_DOT = { 'еФарм': 'var(--accent)', 'Приоритезация': 'var(--violet-fg)', 'Клик-аут': 'var(--traffic)', 'eFMCG': 'var(--income)', 'Доп. размещение': 'var(--warning)' }
