/**
 * Кампания нацеливания — ЛИЦОМ, а не хешем.
 *
 * ЗАЧЕМ ЭТО ЕСТЬ. Настройка хранит `xxhash` кампании, и по нему человек не может сказать
 * ничего: ни какая это кампания, ни жива ли она. 17.09.2026 это стоило дня разбора —
 * кампания в кабинете DSP была ОСТАНОВЛЕНА и закончилась 13.09, ссылка нацеливания при
 * этом честно выпускалась, открывалась и не показывала ничего. Отказ молчал, и вывод
 * делался неверный: «сломался баннер».
 *
 * Поэтому здесь два вида одного и того же: карточка в настройке и большая подсказка у
 * кнопки ◎ в очереди. Данные ОДНИ — `/traffic-catalog/targeting-campaign`: два запроса к
 * чужой системе однажды разошлись бы, и мы бы спорили сами с собой.
 *
 * Состояние спрашивается заново на каждое открытие экрана и не кэшируется: статус меняют
 * руками в кабинете, и вчерашний ответ хуже отсутствующего — ему верят.
 */
import { useCallback, useEffect, useState } from 'react'
import api, { auth } from '@/lib/http'
import { MONO, PortalPopover, Z } from '@/components/salesTableKit'
import { fmtDateOfMoment } from '@/lib/dates'

/* Их словарь статусов. Переводим, но ОРИГИНАЛ оставляем рядом: в кабинете человек увидит
   именно английское слово, и подсказка, называющая его иначе, отправит искать не то. */
const STATUS_RU = {
  LAUNCHED: 'запущена', STOPPED: 'остановлена',
  DELETED: 'удалена', ARCHIVE: 'в архиве',
}

/* Три состояния, и «спит» — не отказ. Полигон нацеливания намеренно стоит остановленным
   и просыпается в момент получения на двое суток: красная плашка на штатном состоянии
   пугала бы человека тем, что работает как задумано. */
const TONE = (state) => (
  state?.running ? ['var(--income)', 'var(--income-tint)']
    : state?.asleep ? ['var(--dot-current-dz)', 'var(--warning-tint)']
      : state?.status ? ['var(--dot-overdue)', 'var(--danger-tint)']
        : ['var(--text-muted)', 'var(--bg-subtle)'])

/* Сроки приходят МОМЕНТОМ (их `date_start`/`date_end` — метка времени), а показываем
   календарный день: разбор один на весь фронт, своего тут быть не должно. */
const d = (iso) => fmtDateOfMoment(iso)

export function useTargetingCampaign() {
  const [state, setState] = useState(null)
  const [loading, setLoading] = useState(true)
  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await api.get('/traffic-catalog/targeting-campaign', auth())
      setState(r.data)
    } catch (e) {
      // Молчащая связь НЕ должна выглядеть как «всё хорошо»: рисуем отказ, а не пустоту.
      setState({ error: e.response?.data?.detail || 'состояние кампании не прочитать',
        running: false })
    } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])
  return { state, loading, reload: load }
}

/* Плашка статуса. Отдельно от текста, потому что её ищут глазом, а не читают. */
export function CampaignChip({ state }) {
  const known = !!state?.status
  const [fg, bg] = TONE(!!state?.running, known)
  const label = known ? (STATUS_RU[state.status] || state.status) : 'неизвестно'
  return (
    <span style={{ padding: '3px 10px', borderRadius: 100, background: bg, color: fg,
      fontFamily: MONO, fontSize: 10.5, fontWeight: 700, letterSpacing: '.04em',
      textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
      {label}
    </span>
  )
}

/* Содержимое подсказки и карточки — одно и то же. Разница только в рамке вокруг. */
function Body({ state, wide }) {
  if (!state) return <span style={{ color: 'var(--text-muted)' }}>читаю состояние…</span>
  return (
    <div style={{ display: 'grid', gap: 6, fontSize: wide ? 12.5 : 12, lineHeight: 1.5 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <b style={{ fontSize: wide ? 13.5 : 13 }}>{state.title || 'кампания без имени'}</b>
        <CampaignChip state={state} />
      </div>
      <div style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)' }}>
        {state.campaign_xxhash || '—'} · срок {d(state.date_start)} — {d(state.date_end)}
      </div>
      {!!state.reason && (
        <div style={{ color: state.running ? 'var(--text-secondary)' : 'var(--dot-overdue)' }}>
          {state.reason}
        </div>
      )}
      {state.running && (
        <div style={{ color: 'var(--text-secondary)' }}>
          Кампания работает: копия баннера уедет сюда, и ссылка покажет его на сайте
          площадки. Кампанию и её креативы видно в кабинете DSP под этим именем.
        </div>
      )}
      {state.asleep && (
        <div style={{ color: 'var(--text-secondary)' }}>
          Нажимать ничего не нужно: кнопка нацеливания сама продлит срок и запустит
          кампанию. Спит она не по ошибке — запущенная крутится настоящим людям, и
          держать полигон открытым между проверками незачем.
        </div>
      )}
      {!!state.error && (
        <div style={{ color: 'var(--dot-overdue)' }}>Обмен с DSP: {state.error}</div>
      )}
    </div>
  )
}

/* Карточка для настройки: показывает, ЧТО стоит за двумя хешами в полях выше. */
export function TargetingCampaignCard({ state }) {
  return (
    <div style={{ marginTop: 10, padding: '10px 12px', borderRadius: 10,
      border: '1px solid var(--border-card)', background: 'var(--bg-subtle)' }}>
      <Body state={state} wide />
    </div>
  )
}

/* Большая подсказка у кнопки: наведение, без клика. Клик у кнопки свой и он дорогой —
   уходит в DSP и заводит креатив; подсказка обязана быть доступна БЕЗ него. */
export function TargetingCampaignHint({ state, children }) {
  const [over, setOver] = useState(false)
  return (
    <span style={{ position: 'relative', display: 'inline-flex' }}
      onMouseEnter={() => setOver(true)} onMouseLeave={() => setOver(false)}>
      {children}
      <PortalPopover open={over} minWidth={340} maxHeight={260} align="right"
        style={{ zIndex: Z.dropdown, padding: 12, cursor: 'default' }}>
        <Body state={state} />
      </PortalPopover>
    </span>
  )
}

export default TargetingCampaignCard
