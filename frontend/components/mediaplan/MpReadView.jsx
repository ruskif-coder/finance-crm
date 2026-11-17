/**
 * Медиаплан ТОЛЬКО ДЛЯ ЧТЕНИЯ — один компонент на карточку сделки и расхлоп реестра медиапланов (хендофф
 * design_handoff_mp_registry, 17.11.2026: «те же блоки, тем же компонентом»).
 *
 * До выноса эти блоки жили разметкой прямо в pages/sales/deals/[id].js; второй экран с теми же таблицами значил бы
 * вторую копию формул прогноза, а формулы прогноза в проекте уже расходились (см. lib/mpRow).
 *
 * Блоки сверху вниз: параметры кампании · размещение · прогноз (с «Итого по МП», как в конструкторе) · доп. услуги ·
 * бриф/таргетинг. Правка — только в конструкторе, по ссылке «Открыть МП →».
 */
import { MONO } from '@/components/salesTableKit'
import { grp, rub2 } from '@/lib/salesFormat'
import { num as mpNum, rowClicks, rowImp, rowNet } from '@/lib/mpRow'

const CAPS = { fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)' }
const SUBCAPS = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }
const INV_LABEL = { web: 'Web', app: 'IN-App', cross: 'Кросс-девайс' }
const MODE_LBL = { full: '100 %', half: '50 %', bonus: 'бонус', fix: 'фикс ₽' }
const TG_TITLES = { audience: 'Аудитория', buys: 'Покупают', interests: 'Интересы', behavior: 'Поведение', competitors: 'Конкуренты' }

// форматы — общие (lib/salesFormat), своих не держим
const rub = (v) => (v == null ? '—' : `${rub2(v)} ₽`)
const int = grp
// С разрядами: доход и CPO бывают шестизначными, и «549006,44» без пробелов читался с трудом.
const dec = rub2

/* Сетки. Размещение — те же доли, что были на карточке. Прогноз: первая колонка фиксированная (иначе на широком экране
   имя строки забирает место у цифр), 15 колонок цифр; минимум — под левую колонку карточки (130 + 15×62 + зазоры). */
const PL_GRID = '1.6fr 0.8fr 0.75fr 0.55fr 0.95fr 0.85fr 0.6fr 1.15fr 1.15fr'
const FC_GRID = '130px repeat(15, minmax(0, 1fr))'
const FC_GAP = 7
const FC_HEADS = ['Частота', 'Охват', 'Показы', 'CTR %', 'Клики', 'CPM ₽', 'CPC ₽',
  'CPU ₽', 'CR %', 'Чеки', 'CPO ₽', 'Цена ₽', 'Доход ₽', 'ROI %', 'SOV %']
const FC_NUM = { fontFamily: MONO, fontSize: 11, textAlign: 'right', whiteSpace: 'nowrap' }

/** Строки плана с деньгами и прогнозом. `vat` — доля (0.22) или null, если ставка не задана: тогда сумм с НДС нет. */
export function planLines(plan, vat) {
  const withVat = (x) => (x == null || vat == null ? null : Math.round(x * (1 + vat) * 100) / 100)
  return ((plan && plan.rows) || []).map(r => {
    // Сумма, показы, клики — общей арифметикой строки (lib/mpRow): у Фикса в объёме штуки, у CPC — клики.
    const net = rowNet(r.model, r.volume, r.unit_price, r.discount)
    const fc = r.forecast || {}
    const imp = rowImp(r.model, r.volume, fc)
    const freq = mpNum(fc.freq)
    const reach = freq > 0 ? imp / freq : 0
    const clicks = rowClicks(r.model, r.volume, fc)
    const cr = mpNum(fc.cr) / 100
    const checks = clicks * cr
    const price = mpNum(fc.price)
    const gross = withVat(net)
    const revenue = checks * price
    return {
      position: r.position, format: r.format, model: r.model, inventory: r.inventory,
      volume: r.volume || 0, unit: r.unit_price || 0, discount: r.discount || 0,
      net, gross, imp, freq, reach, clicks, cr, checks, price, revenue, sov: mpNum(fc.sov),
      roi: gross > 0 ? (revenue - gross) / gross : NaN,
    }
  })
}

/** Итоги плана: объём, показы, суммы — и строка «Итого по МП» прогноза по тем же правилам, что в конструкторе
    (частота — наибольшая из строк, CTR/CR — от сумм, ROI — от суммы с НДС). */
export function planTotals(lines, vat) {
  const s = (k) => lines.reduce((a, r) => a + (r[k] || 0), 0)
  const tNet = s('net')
  const tGross = vat == null ? null : Math.round(tNet * (1 + vat) * 100) / 100
  const imp = s('imp'), clicks = s('clicks'), reach = s('reach'), checks = s('checks'), revenue = s('revenue')
  return {
    tVol: s('volume'), tImp: imp, tNet, tGross, reach, clicks, checks, revenue,
    freq: lines.reduce((a, r) => Math.max(a, r.freq || 0), 0),
    ctr: imp ? clicks / imp : 0, cr: clicks ? checks / clicks : 0, sov: s('sov'),
    roi: tGross > 0 ? (revenue - tGross) / tGross : NaN,
  }
}

const Head = ({ title, sub, right }) => (
  <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
    <span style={CAPS}>{title}</span>
    {sub && <span style={SUBCAPS}>{sub}</span>}
    {right && <span style={{ marginLeft: 'auto' }}>{right}</span>}
  </div>
)

/** «Параметры кампании»: даты РК текстом и плашка реквизитов. Отдельно — карточка сделки без плана показывает её
    над кнопкой «Создать медиаплан». */
export function CampaignParams({ params = [], dates }) {
  return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <Head title="Параметры кампании" right={dates ? (
          <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 10 }}>
            <span style={SUBCAPS}>Старт — стоп РК</span>
            <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--text-primary)' }}>{dates}</span>
          </span>) : null} />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gridTemplateRows: 'repeat(2,auto)', gridAutoFlow: 'column', gap: '0 28px',
          background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 12, padding: '4px 14px 8px' }}>
          {params.map(([label, value], i) => (
            <span key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '6px 0', borderTop: i % 2 ? '1px solid var(--border-row)' : 'none' }}>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
              <span style={{ marginLeft: 'auto', fontSize: 12.5, fontWeight: 600, textAlign: 'right', color: value ? 'var(--text-primary)' : 'var(--text-faint)' }}>{value || '—'}</span>
            </span>
          ))}
        </div>
      </div>
  )
}

const roiTone = (v) => (v >= 0 ? 'var(--income-fg)' : 'var(--danger-fg)')
const roiText = (v) => (Number.isFinite(v) ? `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(0)}` : '—')

/**
 * @param plan      полный план (`GET /sales/media-plans/{id}`)
 * @param vatPct    ставка, по которой считать «с НДС» (у плана — своя `vat_rate`), или null — «ставка не задана»
 * @param params    [[подпись, значение], …] — плашка «Параметры кампании», 3 колонки × 2 строки по столбцам
 * @param dates     «01.11.2026 — 30.11.2026» — текстом, а не полями ввода: здесь ничего не правится
 * @param openHref  ссылка «Открыть МП →»
 */
export default function MpReadView({ plan, vatPct, params = [], dates, openHref }) {
  const vat = vatPct != null ? vatPct / 100 : null
  const lines = planLines(plan, vat)
  const T = planTotals(lines, vat)
  const extras = (plan && plan.extras) || []
  const extrasTotal = extras.reduce((a, e) => a + (e.total || 0), 0)
  const withVat = (x) => (x == null || vat == null ? null : Math.round(x * (1 + vat) * 100) / 100)
  const targeting = Object.entries((plan && plan.targeting) || {})
    .map(([g, arr]) => ({ group: TG_TITLES[g] || g, value: (arr || []).map(v => (typeof v === 'string' ? v : v && v.value)).filter(Boolean).join(' · ') }))
    .filter(x => x.value)
  const open = openHref
    ? <a href={openHref} style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--accent-fg)', textDecoration: 'none', whiteSpace: 'nowrap' }}>Открыть МП →</a>
    : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <CampaignParams params={params} dates={dates} />

      {/* размещение */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7, padding: '14px 0', borderTop: '1px solid var(--border-card)', borderBottom: '1px solid var(--border-card)' }}>
        <Head title="Размещение" right={open} />
        {!lines.length && <div style={{ fontSize: 12, color: 'var(--text-faint)', padding: '6px 0' }}>В медиаплане пока нет строк размещения.</div>}
        {!!lines.length && (
          <div style={{ overflowX: 'auto' }}>
            <div style={{ minWidth: 640 }}>
              <div style={{ display: 'grid', gridTemplateColumns: PL_GRID, gap: 9, paddingBottom: 7, borderBottom: '1px solid var(--border-card)', ...SUBCAPS }}>
                <span>Позиция</span><span>Формат</span><span>Инвентарь</span><span>Модель</span><span style={{ textAlign: 'right' }}>Объём</span><span style={{ textAlign: 'right' }}>Цена/ед.</span><span style={{ textAlign: 'right' }}>Скидка</span><span style={{ textAlign: 'right' }}>До НДС</span><span style={{ textAlign: 'right' }}>С НДС</span>
              </div>
              {lines.map((l, i) => (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: PL_GRID, gap: 9, alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border-row)' }}>
                  <span style={{ fontSize: 11.5, fontWeight: 600, lineHeight: 1.25 }}>{l.position}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{l.format}</span>
                  <span style={{ fontFamily: MONO, fontSize: 10.5, color: l.inventory ? 'var(--text-secondary)' : 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{INV_LABEL[l.inventory] || '—'}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--accent-fg)' }}>{l.model}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right' }}>{int(l.volume)}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', textAlign: 'right' }}>{dec(l.unit)} ₽</span>
                  <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)', textAlign: 'right' }}>{Math.round((l.discount || 0) * 100)} %</span>
                  <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, textAlign: 'right' }}>{rub(l.net)}</span>
                  <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--accent-fg)', textAlign: 'right' }}>{rub(l.gross)}</span>
                </div>
              ))}
              <div style={{ display: 'grid', gridTemplateColumns: PL_GRID, gap: 9, alignItems: 'center', paddingTop: 7 }}>
                <span style={{ ...SUBCAPS, fontWeight: 700, color: 'var(--text-muted)' }}>Итого</span>
                <span /><span /><span />
                <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, textAlign: 'right' }}>{int(T.tVol)}</span>
                <span /><span />
                <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, textAlign: 'right' }}>{rub(T.tNet)}</span>
                <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--accent-fg)', textAlign: 'right' }}>{rub(T.tGross)}</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* прогноз — те же формулы, что в конструкторе; строка «Итого по МП» как там же */}
      {!!lines.length && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          <Head title="Прогнозные показатели" sub="гарантируются показы и CPM" />
          <div style={{ overflowX: 'auto' }}>
            <div style={{ minWidth: 1165 }}>
              <div style={{ display: 'grid', gridTemplateColumns: FC_GRID, gap: FC_GAP, paddingBottom: 7, borderBottom: '1px solid var(--border-card)', ...SUBCAPS }}>
                <span>Строка</span>
                {FC_HEADS.map(h => <span key={h} style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>{h}</span>)}
              </div>
              {lines.map((r, i) => (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: FC_GRID, gap: FC_GAP, alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border-row)' }}>
                  <span title={r.position} style={{ fontSize: 11.5, fontWeight: 600, lineHeight: 1.25, overflow: 'hidden' }}>{r.position}</span>
                  <span style={{ ...FC_NUM, color: 'var(--text-secondary)' }}>{r.freq ? int(r.freq) : '—'}</span>
                  <span style={FC_NUM}>{r.reach ? int(r.reach) : '—'}</span>
                  <span style={{ ...FC_NUM, fontWeight: 700, color: 'var(--income-fg)' }}>{r.imp ? int(r.imp) : '—'}</span>
                  <span style={{ ...FC_NUM, color: 'var(--text-secondary)' }}>{r.imp && r.clicks ? dec(r.clicks / r.imp * 100) : '—'}</span>
                  <span style={{ ...FC_NUM, fontWeight: 700, color: 'var(--income-fg)' }}>{r.clicks ? int(r.clicks) : '—'}</span>
                  <span style={{ ...FC_NUM, color: 'var(--accent-fg)' }}>{r.imp ? dec(r.net / r.imp * 1000) : '—'}</span>
                  <span style={{ ...FC_NUM, color: 'var(--accent-fg)' }}>{r.clicks ? dec(r.net / r.clicks) : '—'}</span>
                  <span style={{ ...FC_NUM, color: 'var(--accent-fg)' }}>{r.reach ? dec(r.net / r.reach) : '—'}</span>
                  <span style={{ ...FC_NUM, color: 'var(--text-secondary)' }}>{r.cr ? dec(r.cr * 100) : '—'}</span>
                  <span style={{ ...FC_NUM, color: 'var(--text-secondary)' }}>{r.checks ? int(r.checks) : '—'}</span>
                  <span style={{ ...FC_NUM, color: 'var(--accent-fg)' }}>{r.checks ? dec(r.net / r.checks) : '—'}</span>
                  <span style={{ ...FC_NUM, color: 'var(--text-secondary)' }}>{r.price ? dec(r.price) : '—'}</span>
                  <span style={{ ...FC_NUM, fontWeight: 700, color: 'var(--income-fg)' }}>{r.revenue ? dec(r.revenue) : '—'}</span>
                  <span style={{ ...FC_NUM, fontWeight: 700, color: roiTone(r.roi) }}>{roiText(r.roi)}</span>
                  <span style={{ ...FC_NUM, color: 'var(--text-secondary)' }}>{r.sov ? dec(r.sov) : '—'}</span>
                </div>
              ))}
              <div style={{ display: 'grid', gridTemplateColumns: FC_GRID, gap: FC_GAP, alignItems: 'center', padding: '7px 0 0' }}>
                <span style={{ fontSize: 11.5, fontWeight: 800, color: 'var(--text-secondary)' }}>Итого по МП</span>
                <span style={{ ...FC_NUM, fontWeight: 700 }}>{T.freq ? String(T.freq).replace('.', ',') : '—'}</span>
                <span style={{ ...FC_NUM, fontWeight: 700 }}>{T.reach ? int(T.reach) : '—'}</span>
                <span style={{ ...FC_NUM, fontWeight: 800, color: 'var(--income-fg)' }}>{T.tImp ? int(T.tImp) : '—'}</span>
                <span style={{ ...FC_NUM, fontWeight: 700 }}>{T.ctr ? dec(T.ctr * 100) : '—'}</span>
                <span style={{ ...FC_NUM, fontWeight: 800, color: 'var(--income-fg)' }}>{T.clicks ? int(T.clicks) : '—'}</span>
                <span style={{ ...FC_NUM, fontWeight: 700, color: 'var(--accent-fg)' }}>{T.tImp ? dec(T.tNet / T.tImp * 1000) : '—'}</span>
                <span style={{ ...FC_NUM, fontWeight: 700, color: 'var(--accent-fg)' }}>{T.clicks ? dec(T.tNet / T.clicks) : '—'}</span>
                <span style={{ ...FC_NUM, fontWeight: 700, color: 'var(--accent-fg)' }}>{T.reach ? dec(T.tNet / T.reach) : '—'}</span>
                <span style={{ ...FC_NUM, fontWeight: 700 }}>{T.cr ? dec(T.cr * 100) : '—'}</span>
                <span style={{ ...FC_NUM, fontWeight: 700 }}>{T.checks ? int(T.checks) : '—'}</span>
                <span style={{ ...FC_NUM, fontWeight: 700, color: 'var(--accent-fg)' }}>{T.checks ? dec(T.tNet / T.checks) : '—'}</span>
                <span style={{ ...FC_NUM, color: 'var(--text-faint)' }}>—</span>
                <span style={{ ...FC_NUM, fontWeight: 800, color: 'var(--income-fg)' }}>{T.revenue ? dec(T.revenue) : '—'}</span>
                <span style={{ ...FC_NUM, fontWeight: 800, color: roiTone(T.roi) }}>{roiText(T.roi)}</span>
                <span style={{ ...FC_NUM, fontWeight: 700 }}>{T.sov ? dec(T.sov) : '—'}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* доп. услуги */}
      {extras.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 14, borderTop: '1px solid var(--border-card)' }}>
          <span style={CAPS}>Дополнительные услуги</span>
          {extras.map((e, i) => (
            <span key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 14, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
              <span style={{ fontSize: 11.5, fontWeight: 600 }}>{e.name || '—'}</span>
              <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{e.period || ''}{e.mode ? ` · ${MODE_LBL[e.mode] || e.mode}` : ''}</span>
              <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)', textDecoration: (e.total || 0) < (e.price || 0) ? 'line-through' : 'none' }}>{rub(e.price || 0)}</span>
              <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--income-fg)', minWidth: 96, textAlign: 'right' }}>{rub(e.total || 0)}</span>
              {/* с НДС — от «итого» (что в счёте), а не от прайса */}
              <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--accent-fg)', minWidth: 104, textAlign: 'right' }}>{rub(withVat(e.total || 0))}</span>
            </span>
          ))}
          <span style={{ display: 'flex', alignItems: 'baseline', gap: 12, paddingTop: 7 }}>
            <span style={{ ...SUBCAPS, fontWeight: 700, color: 'var(--text-muted)' }}>Итого доп. услуги · входят в сумму сделки</span>
            <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--income-fg)' }}>{rub(extrasTotal)}</span>
            <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--accent-fg)', minWidth: 104, textAlign: 'right' }}>{rub(withVat(extrasTotal))}</span>
          </span>
        </div>
      )}

      {/* бриф · таргетинг */}
      {targeting.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 14, borderTop: '1px solid var(--border-card)' }}>
          <Head title="Бриф · таргетинг" right={<span style={SUBCAPS}>из медиаплана</span>} />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 24px' }}>
            {targeting.map((t, i) => (
              <span key={i} style={{ display: 'flex', gap: 12, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
                <span style={{ flex: '0 0 84px', ...SUBCAPS, color: 'var(--text-muted)', lineHeight: 1.45 }}>{t.group}</span>
                <span style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.45 }}>{t.value}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
