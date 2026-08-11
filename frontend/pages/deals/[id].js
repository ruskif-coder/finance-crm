import { useState, useEffect } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import api, { auth } from '../../lib/api'
import { MONO, UI } from '../../components/salesTableKit'
import { BITRIX_DEAL_URL } from '../../lib/salesLayers'

// ── Карточка сделки /deals/[id] ──
// Дизайн строго по хендоффу docs/карточка сделки (design_handoff_deal_card): токены
// нашей дизайн-системы (var(--*)), шрифты Manrope/JetBrains Mono. Данные по МП
// (размещение, прогноз, доп. услуги, таргетинг) — пока из ШАБЛОНА, до конструктора МП;
// остальное — реальные данные сделки. Деньги: сумма реальная, оплачено/остаток/срок —
// заглушки (привязки платежей к сделке ещё нет).

const VAT = 0.22
const rub = (v) => (v == null ? '—' : v.toLocaleString('ru-RU') + ' ₽')
const num = (v) => (v == null ? '—' : v.toLocaleString('ru-RU'))
const dec = (v) => v.toFixed(2).replace('.', ',')
const initials = (name) => (name ? name.trim().split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase() : '—')

// время события в московском времени (UTC+3), как в Журнале действий
const fmtWhen = (str) => {
  if (!str) return ''
  const s = /[zZ]|[+-]\d{2}:?\d{2}$/.test(str) ? str : str + 'Z'
  return new Date(s).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow', day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
}
const EVENT_COLOR = {
  create_deal: 'var(--text-faint)', patch_sales_deal: 'var(--dot-current-dz)',
  save_deal_brief: 'var(--income)', push_deal_to_bitrix: 'var(--accent)', sync_deal_from_bitrix: 'var(--accent)',
}

// ── ШАБЛОН данных медиаплана (заменится живыми из конструктора МП) ──
const TPL_SRC = [
  { position: 'Simb-ad Альфарм — Таргет', format: 'Banners', model: 'CPM', volume: 2440000, unit: 280, net: 683200, freq: 3, reach: 813333, clicks: 29280 },
  { position: 'Simb-ad Альфарм — Ретаргет', format: 'Banners', model: 'CPM', volume: 487400, unit: 280, net: 136472, freq: 3, reach: 162467, clicks: 5849 },
]
const TPL_EXTRAS = [
  { name: 'Sales lift отчёт*', period: 'первый месяц размещения', price: 150000, total: 0 },
  { name: 'Brand lift исследование', period: 'по итогам кампании', price: 180000, total: 90000 },
]
const TPL_BONUS = '* Бонусом при условии: от 500 000 ₽ до НДС на бренд в месяц при первом размещении бренда или при размещении от 1,5 млн ₽ до НДС в месяц на бренд.'
const TPL_TARGETING = [
  { group: 'Аудитория', value: 'Ж/М 30–60 · гео РФ' },
  { group: 'Покупают', value: 'витамины группы B · препараты при нейропатии · обезболивающие при болях в спине · средства при диабетической полинейропатии' },
  { group: 'Интересы', value: 'неврология · здоровье спины и суставов · медицина и здоровье' },
  { group: 'Поведение', value: 'сайты аптек и онлайн-заказа лекарств · медицинские порталы · сервисы записи к неврологу · статьи о нейропатии' },
  { group: 'Конкуренты', value: 'Комбилипен · Нейромультивит · Нейробион · Бенфогамма · Тиогамма' },
]
const TPL_DOCS = [
  ['Бриф', 'Мильгамма_Альфарм.pdf · 05.07.26', true, 'Открыть'],
  ['Медиаплан', 'MP_Woerwag_v3.xlsx · 18.07.26', true, 'Открыть'],
  ['Доп. соглашение', 'ДС-64 · 02.07.26', true, 'Открыть'],
  ['Счёт', 'не выставлен', false, 'Создать'],
  ['Отчёт', 'после размещения', false, 'Загрузить'],
  ['Акт', 'не загружен', false, 'Загрузить'],
]

// стилевые примитивы карточки (из эталона)
const CARD = { background: 'var(--bg-card)', border: '1px solid var(--border-card)', boxShadow: 'var(--shadow-card)', borderRadius: 18 }
const CAPS = { fontFamily: MONO, fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)' }
const SUBCAPS = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-faint)' }
const MONEY_LBL = { fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }
const PL_GRID = '1.8fr 0.9fr 0.6fr 1fr 0.9fr 0.7fr 1.2fr 1.2fr'
const FC_GRID = '2.4fr repeat(8,1fr)'

export default function DealCard() {
  const router = useRouter()
  const { id } = router.query
  const [deal, setDeal] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (typeof window === 'undefined' || !id) return
    if (!localStorage.getItem('token')) { router.push('/login'); return }
    setLoading(true)
    api.get(`/sales/deals/${id}`, auth())
      .then(r => setDeal(r.data))
      .catch(e => setErr(e.response?.status === 404 ? 'Сделка не найдена' : (e.response?.data?.detail || 'Ошибка загрузки')))
      .finally(() => setLoading(false))
    api.get(`/sales/deals/${id}/history`, auth()).then(r => setHistory(r.data.items || [])).catch(() => {})
  }, [id])

  // производные МП из шаблона
  const lines = TPL_SRC.map(l => ({ ...l, gross: Math.round(l.net * (1 + VAT)) }))
  const tVol = TPL_SRC.reduce((a, r) => a + r.volume, 0)
  const tNet = TPL_SRC.reduce((a, r) => a + r.net, 0)
  const extrasTotal = TPL_EXTRAS.reduce((a, e) => a + e.total, 0)

  const wrap = { minHeight: '100vh', boxSizing: 'border-box', padding: '26px 32px 40px', background: 'var(--bg-canvas)', display: 'flex', justifyContent: 'center', fontFamily: UI, color: 'var(--text-primary)' }

  if (loading) return <div style={wrap}><div style={{ color: 'var(--text-muted)', marginTop: 40 }}>Загрузка…</div></div>
  if (err) return <div style={wrap}><div style={{ marginTop: 40 }}><div style={{ color: 'var(--danger)', marginBottom: 12 }}>{err}</div><a href="/sales" style={{ color: 'var(--accent)' }}>← к реестру сделок</a></div></div>

  const d = deal
  const title = [d.advertiser, d.brand].filter(Boolean).join(' · ') || d.title || '—'
  const meta = [d.agency, d.product, d.period, d.account_manager && `аккаунт ${d.account_manager}`, d.sales_rep && `продавец ${d.sales_rep}`].filter(Boolean).join(' · ')
  const dateVal = (x) => (x ? String(x).slice(0, 10) : '')

  const params = [
    ['Агентство', d.agency], ['Рекламодатель', d.advertiser], ['Бренд', d.brand],
    ['Плательщик', d.payer], ['Период размещения', d.period ? `месяц · ${d.period}` : '—'], ['Гео', '—'],
  ]
  const team = [
    { name: d.sales_rep, role: 'Продавец', bg: 'var(--accent-tint)', fg: 'var(--accent)' },
    { name: d.account_manager, role: 'Аккаунт', bg: '#E6F5EF', fg: 'var(--income)' },
    { name: null, role: 'Трафик', bg: '#F1EDFC', fg: '#7B62D6' },
  ]
  const links = [
    { name: `Контрагент ${d.payer || ''}`.trim(), href: d.counterparty_id ? `/counterparty/${d.counterparty_id}` : null, dot: 'var(--accent)' },
    { name: 'Медиаплан', href: null, dot: 'var(--income)' },
    { name: 'Сделка в Битриксе', href: (d.bitrix_id && !String(d.bitrix_id).startsWith('local-')) ? BITRIX_DEAL_URL(d.bitrix_id) : null, dot: '#8B7BE8' },
    { name: `Дебиторка ${rub(d.amount)}`, href: '/receivables', dot: 'var(--dot-current-dz)' },
  ]

  return (
    <>
      <Head><title>{title} · сделка #{d.bitrix_id || d.id}</title></Head>
      <div style={wrap}>
        <div style={{ width: '100%', maxWidth: 1120, display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* назад */}
          <a href="/sales" style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>← к реестру сделок</a>

          {/* ── Шапка ── */}
          <div style={{ ...CARD, padding: '22px 26px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, flexWrap: 'wrap' }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0 }}>
                <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 9 }}>
                  <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--accent)' }}>#{d.bitrix_id || d.id}</span>
                  <span style={{ fontSize: 21, fontWeight: 700, letterSpacing: '-0.02em' }}>{title}</span>
                </span>
                <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{meta || '—'}</span>
              </span>
              <button onClick={() => router.push(`/deals/mp/new?deal=${d.id}`)} title="Создать медиаплан из сделки — реквизиты и бриф подставятся автоматически"
                style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 10, padding: '9px 15px', fontSize: 13, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' }}>+ МП</button>
              {d.bitrix_stage && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: 'var(--warning-tint)', color: '#B26A0C', borderRadius: 10, padding: '7px 13px', fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--warning)' }} />{d.bitrix_stage}
                </span>
              )}
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 26, flexWrap: 'wrap', paddingTop: 2 }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={MONEY_LBL}>Сумма сделки · размещение + доп. услуги</span>
                <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1, whiteSpace: 'nowrap' }}>{rub(d.amount)}</span>
              </span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingLeft: 26, borderLeft: '1px solid var(--border-inner)' }}>
                <span style={MONEY_LBL}>Оплачено</span>
                <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700, color: 'var(--income)', whiteSpace: 'nowrap' }}>{rub(0)}</span>
              </span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={MONEY_LBL}>Остаток</span>
                <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700, color: 'var(--warning)', whiteSpace: 'nowrap' }}>{rub(d.amount)}</span>
              </span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 4, marginLeft: 'auto', textAlign: 'right' }}>
                <span style={MONEY_LBL}>Срок оплаты</span>
                <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: 'var(--text-faint)' }}>—</span>
              </span>
            </div>

            <span style={{ display: 'block', height: 6, borderRadius: 3, background: 'var(--border-inner)', overflow: 'hidden' }}>
              <span style={{ display: 'block', height: 6, width: '0%', borderRadius: 3, background: 'var(--income)' }} />
            </span>
          </div>

          {/* ── Две колонки ── */}
          <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start', flexWrap: 'wrap' }}>

            {/* левая: медиаплан */}
            <div style={{ flex: 1, minWidth: 320, ...CARD, padding: '22px 26px 20px', display: 'flex', flexDirection: 'column', gap: 18 }}>

              {/* параметры кампании */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <span style={CAPS}>Параметры кампании</span>
                  <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <span style={SUBCAPS}>Старт — стоп РК</span>
                    <input type="date" defaultValue={dateVal(d.period_from)} readOnly style={{ height: 30, boxSizing: 'border-box', padding: '0 9px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 9, fontFamily: MONO, fontSize: 11.5, fontWeight: 600, color: 'var(--text-primary)', outline: 'none' }} />
                    <span style={{ color: '#C7D0E8' }}>→</span>
                    <input type="date" defaultValue={dateVal(d.period_to)} readOnly style={{ height: 30, boxSizing: 'border-box', padding: '0 9px', background: 'var(--bg-card)', border: '1px solid var(--border-card)', borderRadius: 9, fontFamily: MONO, fontSize: 11.5, fontWeight: 600, color: 'var(--text-primary)', outline: 'none' }} />
                  </span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gridTemplateRows: 'repeat(3,auto)', gridAutoFlow: 'column', gap: '0 28px' }}>
                  {params.map(([label, value], i) => (
                    <span key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
                      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
                      <span style={{ marginLeft: 'auto', fontSize: 12.5, fontWeight: 600, textAlign: 'right', color: value ? 'var(--text-primary)' : 'var(--text-faint)' }}>{value || '—'}</span>
                    </span>
                  ))}
                </div>
              </div>

              {/* размещение (ШАБЛОН) */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7, padding: '14px 0', borderTop: '1px solid var(--border-card)', borderBottom: '1px solid var(--border-card)' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
                  <span style={CAPS}>Размещение</span>
                  <span style={SUBCAPS}>шаблон · гео РФ · кросс-девайс · период месяц</span>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <div style={{ minWidth: 640 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: PL_GRID, gap: 9, paddingBottom: 7, borderBottom: '1px solid var(--border-card)', ...SUBCAPS }}>
                      <span>Позиция</span><span>Формат</span><span>Модель</span><span style={{ textAlign: 'right' }}>Объём</span><span style={{ textAlign: 'right' }}>Цена/ед.</span><span style={{ textAlign: 'right' }}>Скидка</span><span style={{ textAlign: 'right' }}>До НДС</span><span style={{ textAlign: 'right' }}>С НДС</span>
                    </div>
                    {lines.map((l, i) => (
                      <div key={i} style={{ display: 'grid', gridTemplateColumns: PL_GRID, gap: 9, alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border-row)' }}>
                        <span style={{ fontSize: 11.5, fontWeight: 600, lineHeight: 1.25 }}>{l.position}</span>
                        <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{l.format}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--accent)' }}>{l.model}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right' }}>{num(l.volume)}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', textAlign: 'right' }}>{dec(l.unit)} ₽</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)', textAlign: 'right' }}>0 %</span>
                        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, textAlign: 'right' }}>{rub(l.net)}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: 'var(--accent)', textAlign: 'right' }}>{rub(l.gross)}</span>
                      </div>
                    ))}
                    <div style={{ display: 'grid', gridTemplateColumns: PL_GRID, gap: 9, alignItems: 'center', paddingTop: 7 }}>
                      <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Итого</span>
                      <span /><span />
                      <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, textAlign: 'right' }}>{num(tVol)}</span>
                      <span /><span />
                      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, textAlign: 'right' }}>{rub(tNet)}</span>
                      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: 'var(--accent)', textAlign: 'right' }}>{rub(Math.round(tNet * (1 + VAT)))}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* прогнозные показатели (ШАБЛОН) */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
                  <span style={CAPS}>Прогнозные показатели</span>
                  <span style={SUBCAPS}>гарантируются показы и CPM</span>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <div style={{ minWidth: 640 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: FC_GRID, gap: 9, paddingBottom: 7, borderBottom: '1px solid var(--border-card)', ...SUBCAPS }}>
                      <span>Строка</span><span style={{ textAlign: 'right' }}>Частота</span><span style={{ textAlign: 'right' }}>Охват</span><span style={{ textAlign: 'right' }}>Показы</span><span style={{ textAlign: 'right' }}>CTR</span><span style={{ textAlign: 'right' }}>Клики</span><span style={{ textAlign: 'right' }}>CPM</span><span style={{ textAlign: 'right' }}>CPC</span><span style={{ textAlign: 'right' }}>CPU</span>
                    </div>
                    {TPL_SRC.map((r, i) => (
                      <div key={i} style={{ display: 'grid', gridTemplateColumns: FC_GRID, gap: 9, alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border-row)' }}>
                        <span style={{ fontSize: 11.5, fontWeight: 600, lineHeight: 1.25 }}>{r.position}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', textAlign: 'right' }}>{num(r.freq)}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, textAlign: 'right' }}>{num(r.reach)}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--income)', textAlign: 'right' }}>{num(r.volume)}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--text-secondary)', textAlign: 'right' }}>{dec(r.clicks / r.volume * 100)} %</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: 'var(--income)', textAlign: 'right' }}>{num(r.clicks)}</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--accent)', textAlign: 'right' }}>{dec(r.net / r.volume * 1000)} ₽</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--accent)', textAlign: 'right' }}>{dec(r.net / r.clicks)} ₽</span>
                        <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--accent)', textAlign: 'right' }}>{dec(r.net / r.reach)} ₽</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* доп. услуги (ШАБЛОН) */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 14, borderTop: '1px solid var(--border-card)' }}>
                <span style={CAPS}>Дополнительные услуги</span>
                {TPL_EXTRAS.map((e, i) => (
                  <span key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 14, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
                    <span style={{ fontSize: 11.5, fontWeight: 600 }}>{e.name}</span>
                    <span style={{ fontFamily: MONO, fontSize: 10, color: 'var(--text-faint)' }}>{e.period}</span>
                    <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11, color: 'var(--text-faint)', textDecoration: 'line-through' }}>{rub(e.price)}</span>
                    <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: 'var(--income)', minWidth: 96, textAlign: 'right' }}>{rub(e.total)}</span>
                  </span>
                ))}
                <span style={{ display: 'flex', alignItems: 'baseline', gap: 12, paddingTop: 7 }}>
                  <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Итого доп. услуги · входят в сумму сделки</span>
                  <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: 'var(--income)' }}>{rub(extrasTotal)}</span>
                </span>
                <span style={{ fontSize: 10, color: 'var(--text-faint)', lineHeight: 1.45 }}>{TPL_BONUS}</span>
              </div>

              {/* бриф · таргетинг (ШАБЛОН) */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 14, borderTop: '1px solid var(--border-card)' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
                  <span style={CAPS}>Бриф · таргетинг</span>
                  <span style={{ marginLeft: 'auto', ...SUBCAPS }}>шаблон</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 24px' }}>
                  {TPL_TARGETING.map((t, i) => (
                    <span key={i} style={{ display: 'flex', gap: 12, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
                      <span style={{ flex: '0 0 84px', fontFamily: MONO, fontSize: 9, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', lineHeight: 1.45 }}>{t.group}</span>
                      <span style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.45 }}>{t.value}</span>
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* правая: документы / ответственные / история */}
            <div style={{ width: '25%', flex: '0 0 25%', minWidth: 260, ...CARD, padding: '20px 22px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
              {/* документы (ШАБЛОН) */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={CAPS}>Документы</span>
                <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 10, fontWeight: 700, color: 'var(--accent)' }}>{TPL_DOCS.filter(x => x[2]).length} из {TPL_DOCS.length}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {TPL_DOCS.map(([kind, meta, ok, action], i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 9, background: ok ? 'var(--bg-card)' : '#FBFCFE', border: `1px solid ${ok ? 'var(--border-card)' : 'var(--border-inner)'}`, borderRadius: 11, padding: '9px 10px', minWidth: 0, cursor: 'pointer' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, borderRadius: 7, background: ok ? 'var(--accent-tint)' : 'var(--bg-subtle)', color: ok ? 'var(--accent)' : '#C3C9D8', flex: '0 0 22px' }}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>
                    </span>
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                      <span style={{ fontSize: 11.5, fontWeight: 700, color: ok ? 'var(--text-primary)' : 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{kind}</span>
                      <span style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{meta}</span>
                    </span>
                    <span style={{ marginLeft: 'auto', fontSize: 10.5, fontWeight: 600, color: ok ? 'var(--accent)' : 'var(--text-faint)', whiteSpace: 'nowrap' }}>{action}</span>
                  </div>
                ))}
              </div>

              {/* ответственные */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 9, paddingTop: 12, borderTop: '1px solid var(--border-card)' }}>
                <span style={CAPS}>Ответственные</span>
                {team.map((t, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: 10, background: t.bg, color: t.fg, fontSize: 12, fontWeight: 700, flex: '0 0 32px' }}>{initials(t.name)}</span>
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: t.name ? 'var(--text-primary)' : 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.name || '—'}</span>
                      <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{t.role}</span>
                    </span>
                  </div>
                ))}
              </div>

              {/* история (реальная — audit_log) */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 12, borderTop: '1px solid var(--border-card)' }}>
                <span style={CAPS}>История</span>
                {history.length ? history.map((h, i) => (
                  <div key={i} style={{ display: 'flex', gap: 9, padding: '6px 0', borderTop: '1px solid var(--border-row)' }}>
                    <span style={{ width: 7, height: 7, borderRadius: 2, background: EVENT_COLOR[h.action] || 'var(--text-faint)', flex: '0 0 7px', marginTop: 5 }} />
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                      <span style={{ fontSize: 11.5, fontWeight: 600, lineHeight: 1.35 }}>{h.label}{h.details ? <span style={{ fontWeight: 400, color: 'var(--text-secondary)' }}> · {h.details}</span> : ''}</span>
                      <span style={{ fontFamily: MONO, fontSize: 9, color: 'var(--text-faint)' }}>{fmtWhen(h.at)}{h.who ? ` · ${h.who}` : ''}</span>
                    </span>
                  </div>
                )) : <div style={{ fontSize: 11, color: 'var(--text-faint)', padding: '4px 0' }}>Событий в журнале пока нет.</div>}
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, paddingTop: 8, borderTop: '1px solid var(--border-row)' }}>
                  <input placeholder="Комментарий…" disabled style={{ flex: 1, minWidth: 0, height: 30, boxSizing: 'border-box', padding: '0 10px', background: 'var(--bg-subtle)', border: '1px solid var(--border-card)', borderRadius: 9, fontFamily: UI, fontSize: 11.5, outline: 'none' }} />
                  <span title="скоро" style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 11px', background: 'var(--accent)', color: '#fff', borderRadius: 9, fontSize: 11, fontWeight: 700, opacity: 0.6 }}>→</span>
                </div>
              </div>
            </div>
          </div>

          {/* ряд ссылок */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', padding: '0 6px' }}>
            {links.map((l, i) => (
              l.href
                ? <a key={i} href={l.href} target={l.href.startsWith('http') ? '_blank' : undefined} rel="noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}><span style={{ width: 7, height: 7, borderRadius: 2, background: l.dot }} />{l.name}</a>
                : <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 600, color: 'var(--text-faint)' }}><span style={{ width: 7, height: 7, borderRadius: 2, background: l.dot }} />{l.name}</span>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
