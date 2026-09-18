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

  return { ...(st || {}), reload: load }
}

/** Снять режим прямо из полосы. Без подтверждения: возвращение людей в работу —
 *  не разрушающее действие, а закрытый по ошибке портал стоит дороже лишнего клика. */
function LiftButton({ onLifted }) {
  const [busy, setBusy] = useState(false)
  const lift = async () => {
    setBusy(true)
    try { await api.delete('/maintenance', auth()); if (onLifted) await onLifted() }
    finally { setBusy(false) }
  }
  return (
    <button onClick={lift} disabled={busy}
      style={{ marginLeft: 'auto', padding: '5px 13px', borderRadius: 8, fontSize: 12.5,
        fontWeight: 700, cursor: busy ? 'default' : 'pointer',
        border: '1px solid var(--warning-border)', background: 'var(--bg-card)',
        color: 'var(--warning-text)', fontFamily: 'inherit' }}>
      {busy ? 'Открываю…' : 'Открыть портал'}
    </button>
  )
}

/** Полоса «через N минут». Живёт в шапке, поверх всего. */
export function MaintenanceBar({ state, onLifted }) {
  const announced = state && state.mode === 'announced'
  // РЕЖИМ ИДЁТ, А АДМИН РАБОТАЕТ — и он обязан об этом помнить. Заглушки он не видит
  // (сервер его пропускает), и без полосы портал выглядел бы для него обычным: человек
  // ушёл бы по делам, оставив систему закрытой для всех остальных.
  const adminInside = state && state.mode === 'active' && state.passes
  if (!announced && !adminInside) return null
  const mins = Math.max(1, Math.ceil((state.seconds_left || 0) / 60))
  return (
    <div style={{
      background: 'var(--warning-bg)', borderBottom: '1px solid var(--warning-border)',
      color: 'var(--warning-text)', padding: '9px 22px', fontSize: 13.5, fontWeight: 600,
      display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
    }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--warning)' }} />
      {adminInside ? (
        <>
          <span>Портал закрыт на техобслуживание. Работать можете только вы.</span>
          <span style={{ fontWeight: 400 }}>
            Для возобновления включите его обратно — кнопкой справа.
          </span>
          {/* Кнопка стоит ЗДЕСЬ, а не только в настройках: полоса висит на каждом
              экране, и путь «вспомни, где это лежит» в такой момент лишний. */}
          <LiftButton onLifted={onLifted} />
        </>
      ) : (
        <>
          <span>Портал прервётся на техобслуживание через {mins} мин.</span>
          <span style={{ fontWeight: 400 }}>Просим сохранить вашу работу.</span>
        </>
      )}
    </div>
  )
}

/** Заглушка на весь экран. Показывается ПОСЛЕ входа, а сам вход остаётся рабочим:
 *  иначе админ не сможет войти и снять режим. */
export function MaintenanceStub({ state }) {
  // ЗАГЛУШКА НЕ НАКРЫВАЕТ ТОГО, КОГО СЕРВЕР ПУСКАЕТ. 18.09.2026 админ включил режим и
  // остался снаружи собственного портала: прослойка его пропускала, а этот экран
  // рисовался всем подряд — роли он не спрашивал. Снимать режим пришлось из консоли
  // базы, то есть ровно тогда, когда это сложнее всего.
  //
  // Право решает сервер (`passes` в ответе `/api/maintenance`), экран подчиняется. Своя
  // проверка роли здесь была бы вторым расчётом одного права — а они расходятся.
  if (!state || state.mode !== 'active' || state.passes) return null
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
