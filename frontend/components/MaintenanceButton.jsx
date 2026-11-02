/**
 * Кнопка техобслуживания на экране «Статус».
 *
 * Что закрыть — выбор при объявлении (владелец 02.11.2026): портал и кабинеты паблишеров, обе галочки отмечены.
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
  const [pick, setPick] = useState(null)       // { portal, cabinet } — открыт выбор перед объявлением

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
    if (!window.confirm(question)) return false
    setBusy(true)
    try { setSt((await fn()).data); return true } catch (e) {
      window.alert(e.response?.data?.detail || 'Не получилось')
      return false
    } finally { setBusy(false) }
  }

  if (!st) return null
  const mins = Math.max(1, Math.ceil((st.seconds_left || 0) / 60))

  if (st.mode === 'off' && !pick) {
    return (
      <button style={btnSm(false)} disabled={busy} onClick={() => setPick({ portal: true, cabinet: true })}>
        Техобслуживание
      </button>
    )
  }

  if (st.mode === 'off') {
    const what = [pick.portal && 'портала', pick.cabinet && 'кабинетов паблишеров'].filter(Boolean).join(' и ')
    const announce = () => call(() => api.post('/maintenance', pick, auth()),
      `Объявить техобслуживание ${what}?

Через 10 минут ` +
      (pick.portal ? 'вход и сохранение в портале закроются для всех, кроме администратора. ' : '') +
      (pick.cabinet ? 'Кабинеты паблишеров закроются целиком, включая вход. ' : '') +
      'До начала все увидят полосу с обратным отсчётом.').then(ok => { if (ok) setPick(null) })
    const box = (key, label) => (
      <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, cursor: 'pointer' }}>
        <input type="checkbox" checked={pick[key]} onChange={e => setPick({ ...pick, [key]: e.target.checked })} />
        {label}
      </label>
    )
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        {box('portal', 'Портал')}
        {box('cabinet', 'Кабинеты паблишеров')}
        <button style={btnSm(true)} disabled={busy || !(pick.portal || pick.cabinet)} onClick={announce}>
          Объявить через 10 мин
        </button>
        <button style={btnSm(false)} disabled={busy} onClick={() => setPick(null)}>Отмена</button>
      </span>
    )
  }

  const closed = [st.portal && 'портал', st.cabinet && 'кабинеты'].filter(Boolean).join(' + ')
  return (
    <button style={{ ...btnSm(true), background: 'var(--warning-tint)',
      borderColor: 'var(--warning)', color: 'var(--warning-text)' }} disabled={busy}
      onClick={() => call(() => api.delete('/maintenance', auth()),
        st.mode === 'active'
          ? 'Завершить техобслуживание и вернуть людей в систему?'
          : 'Отменить объявленное обслуживание?')}>
      {st.mode === 'active' ? `Идёт обслуживание (${closed}) — завершить`
        : `Обслуживание (${closed}) через ${mins} мин — отменить`}
    </button>
  )
}
