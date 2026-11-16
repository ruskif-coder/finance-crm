// Кнопка-действие с ожиданием (16.11.2026): пока `run()` не завершился, вместо подписи — крутилка кита и «Собираю…»,
// повторное нажатие игнорируется. Для скачиваний, которые сервер собирает секунды (МП PDF/XLS, отчёт по РК).
// Вид кнопки — от экрана (`style`), здесь только состояние занятости.
import { useState } from 'react'
import { Cube } from '@/components/LogoLoader'

export default function BusyAct({ run, label, title, style, as: Tag = 'span' }) {
  const [busy, setBusy] = useState(false)
  const go = async (e) => {
    e?.stopPropagation?.()
    if (busy) return
    setBusy(true)
    try { await run() } finally { setBusy(false) }
  }
  return (
    <Tag onClick={go} aria-busy={busy} title={busy ? 'Собираю файл…' : title}
      {...(Tag === 'button' ? { type: 'button' } : {})}
      style={{ ...style, gap: 5, cursor: busy ? 'wait' : 'pointer' }}>
      {busy ? <><Cube variant="spinner" size={12} />Собираю…</> : label}
    </Tag>
  )
}
