// «Нацелить на себя» вне конвейера (владелец 01.10.2026): после старта РК трафику и
// аккаунту нужно снимать скриншоты размещения, а кнопка жила только в конвейере и в
// развёрнутом креативе. Логика — та же, что в конвейере (`pages/traffic/queue.js`):
// ссылка выпускается по нажатию (`/launch-prep/set/{id}/targeting-link`), вкладка
// открывается синхронно по клику, цвет — ответ последнего нажатия, а до нажатия —
// жёлтый, если демо-кампания нацеливания уснула («протухла», живёт 2 дня).
//
// Окно ожидания (09.10.2026): пока сервер заводит копию в DSP и запускает её (до минуты),
// экран перекрыт окном со счётчиком секунд; при отказе окно остаётся и показывает причину и
// ЖУРНАЛ (комплект, время, код ответа, сырой ответ сервера) — отказ больше не прячется в
// подсказке кнопки или во вкладке, которую браузер мог не открыть. Успех закрывает окно сам.
//
// `tgtState` — состояние демо-кампании (`useTargetingCampaign`) передаёт родитель: одно на
// экран, а не запрос на каждую кнопку. `offWhy` — причина, по которой кнопка заперта
// (`aim_gate` на сервере): нет нашей площадки с согласованным креативом или не готов ЕРИД.
import { useEffect, useState } from 'react'
import api, { auth } from '@/lib/api'
import { aimExpired, aimToneFor, issueAim } from '@/lib/aimTab'
import { Modal, primaryBtn } from '@/components/salesTableKit'
import { Cube } from '@/components/LogoLoader'

const hhmmss = (d) => d.toLocaleTimeString('ru-RU', { hour12: false })

function AimModal({ setId, state, onClose }) {
  // state: { phase: 'wait' | 'fail', startedAt, log: [строки], why }
  const [sec, setSec] = useState(0)
  useEffect(() => {
    if (state.phase !== 'wait') return undefined
    const t = setInterval(() => setSec(Math.round((Date.now() - state.startedAt) / 1000)), 500)
    return () => clearInterval(t)
  }, [state.phase, state.startedAt])
  const waiting = state.phase === 'wait'
  return (
    <Modal title={waiting ? 'Готовим нацеливание' : 'Нацеливание не выпущено'} width={560}
      onClose={waiting ? () => {} : onClose}
      footer={waiting ? null : <button style={primaryBtn} onClick={onClose}>Закрыть</button>}>
      {waiting ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '8px 0' }}>
          <Cube variant="spinner" size={64} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <b style={{ fontSize: 14 }}>Ждём ответ сервера… {sec} с</b>
            <span style={{ fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
              Заводим копию баннера в DSP, запускаем её и выпускаем ссылку. Первое нажатие по комплекту
              занимает до минуты. Окно закроется само, вкладка DSP откроется рядом.
            </span>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div role="alert" style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--danger-fg)', lineHeight: 1.45 }}>{state.why}</div>
          <div>
            <div style={{ fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text-faint)', marginBottom: 6 }}>Журнал</div>
            <pre style={{ margin: 0, padding: '10px 12px', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)',
              borderRadius: 10, fontSize: 11.5, lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              maxHeight: 220, overflow: 'auto', fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>{state.log.join('\n')}</pre>
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>Комплект {setId}. Если причина не ясна, пришлите журнал.</div>
        </div>
      )}
    </Modal>
  )
}

export default function AimButton({ setId, tgtState, mayEdit = true, compact = false, offWhy = '', style }) {
  const [busy, setBusy] = useState(false)
  const [live, setLive] = useState(undefined)
  const [msg, setMsg] = useState('')
  const [modal, setModal] = useState(null)

  const go = async (e) => {
    e && e.stopPropagation()
    if (busy || !setId || offWhy) return
    const startedAt = Date.now()
    const log = [`${hhmmss(new Date())}  POST /launch-prep/set/${setId}/targeting-link`]
    setMsg(''); setBusy(true); setModal({ phase: 'wait', startedAt, log })
    try {
      const r = await issueAim(api, auth, setId)
      const took = Math.round((Date.now() - startedAt) / 100) / 10
      setLive(r.active); setMsg(r.message || '')
      if (r.failed) {
        log.push(`${hhmmss(new Date())}  ответ ${r.status || 'нет ответа'} за ${took} с`,
          `detail: ${typeof r.raw === 'string' ? r.raw : JSON.stringify(r.raw)}`)
        setModal({ phase: 'fail', startedAt, log, why: r.message })
      } else {
        setModal(null)
      }
    } catch (err) {
      log.push(`${hhmmss(new Date())}  сбой экрана: ${err?.message || err}`)
      setModal({ phase: 'fail', startedAt, log, why: 'Не удалось выпустить ссылку нацеливания' })
    } finally { setBusy(false) }
  }

  const expired = aimExpired(tgtState) && live === undefined
  const title = offWhy || msg || (expired
    ? 'Время нацеливания истекло (кампания живёт 48 часов) — нажмите, чтобы перезапустить; баннер появится минут через 10'
    : 'Нацелить на себя: откроется страница DSP, нажмите «Включить» — и увидите баннер на сайте площадки')
  return (
    <>
      <button type="button" disabled={!mayEdit || busy || !setId || !!offWhy} onClick={go} title={title}
        style={{ height: compact ? 26 : 30, padding: compact ? '0 9px' : '0 12px', borderRadius: 8,
          border: '1px solid var(--border-card)', background: 'var(--bg-card)', color: 'var(--accent)',
          fontSize: compact ? 11.5 : 12, fontWeight: 700, whiteSpace: 'nowrap',
          cursor: busy ? 'progress' : mayEdit ? 'pointer' : 'default', opacity: busy ? 0.7 : 1,
          ...(offWhy ? { opacity: 0.45, color: 'var(--text-faint)' } : aimToneFor(live, tgtState)), ...style }}>
        {busy ? 'выпускаю…' : compact ? '◎ нацелить' : '◎ Нацелить на себя'}
      </button>
      {!!offWhy && (
        <span style={{ fontSize: 11, color: 'var(--text-faint)', maxWidth: 360 }} title={offWhy}>
          {offWhy.length > 70 ? `${offWhy.slice(0, 68)}…` : offWhy}
        </span>
      )}
      {!!msg && live === true && !modal && (
        <span style={{ fontSize: 11.5, color: 'var(--warning-fg)', maxWidth: 420 }}>{msg}</span>
      )}
      {modal && <AimModal setId={setId} state={modal} onClose={() => setModal(null)} />}
    </>
  )
}
