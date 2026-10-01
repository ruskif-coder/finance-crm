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
import { downloadFile } from '@/lib/download'
import { CreativePreview, FORM_LABEL } from './AssemblyCreatives'
import { CreativesBrief, derive } from './CreativesSection'
import AimButton from '@/components/traffic/AimButton'
import { useTargetingCampaign } from '@/components/traffic/TargetingCampaign'

const fileSize = (n) => !n ? '' : n > 1048576 ? `${(n / 1048576).toFixed(1)} МБ` : `${Math.round(n / 1024)} КБ`

/* Статус площадки в словарь сводки. Отказ — отдельным значением (макет владельца
   27.09.2026: «доработка» и «отказ» разными цветами). До того отказ лежал в «правках»:
   в хендоффе пятого значения не было. */
function siteStatus(r) {
  if (r.verdict === 'ок') return 'принято'
  if (r.verdict === 'отказ' || r.state === 'отказ площадки') return 'отказ'
  if (r.verdict === 'на доработку'
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
    fileId: f ? f.id : null,
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
    extS: screensCount(s.recipients),
  }
}

/** Скрины запуска (01.10.2026): отмечено трафиком из площадок, где креатив в размещении. */
function screensCount(recipients) {
  let done = 0
  let need = 0
  for (const r of recipients || []) {
    if (r.state !== 'в размещении' && !r.screens_done_at) continue
    need += 1
    if (r.screens_done_at) done += 1
  }
  return { done, need }
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

/** 1 площадка, 3 площадки, 5 площадок (и 11–14 — «площадок»). */
function plural(n, one, few, many) {
  const m10 = n % 10
  const m100 = n % 100
  if (m10 === 1 && m100 !== 11) return one
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few
  return many
}

/** Итог секции — строка `summary` в заголовке. Считается тем же `derive`, что и таблица:
 *  два счёта, посчитанные каждый по-своему, однажды разойдутся. */
export function creativesSummary(data) {
  const sets = (data && data.sets) || []
  if (!sets.length) return { text: 'креативов нет', tone: 'off' }
  const d = sets.map(s => derive(toCreative(s)))
  const fix = d.reduce((a, x) => a + x.fix, 0)
  // «правки: 3 площадки в 1 креативе» — плашкой в шапке секции (макет 27.09.2026).
  // Отказ — своей красной плашкой рядом, а не вместо: одна плашка на двоих прятала бы
  // отказы, пока есть хоть одна доработка (ревью 27.09.2026).
  const rej = d.reduce((a, x) => a + x.rej, 0)
  const chip = (label, n, key, tone) => {
    const inSets = d.filter(x => x[key]).length
    return { text: `${label}: ${n} ${plural(n, 'площадка', 'площадки', 'площадок')} в ${inSets} `
      + plural(inSets, 'креативе', 'креативах', 'креативах'), tone }
  }
  const chips = [fix ? chip('правки', fix, 'fix', 'warn') : null,
    rej ? chip('отказ', rej, 'rej', 'danger') : null].filter(Boolean)
  if (chips.length) return { text: chips.map(c => c.text).join(' · '), tone: 'warn', chips }
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

const ALERT_TONE = {
  warn:   { bg: 'var(--warning-tint)', bd: 'var(--warning-border)', fg: 'var(--warning-text)', dot: 'var(--warning)' },
  danger: { bg: 'var(--danger-tint)',  bd: 'var(--danger-border)',  fg: 'var(--danger-fg)',    dot: 'var(--danger)' },
}

/** Плашка «правки» (оранжевая) или «отказ» (красная) в шапке секции — тон как в таблице. */
export function CreativesAlert({ text, tone = 'warn' }) {
  const t = ALERT_TONE[tone] || ALERT_TONE.warn
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 26, padding: '0 11px',
      background: t.bg, border: `1px solid ${t.bd}`, borderRadius: 8,
      color: t.fg, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap' }}>
      <span style={{ width: 7, height: 7, borderRadius: 2, background: t.dot }} />{text}
    </span>
  )
}

export default function CreativesSummary({ data, canApprove, onReviewed }) {
  const [preview, setPreview] = useState(null)
  const [err, setErr] = useState('')
  // Состояние демо-кампании нацеливания — одно на блок: «протухла» ли (кнопки жёлтые).
  const tgt = useTargetingCampaign()
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
        renderAim={(c) => c._set?.id ? <AimButton setId={c._set.id} tgtState={tgt.state} compact /> : null}
        onPreview={(c) => {
          const f = (c._set.files || [])[0]
          if (f) setPreview({ set: c._set, fileId: f.id })
        }}
        onDownload={(c) => {
          const f = (c._set.files || [])[0]
          if (f) { setErr(''); downloadFile(`/launch-prep/file/${f.id}`, f.name, setErr) }
        }} />
      {!!err && <div style={{ marginTop: 8, fontSize: 12, color: 'var(--danger-fg)' }}>{err}</div>}

      {!!preview && (
        <CreativePreview files={preview.set.files} startId={preview.fileId}
          set={preview.set} canApprove={canApprove}
          onReviewed={() => { setPreview(null); if (onReviewed) onReviewed() }}
          onClose={() => setPreview(null)} />
      )}
    </div>
  )
}
