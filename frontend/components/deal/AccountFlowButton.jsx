/**
 * Кнопка контура аккаунта (владелец 14.10.2026): у сделок услуг из воронки «контур аккаунта» запуск и завершение ведёт аккаунт —
 * «Запустить» («Готовятся к старту» → «В размещении») и «Завершить» («В размещении» → «Итоговая сверка»). Трафик такие сделки не ведёт.
 * Сервер решает, какая кнопка сейчас доступна (`/final-recon/deal/{id}/flow`), и переводит тем же путём, что диалог движения.
 */
import { useCallback, useEffect, useState } from 'react'
import api, { auth } from '@/lib/api'
import { UI } from '@/components/salesTableKit'

const LABEL = { launch: 'Запустить', finish: 'Завершить' }
const ASK = {
  launch: 'Запустить размещение? Сделка перейдёт в «В размещении».',
  finish: 'Завершить размещение? Сделка перейдёт в «Итоговую сверку» — там вносится факт.',
}

/** Главная кнопка сделки — одна: действие следующей стадии (владелец 14.10.2026). Через стадию, назад, «сорвалась» — мастер из реестра. */
const GREEN = { height: 38, border: 'none', background: 'var(--income)', color: 'var(--on-accent)', fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap', fontFamily: UI }

export default function AccountFlowButton({ dealId, stageId, onDone, nextLabel, nextTitle, onNext, onLost, lostLabel }) {
  const [action, setAction] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const load = useCallback(() => {
    api.get(`/final-recon/deal/${dealId}/flow`, auth()).then(r => setAction(r.data.action || null)).catch(e => { setAction(null); setErr(e?.response?.data?.detail || 'Не удалось узнать, доступна ли кнопка') })
  }, [dealId])
  useEffect(() => { load() }, [load, stageId])

  const run = async () => {
    if (!window.confirm(ASK[action])) return
    setBusy(true); setErr('')
    try { await api.post(`/final-recon/deal/${dealId}/${action}`, {}, auth()); if (onDone) onDone() }
    catch (e) { setErr(e?.response?.data?.detail || 'Не удалось перевести сделку') }
    finally { setBusy(false) }
  }
  // Контур аккаунта — «Запустить/Завершить» переводят сразу; иначе — действие следующей стадии через диалог; нет следующей — кнопки нет.
  const label = action ? LABEL[action] : nextLabel
  const main = action ? run : onNext
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flex: '0 0 auto' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      {!!label && (
        <button onClick={main} disabled={busy} title={action ? 'Контур аккаунта: запуск и завершение ведёт аккаунт' : nextTitle}
          style={{ ...GREEN, borderRadius: 10, padding: '0 18px', cursor: busy ? 'wait' : 'pointer' }}>
          {busy ? 'Перевожу…' : label}
        </button>
      )}
      {/* Срыв — красный квадрат с ✕ после основной кнопки; что именно («не случилась» / «сорвалась») — в подсказке (владелец 14.10.2026). */}
      {!!onLost && !!lostLabel && (
        <button onClick={onLost} title={`${lostLabel} — перевести с причиной`} aria-label={lostLabel}
          style={{ width: 38, height: 38, flex: '0 0 auto', borderRadius: 10, border: 'none', background: 'var(--danger)', color: 'var(--on-accent)',
            fontSize: 17, fontWeight: 700, lineHeight: 1, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>✕</button>
      )}
      </span>
      {!!err && <span style={{ maxWidth: 360, fontSize: 11.5, color: 'var(--danger-fg)', textAlign: 'right' }}>{err}</span>}
    </span>
  )
}
