// Расхлоп площадки v2 (хендофф 8.6): креативы площадки с ЕРИД, двумя хешами DSP и результатом — факт, клики, CTR.
// Те же данные и действия, что у боевого `CreativeRows` (dashboardKit), плюс три столбца результата: факт и клики
// пары креатив × площадка считает сервер (`app/traffic/expand_view.enrich_creatives`), CTR — там же.
// Код креатива (`ms_title`) — общий для всех его площадок. Хеш РК — один на кампанию, `campaignHash`.
import { EXT_TONE, MONO } from '@/components/salesTableKit'
import { DASH, PlaceActions, creativeCanStart, num } from '@/components/traffic/dashboardKit'
import BannerCheckMark from '@/components/traffic/BannerCheckMark'
import { creativeSystemsOf, ctrTone } from '@/lib/sitesModel.mjs'
import { CAP_V2, CR_GRID_V2, CTR_STYLE, CtrBar, NUM, ctrTitle, pct1, pct2, SysCell, SysLegend } from './sitesBits'

const HEAD = ['Креатив', 'ЕРИД', 'Хеш РК в DSP', 'Хеш креатива в DSP', 'Доля', 'План', 'Факт', 'Клики', 'CTR', 'Статус', 'Системы', '']
const RIGHT = new Set([4, 5, 6, 7, 8])

// Плашка статуса креатива (8.6): согласованный и дальше — спокойная, остальное — тоном «мяч не у нас».
const crChip = (s) => (['согласован', 'запущен', 'пауза'].includes(s)
  ? ['var(--bg-card)', 'var(--border-card)', 'var(--text-secondary)']
  : s === 'отклонён' ? ['var(--danger-tint)', 'var(--danger-border)', 'var(--danger-fg)']
    : ['var(--warning-tint)', 'var(--warning-border)', 'var(--warning-fg)'])

const CreativeLine = ({ c, p, manual, mayEdit, onStatus, campaignHash, goal }) => {
  const tone = ctrTone(c.ctr, goal)
  const [bg, border, fg] = crChip(c.status)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: CR_GRID_V2, gap: 8, alignItems: 'center', minHeight: 36,
      borderTop: '1px solid var(--border-inner)' }}>
      <span style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 1 }}>
        <span style={{ fontSize: 12.5, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          title={c.origin === 'доработка' ? `в эфире доработанная версия сообщения — правка №${c.version_no}` : undefined}>
          {c.name || `креатив №${c.set_no ?? c.creative_no}`}
          {c.origin === 'доработка' && (
            <span style={{ marginLeft: 6, fontSize: 9, padding: '1px 5px', borderRadius: 5,
              background: 'var(--bg-card)', color: 'var(--text-muted)' }}>правка №{c.version_no}</span>
          )}
        </span>
        <span style={{ fontFamily: MONO, fontSize: 9.5, color: 'var(--text-faint)' }}>{c.ms_title || DASH}</span>
      </span>
      <span style={{ fontFamily: MONO, fontSize: 11, color: c.erid ? 'var(--text-primary)' : 'var(--text-disabled)',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.erid || 'ЕРИД нет'}>
        {c.erid || DASH}</span>
      <span title={campaignHash ? 'Кампания в DSP' : 'Кампания в DSP не заведена'}
        style={{ fontFamily: MONO, fontSize: 11, fontWeight: campaignHash ? 700 : 400,
          color: campaignHash ? 'var(--accent-fg)' : 'var(--text-faint)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{campaignHash || 'не заведена'}</span>
      <span title={c.ms_creative_xxhash || 'Креатив в DSP не заведён'}
        style={{ fontFamily: MONO, fontSize: 11, fontWeight: c.ms_creative_xxhash ? 700 : 400,
          color: c.ms_creative_xxhash ? 'var(--accent-fg)' : 'var(--text-faint)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {c.ms_creative_xxhash || 'не заведён'}
        {!!c.ms_creative_xxhash && <BannerCheckMark check={c.banner_check} />}</span>
      <span style={NUM}>{c.share ? pct1(c.share * 100) : DASH}</span>
      <span style={{ ...NUM, fontWeight: 700 }}>{num(c.plan_show)}</span>
      <span style={{ ...NUM, fontWeight: 700 }}>{num(c.fact)}</span>
      <span style={{ ...NUM, color: 'var(--text-secondary)' }}>{num(c.clicks)}</span>
      <span title={ctrTitle(c.ctr, goal)} style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6 }}>
        <CtrBar ctr={c.ctr} tone={tone} />
        <span style={{ ...NUM, ...CTR_STYLE[tone] }}>{pct2(c.ctr)}</span>
      </span>
      <span>
        <span title={(manual || []).includes(c.status) ? '' : 'Ставит согласование креативов'}
          style={{ display: 'inline-flex', alignItems: 'center', height: 20, padding: '0 8px', borderRadius: 6,
            background: bg, border: `1px solid ${border}`, fontSize: 11, fontWeight: 700, color: fg,
            whiteSpace: 'nowrap' }}>{c.status}</span>
      </span>
      {/* Системы креатива — те же полоски, что у площадки, но по самому креативу (владелец 17.11.2026) */}
      <SysCell s={creativeSystemsOf(c, p, EXT_TONE)} />
      <span style={{ justifySelf: 'end' }}>
        {mayEdit && (
          <PlaceActions status={c.status === 'отклонён' ? 'завершена' : c.status} canStart={creativeCanStart(c)}
            onStart={() => onStatus(c, 'запущен')} onPause={() => onStatus(c, 'пауза')}
            onOff={() => onStatus(c, 'отклонён')} />
        )}
      </span>
    </div>
  )
}

/**
 * Таблица креативов под строкой площадки. Не едет при горизонтальном скролле таблицы (8.7): `sticky; left: 0`
 * и ширина контейнера `100cqw`; самой ей тесно меньше 880 px — свой скролл.
 */
export default function SiteCreatives({ rows, place, manual, mayEdit, onStatus, campaignHash, goal }) {
  return (
    <div style={{ position: 'sticky', left: 0, width: '100cqw', boxSizing: 'border-box', overflowX: 'auto',
      padding: '6px 18px 8px 22px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-inner)' }}>
      {!rows || !rows.length ? (
        <div style={{ fontSize: 11.5, color: 'var(--text-faint)', padding: '4px 0' }}>
          Креативов нет: материал этой площадке ещё не отправляли.
        </div>
      ) : (
        <div style={{ minWidth: 880 }}>
          <div style={{ ...CAP_V2, display: 'grid', gridTemplateColumns: CR_GRID_V2, gap: 8, alignItems: 'center',
            padding: '3px 0 5px' }}>
            {HEAD.map((h, i) => (h === 'Системы'
              ? <SysLegend key={h} />
              : <span key={h + i} style={{ textAlign: RIGHT.has(i) ? 'right' : 'left' }}
                title={h === 'CTR' ? 'CTR креатива на этой площадке за период' : undefined}>{h}</span>
            ))}
          </div>
          {rows.map(c => (
            <CreativeLine key={c.id} c={c} p={place || {}} manual={manual} mayEdit={mayEdit} onStatus={onStatus}
              campaignHash={campaignHash} goal={goal} />
          ))}
        </div>
      )}
    </div>
  )
}
