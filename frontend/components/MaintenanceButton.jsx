/**
 * Кнопка техобслуживания на экране «Статус».
 *
 * Два состояния и два разных вопроса в подтверждении: «объявить» спрашивает про людей,
 * «снять» — про готовность системы. Одно подтверждение на оба действия читалось бы
 * как формальность.
 */
import { useCallback, useEffect, useState } from 'react'
import api, { auth } from '../lib/http'
import { btnSm } from './salesTableKit'

export default function MaintenanceButton() {
  const [st, setSt] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => api.get('/maintenance', auth())
    .then(r => setSt(r.data)).catch(() => {}), [])

  useEffect(() => { load() }, [load])
  // Пока режим объявлен, кнопка сама показывает обратный отсчёт — иначе непонятно,
  // сколько осталось, и приходится считать в уме от времени объявления.
  useEffect(() => {
    if (st?.mode !== 'announced') return undefined
    const t = setInterval(load, 15000)
    return () => clearInterval(t)
  }, [st?.mode, load])

  const call = async (fn, question) => {
    if (!window.confirm(question)) return
    setBusy(true)
    try { setSt((await fn()).data) } catch (e) {
      window.alert(e.response?.data?.detail || 'Не получилось')
    } finally { setBusy(false) }
  }

  if (!st) return null
  const mins = Math.max(1, Math.ceil((st.seconds_left || 0) / 60))

  if (st.mode === 'off') {
    return (
      <button style={btnSm(false)} disabled={busy}
        onClick={() => call(() => api.post('/maintenance', {}, auth()),
          'Объявить техобслуживание?\n\nЧерез 10 минут вход и сохранение закроются ' +
          'для всех, кроме администратора. Все сейчас работающие увидят полосу ' +
          'с обратным отсчётом.')}>
        Техобслуживание
      </button>
    )
  }

  return (
    <button style={{ ...btnSm(true), background: 'var(--warning-tint)',
      borderColor: 'var(--warning)', color: 'var(--warning-text)' }} disabled={busy}
      onClick={() => call(() => api.delete('/maintenance', auth()),
        st.mode === 'active'
          ? 'Завершить техобслуживание и вернуть людей в систему?'
          : 'Отменить объявленное обслуживание?')}>
      {st.mode === 'active' ? 'Идёт обслуживание — завершить' : `Обслуживание через ${mins} мин — отменить`}
    </button>
  )
}
