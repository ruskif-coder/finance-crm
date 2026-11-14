/**
 * Состояние и действия «Итоговой сверки» — одни для блока карточки (`ClosingBlock`) и компактного блока расхлопа «Моих сделок»
 * (`ClosingCompact`, хендофф design_handoff_final_recon, 14.11.2026). Расчёт — на сервере (`/final-recon/deal/{id}/closing`).
 */
import { useCallback, useEffect, useState } from 'react'
import api, { auth } from '@/lib/api'
import { detailText } from '@/lib/loadError'

export default function useClosing(dealId, reloadKey) {
  const [s, setS] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const url = `/final-recon/deal/${dealId}`

  const load = useCallback(() => {
    api.get(`${url}/closing`, auth())
      .then(r => { setS(r.data); setErr('') })
      .catch(e => setErr(detailText(e, 'Сверка не посчиталась')))
  }, [url])
  useEffect(() => { load() }, [load, reloadKey])

  const call = async (fn) => {
    setBusy(true); setErr('')
    try { await fn(); return true } catch (e) { setErr(detailText(e, 'Не удалось сохранить')); return false } finally { setBusy(false) }
  }
  const put = (path, body) => call(async () => { setS((await api.put(`${url}/${path}`, body, auth())).data) })

  return {
    s, err, busy, load,
    setMode: (mode, manualNet, vol, reason) => put('closing', { mode, manual_net: manualNet ?? null, manual_volume: vol ?? null, reason: reason || null }),
    saveSk: (mode, percent) => call(async () => {
      await api.put(`${url}/sk`, { mode, percent }, auth())
      setS((await api.get(`${url}/closing`, auth())).data)
    }),
    saveCost: (cost) => put('cost', { cost_net: cost }),
    saveFact: (rows, note) => put('fact', { rows, note: note || null }),
    confirm: (on) => put('closing/confirm', { on }),
    closeNoDocs: () => call(async () => {
      if (!window.confirm('Закрыть без документов? Бонусное размещение: сверка замораживается, сделка уходит в «Архив успешных сделок». ДС и закрывающих не будет.')) return
      setS((await api.post(`${url}/close-no-docs`, {}, auth())).data)
    }),
  }
}
