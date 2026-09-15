/**
 * Блок «Рекламная кампания» — сводка открутки на карточке сделки.
 *
 * Отдельным компонентом, а не кусками разметки в карточке: тот же блок поедет на
 * предварительную сверку (владелец 05.09.2026), а вторая копия разошлась бы с первой —
 * в этом проекте так уже расходились генератор имени и расчёт статуса площадки.
 *
 * Появляется, ТОЛЬКО когда пошла статистика. До первого замера в нём одни прочерки, и
 * блок из прочерков читается как поломка, а не как «ещё не началось»: сервер отвечает
 * `has: false` и говорит словами, чего именно нет.
 *
 * Ничего не считает: план, факт, темп, недокрут и доли приходят посчитанными той же
 * ручкой, что кормит дашборд трафика. Здесь только оформление.
 *
 * Отчёт — РАСХЛОП, а не модалка (владелец 05.09.2026): так устроены все подробности в
 * проекте, от реестра сделок до дашборда трафика. Внутри те же два блока, что в расхлопе
 * дашборда: динамика показов и таблица площадок. `Dynamics` берётся оттуда же
 * компонентом, вместе с суточной карточкой по наведению — второй график разошёлся бы с
 * первым при первой правке.
 */
import { useEffect, useState } from 'react'
import { MONO, UI, PortalPopover, Z, btnSm } from '@/components/salesTableKit'
import Section from '@/components/deal/Section'
import { Dynamics, GOAL_LABELS, PaceBar, StatusPill, pctTone } from '@/components/traffic/dashboardKit'
import { grp } from '@/lib/salesFormat'
import api, { auth } from '@/lib/api'

const DASH = '—'
const num = (v) => (v == null ? DASH : grp(v))
const rub = (v) => (v == null ? DASH : `${grp(v)} ₽`)

const CAP = {
  fontFamily: MONO, fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase',
  color: 'var(--text-faint)',
}

/** Число с подписью — одна ячейка сводки. */
const Cell = ({ label, value, unit, tone, hint }) => (
  <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
    <span style={CAP}>{label}</span>
    <span style={{ display: 'flex', alignItems: 'baseline', gap: 5 }}>
      <span style={{ fontFamily: MONO, fontSize: 17, fontWeight: 700,
        color: tone || 'var(--text-primary)' }}>{value}</span>
      {!!unit && <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{unit}</span>}
    </span>
    {!!hint && <span style={{ fontSize: 10.5, color: 'var(--text-faint)' }}>{hint}</span>}
  </span>
)

/** Сводка цифрами — одна и та же в блоке и в шапке модалки, поэтому вынесена. */
const Numbers = ({ d }) => (
  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0,1fr))', gap: 14 }}>
    <Cell label="план показов" value={num(d.plan_show)}
      hint={d.plan_budget != null ? rub(d.plan_budget) : null} />
    <Cell label="факт" value={num(d.fact_shows)} tone="var(--accent)"
      hint={d.fact_budget != null ? `${rub(d.fact_budget)} по цене плана` : null} />
    <Cell label="переходы" value={num(d.fact_clicks)}
      hint={d.ctr != null ? `CTR ${String(d.ctr).replace('.', ',')} %` : null} />
    {/* «Потенциал недокрута» — ПРОГНОЗ на конец флайта при текущем темпе, а не разница
        плана и факта на сегодня: она в середине РК всегда огромна и ничего не значит. */}
    <Cell label="потенциал недокрута"
      value={d.under ? `−${num(d.under)}` : num(0)}
      tone={d.under ? 'var(--danger)' : 'var(--income)'}
      hint={d.forecast != null ? `прогноз ${num(d.forecast)}` : null} />
    <Cell label="крутит площадок" value={`${d.placements_on} / ${d.placements}`}
      hint={d.days_left != null ? `дней осталось ${d.days_left}` : null} />
    {/* Расхождение с верификатором — шестым числом, в общем ряду.

        Прочерк тут значит «сверять не с чем», а не «сошлось»: соответствие «их вставка →
        наша площадка» появляется только у тех размещений, что заводили мы. Поэтому
        подпись под прочерком говорит это словами — пустое место читалось бы как ноль.

        Цвет — по цели приёмки из медиаплана («Расхождение 10»), и только когда цель
        задана числом: она поле свободного ввода, там бывает «до 10 %». Нет числа —
        красить не по чему, и вердикт не выносим. */}
    <Cell label="расхождение"
      value={d.mismatch_pct == null ? DASH
        : `${String(d.mismatch_pct).replace('.', ',')} %`}
      tone={mismatchTone(d)}
      hint={d.mismatch_pct == null
        ? (d.pixel_mode === 'external' ? 'внешний тег — внесите на сверке'
          : 'Weborama не измеряла')
        : (d.verifier_placements < d.placements
          ? `по ${d.verifier_placements} из ${d.placements} площадок`
          : `Weborama ${num(d.verifier_shows)}`)} />
  </div>
)

/** Порог из KPI приёмки, если он задан числом. «до 10 %» — тоже число, «по факту» — нет. */
const goalLimit = (d) => {
  const raw = String((d.goals && d.goals.weborama) || '').replace(',', '.')
  const m = raw.match(/\d+(\.\d+)?/)
  return m ? Number(m[0]) : null
}

const mismatchTone = (d) => {
  if (d.mismatch_pct == null) return 'var(--text-cap)'
  const lim = goalLimit(d)
  if (lim == null) return null
  return Math.abs(d.mismatch_pct) > lim ? 'var(--danger-fg)' : 'var(--income-fg)'
}

/** Полоса выполнения с риской «где должны быть по календарю». */
const Pace = ({ d }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
    <span style={{ flex: 1 }}><PaceBar pct={d.done_pct} pace={d.pace} height={9} /></span>
    <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700,
      color: pctTone(d.done_pct, d.pace), minWidth: 54, textAlign: 'right' }}>
      {d.done_pct == null ? DASH : `${String(d.done_pct).replace('.', ',')} %`}
    </span>
    {d.pace != null && (
      <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)',
        whiteSpace: 'nowrap' }}>флайт {Math.round(d.pace * 100)} %</span>
    )}
  </div>
)

// Две колонки верификатора идут ПОСЛЕ недокрута и перед статусом: сначала наши
// числа, потом независимое измерение. Смешивать их в одном столбце нельзя —
// сложение факта с верификатором и есть та ошибка, ради которой заведён
// `app/ad/stat_sources.py`.
const GRID = 'minmax(0,1.4fr) 52px 104px 62px 104px 104px 104px 104px 92px 120px'

/**
 * Тело расхлопа — те же два блока, что в расхлопе дашборда трафика: сначала динамика
 * показов (с суточным срезом по наведению), под ней таблица площадок. Сводку здесь не
 * повторяем: она осталась на своём месте прямо над расхлопом и никуда не делась —
 * в этом и разница с модалкой, которая её перекрывала.
 */
/**
 * Ручной ввод показов верификатора. Только для ВНЕШНЕГО пикселя: вставку заводил клиент,
 * в нашем реестре её нет, и снимать статистику неоткуда. Их отчёт приходит файлом —
 * показы за период, одним числом, без кликов.
 *
 * Компонент объявлен НА МОДУЛЬНОМ УРОВНЕ: объявленный внутри рендера, он пересоздаётся
 * на каждый набранный символ, и поле теряет фокус — ловушка, на которой проект уже
 * обжигался.
 */
const ManualVerifier = ({ d, dealId }) => {
  const cur = d.verifier_manual
  const [val, setVal] = useState(cur ? String(cur.shows) : '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [ok, setOk] = useState(false)

  const save = (clear) => {
    setBusy(true); setErr(''); setOk(false)
    const shows = clear ? null : Number(String(val).replace(/\s/g, '').replace(',', '.'))
    if (!clear && !Number.isFinite(shows)) { setBusy(false); setErr('Ожидается число'); return }
    api.put(`/sales/deals/${dealId}/verifier-shows`, { shows }, auth())
      .then(() => { setBusy(false); setOk(true); if (clear) setVal('') })
      .catch(e => { setBusy(false); setErr(e.response?.data?.detail || 'Не удалось сохранить') })
  }

  return (
    <div style={{ paddingTop: 12, borderTop: '1px solid var(--border-inner)' }}>
      <span style={{ ...CAP, display: 'block', marginBottom: 8 }}>
        сверка · показы по данным weborama
      </span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <input value={val} onChange={e => { setVal(e.target.value); setOk(false) }}
          placeholder="показы за период"
          style={{ width: 180, height: 34, fontFamily: MONO, fontSize: 13, padding: '0 10px',
            borderRadius: 9, border: '1px solid var(--border-card)',
            background: 'var(--bg-card)', color: 'var(--text-primary)', outline: 'none' }} />
        <button type="button" style={btnSm(true)} disabled={busy} onClick={() => save(false)}>
          {busy ? '…' : 'Сохранить'}
        </button>
        {!!cur && (
          <button type="button" style={btnSm(false)} disabled={busy} onClick={() => save(true)}>
            очистить
          </button>
        )}
        {ok && <span style={{ fontSize: 12, color: 'var(--income-fg)' }}>сохранено, перезагрузите карточку</span>}
        {!!err && <span style={{ fontSize: 12, color: 'var(--danger-fg)' }}>{err}</span>}
        <span style={{ fontSize: 11, color: 'var(--text-faint)', flexBasis: '100%' }}>
          Одним числом за весь период — в отчёте клиента разбивки по площадкам нет.
          В факт не входит: это независимое измерение, оно только сверяется.
          {cur ? ` Сейчас внесено на ${cur.period_to}.` : ''}
        </span>
      </div>
    </div>
  )
}

const Report = ({ d, dealId }) => {
  const [stat, setStat] = useState(null)
  const [grain, setGrain] = useState('day')

  useEffect(() => {
    let alive = true
    api.get(`/sales/deals/${dealId}/campaign/stat?grain=${grain}`, auth())
      .then(r => { if (alive) setStat(r.data) })
      .catch(() => { if (alive) setStat({ buckets: [] }) })
    return () => { alive = false }
  }, [dealId, grain])

  return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ paddingTop: 12, borderTop: '1px solid var(--border-inner)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
            <span style={CAP}>динамика показов</span>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 5 }}>
              {[['day', 'дни'], ['week', 'недели']].map(([g, l]) => (
                <button key={g} type="button" style={btnSm(grain === g)}
                  onClick={() => setGrain(g)}>{l}</button>
              ))}
            </span>
            <span style={{ display: 'inline-flex', gap: 10, marginLeft: 6 }}>
              {[['план', 'var(--blue-soft)'], ['факт', 'var(--blue)']].map(([l, c]) => (
                <span key={l} style={{ display: 'inline-flex', alignItems: 'center', gap: 5,
                  fontSize: 10.5, color: 'var(--text-muted)' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />{l}
                </span>
              ))}
            </span>
          </div>
          <Dynamics data={stat} label={d.deal_code || ''} />
        </div>

        {d.pixel_mode === 'external' && (
          <ManualVerifier d={d} dealId={dealId} />
        )}

        <div style={{ paddingTop: 12, borderTop: '1px solid var(--border-inner)' }}>
          <span style={{ ...CAP, display: 'block', marginBottom: 8 }}>
            площадки и распределение
          </span>
          <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 9,
            padding: '0 0 6px', borderBottom: '1px solid var(--border-inner)' }}>
            {['Площадка', 'Код', 'Вес', 'Доля', 'План', 'Факт', 'Недокрут',
              'Weborama', 'Расхожд.', 'Статус']
              .map((h, i) => (
                <span key={h} style={{ ...CAP, textAlign: i >= 2 && i <= 8 ? 'right' : 'left' }}>
                  {h}</span>
              ))}
          </div>
          {(d.rows || []).map(r => (
            <div key={r.id} style={{ display: 'grid', gridTemplateColumns: GRID, gap: 9,
              alignItems: 'center', padding: '7px 0',
              borderBottom: '1px solid var(--border-row)' }}>
              <span style={{ fontFamily: MONO, fontSize: 11.5, overflow: 'hidden',
                textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.domain}>
                {r.domain}</span>
              <span style={{ fontFamily: MONO, fontSize: 10.5, color: 'var(--text-faint)' }}>
                {r.code || DASH}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right',
                color: 'var(--text-muted)' }}>{num(r.weight)}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right' }}>
                {r.share ? `${Math.round(r.share * 100)} %` : DASH}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right' }}>
                {num(r.plan_show)}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right',
                color: r.fact_shows == null ? 'var(--text-faint)' : 'var(--text-primary)' }}>
                {num(r.fact_shows)}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right',
                color: r.under ? 'var(--danger)' : 'var(--text-faint)' }}>
                {r.under ? `−${num(r.under)}` : DASH}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right',
                color: r.verifier_shows == null ? 'var(--text-cap)' : 'var(--text-muted)' }}
                title={r.verifier_shows == null
                  ? 'Замеров Weborama по этой площадке нет'
                  : 'Справочная величина: в факт и в закрытие не входит'}>
                {num(r.verifier_shows)}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right',
                color: r.mismatch_pct == null ? 'var(--text-cap)' : 'var(--text-primary)' }}>
                {r.mismatch_pct == null ? DASH
                  : `${String(r.mismatch_pct).replace('.', ',')} %`}</span>
              <span style={{ justifySelf: 'center' }}>
                <StatusPill value={r.status} w={116} /></span>
            </div>
          ))}
          {!(d.rows || []).length && (
            <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>
              Площадки к РК не подключены.</span>
          )}
        </div>
      </div>
  )
}

export default function CampaignSummary({ dealId, title = 'Рекламная кампания', cardStyle }) {
  const [data, setData] = useState(null)
  const [pop, setPop] = useState(false)

  useEffect(() => {
    let alive = true
    api.get(`/sales/deals/${dealId}/campaign`, auth())
      .then(r => { if (alive) setData(r.data) })
      .catch(() => { if (alive) setData({ has: false, reason: '' }) })
    return () => { alive = false }
  }, [dealId])

  // Блока нет, пока нет статистики. Не «пустой блок», а отсутствие блока: место на
  // карточке дорогое, и рамка вокруг пяти прочерков ничего не сообщает.
  if (!data || !data.has) return null

  const goals = GOAL_LABELS.filter(([k]) => data.goals && data.goals[k])

  /* Сводка видна В ОБОИХ состояниях — и свёрнутом, и раскрытом: это не подробности,
     а то, ради чего блок существует. Поэтому она отдаётся секции и как `collapsed`,
     и первой строкой раскрытого вида. */
  const head = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Numbers d={data} />
      <Pace d={data} />

      {/* Цели приёмки — из медиаплана, теми же пятью и в том же порядке, что в
          конструкторе. Значения свободного ввода, поэтому показываем как есть и
          вердикта «уложились / нет» не выносим: сверяет человек. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
        background: 'var(--bg-subtle)', border: '1px solid var(--border-card)',
        borderRadius: 12, padding: '9px 12px' }}>
        <span style={CAP}>цель · kpi приёмки</span>
        {goals.length ? goals.map(([k, label]) => (
          <span key={k} style={{ display: 'inline-flex', alignItems: 'baseline', gap: 5,
            fontSize: 12 }}>
            <span style={{ color: 'var(--text-muted)' }}>{label}</span>
            <span style={{ fontFamily: MONO, fontWeight: 700 }}>
              {String(data.goals[k]).trim()}</span>
          </span>
        )) : (
          <span data-pop-root style={{ position: 'relative', display: 'inline-block' }}>
            <span onClick={() => setPop(v => !v)}
              style={{ fontSize: 11.5, color: 'var(--warning-text)', cursor: 'pointer',
                borderBottom: '1px dashed var(--warning-text)' }}>
              в медиаплане не заданы
            </span>
            <PortalPopover open={pop} minWidth={280} style={{ padding: 12, zIndex: Z.dropdown }}>
              <span style={{ fontSize: 12, lineHeight: 1.5, color: 'var(--text-secondary)' }}>
                KPI приёмки заполняются в конструкторе медиаплана — блок «Целевые
                показатели». Пока их нет, принимать размещение не по чему.
              </span>
            </PortalPopover>
          </span>
        )}

      </div>
    </div>
  )

  /* Заголовок и стрелка — из общей `Section` карточки сделки, а не свои: у соседних
     блоков («Медиаплан», «ОРД», «Креативы») шрифт, капс и шеврон слева, и вторая
     реализация того же заголовка разъехалась бы с ними при первой правке.
     
     Рамку рисует САМ компонент и только когда внутри есть что показать: иначе на
     карточке повис бы пустой прямоугольник. Стиль карточки приходит пропом — на сверке
     он будет другой. */
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, ...(cardStyle || null) }}>
      <Section id="campaign" dealId={dealId} title={title}
        subtitle={`${data.date_start} — ${data.date_end}`} collapsed={head}>
        {() => (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {head}
            <Report d={data} dealId={dealId} />
          </div>
        )}
      </Section>
    </div>
  )
}
