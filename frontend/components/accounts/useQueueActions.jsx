/**
 * Кнопки строки очереди аккаунта и их диалоги — общие для «Дашборда» и «Моих сделок» (v5, 13.11.2026). Куда ведёт кнопка,
 * решил сервер (`action.do` из `queue_state`); здесь — как это сделать. Один код на оба экрана: иначе второй экран разошёлся
 * бы с первым в том, что делает та же кнопка.
 */
import { useState } from 'react'
import api, { auth } from '@/lib/api'
import MoveDealDialog from '@/components/sales/MoveDealDialog'
import { SnoozeDialog, BookingConfirm, LaunchPrepDialog } from '@/components/accounts/QueueDialogs'
import { detailText } from '@/lib/loadError'
import { useDialogs } from '@/components/dialogs'

export default function useQueueActions({ router, load, onExpand }) {
  const { confirm, alert } = useDialogs()
  const [moveDeal, setMoveDeal] = useState(null)
  const [snoozeFor, setSnoozeFor] = useState(null)
  const [prepFor, setPrepFor] = useState(null)
  const [confirmFor, setConfirmFor] = useState(null)

  const doSnooze = async (row, note, returnAt) => {
    try {
      await api.post(`/sales/deals/${row.code || row.id}/snooze`, { note, return_at: returnAt }, auth())
      setSnoozeFor(null); load()
    } catch (e) { alert(detailText(e, 'Не удалось отложить')) }
  }
  const unsnooze = async (row) => {
    try { await api.delete(`/sales/deals/${row.code || row.id}/snooze`, auth()); load() }
    catch (e) { alert(detailText(e, 'Не удалось вернуть в очередь')) }
  }

  // «Завершить» своего запуска (контур аккаунта, приоритезация) — тот же путь, что кнопка в карточке: `final_recon/launch`.
  const finish = async (row) => {
    if (!await confirm('Завершить запуск? Сделка перейдёт на «Итоговую сверку».')) return
    try { await api.post(`/final-recon/deal/${row.id}/finish`, {}, auth()); load() }
    catch (e) { alert(detailText(e, 'Не удалось завершить')) }
  }

  // Карточку сделки открываем в новой вкладке: очередь с фильтрами остаётся на месте.
  const runAction = (row, a) => {
    if (a.do === 'mp') return router.push(`/accounts/mp/new?deal=${row.id}`)
    if (a.do === 'move') return setMoveDeal(row)
    if (a.do === 'confirm') return setConfirmFor(row)
    if (a.do === 'prep') return setPrepFor(row)
    if (a.do === 'expand') return onExpand(row)
    if (a.do === 'finish') return finish(row)
    if (a.do === 'link' && a.url) {
      if (a.url.startsWith('/sales/deals/')) return window.open(a.url, '_blank', 'noopener')
      return router.push(a.url)
    }
    return null
  }

  const dialogs = (
    <>
      {moveDeal && <MoveDealDialog deal={moveDeal} toStageKey={moveDeal.__to} toLost={moveDeal.__lost}
        onClose={() => setMoveDeal(null)} onMoved={() => { setMoveDeal(null); load() }} />}
      {confirmFor && (
        <BookingConfirm row={confirmFor} onClose={() => setConfirmFor(null)}
          onPick={(target) => { setMoveDeal({ ...confirmFor, ...target }); setConfirmFor(null) }} />
      )}
      {prepFor && (
        <LaunchPrepDialog row={prepFor} onClose={() => setPrepFor(null)}
          onToLaunch={() => { setMoveDeal({ ...prepFor, __to: 'launch' }); setPrepFor(null) }} />
      )}
      {snoozeFor && <SnoozeDialog row={snoozeFor} onClose={() => setSnoozeFor(null)} onSave={doSnooze} />}
    </>
  )
  return { runAction, setSnoozeFor, unsnooze, dialogs }
}
