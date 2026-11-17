// Вид «по креативам» v2 (хендофф 8.8): секция на креатив — план, факт, клики, CTR с полосой до 1 % и риской цели,
// «лучший», «в МС N / M», управление креативом целиком; под ним плашки его площадок со ссылкой, статусом, планом,
// CTR пары и галочкой «Скрины запуска сняты».
//
// Группировка — боевая `byCreative` (dashboardKit): комплект креатива, план — СУММА по площадкам (весов у креативов
// нет). «в МС» — как на бою: площадок, где креатив заведён в DSP (есть хеш). Галочка на плашке — та же отметка
// скринов запуска, что была в этом виде (решение владельца 17.11.2026), а не «включено в МС» из макета.
import { MONO } from '@/components/salesTableKit'
import { DASH, PlaceActions, byCreative, num } from '@/components/traffic/dashboardKit'
import AimButton from '@/components/traffic/AimButton'
import safeHref from '@/lib/safeHref'
import { fmtDateTime } from '@/lib/dates'
import { creativeResults, ctrTone } from '@/lib/sitesModel.mjs'
import { CTR_STYLE, CtrBar, StatusDot, ctrTitle, pct2 } from './sitesBits'

const LBL = { color: 'var(--text-faint)' }
const VAL = { fontFamily: MONO, fontSize: 11.5, whiteSpace: 'nowrap' }

const GROUP_TITLES = {
  start: 'Запустить креатив на всех площадках, где он согласован',
  cannot: 'Нет площадок, где креатив согласован или на паузе',
  pause: 'Пауза креатива на всех площадках: доли останутся',
  off: 'Отключить креатив на всех площадках: объём уйдёт остальным креативам',
  offDone: 'Креатив отключён на всех площадках',
}

const SiteChip = ({ pl, goal, mayEdit, onScreens }) => {
  const tone = ctrTone(pl.ctr, goal)
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 30, padding: '0 8px 0 10px',
      background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 9, whiteSpace: 'nowrap' }}>
      {!!pl.domain && (
        <a href={safeHref(`https://${pl.domain}`)} target="_blank" rel="noreferrer" title={`Открыть ${pl.domain} в новой вкладке`}
          style={{ fontSize: 10, color: 'var(--accent-fg)', textDecoration: 'none' }}>↗</a>
      )}
      <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700 }}>{pl.domain || DASH}</span>
      <StatusDot value={pl.status} size={11} />
      <span title={pl.fixed ? 'Объём задан в блоке креатива' : undefined}
        style={{ fontFamily: MONO, fontSize: 11, color: pl.fixed ? 'var(--accent-fg)' : 'var(--text-muted)',
          fontWeight: pl.fixed ? 700 : 400 }}>{pl.fixed ? 'фикс ' : ''}{num(pl.plan_show)}</span>
      {pl.ctr != null && (
        <span title={`CTR этого креатива на площадке за период · ${ctrTitle(pl.ctr, goal)}`}
          style={{ fontFamily: MONO, fontSize: 11, ...CTR_STYLE[tone] }}>{pct2(pl.ctr)}</span>
      )}
      <input type="checkbox" checked={!!pl.screens_done_at} disabled={!mayEdit} aria-label="Скрины запуска сняты"
        title={pl.screens_done_at
          ? `Скрины запуска сняты · ${fmtDateTime(pl.screens_done_at)}${pl.screens_by ? ` · ${pl.screens_by}` : ''}`
          : 'Скрины запуска сняты?'}
        style={{ width: 14, height: 14, margin: 0, cursor: mayEdit ? 'pointer' : 'not-allowed' }}
        onChange={e => onScreens(pl, e.target.checked)} />
    </span>
  )
}

const CreativeSection = ({ g, goal, mayEdit, tgt, h }) => {
  const tone = ctrTone(g.ctr, goal)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '10px 18px 12px',
      borderBottom: '1px solid var(--border-inner)' }}>
      {/* Шапка креатива — сеткой (владелец 17.11.2026): название и причина «Нацелить» в две строки слева, цифры посередине,
          старт/стоп — в колонке постоянной ширины справа, на одном месте у всех креативов. */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto 64px', columnGap: 14, alignItems: 'center', minHeight: 28 }}>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <span style={{ fontSize: 13, fontWeight: 800, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{g.name || 'без названия'}</span>
            <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{g.ms_title || DASH}</span>
            {/* Нацеливание для скриншотов после старта (01.10.2026) — на текущую версию комплекта. */}
            {!!g.set_id && <AimButton setId={g.set_id} tgtState={tgt?.state} offWhy={g.aim_off} compact hideWhy />}
          </span>
          {!!g.aim_off && (
            <span title={g.aim_off} style={{ fontSize: 11.5, lineHeight: 1.35, color: 'var(--text-muted)', overflow: 'hidden',
              display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{g.aim_off}</span>
          )}
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10, whiteSpace: 'nowrap' }}>
          <span style={VAL}><span style={LBL}>план </span><b>{num(g.plan)}</b></span>
          <span style={VAL}><span style={LBL}>факт </span><b>{num(g.fact)}</b></span>
          <span style={VAL}><span style={LBL}>клики </span><b>{num(g.clicks)}</b></span>
          <span title={g.ctr == null ? 'Показов ещё нет' : `CTR креатива по всем его площадкам за период · ${ctrTitle(g.ctr, goal)}`}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 7, whiteSpace: 'nowrap' }}>
            <span style={VAL}><span style={LBL}>CTR </span><b style={CTR_STYLE[tone]}>{pct2(g.ctr)}</b></span>
            <CtrBar ctr={g.ctr} tone={tone} width={54} height={6} goal={goal} />
            <span style={{ display: 'inline-flex', alignItems: 'center', height: 18, padding: '0 7px', borderRadius: 6,
              background: 'var(--ok-tint)', border: '1px solid var(--ok-border)', fontSize: 10.5, fontWeight: 700,
              color: 'var(--ok-fg)', visibility: g.best ? 'visible' : 'hidden' }}>лучший</span>
          </span>
          <span title="Площадок, где креатив заведён в DSP"
            style={{ ...VAL, fontWeight: 700, color: g.live ? 'var(--accent-fg)' : 'var(--text-faint)' }}>
            в МС {g.live} / {g.places.length}</span>
        </span>
        {/* Креатив целиком, на всех площадках РК (15.10.2026): крутит, если крутит хоть одна пара. */}
        <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
          {mayEdit && (
            <PlaceActions
              status={g.places.some(c => c.status === 'запущен') ? 'запущен'
                : g.places.every(c => c.status === 'отклонён') ? 'завершена' : 'пауза'}
              canStart={g.places.some(c => ['согласован', 'пауза'].includes(c.status))}
              onStart={() => h.setCreativeGroupStatus(g, 'запущен')}
              onPause={() => h.setCreativeGroupStatus(g, 'пауза')}
              onOff={() => h.setCreativeGroupStatus(g, 'отклонён')}
              titles={GROUP_TITLES} />
          )}
        </span>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {g.places.map(pl => (
          <SiteChip key={pl.id} pl={pl} goal={goal} mayEdit={mayEdit} onScreens={h.setCreativeScreens} />
        ))}
      </div>
    </div>
  )
}

export default function ByCreatives({ placements, goal, mayEdit, tgt, h }) {
  const groups = creativeResults(byCreative(placements))
  return (
    <div style={{ borderTop: '1px solid var(--border-card)' }}>
      {groups.map(g => <CreativeSection key={g.key} g={g} goal={goal} mayEdit={mayEdit} tgt={tgt} h={h} />)}
      <div style={{ padding: '9px 18px 11px', fontSize: 11, lineHeight: 1.45, color: 'var(--text-faint)' }}>
        Обратный вид суммирует по площадкам. Объём идёт «вес площадки → план площадки → поровну по креативам»;
        весов у креативов нет.
      </div>
    </div>
  )
}
