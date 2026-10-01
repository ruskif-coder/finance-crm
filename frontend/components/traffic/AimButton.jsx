// «Нацелить на себя» вне конвейера (владелец 01.10.2026): после старта РК трафику и
// аккаунту нужно снимать скриншоты размещения, а кнопка жила только в конвейере и в
// развёрнутом креативе. Логика — та же, что в конвейере (`pages/traffic/queue.js`):
// ссылка выпускается по нажатию (`/launch-prep/set/{id}/targeting-link`), вкладка
// открывается синхронно по клику, цвет — ответ последнего нажатия, а до нажатия —
// жёлтый, если демо-кампания нацеливания уснула («протухла», живёт 2 дня).
//
// `tgtState` — состояние демо-кампании (`useTargetingCampaign`) передаёт родитель: одно на
// экран, а не запрос на каждую кнопку.
import { useState } from 'react'
import api, { auth } from '@/lib/api'
import { aimExpired, aimToneFor, issueAim } from '@/lib/aimTab'

export default function AimButton({ setId, tgtState, mayEdit = true, compact = false, style }) {
  const [busy, setBusy] = useState(false)
  const [live, setLive] = useState(undefined)
  const [msg, setMsg] = useState('')

  const go = async (e) => {
    e && e.stopPropagation()
    if (busy || !setId) return
    setMsg(''); setBusy(true)
    try {
      const r = await issueAim(api, auth, setId)
      setLive(r.active); setMsg(r.message || '')
    } finally { setBusy(false) }
  }

  const expired = aimExpired(tgtState) && live === undefined
  const title = msg || (expired
    ? 'Время нацеливания истекло (кампания живёт 48 часов) — нажмите, чтобы перезапустить; баннер появится минут через 10'
    : 'Нацелить на себя: откроется страница DSP, нажмите «Включить» — и увидите баннер на сайте площадки')
  return (
    <button type="button" disabled={!mayEdit || busy || !setId} onClick={go} title={title}
      style={{ height: compact ? 26 : 30, padding: compact ? '0 9px' : '0 12px', borderRadius: 8,
        border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--accent)',
        fontSize: compact ? 11.5 : 12, fontWeight: 700, whiteSpace: 'nowrap',
        cursor: busy ? 'progress' : mayEdit ? 'pointer' : 'default', opacity: busy ? 0.7 : 1,
        ...aimToneFor(live, tgtState), ...style }}>
      {busy ? 'выпускаю…' : compact ? '◎ нацелить' : '◎ Нацелить на себя'}
    </button>
  )
}
