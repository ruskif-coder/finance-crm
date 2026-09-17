/**
 * Техобслуживание на стороне экрана: полоса предупреждения и заглушка.
 *
 * ОПРОС, А НЕ ПОДПИСКА. Websocket'ов в системе нет, и заводить их ради одного сообщения
 * незачем: обычный опрос идёт раз в минуту, а когда обслуживание ОБЪЯВЛЕНО — раз в
 * пятнадцать секунд. Десяти минут предупреждения хватает с запасом даже при минутном
 * шаге; обещать «мгновенно всем» было бы неправдой, а неправда в таком сообщении стоит
 * потерянной работы.
 *
 * Полоса не закрывается крестиком намеренно: это не новость, а обратный отсчёт.
 */
import { useCallback, useEffect, useState } from 'react'
import api, { auth } from '../lib/http'

const SLOW = 60000        // обычный шаг опроса
const FAST = 15000        // когда обслуживание объявлено — чаще

export function useMaintenance() {
  const [st, setSt] = useState(null)

  const load = useCallback(async () => {
    try {
      const r = await api.get('/maintenance', auth())
      setSt(r.data)
    } catch (e) {
      // 503 от прослойки означает, что обслуживание УЖЕ идёт: сама ручка открыта, но
      // сеть могла не дойти. Молчим — заглушку покажет следующий удачный ответ.
      if (e.response?.status === 503 && e.response?.data?.maintenance) {
        setSt({ mode: 'active', stub_title: e.response.data.detail,
          stub_note: e.response.data.note })
      }
    }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    if (!localStorage.getItem('token')) return undefined
    load()
    const t = setInterval(load, st?.mode === 'announced' ? FAST : SLOW)
    return () => clearInterval(t)
  }, [load, st?.mode])

  return st
}

/** Полоса «через N минут». Живёт в шапке, поверх всего. */
export function MaintenanceBar({ state }) {
  if (!state || state.mode !== 'announced') return null
  const mins = Math.max(1, Math.ceil((state.seconds_left || 0) / 60))
  return (
    <div style={{
      background: 'var(--warning-bg)', borderBottom: '1px solid var(--warning-border)',
      color: 'var(--warning-text)', padding: '9px 22px', fontSize: 13.5, fontWeight: 600,
      display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
    }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--warning)' }} />
      <span>Портал прервётся на техобслуживание через {mins} мин.</span>
      <span style={{ fontWeight: 400 }}>Просим сохранить вашу работу.</span>
    </div>
  )
}

/** Заглушка на весь экран. Показывается ПОСЛЕ входа, а сам вход остаётся рабочим:
 *  иначе админ не сможет войти и снять режим. */
export function MaintenanceStub({ state }) {
  if (!state || state.mode !== 'active') return null
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 900, background: 'var(--bg-canvas)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
      textAlign: 'center',
    }}>
      <div style={{ maxWidth: 460 }}>
        <div style={{ fontSize: 46, lineHeight: 1, marginBottom: 14 }}>🛠</div>
        <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 8 }}>
          {state.stub_title || 'Мы на техобслуживании'}
        </div>
        <div style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
          {state.stub_note}
        </div>
        {/* Страница сама себя перепроверяет: человеку не надо гадать, когда пробовать
            снова, и не надо нажимать «обновить» вслепую. */}
        <div style={{ marginTop: 16, fontSize: 11.5, color: 'var(--text-faint)' }}>
          страница обновится сама, как только обслуживание закончится
        </div>
      </div>
    </div>
  )
}
