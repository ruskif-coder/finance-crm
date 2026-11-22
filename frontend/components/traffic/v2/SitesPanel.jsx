// Площадки в расхлопе РК — дашборд трафика v2 (хендофф design_handoff_traffic_expand_v2, раздел 8).
//
// Панель: «Площадки» (в подсказке — «N из M крутят») · вид «по площадкам / по креативам» · «Порядок»
// (внимание · вес · недокрут · расх. WR — то же состояние, что сортировка заголовком) · справа кнопки.
// Таблица: группы «по вниманию» со строками итогов либо плоский список по столбцу; раскрыта одна площадка.
// На узком экране (< 1150 px таблицы) — горизонтальный скролл внутри блока, первый столбец и расхлоп закреплены.
//
// Экран ничего не считает: недокрут, темп, CTR и расхождение с WR приходят с сервера (`/traffic-dashboard/
// campaign/{id}`), здесь только раскладка (`lib/sitesModel.mjs`) и оформление. Пороги — боевые (17.11.2026).
import { Fragment, useEffect, useMemo, useState } from 'react'
import { EXT_TONE, MONO } from '@/components/salesTableKit'
import { ORDERS, goalCtr, layout, nextSort, noShows } from '@/lib/sitesModel.mjs'
import { CAP_V2, Seg } from './sitesBits'
import { GroupRow, SiteRow, SitesHead } from './SiteRow'
import SiteCreatives from './SiteCreatives'
import ByCreatives from './ByCreatives'
import SitesToolbar from './SitesToolbar'
import SitesColumns from './SitesColumns'
import useUiPref from '@/lib/useUiPref'
import { PREF_KEY, shownCols } from '@/lib/sitesColumns.mjs'
import { dm } from '@/lib/salesFormat'

const VIEWS = [['sites', 'по площадкам'], ['cr', 'по креативам']]
const NOTE = { padding: '9px 18px 11px', fontSize: 11, lineHeight: 1.45, color: 'var(--text-faint)' }

const SitesTable = ({ rk, d, rows, sort, onSort, goal, mayEdit, h, cols }) => {
  const [openPlace, setOpenPlace] = useState(null)
  const groups = useMemo(() => layout(rows, sort, EXT_TONE), [rows, sort])
  return (
    <div style={{ overflowX: 'auto', containerType: 'inline-size' }}>
      <div style={{ minWidth: 1150 }}>
        <SitesHead sort={sort} onSort={onSort} goal={goal} cols={cols} unit={d?.unit} />
        {groups.map(g => (
          <Fragment key={g.key}>
            {g.key !== 'flat' && <GroupRow g={g} cols={cols} />}
            {g.rows.map(p => (
              <Fragment key={p.id}>
                <SiteRow p={p} d={d} goal={goal} mayEdit={mayEdit} h={h} cols={cols} open={openPlace === p.id}
                  onToggle={() => setOpenPlace(x => (x === p.id ? null : p.id))} />
                {openPlace === p.id && (
                  <SiteCreatives rows={p.creatives} place={p} manual={d.creative_manual} mayEdit={mayEdit} goal={goal}
                    campaignHash={rk.ms_campaign_xxhash} onStatus={h.setCreativeStatus} />
                )}
              </Fragment>
            ))}
          </Fragment>
        ))}
        <div style={NOTE}>
          До старта и первые 5 дней РК объём делят все площадки в работе, дальше — только запущенные. Пауза
          останавливает открутку, доля площадки в плане сохраняется. Отключение убирает её из распределения — объём
          уходит остальным.
        </div>
      </div>
    </div>
  )
}

// Фильтр «площадки →» из пульта: площадки в работе без показов за последние отчитанные сутки РК.
const NoShowsChip = ({ ns, shown, total, onClear }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 24, padding: '0 6px 0 10px', borderRadius: 8,
    background: 'var(--warning-tint)', border: '1px solid var(--warning-border)', fontSize: 11.5, fontWeight: 600,
    color: 'var(--warning-fg)', whiteSpace: 'nowrap' }}
    title={ns ? 'Запущенные площадки, у которых нет показов в последние отчитанные сутки РК'
      : 'По РК ещё нет ни одних суток с показами — сравнивать не с чем, показаны все площадки'}>
    {ns ? `без показов ${dm(ns.day)} — ${shown} из ${total}` : 'суточных данных нет — показаны все'}
    {!!onClear && (
      <span onClick={onClear} title="Показать все площадки"
        style={{ fontFamily: MONO, fontSize: 11, cursor: 'pointer', padding: '0 4px' }}>×</span>
    )}
  </span>
)

/**
 * @param rk     строка РК из реестра дашборда (`id`, `deal_id`, `placements`, `placements_on`, `creatives_ready`,
 *               `volumes`, `ms_campaign_xxhash`)
 * @param d      ответ `GET /traffic-dashboard/campaign/{id}`; `null` — ещё грузится
 * @param mayEdit  право менять статусы и выгружать во внешние системы
 * @param tgt    `useTargetingCampaign()` — состояние демо-кампании нацеливания для «Нацелить»
 * @param handlers  { setPlacementStatus(p, s), setCreativeStatus(cr, s), setCreativeGroupStatus(g, s),
 *                    setCreativeScreens(cr, done), askExternal(kind), downloadCreatives() }
 * @param filterNoShows  показать только площадки без показов за последние сутки (ссылка «площадки →» из пульта)
 * @param onClearNoShows снять этот фильтр
 */
export default function SitesPanel({ rk, d, mayEdit, tgt, handlers, filterNoShows = false, onClearNoShows, style }) {
  const [view, setView] = useState('sites')
  const [sort, setSort] = useState({ key: 'attn', dir: 'desc' })
  useEffect(() => { if (filterNoShows) setView('sites') }, [filterNoShows])

  const h = handlers || {}
  const placements = useMemo(() => d?.placements || [], [d])
  const ns = useMemo(() => (filterNoShows ? noShows(placements) : null), [filterNoShows, placements])
  const rows = useMemo(() => (ns ? placements.filter(p => ns.ids.includes(p.id)) : placements), [ns, placements])
  const goal = goalCtr(d?.goals)
  const sitesView = view === 'sites'
  const [colPref, setColPref] = useUiPref(PREF_KEY)
  const cols = useMemo(() => shownCols(colPref), [colPref])

  return (
    <div id={`rk-${rk.id}-placements`} style={{ minWidth: 0, ...style }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 18px', flexWrap: 'wrap', whiteSpace: 'nowrap' }}>
        <span title={`${rk.placements_on ?? 0} из ${rk.placements ?? 0} крутят · доля по весам`}
          style={{ fontSize: 14, fontWeight: 800 }}>Площадки</span>
        {/* Единица объёма кликовой РК (22.11.2026): у click-РК план площадки, факт и недокрут —
            КЛИКИ, а не показы. Сказано словами у заголовка таблицы: колонки «План»/«Факт» без
            единицы читались бы как показы. */}
        {d?.unit === 'click' && (
          <span title="РК кликовая (CPC): план площадки, её факт и недокрут — в кликах"
            style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--accent-fg)', whiteSpace: 'nowrap' }}>
            объём и факт — в кликах</span>
        )}
        <Seg items={VIEWS} value={view} onPick={setView} />
        {sitesView && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
            <span style={CAP_V2}>Порядок</span>
            <Seg items={ORDERS} value={sort.key} onPick={k => setSort({ key: k, dir: 'desc' })} />
          </span>
        )}
        {!!d && (
          <SitesToolbar rk={rk} d={d} mayEdit={mayEdit} onDownloadCreatives={h.downloadCreatives}
            onExternal={h.askExternal} settings={sitesView ? <SitesColumns pref={colPref} onChange={setColPref} /> : null} />
        )}
      </div>
      {(filterNoShows || (d && d.share_sum > 0 && d.share_sum < 0.99)) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 18px 8px', flexWrap: 'wrap' }}>
          {filterNoShows && sitesView && (
            <NoShowsChip ns={ns} shown={rows.length} total={placements.length} onClear={onClearNoShows} />
          )}
          {d && d.share_sum > 0 && d.share_sum < 0.99 && (
            <span style={{ fontSize: 10.5, color: 'var(--warning-text)' }}>
              сумма долей {Math.round(d.share_sum * 100)} % — часть объёма стоит на выключенных</span>
          )}
        </div>
      )}
      {!d && <div style={{ ...NOTE, fontSize: 12 }}>загрузка…</div>}
      {!!d && !placements.length && <div style={{ ...NOTE, fontSize: 12 }}>К этой РК не подключена ни одна площадка.</div>}
      {!!d && !!placements.length && sitesView && (
        <SitesTable rk={rk} d={d} rows={rows} sort={sort} goal={goal} mayEdit={mayEdit} h={h} cols={cols}
          onSort={k => setSort(cur => nextSort(cur, k))} />
      )}
      {!!d && !!placements.length && !sitesView && (
        <ByCreatives placements={placements} goal={goal} mayEdit={mayEdit} tgt={tgt} h={h} />
      )}
    </div>
  )
}

export { SitesPanel }
