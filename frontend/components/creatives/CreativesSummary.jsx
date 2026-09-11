/**
 * Свёрнутый вид блока «Креативы» — МАППЕР к компоненту из хендоффа.
 *
 * Разметку рисует `CreativesSection.jsx` (папка `code/` дизайн-хендоффа, вставлена
 * дословно): по правилу проекта компонент из хендоффа не пересобирается по скриншоту,
 * к нему подключаются данные. Здесь только перевод нашего ответа `/launch-prep/deal/{id}`
 * в контракт `Creative[]`, описанный в README хендоффа, и предпросмотр по кнопке.
 *
 * ДАННЫЕ ПРИХОДЯТ СВЕРХУ. Тело секции — функция, свёрнутая секция не монтируется, и
 * запрос, живущий внутри блока, до свёрнутого вида не доходит. На этой же карточке так
 * уже случилось с обвязкой ОРД: свёрнутый вид показывал «не проверено» до первого
 * разворачивания — ровно то, ради чего сворачивание делали, не работало.
 */
import { useState } from 'react'
import { CreativePreview, FORM_LABEL } from './AssemblyCreatives'
import { CreativesBrief, derive } from './CreativesSection'

const fileSize = (n) => !n ? '' : n > 1048576 ? `${(n / 1048576).toFixed(1)} МБ` : `${Math.round(n / 1024)} КБ`

/* Статус площадки в словарь хендоффа. У него четыре значения, отказа среди них нет —
   он появился у нас позже (владелец, 27.08.2026). Отказ кладём в «правки»: обе группы
   отвечают на один вопрос «эта площадка требует действия и точно не согласована», а
   завести пятый цвет — правка дизайна, а не подключение данных. */
function siteStatus(r) {
  if (r.verdict === 'ок') return 'принято'
  if (r.verdict === 'на доработку' || r.verdict === 'отказ'
      || r.state === 'отказ площадки'
      // Трафик завернул материал (28.08.2026) — площадка о нём не узнала, но для
      // аккаунта это то же самое: собрать новую версию.
      || r.traffic_verdict === 'на переделку') return 'правки'
  if (r.pair_id) return 'на проверке'
  return 'черновик'
}

/** Наш комплект → `Creative` из контракта хендоффа. */
export function toCreative(s) {
  const f = (s.files || [])[0]
  return {
    num: `№${s.no}`,
    name: s.title || 'без названия',
    tags: [s.scope, s.origin !== 'первичный' ? s.origin : null,
      s.form ? (FORM_LABEL[s.form] || s.form).toLowerCase() : null].filter(Boolean).join(' · '),
    tech: s.form ? (FORM_LABEL[s.form] || s.form) : '—',
    file: f ? f.name : 'файла нет',
    size: f ? fileSize(f.size_bytes) : '',
    erid: s.erid || '',
    // Скриншоты размещения по всем площадкам креатива: в свёрнутой сводке нужен факт
    // «доказательства собраны», а не их разбивка — за разбивкой идут в очередь трафика.
    shots: (s.recipients || []).reduce((a, r) => a + (r.files_count || 0), 0),
    _set: s,                       // чтобы предпросмотр знал, чей файл открывать
    sites: (s.recipients || []).map(r => ({
      site: r.name || '',
      surface: r.surface_kind === 'app' ? 'app' : 'web',
      hasSpec: !!r.tech_requirements,
      url: r.advertiser_url || '',
      erid: s.erid && ['ерид получен', 'заведён в DSP', 'в размещении'].includes(r.state)
        ? s.erid : '',
      // Состояние во внешних системах считает СЕРВЕР одной функцией на два экрана.
      // Здесь только раскладываем — своей арифметики у витрины быть не должно.
      weborama: r.external?.weborama?.state || '',
      weboramaWhy: r.external?.weborama?.why || '',
      dsp: r.external?.dsp?.state || '',
      dspWhy: r.external?.dsp?.why || '',
      status: siteStatus(r),
    })),
    // Счётчики для сводки. Знаменатель — только те площадки, которым это НУЖНО:
    // крутящие сами («—») не считаются ни в числителе, ни в знаменателе, иначе итог
    // никогда не сойдётся и перестанет что-либо значить.
    extW: extCount(s.recipients, 'weborama', ['есть']),
    extD: extCount(s.recipients, 'dsp', ['заведён', 'крутится']),
  }
}

/** «Сделано из нужных» по одной внешней системе. */
function extCount(recipients, key, doneStates) {
  let done = 0
  let need = 0
  for (const r of recipients || []) {
    const st = r.external?.[key]?.state
    if (!st || st === '—') continue
    need += 1
    if (doneStates.includes(st)) done += 1
  }
  return { done, need }
}

/** Итог секции — строка `summary` в заголовке. Считается тем же `derive`, что и таблица:
 *  два счёта, посчитанные каждый по-своему, однажды разойдутся. */
export function creativesSummary(data) {
  const sets = (data && data.sets) || []
  if (!sets.length) return { text: 'креативов нет', tone: 'off' }
  const d = sets.map(s => derive(toCreative(s)))
  const fix = d.reduce((a, x) => a + x.fix, 0)
  if (fix) return { text: `правки по ${fix}`, tone: 'warn' }
  const marked = sets.filter(s => s.erid).length
  if (marked === sets.length) return { text: 'все маркированы', tone: 'ok' }
  const ok = d.reduce((a, x) => a + x.ok, 0)
  const total = d.reduce((a, x) => a + x.total, 0)
  // Пока материал у трафика, «согласовано 0 из 6» — правда, но не новость: площадки
  // ещё не спрашивали, и строка в свёрнутой шапке читалась как «площадки молчат».
  const atTraffic = sets.reduce((a, s) => a + (s.recipients || [])
    .filter(r => r.pair_id && !r.traffic_verdict).length, 0)
  if (atTraffic && !ok) return { text: `у трафика на проверке · ${atTraffic}`, tone: null }
  return { text: `согласовано ${ok} из ${total}`, tone: ok && ok === total ? 'ok' : null }
}

export default function CreativesSummary({ data, canApprove, onReviewed }) {
  const [preview, setPreview] = useState(null)
  const sets = (data && data.sets) || []

  if (!sets.length) {
    return (
      <div style={{ paddingLeft: 21, fontSize: 12, color: 'var(--text-faint)' }}>
        Креативов пока нет.
      </div>
    )
  }

  return (
    <div style={{ paddingLeft: 21 }}>
      <CreativesBrief creatives={sets.map(toCreative)}
        onPreview={(c) => {
          const f = (c._set.files || [])[0]
          if (f) setPreview({ set: c._set, fileId: f.id })
        }} />

      {!!preview && (
        <CreativePreview files={preview.set.files} startId={preview.fileId}
          set={preview.set} canApprove={canApprove}
          onReviewed={() => { setPreview(null); if (onReviewed) onReviewed() }}
          onClose={() => setPreview(null)} />
      )}
    </div>
  )
}
