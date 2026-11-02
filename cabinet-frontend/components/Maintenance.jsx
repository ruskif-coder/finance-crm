/**
 * Техобслуживание кабинета (владелец 02.11.2026): полоса с обратным отсчётом и заглушка на весь экран.
 *
 * Режим объявляют у нас (экран «Статус» ядра) с галочкой «Кабинеты паблишеров»; сервер кабинета отдаёт его ручкой
 * `/api/maintenance` БЕЗ входа — поэтому заглушка встаёт и на странице входа. Опрос, как в ядре: раз в минуту, а когда
 * обслуживание объявлено — раз в пятнадцать секунд. Полоса не закрывается крестиком: это обратный отсчёт, не новость.
 */
import { useCallback, useEffect, useState } from 'react'
import api from '../lib/http'
import { C, UI } from '../lib/ui'

const SLOW = 60000
const FAST = 15000

export function useMaintenance() {
  const [st, setSt] = useState(null)
  const load = useCallback(async () => {
    try {
      setSt((await api.get('/maintenance')).data)
    } catch (e) {
      if (e.response?.status === 503 && e.response?.data?.maintenance) {
        setSt({ mode: 'active', title: e.response.data.detail, note: e.response.data.note })
      }
    }
  }, [])
  useEffect(() => {
    load()
    const t = setInterval(load, st?.mode === 'announced' ? FAST : SLOW)
    return () => clearInterval(t)
  }, [load, st?.mode])
  return st
}

export function MaintenanceBar({ state }) {
  if (!state || state.mode !== 'announced') return null
  const mins = Math.max(1, Math.ceil((state.seconds_left || 0) / 60))
  return (
    <div style={{
      background: C.warningTint, borderBottom: `1px solid ${C.warningBorder}`, color: C.warningFg,
      padding: '9px 22px', fontSize: 13.5, fontWeight: 700, fontFamily: UI,
      display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
    }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: C.warning }} />
      <span>Кабинет прервётся на техобслуживание через {mins} мин.</span>
      <span style={{ fontWeight: 500 }}>{state.bar}</span>
    </div>
  )
}

export function MaintenanceStub({ state }) {
  if (!state || state.mode !== 'active') return null
  return (
    <div data-overlay="" style={{
      position: 'fixed', inset: 0, zIndex: 10000, background: C.canvas, fontFamily: UI,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, textAlign: 'center',
    }}>
      <div style={{ maxWidth: 460 }}>
        <div style={{ fontSize: 46, lineHeight: 1, marginBottom: 14 }}>🛠</div>
        <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 8, color: C.text }}>
          {state.title || 'Кабинет на техобслуживании'}
        </div>
        <div style={{ fontSize: 14, lineHeight: 1.6, color: C.secondary }}>{state.note}</div>
        <div style={{ marginTop: 16, fontSize: 11.5, color: C.faint }}>
          страница обновится сама, как только обслуживание закончится
        </div>
      </div>
    </div>
  )
}
